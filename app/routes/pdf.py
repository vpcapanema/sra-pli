from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import pdf as pdf_service
from ..services.pdf import ExportarQuery, exportar_query_params

router = APIRouter()


@router.get("/relatorios/{rel_id}/pdf")
def gerar_pdf(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    secao_ids: list[int] = Query(default=[]),
):
    return pdf_service.gerar_pdf(rel_id, request, db, secao_ids)


@router.get("/relatorios/{rel_id}/preview", response_class=HTMLResponse)
def preview_html(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    secao_ids: list[int] = Query(default=[]),
):
    return pdf_service.preview_html(rel_id, request, db, secao_ids)


@router.get("/relatorios/{rel_id}/exportar")
def exportar_relatorio(
    rel_id: int,
    request: Request,
    query: ExportarQuery = Depends(exportar_query_params),
    db: Session = Depends(get_db),
):
    return pdf_service.exportar_relatorio(rel_id, request, query, db)


@router.get("/relatorios/{rel_id}/exportar-assinatura")
def exportar_para_assinatura(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return pdf_service.exportar_para_assinatura(rel_id, request, db)
