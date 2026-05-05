"""Endpoints HTTP token-protegidos equivalentes aos jobs CLI.

Lógica das rotas em ``app/routes/cron_admin.py``. Autenticação via header
``X-Cron-Token`` (comparação em tempo constante). 401 em JSON (sem redirect).
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import BackgroundTasks, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..notificacoes.service import (
    abrir_periodo,
    enviar_lembretes,
    notificar_autores_abertura,
    retry_falhas,
)

log = logging.getLogger(__name__)


def check_token(
    x_cron_token: str | None = Header(default=None, alias="X-Cron-Token"),
) -> None:
    """Compara em tempo constante (evita timing attack). Token vazio = fail."""
    expected = settings.CRON_TOKEN or ""
    received = x_cron_token or ""
    if not expected:
        raise HTTPException(503, detail="CRON_TOKEN não configurado.")
    if len(expected) != len(received):
        raise HTTPException(401, detail="X-Cron-Token inválido.")
    diff = 0
    for a, b in zip(expected, received):
        diff |= ord(a) ^ ord(b)
    if diff != 0:
        raise HTTPException(401, detail="X-Cron-Token inválido.")


def http_abrir_periodo(force: bool, db: Session):
    return asdict(abrir_periodo(db, force=force))


def _abrir_periodo_background(force: bool) -> None:
    """Executa abertura em sessão própria após resposta rápida ao cron externo."""
    db = SessionLocal()
    try:
        resumo = abrir_periodo(db, force=force)
        log.info("[cron/bg/abrir-periodo] done %s", asdict(resumo))
    except Exception:  # noqa: BLE001
        log.exception("[cron/bg/abrir-periodo] falhou")
    finally:
        db.close()


def http_abrir_periodo_background(
    background_tasks: BackgroundTasks, force: bool
):
    """Agenda a abertura em background e responde rápido ao cron HTTP.

    O cron-job.org encerra chamadas longas por volta de 30s. A abertura mensal
    pode demorar mais quando clona conteúdo e envia e-mails, então este
    endpoint evita falso negativo do cron sem mudar a rotina de negócio.
    """
    background_tasks.add_task(_abrir_periodo_background, force)
    return {"accepted": True, "job": "abrir_periodo", "force": force}


def http_notificar_autores_abertura(
    relatorio_id: int, force: bool, db: Session
):
    """``force=true`` força reenvio mesmo a quem já recebeu — espelha o botão
    assistido do coordenador. Padrão é idempotente (cron seguro)."""
    return asdict(notificar_autores_abertura(db, relatorio_id, force=force))


def http_lembretes(
    tipo: str,
    relatorio_id: int | None,
    ignorar_calendario: bool,
    db: Session,
):
    return asdict(
        enviar_lembretes(
            db,
            tipo=tipo,
            relatorio_id=relatorio_id,
            ignorar_calendario=ignorar_calendario,
        )
    )


def http_retry(db: Session):
    return asdict(retry_falhas(db))
