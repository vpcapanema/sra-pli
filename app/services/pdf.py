"""Lógica de preview HTML e exportação DOCX (rotas em ``app/routes/pdf.py``).

Endpoints históricos de PDF foram substituídos pelo preview HTML A4 + DOCX.
Eles agora respondem com ``307 Temporary Redirect`` para o equivalente ativo,
preservando bookmarks externos. Este módulo concentra toda a regra de negócio,
resolução de escopo de seções e montagem de respostas binárias/HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..auth import current_user
from ..docx_render import render_docx
from ..models import Relatorio
from ..pdf_render import render_html
from ..ref_resolve import carregar_relatorio_com_secoes_e_blocos
from .pages import response_dashboard, response_login


# ---------------------------------------------------------------------------
# Query DTO da exportação
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExportarQuery:
    formato: str
    escopo: str
    secao_ids: list[int]


def exportar_query_params(
    formato: str = Query("docx"),
    escopo: str = Query("inteiro"),
    secao_ids: list[int] = Query(default=[]),
) -> ExportarQuery:
    return ExportarQuery(formato=formato, escopo=escopo, secao_ids=secao_ids)


# ---------------------------------------------------------------------------
# Regras de seleção de seções
# ---------------------------------------------------------------------------


def _section_filter(
    rel: Relatorio, escopo: str, secao_ids: list[int]
) -> set[int] | None:
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


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def gerar_pdf(rel_id: int, request: Request, db: Session, secao_ids: list[int]):
    """Endpoint legado: redireciona para o preview HTML A4 (307)."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    destino = f"/relatorios/{rel_id}/preview"
    if secao_ids:
        destino = f"{destino}?{urlencode([('secao_ids', s) for s in secao_ids])}"
    return RedirectResponse(url=destino, status_code=307)


def preview_html(rel_id: int, request: Request, db: Session, secao_ids: list[int]):
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


def exportar_relatorio(
    rel_id: int,
    request: Request,
    query: ExportarQuery,
    db: Session,
):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = carregar_relatorio_com_secoes_e_blocos(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_ids = _section_filter(rel, query.escopo, query.secao_ids)
    suffix = (
        "-importadas"
        if query.escopo == "importadas"
        else ("-secoes" if section_ids else "")
    )
    if query.formato == "pdf":
        params = [("formato", "docx"), ("escopo", query.escopo)]
        params.extend(("secao_ids", s) for s in query.secao_ids)
        return RedirectResponse(
            url=f"/relatorios/{rel_id}/exportar?{urlencode(params)}",
            status_code=307,
        )
    if query.formato == "docx":
        docx = render_docx(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.docx"
        return Response(
            content=docx,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    raise HTTPException(400, detail="Formato de exportação inválido.")


def exportar_para_assinatura(rel_id: int, request: Request, db: Session):
    """Endpoint legado: pacote de assinatura em PDF foi substituído pelo DOCX."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    return RedirectResponse(
        url=f"/relatorios/{rel_id}/exportar?formato=docx&escopo=inteiro",
        status_code=307,
    )
