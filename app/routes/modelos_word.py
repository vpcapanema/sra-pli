from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import modelos_word as modelos_word_service

router = APIRouter()


@router.get("/modelos-word-importacao")
def pagina_modelos_word_importacao(
    request: Request, db: Session = Depends(get_db)
):
    return modelos_word_service.pagina_modelos_word_importacao(request, db)


@router.get("/modelos-word-importacao/baixar/{arquivo}")
def baixar_modelo_catalogo(
    arquivo: str,
    request: Request,
    db: Session = Depends(get_db),
):
    return modelos_word_service.baixar_modelo_catalogo(arquivo, request, db)
