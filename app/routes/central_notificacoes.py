from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.central_notificacoes.contexto_pagina import (
    central_notificacoes_page,
    central_salvar_parametros_ciclo,
    central_ativar_defcon,
    central_desativar_defcon,
    central_enviar_email,
)
from ..services import governanca_relatorio
from ..services.pages import templates

router = APIRouter(tags=["central_notificacoes"])


@router.get("/central-notificacoes")
def central_notificacoes_page_route(request: Request, db: Session = Depends(get_db)):
    try:
        resultado = central_notificacoes_page(request, db)
        if hasattr(resultado, "status_code"):
            return resultado
        return templates.TemplateResponse(
            request,
            "central_notificacoes.html",
            resultado,
        )
    except Exception as e:
        import traceback
        print("Erro ao renderizar central_notificacoes:")
        print(traceback.format_exc())
        raise


@router.post("/central-notificacoes/parametros-ciclo")
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def central_salvar_parametros_ciclo_route(
    request: Request,
    db: Session = Depends(get_db),
    ciclo_dia_prev: str = Form(""),
    ciclo_dia_atual: str = Form(""),
    prazo_autor: str = Form(""),
    prazo_coord: str = Form(""),
    dias_lembrete_csv: str = Form(""),
    dia_ultima: str = Form(""),
    dia_abertura: str = Form(""),
    hora_aber: str = Form(""),
    hora_lem: str = Form(""),
    hora_ret: str = Form(""),
    observacoes: str = Form(""),
):
    return central_salvar_parametros_ciclo(
        request,
        db,
        ciclo_dia_prev=ciclo_dia_prev,
        ciclo_dia_atual=ciclo_dia_atual,
        prazo_autor=prazo_autor,
        prazo_coord=prazo_coord,
        dias_lembrete_csv=dias_lembrete_csv,
        dia_ultima=dia_ultima,
        dia_abertura=dia_abertura,
        hora_aber=hora_aber,
        hora_lem=hora_lem,
        hora_ret=hora_ret,
        observacoes=observacoes,
    )


@router.post("/central-notificacoes/defcon-ativar")
def central_ativar_defcon_route(request: Request, db: Session = Depends(get_db)):
    return central_ativar_defcon(request, db)


@router.post("/central-notificacoes/defcon-desativar")
def central_desativar_defcon_route(request: Request, db: Session = Depends(get_db)):
    return central_desativar_defcon(request, db)


@router.post("/central-notificacoes/enviar-email")
def central_enviar_email_route(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str = Form(""),
    assunto: str = Form(""),
    corpo: str = Form(""),
    relatorio_id: str = Form(""),
    destinatarios: list = Form([]),
    agendar: str = Form("agora"),
    data_agendada: str = Form(""),
):
    return central_enviar_email(
        request,
        db,
        tipo=tipo,
        assunto=assunto,
        corpo=corpo,
        relatorio_id=relatorio_id,
        destinatarios=destinatarios,
        agendar=agendar,
        data_agendada=data_agendada,
    )


@router.post("/central-notificacoes/testar/abrir-periodo")
def central_testar_abrir_periodo_route(
    request: Request,
    db: Session = Depends(get_db),
    base_relatorio_id: str = Form(""),
    force: str = Form("1"),
):
    return governanca_relatorio.governanca_testar_abrir_periodo(
        request,
        db,
        base_relatorio_id=base_relatorio_id,
        force=force,
        redirect_base="/central-notificacoes",
    )


@router.post("/central-notificacoes/testar/notificar")
def central_testar_notificar_route(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str = Form(...),
    relatorio_id: int = Form(...),
):
    return governanca_relatorio.governanca_testar_notificar(
        request,
        db,
        tipo=tipo,
        relatorio_id=relatorio_id,
        redirect_base="/central-notificacoes",
    )


@router.post("/central-notificacoes/testar/retry")
def central_testar_retry_route(request: Request, db: Session = Depends(get_db)):
    return governanca_relatorio.governanca_testar_retry(
        request, db, redirect_base="/central-notificacoes"
    )
