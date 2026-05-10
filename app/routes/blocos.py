from fastapi import APIRouter, Request, Form, Depends, HTTPException

from sqlalchemy.orm import Session

from ..db import get_db
from ..services import blocos as blocos_service

router = APIRouter(prefix="/relatorios/{rel_id}/secoes/{sec_id}/blocos", tags=["blocos"])


@router.get(".json")
def listar_blocos_json(rel_id: int, sec_id: int, request: Request, db: Session = Depends(get_db)):
    return blocos_service.listar_blocos_json(rel_id, sec_id, request, db)


@router.post("")
def criar_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    sec_id: int,
    request: Request,
    tipo: str = Form(...),
    titulo: str = Form(""),
    conteudo: str = Form(""),
    legenda: str = Form(""),
    fonte: str = Form(""),
    figura_id: str = Form(""),
    db: Session = Depends(get_db),
):
    return blocos_service.criar_bloco(rel_id, sec_id, request, tipo, titulo, conteudo, legenda, fonte, figura_id, db)


@router.post("/aprovar-lote")
def aprovar_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    return blocos_service.aprovar_blocos_lote(rel_id, sec_id, request, bloco_ids, db)


@router.post("/desbloquear-lote")
def desbloquear_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    return blocos_service.desbloquear_blocos_lote(rel_id, sec_id, request, bloco_ids, db)


@router.post("/excluir-lote")
def excluir_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    # Aceita tanto bloco_ids quanto bloco_ids[] do formulário
    if not bloco_ids:
        raise HTTPException(400, detail="Selecione ao menos um bloco.")
    return blocos_service.excluir_blocos_lote(rel_id, sec_id, request, bloco_ids, db)


@router.post("/{bloco_id}/editar")
def editar_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    titulo: str = Form(""),
    conteudo: str = Form(""),
    legenda: str = Form(""),
    fonte: str = Form(""),
    figura_id: str = Form(""),
    db: Session = Depends(get_db),
):
    return blocos_service.editar_bloco(
        rel_id, sec_id, bloco_id, request, titulo, conteudo, legenda, fonte, figura_id, db
    )


@router.post("/{bloco_id}/excluir")
def excluir_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    return blocos_service.excluir_bloco(rel_id, sec_id, bloco_id, request, db)


@router.post("/{bloco_id}/confirmar")
def confirmar_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    return blocos_service.confirmar_bloco(rel_id, sec_id, bloco_id, request, db)


@router.post("/{bloco_id}/desbloquear")
def desbloquear_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    return blocos_service.desbloquear_bloco(rel_id, sec_id, bloco_id, request, db)


@router.post("/{bloco_id}/mover")
def mover_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    direcao: str = Form(...),
    db: Session = Depends(get_db),
):
    return blocos_service.mover_bloco(rel_id, sec_id, bloco_id, request, direcao, db)
