"""Teste PONTA A PONTA com dados reais do banco (não é smoke_email).

Usa as mesmas funções de produção: atribuição em ``Secao``, ``notificar_autores_abertura``,
templates Jinja e SendGrid conforme ``.env``.

Diferença do ``smoke_email.py``: o contexto do e-mail vem de ``_montar_contexto_email`` com
``Secao``/``Relatorio`` reais (números, títulos, links com ``APP_BASE_URL``).

Requisitos no ``.env``:
- ``DATABASE_URL``
- Para **entrega real** na caixa: ``SENDGRID_*``, ``NOTIFICAR_HABILITADO=true``,
  ``NOTIFICAR_SANDBOX=false``, ``APP_BASE_URL`` acessível ao destinatário.
- Com ``NOTIFICAR_SANDBOX=true`` o pipeline roda igual (``NotificacaoEnvio`` + entregas),
  mas o SMTP não entrega — ainda assim o HTML é o mesmo de produção.

Exemplos (PowerShell)::

    # Listar números de seção de um relatório
    .\\.venv\\Scripts\\python.exe scripts/teste_real_ciclo_notificacao.py --listar-secoes 22

    # Criar relatório do mês (data simulada) + atribuir seções + notificar um e-mail
    .\\.venv\\Scripts\\python.exe scripts/teste_real_ciclo_notificacao.py --confirmar \\
        --criar-periodo --data-referencia 2077-08-01 --force \\
        --usuario-email relatorio.atividades.pli@gmail.com \\
        --secoes 4.4.1 --zerar-demais --salvar-html .\\out_notif

    # Só notificar relatório já existente (seções já atribuídas ou use --secoes)
    .\\.venv\\Scripts\\python.exe scripts/teste_real_ciclo_notificacao.py --confirmar \\
        --relatorio-id 22 --usuario-email vinicius.capanema@concremat-transplan.com.br \\
        --usuario-role autor --secoes 4.4.1 --salvar-html .\\out_notif
"""
from __future__ import annotations

# pylint: disable=duplicate-code

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session, selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Relatorio, Secao, User  # noqa: E402
from app.notificacoes.email_sender import (  # noqa: E402
    modo_atual,
    preview_assunto_notificacao,
    preview_corpo_notificacao,
)
from app.notificacoes.service import (  # noqa: E402
    _montar_contexto_email,
    abrir_periodo,
    notificar_autores_abertura,
)


def _listar_secoes(db: Session, rel_id: int) -> None:
    secos = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id)
        .order_by(Secao.ordem)
        .all()
    )
    print(f"Relatório id={rel_id}: {len(secos)} seção(ões)")
    for s in secos:
        rid = s.responsavel_id or "—"
        print(f"  [{s.numero:8}] id={s.id:5} resp={rid} {s.titulo[:60]}")


def _parse_secoes(raw: str) -> set[str]:
    return {x.strip() for x in raw.split(",") if x.strip()}


def _atribuir_secoes(
    db: Session,
    rel: Relatorio,
    user: User,
    numeros: set[str],
    zerar_demais: bool,
) -> list[Secao]:
    secoes = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel.id)
        .order_by(Secao.ordem)
        .all()
    )
    encontrados = {s.numero for s in secoes}
    faltando = numeros - encontrados
    if faltando:
        raise SystemExit(f"Seções inexistentes neste relatório: {sorted(faltando)}")
    atualizadas: list[Secao] = []
    for s in secoes:
        if s.numero in numeros:
            s.responsavel_id = user.id
            atualizadas.append(s)
        elif zerar_demais:
            s.responsavel_id = None
    db.flush()
    return atualizadas


