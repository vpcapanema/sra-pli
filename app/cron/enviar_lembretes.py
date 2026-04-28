"""CLI: envia Mensagem 2 (lembrete ou última chamada) para entregas pendentes.

Uso (PowerShell):

  .\\.venv\\Scripts\\python.exe -m app.cron.enviar_lembretes --tipo lembrete
  .\\.venv\\Scripts\\python.exe -m app.cron.enviar_lembretes --tipo ultima_chamada

Schedule sugerida (Render Cron, UTC):
- ``0 12 5 * *``  → 09:00 BRT, dia 5  (lembrete)
- ``0 12 8 * *``  → 09:00 BRT, dia 8  (lembrete)
- ``0 12 10 * *`` → 09:00 BRT, dia 10 (ultima_chamada)
"""
from __future__ import annotations

import argparse
import logging
import sys

from ..db import SessionLocal
from ..notificacoes.service import agora_brt, enviar_lembretes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("app.cron.enviar_lembretes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envia Mensagem 2 para pendentes.")
    parser.add_argument(
        "--tipo", choices=("lembrete", "ultima_chamada"), default="lembrete",
    )
    parser.add_argument(
        "--relatorio-id", type=int, default=None,
        help="Restringe a um relatório específico (uso manual).",
    )
    args = parser.parse_args(argv)
    log.info("[lembretes] start now_brt=%s tipo=%s rel=%s",
             agora_brt(), args.tipo, args.relatorio_id)
    with SessionLocal() as db:
        resumo = enviar_lembretes(
            db, tipo=args.tipo, relatorio_id=args.relatorio_id,
        )
    log.info(
        "[lembretes] done tipo=%s rel_proc=%d env=%d fal=%d pul_int=%d",
        resumo.tipo, resumo.relatorios_processados,
        resumo.emails_enviados, resumo.emails_falhados,
        resumo.pulados_intervalo,
    )
    for a in resumo.avisos:
        log.warning("[lembretes] aviso: %s", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
