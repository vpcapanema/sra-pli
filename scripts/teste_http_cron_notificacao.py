"""Teste prático dos endpoints HTTP do ciclo mensal (equivalente ao cron às 03:00 BRT).

O job agendado no Render (ou cron-job.org) chama o mesmo contrato que estes POST
(com ``force=false`` — idempotente):

  POST {APP_BASE_URL}/admin/cron/abrir-periodo?force=false
  Header: X-Cron-Token: {CRON_TOKEN}

**Este script** usa por padrão ``force=true`` ao chamar ``abrir-periodo`` (cria
de novo mesmo se o mês já existir — laboratório). Use ``--no-force`` para imitar
produção.

Comportamento real de ``abrir_periodo`` (ver ``app/notificacoes/service.py``):

- Cria o relatório do mês clonando o último (idealmente ``finalizado``) e
  **zera** ``responsavel_id`` nas seções clonadas.
- Na **mesma** chamada envia Mensagem 1 (abertura) a **todos** os ``autor`` com
  ``notificacoes_ativas`` (não exige secção atribuída). ``emails_enviados`` pode
  ser 0 se ninguém cumprir esse critério, se o mês já existir (idempotência), ou
  se ``NOTIFICAR_HABILITADO=False`` (kill switch → tentativas falham).
- ``POST /admin/cron/notificar-autores-abertura?relatorio_id=N`` só é necessário
  para quem **ainda não** recebeu abertura com sucesso (reenvio / após falha).

Modos:

  # Só HTTP (servidor tem de estar no ar; lê .env na raiz do repo se existir)
  .\\.venv\\Scripts\\python.exe scripts/teste_http_cron_notificacao.py --http

  # Mesma lógica dos endpoints, no processo atual (sem uvicorn nem httpx)
  .\\.venv\\Scripts\\python.exe scripts/teste_http_cron_notificacao.py --in-process

  # Após abrir-periodo, atribui a 1ª seção folheada ao 1º user role=autor e chama notificar
  .\\.venv\\Scripts\\python.exe scripts/teste_http_cron_notificacao.py --in-process --cadeia-atribuir

  # Igual ao cron real (não duplica mês se já existir)
  .\\.venv\\Scripts\\python.exe scripts/teste_http_cron_notificacao.py --in-process --no-force

Requisitos:

- ``CRON_TOKEN`` não vazio (senão os endpoints respondem 503/401).
- ``--http``: ``APP_BASE_URL`` apontando para a instância (ex.: http://127.0.0.1:8001).
- ``--in-process`` / ``--cadeia-atribuir``: ``DATABASE_URL`` e resto do ``.env`` como no app.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env_file() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _post_json(url: str, token: str, timeout: float = 120.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-Cron-Token": token,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"raw": raw}
        return e.code, detail


def _run_http(base: str, token: str, force: bool) -> int:
    base = base.rstrip("/")
    q = f"{base}/admin/cron/abrir-periodo?force={'true' if force else 'false'}"
    print(f"POST {q}")
    status, data = _post_json(q, token)
    print(f"status={status}")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    if status not in (200, 201):
        return 1
    return 0


def _atribuir_primeira_secao_livre(rel_id: int) -> bool:
    from app.db import SessionLocal
    from app.models import Secao, User

    with SessionLocal() as db:
        autor = (
            db.query(User)
            .filter(User.role == "autor")
            .order_by(User.id)
            .first()
        )
        if not autor:
            print("Nenhum user com role=autor no banco.", file=sys.stderr)
            return False
        sec = (
            db.query(Secao)
            .filter(Secao.relatorio_id == rel_id, Secao.responsavel_id.is_(None))
            .order_by(Secao.ordem)
            .first()
        )
        if not sec:
            print(
                "Nenhuma seção sem responsável neste relatório.",
                file=sys.stderr,
            )
            return False
        sec.responsavel_id = autor.id
        if not autor.notificacoes_ativas:
            autor.notificacoes_ativas = True
        db.commit()
        print(
            f"\n[cadeia] secao id={sec.id} ({sec.numero}) -> "
            f"autor id={autor.id} ({autor.email})"
        )
    return True


def _run_in_process(  # pylint: disable=too-many-return-statements
    force: bool,
    cadeia_atribuir: bool,
    notificar_only_id: int | None,
) -> int:
    """Replica o corpo de ``cron_admin`` sem ASGI (evita dependência ``httpx``)."""
    from dataclasses import asdict

    _load_env_file()
    from app.config import settings
    from app.db import SessionLocal
    from app.notificacoes.service import abrir_periodo, notificar_autores_abertura
    if not settings.CRON_TOKEN:
        print("ERRO: CRON_TOKEN vazio no ambiente / .env.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if notificar_only_id is not None:
            print("notificar_autores_abertura (serviço, mesmo retorno JSON da rota)")
            out = asdict(notificar_autores_abertura(db, notificar_only_id))
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        print("abrir_periodo (serviço, mesmo retorno JSON da rota)")
        resumo = abrir_periodo(db, force=force)
        body = asdict(resumo)
        print(json.dumps(body, indent=2, ensure_ascii=False))

    rel_id = body.get("relatorio_id")
    if not cadeia_atribuir:
        print(
            "\nNota: sem --cadeia-atribuir, não chama ``notificar_autores_abertura`` "
            "de novo (a abertura já foi tentada dentro de ``abrir_periodo``). "
            "Se ``emails_enviados`` veio 0, veja ``avisos`` no JSON e "
            "``NOTIFICAR_*`` / modo sandbox no ``.env``."
        )
        return 0
    if not rel_id:
        print("Sem relatorio_id na resposta.", file=sys.stderr)
        return 1
    if not _atribuir_primeira_secao_livre(rel_id):
        return 1
    print("\nnotificar_autores_abertura (serviço, após atribuir)")
    with SessionLocal() as db:
        out2 = asdict(notificar_autores_abertura(db, rel_id))
        print(json.dumps(out2, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    _load_env_file()
    p = argparse.ArgumentParser(description="Teste HTTP /admin/cron (ciclo mensal)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--http", action="store_true", help="Chama APP_BASE_URL via urllib")
    g.add_argument(
        "--in-process",
        action="store_true",
        help="Chama o serviço no processo atual (precisa DATABASE_URL; sem uvicorn)",
    )
    p.add_argument(
        "--no-force",
        action="store_true",
        help="abrir-periodo com force=false (igual produção; não duplica o mês)",
    )
    p.add_argument(
        "--cadeia-atribuir",
        action="store_true",
        help="Só com --in-process: após abrir, atribui 1 seção a 1 autor e chama notificar",
    )
    p.add_argument(
        "--notificar-apenas",
        type=int,
        metavar="REL_ID",
        default=0,
        help="Só com --in-process: pula abrir-periodo; chama só notificar-autores-abertura",
    )
    args = p.parse_args()

    token = os.environ.get("CRON_TOKEN", "").strip()
    if not token:
        print("ERRO: defina CRON_TOKEN no ambiente ou no .env", file=sys.stderr)
        return 1

    forcar = not args.no_force

    if args.http:
        base = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8001").strip()
        return _run_http(base, token, forcar)

    n_id = args.notificar_apenas or None
    if n_id and args.cadeia_atribuir:
        print("Use só um de --notificar-apenas ou --cadeia-atribuir.", file=sys.stderr)
        return 1
    return _run_in_process(
        force=forcar,
        cadeia_atribuir=args.cadeia_atribuir,
        notificar_only_id=n_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
