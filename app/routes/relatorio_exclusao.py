from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import relatorio_exclusao as relatorio_exclusao_service

router = APIRouter()


@router.post("/{rel_id}/excluir")
def excluir_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorio_exclusao_service.excluir_relatorio(rel_id, request, db)


@router.post("/{rel_id}/secoes/{sec_id}/excluir")
def excluir_subsecao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return relatorio_exclusao_service.excluir_subsecao(
        rel_id, sec_id, request, db
    )


@router.post("/{rel_id}/secoes/excluir-lote")
def excluir_secoes_lote(
    rel_id: int,
    request: Request,
    secao_ids: list[int] = Form(default_factory=list),
    db: Session = Depends(get_db),
):
    return relatorio_exclusao_service.excluir_secoes_lote(
        rel_id, secao_ids, request, db
    )
