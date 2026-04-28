"""Smoke test do envio de email via SendGrid.

Uso:

    .\\.venv\\Scripts\\python.exe scripts/smoke_email.py destino@exemplo.com

Renderiza um payload mínimo do template `abertura` e tenta enviar usando as
variáveis de ambiente atuais. Reporta o modo (`real`/`sandbox`/`desligado`),
o ``message_id`` (real ou sintético), e qualquer erro retornado pelo SendGrid.

Para evidenciar exatamente o que acontece, force os modos via ambiente antes
de rodar. Ex (PowerShell):

    $env:NOTIFICAR_HABILITADO='true'; $env:NOTIFICAR_SANDBOX='true'
    .\\.venv\\Scripts\\python.exe scripts/smoke_email.py voce@exemplo.com

    $env:NOTIFICAR_SANDBOX='false'
    .\\.venv\\Scripts\\python.exe scripts/smoke_email.py voce@exemplo.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.notificacoes.email_sender import (  # noqa: E402
    enviar_notificacao,
    modo_atual,
)
from app.notificacoes.email_context_arvore import (  # noqa: E402
    format_arvore_secoes_email_plaintext,
)


def _contexto_minimo(destinatario_nome: str) -> dict:
    arvore = [
        {
            "numero": "4.1",
            "titulo": "Seção de teste (smoke)",
            "link_upload": (
                "http://127.0.0.1:8001/relatorios/0/secoes/0/upload-conteudo"
            ),
            "link_dotx": (
                "http://127.0.0.1:8001/relatorios/0/secoes/0/modelo.dotx"
            ),
            "filhos": [],
        },
    ]
    return {
        "destinatario_nome": destinatario_nome,
        "relatorio_codigo": "D20-SMOKE",
        "mes_referencia": "Abril/2026",
        "prazo_envio": "10/05/2026 23:59",
        "prazo_limite_conteudo_autor": "08/05/2026 23:59",
        "link_relatorio_painel": "http://127.0.0.1:8001/relatorios/0",
        "link_modelos_word_ajuda": "http://127.0.0.1:8001/modelos-word-importacao",
        "link_login_sra": "http://127.0.0.1:8001/login",
        "link_painel_upload": "http://127.0.0.1:8001/painel-upload",
        "arvore_secoes_links": arvore,
        "arvore_modelos_dotx_texto": format_arvore_secoes_email_plaintext(
            arvore, apenas_dotx=True
        ),
        "minhas_secoes": [
            {
                "numero": "4.1",
                "titulo": "Seção de teste (smoke)",
                "contexto": "4 - Atividades do Período",
                "link_upload": (
                    "http://127.0.0.1:8001/relatorios/0/secoes/0/upload-conteudo"
                ),
                "link_dotx": (
                    "http://127.0.0.1:8001/relatorios/0/secoes/0/modelo.dotx"
                ),
            },
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke test do envio de email")
    p.add_argument("destinatario", help="email de destino")
    p.add_argument(
        "--nome",
        default="Vinícius (smoke)",
        help="nome do destinatário (default: Vinícius (smoke))",
    )
    p.add_argument(
        "--tipo",
        default="abertura",
        choices=["abertura", "lembrete", "ultima_chamada", "manual"],
        help="tipo de mensagem (default: abertura)",
    )
    args = p.parse_args()

    print(f"[modo] {modo_atual()}")
    res = enviar_notificacao(
        destinatario_email=args.destinatario,
        destinatario_nome=args.nome,
        tipo=args.tipo,
        contexto=_contexto_minimo(args.nome),
    )
    print(f"[resultado] modo={res.modo} sucesso={res.sucesso}")
    print(f"[message_id] {res.message_id}")
    if res.erro:
        print(f"[erro] {res.erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
