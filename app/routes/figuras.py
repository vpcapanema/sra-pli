from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import figuras as figuras_service

router = APIRouter(tags=["figuras"])


@router.post("/relatorios/{rel_id}/figuras")
def upload_figura(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    request: Request,
    arquivo: UploadFile = File(...),
    legenda: str = Form(""),
    fonte: str = Form(""),
    db: Session = Depends(get_db),
):
    return figuras_service.upload_figura(
        rel_id, request, arquivo, legenda, fonte, db
    )


@router.get("/figuras/{fig_id}")
def baixar_figura(fig_id: int, request: Request, db: Session = Depends(get_db)):
    return figuras_service.baixar_figura(fig_id, request, db)
