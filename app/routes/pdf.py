from dataclasses import dataclass

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Relatorio
from ..auth import current_user
from ..docx_render import render_docx
from ..pdf_render import render_html
from ..ref_resolve import carregar_relatorio_com_secoes_e_blocos
from .pages import response_dashboard, response_login

router = APIRouter()


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
    formato: str = Query("docx"),
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
    """Endpoint legado desativado: o sistema usa preview HTML A4 e DOCX."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    raise HTTPException(410, detail="Geração de PDF desativada. Use a pré-visualização HTML.")


@router.get("/relatorios/{rel_id}/preview", response_class=HTMLResponse)
def preview_html(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    secao_ids: list[int] = Query(default=[]),
):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = carregar_relatorio_com_secoes_e_blocos(db, rel_id)
    if not rel:
        return response_dashboard(request, db)
    section_filter: set[int] | None = None
    if secao_ids:
        ids_rel = {sec.id for sec in rel.secoes}
        chosen = {sid for sid in secao_ids if sid in ids_rel}
        if chosen:
            section_filter = chosen
    html = render_html(db, rel, section_filter)
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
    rel = carregar_relatorio_com_secoes_e_blocos(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_ids = _section_filter(rel, query.escopo, query.secao_ids)
    suffix = "-importadas" if query.escopo == "importadas" else ("-secoes" if section_ids else "")
    if query.formato == "pdf":
        raise HTTPException(410, detail="Exportação PDF desativada. Use DOCX.")
    if query.formato == "docx":
        docx = render_docx(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.docx"
        return Response(
            content=docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    raise HTTPException(400, detail="Formato de exportação inválido.")


@router.get("/relatorios/{rel_id}/exportar-assinatura")
def exportar_para_assinatura(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    raise HTTPException(410, detail="Pacote com PDF para assinatura desativado. Use DOCX.")
