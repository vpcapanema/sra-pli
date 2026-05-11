from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..services import pdf as pdf_service
from ..services.pdf import ExportarQuery, docx_export, exportar_query_params
from ..services.pages import response_login

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
    bloco_ids: list[int] = Query(default=[]),
    contexto: str = Query("default"),
):
    return pdf_service.preview_html(
        rel_id=rel_id, request=request, db=db, secao_ids=secao_ids, bloco_ids=bloco_ids, contexto=contexto
    )


@router.get("/relatorios/{rel_id}/exportar")
def exportar_relatorio(
    rel_id: int,
    request: Request,
    query: ExportarQuery = Depends(exportar_query_params),
    db: Session = Depends(get_db),
):
    return pdf_service.exportar_relatorio(rel_id, request, query, db)


@router.get("/relatorios/{rel_id}/docx_export")
def docx_export_route(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user = current_user(request, db)
        if not user:
            return response_login(request)
        docx = docx_export(rel_id, db)
        return Response(
            content=docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="relatorio-{rel_id}.docx"'},
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception("Error exporting docx")
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=500, content={"error": "Failed to generate document", "detail": str(e)})


@router.get("/relatorios/{rel_id}/exportar-assinatura")
def exportar_para_assinatura(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return pdf_service.exportar_para_assinatura(rel_id, request, db)
