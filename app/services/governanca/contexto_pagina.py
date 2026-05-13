"""Montagem do contexto Jinja da página de governança."""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote_plus

from fastapi import Request
from sqlalchemy.orm import Session, joinedload

from ...models import ENTREGA_STATUS_VALIDOS, EntregaRelatorio, Relatorio, User
from ...notificacoes.email_sender import modo_atual
from ...services.entregas.lista_painel import montar_lista_entregas
from .consultas_painel import (
    LIMITE_ENTREGAS,
    LIMITE_NOTIFICACOES,
    carregar_listas_governanca,
    relatorio_filtro_id,
)
from .datas_horarios import (
    formatar_datetime_input_sao_paulo,
    formatar_datetime_sao_paulo,
)
from .execucao_manual_jobs import RESULTADO_TESTE_SESS_KEY
from .status_jobs_cron import cron_status_real
from .status_notificacoes_ciclo import ciclo_execucao_rows


def montar_contexto_governanca(request: Request, db: Session, user: User) -> dict[str, Any]:
    erro_raw = request.query_params.get("erro")
    relatorio_id = relatorio_filtro_id(request, db)
    listas = carregar_listas_governanca(db, relatorio_id=relatorio_id)
    resultado_teste = request.session.pop(RESULTADO_TESTE_SESS_KEY, None)
    cron_status = cron_status_real()
    relatorio_filtro = next((rel for rel in listas[5] if rel.id == relatorio_id), None)
    entregas_ciclo = _entregas_ciclo(db, relatorio_id)
    lista_entregas_linhas, lista_entregas_pode_acoes = _carregar_lista_entregas(
        db, relatorio_filtro, user
    )
    return {
        "user": user,
        "ciclo_row": listas[0],
        "entregas": listas[1],
        "notificacoes": listas[2],
        "usuarios_gov": listas[3],
        "autores_lista": listas[4],
        "relatorios_filtro": listas[5],
        "relatorio_filtro_id": relatorio_id,
        "relatorios_abertos": listas[6],
        "ciclo_execucao_rows": ciclo_execucao_rows(
            cron_status,
            relatorio_filtro,
            listas[4],
            entregas_ciclo,
        ),
        "entrega_status_ops": ENTREGA_STATUS_VALIDOS,
        "modo_envio": modo_atual(),
        "fmt_dt_sp": formatar_datetime_sao_paulo,
        "fmt_dt_input_sp": formatar_datetime_input_sao_paulo,
        "formatar_datetime_sao_paulo": formatar_datetime_sao_paulo,
        "formatar_datetime_input_sao_paulo": formatar_datetime_input_sao_paulo,
        "resultado_teste": resultado_teste,
        "ok": request.query_params.get("ok"),
        "erro": unquote_plus(erro_raw) if erro_raw else None,
        "limite_entregas": LIMITE_ENTREGAS,
        "limite_notifs": LIMITE_NOTIFICACOES,
        "lista_entregas_linhas": lista_entregas_linhas,
        "lista_entregas_pode_acoes": lista_entregas_pode_acoes,
        "lista_entregas_rel": relatorio_filtro,
    }


def _carregar_lista_entregas(
    db: Session, rel: Relatorio | None, viewer: User
) -> tuple[list[dict[str, Any]], bool]:
    """Mesma fonte do painel /relatorios/{id}/entregas. Sem relatório no filtro,
    a lista vem vazia (o template mostra estado neutro)."""
    if rel is None:
        return [], False
    return montar_lista_entregas(db, rel, viewer)


def _entregas_ciclo(db: Session, relatorio_id: int | None) -> list[EntregaRelatorio]:
    if relatorio_id is None:
        return []
    return (
        db.query(EntregaRelatorio)
        .options(joinedload(EntregaRelatorio.notificacoes))
        .filter(EntregaRelatorio.relatorio_id == relatorio_id)
        .all()
    )
