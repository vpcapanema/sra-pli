from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from ..db import get_db
from ..services.pages import (
    response_conteudo_upload,
    response_dashboard,
    response_painel_upload,
    response_relatorio_detail,
)

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    return response_dashboard(request, db)


@router.get("/painel-upload")
def painel_upload(request: Request, db: Session = Depends(get_db)):
    return response_painel_upload(request, db)


@router.get("/relatorios/{rel_id}")
def relatorio_detail(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return response_relatorio_detail(request, db, rel_id)


@router.get("/relatorios/{rel_id}/secoes/{sec_id}")
def secao_edit_redirect_upload_conteudo(rel_id: int, sec_id: int):
    """Redireciona para ``…/upload-conteudo`` — único template de edição."""
    return RedirectResponse(
        url=f"/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo",
        status_code=303,
    )


@router.get("/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo")
def conteudo_upload(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return response_conteudo_upload(request, db, rel_id, sec_id)
