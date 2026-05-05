from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import notificacoes as notificacoes_service

router = APIRouter()


@router.post("/usuarios/{user_id}/notificacoes-toggle")
def usuarios_notificacoes_toggle(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return notificacoes_service.usuarios_notificacoes_toggle(
        user_id, request, db
    )


@router.get("/relatorios/{rel_id}/entregas")
def entregas_painel(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return notificacoes_service.entregas_painel(rel_id, request, db)


@router.post("/relatorios/{rel_id}/notificar-autores-abertura")
def rota_notificar_autores_abertura(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return notificacoes_service.rota_notificar_autores_abertura(
        rel_id, request, db
    )


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/status")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def entrega_atualizar_status(
    rel_id: int,
    entrega_id: int,
    request: Request,
    novo_status: str = Form(...),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    return notificacoes_service.entrega_atualizar_status(
        rel_id, entrega_id, request, novo_status, redirect_to, db
    )


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/reenviar")
def entrega_reenviar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    return notificacoes_service.entrega_reenviar(
        rel_id, entrega_id, request, redirect_to, db
    )


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/reprovar")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def entrega_reprovar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    motivo: str = Form(...),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    return notificacoes_service.entrega_reprovar(
        rel_id, entrega_id, request, motivo, redirect_to, db
    )


@router.get("/relatorios/{rel_id}/secoes/{sec_id}/modelo.dotx")
def baixar_modelo_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return notificacoes_service.baixar_modelo_secao(
        rel_id, sec_id, request, db
    )
