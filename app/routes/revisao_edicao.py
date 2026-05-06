from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import revisao_edicao as revisao_edicao_service

router = APIRouter()


@router.post("/relatorios/{rel_id}/secoes/{sec_id}/observacao-validacao")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def salvar_observacao_validacao_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    observacao: str = Form(""),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    return revisao_edicao_service.salvar_observacao_validacao_secao(
        rel_id, sec_id, request, observacao, redirect_to, db
    )


@router.post("/relatorios/{rel_id}/revisao-linguistica")
def revisao_linguistica_rodar(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return revisao_edicao_service.revisao_linguistica_rodar(
        rel_id, request, db
    )


@router.get("/relatorios/{rel_id}/revisao-edicao")
def revisao_edicao_page(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return revisao_edicao_service.revisao_edicao_page(
        rel_id, request, db
    )


@router.post("/relatorios/{rel_id}/blocos/{bloco_id}/revisao-salvar")
async def revisao_salvar_bloco(
    rel_id: int,
    bloco_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return await revisao_edicao_service.revisao_salvar_bloco(
        rel_id, bloco_id, request, db
    )


@router.post("/relatorios/{rel_id}/blocos/{bloco_id}/revisao-desconfirmar")
def revisao_desconfirmar_bloco(
    rel_id: int,
    bloco_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return revisao_edicao_service.revisao_desconfirmar_bloco(
        rel_id, bloco_id, request, db
    )


@router.post("/relatorios/{rel_id}/revisao-linguistica/vocabulario")
async def revisao_vocabulario_adicionar(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return await revisao_edicao_service.revisao_vocabulario_adicionar(
        rel_id, request, db
    )
