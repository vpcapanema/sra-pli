from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import mapa_aplicacao as mapa_aplicacao_service

router = APIRouter()


@router.get("/mapa-aplicacao")
def mapa_aplicacao_pagina(request: Request, db: Session = Depends(get_db)):
    return mapa_aplicacao_service.mapa_aplicacao_pagina(request, db)
