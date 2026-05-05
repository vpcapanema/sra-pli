from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import dev_ui as dev_ui_service

router = APIRouter()


@router.get("/dev/modais")
def dev_modais_previews(request: Request, db: Session = Depends(get_db)):
    return dev_ui_service.dev_modais_previews(request, db)


@router.get("/dev/preview-email-notificacao")
def dev_preview_email_notificacao(
    request: Request,
    db: Session = Depends(get_db),
    *,
    raw: bool = Query(False),
    tipo: str = Query("abertura"),
    relatorio_id: int | None = Query(None),
):
    return dev_ui_service.dev_preview_email_notificacao(
        request, db, raw=raw, tipo=tipo, relatorio_id=relatorio_id
    )


@router.get("/dev/preview-emails-notificacao")
def dev_preview_emails_notificacao_todas(
    request: Request,
    db: Session = Depends(get_db),
    *,
    relatorio_id: int | None = Query(None),
):
    return dev_ui_service.dev_preview_emails_notificacao_todas(
        request, db, relatorio_id=relatorio_id
    )
