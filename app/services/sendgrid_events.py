"""Recebe eventos do SendGrid para distinguir aceite, entrega e abertura.

Lógica das rotas em ``app/routes/sendgrid_events.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..models import NotificacaoEnvio

_EVENTOS_FALHA = {"bounce", "dropped", "spamreport", "blocked"}
_EVENTOS_ENTREGA = {"delivered", "open"}
_EVENTOS_SENDGRID = _EVENTOS_FALHA | _EVENTOS_ENTREGA | {"processed", "deferred"}
_PRIORIDADE_EVENTO = {
    "processed": 1,
    "deferred": 1,
    "delivered": 2,
    "open": 3,
    "bounce": 4,
    "dropped": 4,
    "spamreport": 4,
    "blocked": 4,
}


def check_sendgrid_token(
    token: str = Query(""),
    x_sendgrid_webhook_token: str | None = Header(
        default=None,
        alias="X-SendGrid-Webhook-Token",
    ),
) -> None:
    expected = settings.SENDGRID_EVENT_WEBHOOK_TOKEN or ""
    received = token or x_sendgrid_webhook_token or ""
    if not expected:
        raise HTTPException(
            503, detail="SENDGRID_EVENT_WEBHOOK_TOKEN não configurado."
        )
    if len(expected) != len(received):
        raise HTTPException(401, detail="Token do webhook inválido.")
    diff = 0
    for a, b in zip(expected, received):
        diff |= ord(a) ^ ord(b)
    if diff != 0:
        raise HTTPException(401, detail="Token do webhook inválido.")


def _event_dt(evento: dict[str, Any]) -> datetime:
    ts = evento.get("timestamp")
    if isinstance(ts, (int, float)):
        return datetime.utcfromtimestamp(ts)
    return datetime.utcnow()


def _motivo_evento(evento: dict[str, Any]) -> str | None:
    return (
        evento.get("reason")
        or evento.get("response")
        or evento.get("status")
        or evento.get("attempt")
    )


def _candidatos_message_id(evento: dict[str, Any]) -> list[str]:
    raw = str(evento.get("sg_message_id") or evento.get("message_id") or "").strip()
    candidatos = [raw] if raw else []
    if "." in raw:
        candidatos.append(raw.split(".", 1)[0])
    return list(dict.fromkeys(c for c in candidatos if c))


def _buscar_notificacao(
    db: Session, evento: dict[str, Any]
) -> NotificacaoEnvio | None:
    candidatos = _candidatos_message_id(evento)
    if not candidatos:
        return None
    row = (
        db.query(NotificacaoEnvio)
        .filter(NotificacaoEnvio.sendgrid_message_id.in_(candidatos))
        .order_by(NotificacaoEnvio.id.desc())
        .first()
    )
    if row is not None:
        return row
    raw = candidatos[0]
    rows = (
        db.query(NotificacaoEnvio)
        .filter(NotificacaoEnvio.sendgrid_message_id.isnot(None))
        .order_by(NotificacaoEnvio.id.desc())
        .limit(500)
        .all()
    )
    return next(
        (
            item
            for item in rows
            if raw.startswith(str(item.sendgrid_message_id) + ".")
        ),
        None,
    )


def _aplicar_evento(row: NotificacaoEnvio, evento: dict[str, Any]) -> bool:
    nome = str(evento.get("event") or "").strip().lower()
    if nome not in _EVENTOS_SENDGRID:
        return False
    quando = _event_dt(evento)
    atual = row.provedor_status or ""
    if _PRIORIDADE_EVENTO.get(atual, 0) > _PRIORIDADE_EVENTO[nome]:
        return False
    row.provedor_status = nome
    row.provedor_status_em = quando
    row.provedor_motivo = _motivo_evento(evento)
    if nome in _EVENTOS_FALHA:
        row.sucesso = False
        row.erro = row.provedor_motivo or f"Evento SendGrid: {nome}"
    elif nome in _EVENTOS_ENTREGA:
        row.sucesso = True
        row.erro = None
        if nome == "open" and row.aberto_em is None:
            row.aberto_em = quando
    return True


async def sendgrid_events(request: Request, db: Session):
    eventos = await request.json()
    if not isinstance(eventos, list):
        raise HTTPException(
            400, detail="Payload do SendGrid deve ser uma lista."
        )
    aplicados = 0
    ignorados = 0
    for evento in eventos:
        if not isinstance(evento, dict):
            ignorados += 1
            continue
        row = _buscar_notificacao(db, evento)
        if row is None or not _aplicar_evento(row, evento):
            ignorados += 1
            continue
        aplicados += 1
    db.commit()
    return {"ok": True, "aplicados": aplicados, "ignorados": ignorados}
