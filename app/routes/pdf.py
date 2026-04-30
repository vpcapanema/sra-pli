from dataclasses import dataclass

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user
from ..docx_render import render_docx
from ..pdf_render import render_pdf, render_html
from .pages import response_dashboard, response_login

router = APIRouter()


def _get_relatorio_completo(db: Session, rel_id: int) -> Relatorio | None:
    return (
        db.query(Relatorio)
        .options(selectinload(Relatorio.secoes).selectinload(Secao.blocos))
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )


def _section_filter(rel: Relatorio, escopo: str, secao_ids: list[int]) -> set[int] | None:
    if escopo == "importadas":
        imported = {
            sec.id
            for sec in rel.secoes
            if any((bloco.origem or "") == "upload" for bloco in sec.blocos)
        }
        if not imported:
            raise HTTPException(400, detail="Nenhuma seção importada encontrada.")
        return imported
    if escopo != "selecionadas":
        return None
    ids_relatorio = {sec.id for sec in rel.secoes}
    selected = {sec_id for sec_id in secao_ids if sec_id in ids_relatorio}
    if not selected:
        raise HTTPException(400, detail="Selecione ao menos uma seção para exportar.")
    return selected


@dataclass(frozen=True, slots=True)
class _ExportarQuery:
    formato: str
    escopo: str
    secao_ids: list[int]


def _exportar_query_params(
    formato: str = Query("pdf"),
    escopo: str = Query("inteiro"),
    secao_ids: list[int] = Query(default=[]),
) -> _ExportarQuery:
    return _ExportarQuery(formato=formato, escopo=escopo, secao_ids=secao_ids)


@router.get("/relatorios/{rel_id}/pdf")
def gerar_pdf(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    secao_ids: list[int] = Query(default=[]),
):
    """`secao_ids`: limita a renderização às seções indicadas (e a árvore acima
    delas), permitindo que o iframe de pré-visualização acompanhe a Seção alvo
    selecionada na página de upload sem recarregar o relatório inteiro.
    """
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_filter = _section_filter(rel, "selecionadas", secao_ids) if secao_ids else None
    pdf = render_pdf(db, rel, section_filter)
    fname = f"{rel.codigo}-{rel.versao}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/relatorios/{rel_id}/preview", response_class=HTMLResponse)
def preview_html(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        return response_dashboard(request, db)
    html = render_html(db, rel)
    return HTMLResponse(html)


@router.get("/relatorios/{rel_id}/exportar")
def exportar_relatorio(
    rel_id: int,
    request: Request,
    query: _ExportarQuery = Depends(_exportar_query_params),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_ids = _section_filter(rel, query.escopo, query.secao_ids)
    suffix = "-importadas" if query.escopo == "importadas" else ("-secoes" if section_ids else "")
    if query.formato == "pdf":
        pdf = render_pdf(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.pdf"
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    if query.formato == "docx":
        docx = render_docx(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.docx"
        return Response(
            content=docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    raise HTTPException(400, detail="Formato de exportação inválido.")
