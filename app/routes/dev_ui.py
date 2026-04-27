"""Rotas auxiliares de desenvolvimento (pré-visualização de UI)."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..db import get_db
from .pages import response_login

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _modais_preview_allowed() -> bool:
    v = (os.environ.get("SRA_MODAL_PREVIEW", "") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return (getattr(settings, "APP_ENV", None) or "").lower() == "development"


@router.get("/dev/modais")
def dev_modais_previews(request: Request, db: Session = Depends(get_db)):
    if not _modais_preview_allowed():
        raise HTTPException(status_code=404, detail="Não disponível")
    user = current_user(request, db)
    if not user:
        return response_login(request)
    return templates.TemplateResponse(
        request,
        "dev_modais.html",
        {
            "request": request,
            "user": user,
        },
    )
