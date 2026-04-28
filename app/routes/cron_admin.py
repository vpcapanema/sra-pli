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

from dataclasses import asdict

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..notificacoes.service import (
    abrir_periodo,
    enviar_lembretes,
    notificar_autores_abertura,
    retry_falhas,
)

router = APIRouter(prefix="/admin/cron")


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
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
    return asdict(
        enviar_lembretes(db, tipo=tipo, relatorio_id=relatorio_id)
    )


@router.post("/retry")
def http_retry(
    db: Session = Depends(get_db),
    _t: None = Depends(_check_token),
):
    return asdict(retry_falhas(db))
