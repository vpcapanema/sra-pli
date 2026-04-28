"""Exporta HTML e texto plano dos e-mails de notificação para ``tmp/``.

Usa o mesmo contexto do preview sem BD: sumário completo ``SECOES_PADRAO``.

Uso::

    .\\.venv\\Scripts\\python.exe scripts/export_tmp_email_previews.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.notificacoes.email_sender import preview_corpo_notificacao  # noqa: E402
from app.routes.dev_ui import contexto_email_sumario_padrao  # noqa: E402


def main() -> None:
    ctx = contexto_email_sumario_padrao("Autor exemplo")
    tmp = ROOT / "tmp"
    tmp.mkdir(exist_ok=True)
    for tipo in ("abertura", "lembrete"):
        html, texto = preview_corpo_notificacao(tipo, ctx)
        (tmp / f"email_preview_{tipo}.html").write_text(html, encoding="utf-8")
        (tmp / f"email_preview_{tipo}.txt").write_text(texto, encoding="utf-8")
    print(
        "Gravado: tmp/email_preview_abertura.html, .txt e "
        "tmp/email_preview_lembrete.html, .txt"
    )


if __name__ == "__main__":
    main()
