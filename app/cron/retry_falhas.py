"""CLI: reenvia notificações falhadas (até 3 tentativas / 7 dias).

Uso (PowerShell):

  .\\.venv\\Scripts\\python.exe -m app.cron.retry_falhas

Schedule sugerida (Render Cron): ``*/30 * * * *`` (a cada 30 min).
"""
from __future__ import annotations

import logging
import sys

from ..db import SessionLocal
from ..notificacoes.service import agora_brt, retry_falhas

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app.cron.retry_falhas")


def main(_argv: list[str] | None = None) -> int:
    log.info("[retry] start now_brt=%s", agora_brt())
    with SessionLocal() as db:
        resumo = retry_falhas(db)
    log.info(
        "[retry] done tentativas=%d sucessos=%d falhas=%d desistencias=%d",
        resumo.tentativas, resumo.sucessos, resumo.falhas, resumo.desistencias,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
