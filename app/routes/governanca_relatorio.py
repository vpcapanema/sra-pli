from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import governanca_relatorio as governanca_relatorio_service

router = APIRouter(tags=["governanca"])


@router.get("/governanca-relatorio")
def governanca_relatorio_page(
    request: Request, db: Session = Depends(get_db)
):
    return governanca_relatorio_service.governanca_relatorio_page(request, db)


@router.post("/governanca-relatorio/parametros-ciclo")
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
def governanca_salvar_parametros_ciclo(
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
    return governanca_relatorio_service.governanca_salvar_parametros_ciclo(
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


@router.post("/governanca-relatorio/entrega/{entrega_id}")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def governanca_entrega_salvar(
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Form(...),
    data_envio: str = Form(""),
    data_validacao: str = Form(""),
    validado_por_id: str = Form(""),
    relatorio_filtro_id: str = Form(""),
):
    return governanca_relatorio_service.governanca_entrega_salvar(
        entrega_id,
        request,
        db,
        status=status,
        data_envio=data_envio,
        data_validacao=data_validacao,
        validado_por_id=validado_por_id,
        relatorio_filtro_id=relatorio_filtro_id,
    )


@router.post("/governanca-relatorio/usuario/{user_id}")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def governanca_usuario_salvar(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(...),
    role: str = Form(""),
    notificacoes_ativas: str = Form("1"),
):
    return governanca_relatorio_service.governanca_usuario_salvar(
        user_id,
        request,
        db,
        nome=nome,
        email=email,
        email2=email2,
        role=role,
        notificacoes_ativas=notificacoes_ativas,
    )


@router.post("/governanca-relatorio/usuario/{user_id}/toggle-relatorio")
def governanca_toggle_relatorio_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return governanca_relatorio_service.governanca_toggle_relatorio_user(
        user_id, request, db
    )


@router.post("/governanca-relatorio/testar/abrir-periodo")
def governanca_testar_abrir_periodo(
    request: Request,
    db: Session = Depends(get_db),
    force: str = Form("1"),
    base_relatorio_id: str = Form(""),
):
    return governanca_relatorio_service.governanca_testar_abrir_periodo(
        request,
        db,
        force=force,
        base_relatorio_id=base_relatorio_id,
    )


@router.post("/governanca-relatorio/testar/notificar")
def governanca_testar_notificar(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str = Form(...),
    relatorio_id: int = Form(...),
):
    return governanca_relatorio_service.governanca_testar_notificar(
        request, db, tipo=tipo, relatorio_id=relatorio_id
    )


@router.post("/governanca-relatorio/testar/retry")
def governanca_testar_retry(
    request: Request,
    db: Session = Depends(get_db),
):
    return governanca_relatorio_service.governanca_testar_retry(request, db)
