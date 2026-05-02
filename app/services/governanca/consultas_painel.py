"""Consultas que alimentam tabelas e filtros da governança."""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session, joinedload

from ...models import (
    EntregaRelatorio,
    NotificacaoEnvio,
    ParametrosCicloNotificacao,
    Relatorio,
    User,
)

LIMITE_ENTREGAS = 250
LIMITE_NOTIFICACOES = 300


def ultimo_relatorio_id(db: Session) -> int | None:
    row = db.query(Relatorio.id).order_by(Relatorio.created_at.desc()).first()
    return int(row[0]) if row else None


def relatorio_filtro_id(request: Request, db: Session) -> int | None:
    raw = (request.query_params.get("relatorio_id") or "").strip()
    if raw:
        try:
            rel_id = int(raw)
        except ValueError:
            rel_id = None
        else:
            if db.get(Relatorio, rel_id) is not None:
                return rel_id
    return ultimo_relatorio_id(db)


def carregar_listas_governanca(
    db: Session,
    relatorio_id: int | None,
) -> tuple[
    ParametrosCicloNotificacao | None,
    list[EntregaRelatorio],
    list[NotificacaoEnvio],
    list[User],
    list[User],
    list[Relatorio],
    list[Relatorio],
]:
    ciclo = db.get(ParametrosCicloNotificacao, 1)
    entregas_q = db.query(EntregaRelatorio).options(
        joinedload(EntregaRelatorio.relatorio),
        joinedload(EntregaRelatorio.user),
        joinedload(EntregaRelatorio.validado_por),
        joinedload(EntregaRelatorio.atualizado_por),
    )
    if relatorio_id is not None:
        entregas_q = entregas_q.filter(EntregaRelatorio.relatorio_id == relatorio_id)
    entregas = entregas_q.order_by(EntregaRelatorio.id.desc()).limit(LIMITE_ENTREGAS).all()

    notifs_q = db.query(NotificacaoEnvio).options(
        joinedload(NotificacaoEnvio.entrega).joinedload(EntregaRelatorio.relatorio),
        joinedload(NotificacaoEnvio.entrega).joinedload(EntregaRelatorio.user),
    )
    if relatorio_id is not None:
        notifs_q = notifs_q.join(EntregaRelatorio).filter(
            EntregaRelatorio.relatorio_id == relatorio_id
        )
    notificacoes = notifs_q.order_by(NotificacaoEnvio.id.desc()).limit(
        LIMITE_NOTIFICACOES
    ).all()
    # Diretório completo de utilizadores (usado por seletores de validador na
    # tabela de Parciais de entrega) e subset de autores para o painel de ciclo.
    usuarios = db.query(User).order_by(User.nome).all()
    autores = [u for u in usuarios if u.role == "autor"]
    relatorios = db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    relatorios_abertos = (
        db.query(Relatorio)
        .filter(Relatorio.status.in_(("aberto", "em_revisao")))
        .order_by(Relatorio.created_at.desc())
        .all()
    )
    return ciclo, entregas, notificacoes, usuarios, autores, relatorios, relatorios_abertos
