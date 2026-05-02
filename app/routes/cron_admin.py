"""Endpoints HTTP token-protegidos equivalentes aos jobs CLI.

Permite invocar abrir_periodo / enviar_lembretes / retry_falhas a partir de
um cron externo (cron-job.org, etc.) ou via curl manual quando o ambiente
não tem Render Cron habilitado.

Autenticação: header ``X-Cron-Token`` deve bater com ``settings.CRON_TOKEN``.
Token vazio rejeita qualquer chamada (fail-closed). Em produção use string
≥32 chars aleatória.

Estes endpoints **não** redirecionam para login: 401 estruturado em JSON.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..notificacoes.service import (
    abrir_periodo,
    enviar_lembretes,
    notificar_autores_abertura,
    retry_falhas,
)

router = APIRouter(prefix="/admin/cron")
log = logging.getLogger(__name__)


def _check_token(
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


@router.post("/abrir-periodo")
def http_abrir_periodo(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
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


@router.post("/abrir-periodo-background")
def http_abrir_periodo_background(
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
    _t: None = Depends(_check_token),
):
    """Agenda a abertura em background e responde rápido ao cron HTTP.

    O cron-job.org encerra chamadas longas por volta de 30s. A abertura mensal
    pode demorar mais quando clona conteúdo e envia e-mails, então este endpoint
    evita falso negativo do cron sem mudar a rotina de negócio.
    """
    background_tasks.add_task(_abrir_periodo_background, force)
    return {"accepted": True, "job": "abrir_periodo", "force": force}


@router.post("/notificar-autores-abertura")
def http_notificar_autores_abertura(
    relatorio_id: int = Query(...),
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
    return asdict(notificar_autores_abertura(db, relatorio_id))


@router.post("/lembretes")
def http_lembretes(
    tipo: str = Query("lembrete"),
    relatorio_id: int | None = Query(None),
    ignorar_calendario: bool = Query(False),
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
    return asdict(
        enviar_lembretes(
            db,
            tipo=tipo,
            relatorio_id=relatorio_id,
            ignorar_calendario=ignorar_calendario,
        )
    )


@router.post("/retry")
def http_retry(
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
    return asdict(retry_falhas(db))