def main() -> int:  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    p = argparse.ArgumentParser(description="Teste real: DB + notificação (conteúdo real)")
    p.add_argument("--listar-secoes", type=int, metavar="REL_ID", default=0)
    p.add_argument("--criar-periodo", action="store_true")
    p.add_argument("--data-referencia", type=str, default="")
    p.add_argument("--force", action="store_true")
    p.add_argument("--relatorio-id", type=int, default=0)
    p.add_argument("--usuario-email", type=str, default="")
    p.add_argument(
        "--usuario-role",
        type=str,
        default="autor",
        choices=("admin", "coordenador", "autor"),
        help="Perfil do utilizador (unicidade no banco é e-mail + perfil).",
    )
    p.add_argument("--secoes", type=str, default="")
    p.add_argument("--zerar-demais", action="store_true")
    p.add_argument(
        "--confirmar",
        action="store_true",
        help="Obrigatório para gravar no banco e disparar notificação",
    )
    p.add_argument(
        "--salvar-html",
        type=str,
        default="",
        metavar="DIR",
        help=(
            "Grava preview_abertura_CODE.html e preview_abertura_CODE.txt "
            "(CODE=codigo do relatorio), mesmo corpo do envio"
        ),
    )
    args = p.parse_args()

    db = SessionLocal()
    try:
        if args.listar_secoes:
            _listar_secoes(db, args.listar_secoes)
            return 0

        if not args.confirmar:
            print(
                "Use --confirmar para executar gravações e envio. "
                "Nada foi alterado.",
                file=sys.stderr,
            )
            return 2

        if not args.usuario_email.strip():
            print("--usuario-email é obrigatório.", file=sys.stderr)
            return 2

        user = (
            db.query(User)
            .filter(
                User.email == args.usuario_email.strip().lower(),
                User.role == args.usuario_role,
            )
            .one_or_none()
        )
        if not user:
            print(
                f"Usuário não encontrado: {args.usuario_email} (perfil={args.usuario_role})",
                file=sys.stderr,
            )
            return 1

        rel_id: int | None = None
        if args.criar_periodo:
            dr = None
            if args.data_referencia.strip():
                dr = date.fromisoformat(args.data_referencia.strip())
            res = abrir_periodo(db, force=args.force, data_referencia=dr)
            print(
                f"abrir_periodo: criou={res.criou_relatorio} "
                f"id={res.relatorio_id} codigo={res.relatorio_codigo} "
                f"avisos={res.avisos}"
            )
            if not res.relatorio_id:
                print("Falha ao obter relatório.", file=sys.stderr)
                return 1
            rel_id = res.relatorio_id
        else:
            rel_id = args.relatorio_id or None
            if not rel_id:
                print(
                    "Informe --relatorio-id ou use --criar-periodo.", file=sys.stderr
                )
                return 2

        rel = db.get(Relatorio, rel_id)
        if not rel:
            print(f"Relatório id={rel_id} não encontrado.", file=sys.stderr)
            return 1

        if not args.secoes.strip():
            print("--secoes é obrigatório (ex.: 4.4.1,4.4.7).", file=sys.stderr)
            return 2

        nums = _parse_secoes(args.secoes)
        atualizadas = _atribuir_secoes(db, rel, user, nums, args.zerar_demais)
        db.commit()
        print(
            f"Atribuído responsável user_id={user.id} às seções: "
            f"{[s.numero for s in atualizadas]}"
        )
        if args.zerar_demais:
            print("Demais seções tiveram responsável removido neste relatório.")

        print(f"modo email: {modo_atual()} | APP_BASE_URL carregado da config")

        todas_map = {
            s.numero: s
            for s in db.query(Secao)
            .options(selectinload(Secao.responsavel))
            .filter(Secao.relatorio_id == rel.id)
            .all()
        }
        minhas = (
            db.query(Secao)
            .options(selectinload(Secao.responsavel))
            .filter(
                Secao.relatorio_id == rel.id,
                Secao.responsavel_id == user.id,
                Secao.numero.in_(nums),
            )
            .order_by(Secao.ordem)
            .all()
        )
        ctx = _montar_contexto_email(db, rel, user, minhas, todas_map)
        assunto = preview_assunto_notificacao("abertura", ctx)
        html, texto = preview_corpo_notificacao("abertura", ctx)
        print(f"Assunto (preview): {assunto}")
        print(f"HTML gerado: {len(html)} caracteres | texto: {len(texto)} caracteres")

        if args.salvar_html.strip():
            out = Path(args.salvar_html.strip())
            out.mkdir(parents=True, exist_ok=True)
            cod = rel.codigo.replace("/", "-")
            ha = out / f"preview_abertura_{cod}.html"
            ta = out / f"preview_abertura_{cod}.txt"
            ha.write_text(html, encoding="utf-8")
            ta.write_text(texto, encoding="utf-8")
            print(f"Gravado: {ha} e {ta}")

        resn = notificar_autores_abertura(db, rel.id)
        print(
            f"notificar_autores_abertura: emails_ok={resn.emails_enviados} "
            f"falhas={resn.emails_falhados} pulados={resn.pulados_ja_enviados} "
            f"avisos={resn.avisos}"
        )
        return 0 if resn.emails_falhados == 0 else 3
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
