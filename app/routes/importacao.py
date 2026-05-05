from fastapi import APIRouter, Body, Depends, File, Request, UploadFile

from sqlalchemy.orm import Session

from ..db import get_db
from ..services import importacao as importacao_service

router = APIRouter(
    prefix="/relatorios/{rel_id}/secoes/{sec_id}/importar",
    tags=["importacao"],
)


@router.post("/sincronizar-indices")
def sincronizar_indices_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    return importacao_service.sincronizar_indices_importacao(rel_id, sec_id, payload, request, db)


@router.post("/analisar")
async def analisar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await importacao_service.analisar_importacao(rel_id, sec_id, request, arquivo, db)


@router.post("/confirmar")
async def confirmar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return await importacao_service.confirmar_importacao(rel_id, sec_id, request, db)
