"""CLI: abre o relatório do mês corrente e dispara Mensagem 1.

Uso (PowerShell):

  .\\.venv\\Scripts\\python.exe -m app.cron.abrir_periodo
  .\\.venv\\Scripts\\python.exe -m app.cron.abrir_periodo --force

Configurar no Render Cron com schedule ``0 6 1 * *`` (06:00 UTC = 03:00 BRT).
"""
from __future__ import annotations

import argparse
import logging
import sys

from ..db import SessionLocal
from ..notificacoes.service import abrir_periodo, agora_brt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app.cron.abrir_periodo")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Abre o relatório do mês corrente.")
    parser.add_argument(
        "--force", action="store_true",
        help="Cria mesmo se já existir relatório do mês.",
    )
    args = parser.parse_args(argv)
    log.info("[abrir_periodo] start now_brt=%s force=%s", agora_brt(), args.force)
    with SessionLocal() as db:
        resumo = abrir_periodo(db, force=args.force)
    log.info(
        "[abrir_periodo] done rel=%s criou=%s entregas=%d env=%d fal=%d "
        "pulada=%s avisos=%d",
        resumo.relatorio_codigo, resumo.criou_relatorio,
        resumo.entregas_criadas, resumo.emails_enviados,
        resumo.emails_falhados, resumo.pulada_idempotencia, len(resumo.avisos),
    )
    for a in resumo.avisos:
        log.warning("[abrir_periodo] aviso: %s", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
