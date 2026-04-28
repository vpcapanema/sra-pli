from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user
from ..docx_render import render_docx
from ..pdf_render import render_pdf, render_html
from ..process_events import process_done, process_log, process_start
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
    if escopo != "selecionadas":
        return None
    ids_relatorio = {sec.id for sec in rel.secoes}
    selected = {sec_id for sec_id in secao_ids if sec_id in ids_relatorio}
    if not selected:
        raise HTTPException(400, detail="Selecione ao menos uma seção para exportar.")
    return selected


@router.get("/relatorios/{rel_id}/pdf")
def gerar_pdf(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    embed: int = Query(default=0, ge=0, le=1),
    secao_ids: list[int] = Query(default=[]),
):
    """`embed=1`: PDF para iframes (pré-visualização) sem eventos SSE de processo.

    `secao_ids`: limita a renderização às seções indicadas (e a árvore acima
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
    silent = embed == 1
    process_id = None
    if not silent:
        process_id = process_start(
            request,
            "Geração de PDF",
            f"Composição do ficheiro final a partir de {rel.codigo}-{rel.versao}.",
            data={"process_key": "gerar_pdf"},
        )
        process_log(
            request,
            process_id,
            "O conteúdo em HTML do relatório é composto e convertido em PDF (WeasyPrint), com aplicação da folha de estilos do contrato.",
            etapa="Conversão para PDF",
            tarefa="Geração de PDF",
            progresso_tarefa=55,
            progresso_geral=48,
        )
    pdf = render_pdf(db, rel, section_filter)
    fname = f"{rel.codigo}-{rel.versao}.pdf"
    if not silent and process_id:
        process_done(request, process_id, "PDF pronto", fname, process_key="gerar_pdf")
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
    process_id = process_start(
        request,
        "Pré-visualização em HTML",
        f"Geração da página a partir de {rel.codigo}.",
        data={"process_key": "preview_html"},
    )
    html = render_html(db, rel)
    process_done(
        request, process_id, "Pré-visualização pronta", f"{rel.codigo}-{rel.versao}", process_key="preview_html"
    )
    return HTMLResponse(html)


@router.get("/relatorios/{rel_id}/exportar")
def exportar_relatorio(
    rel_id: int,
    request: Request,
    formato: str = Query("pdf"),
    escopo: str = Query("inteiro"),
    secao_ids: list[int] = Query(default=[]),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_ids = _section_filter(rel, escopo, secao_ids)
    suffix = "-secoes" if section_ids else ""
    process_id = process_start(
        request,
        "Exportação de relatório",
        f"Formato pretendido: {formato.upper()}.",
        data={"process_key": "exportar_relatorio"},
    )
    if section_ids:
        process_log(
            request,
            process_id,
            f"O âmbito restringe-se a {len(section_ids)} secção(ões) selecionada(s) antes de gerar o ficheiro.",
            etapa="Definição do âmbito",
            tarefa="Exportação de relatório",
            progresso_tarefa=30,
            progresso_geral=25,
        )
    else:
        process_log(
            request,
            process_id,
            "Exporta-se o relatório completo, sem exclusão de secções, no formato solicitado.",
            etapa="Definição do âmbito",
            tarefa="Exportação de relatório",
            progresso_tarefa=30,
            progresso_geral=25,
        )
    if formato == "pdf":
        pdf = render_pdf(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.pdf"
        process_done(request, process_id, "Exportação pronta", fname, process_key="exportar_relatorio")
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    if formato == "docx":
        docx = render_docx(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.docx"
        process_done(request, process_id, "Exportação pronta", fname, process_key="exportar_relatorio")
        return Response(
            content=docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    process_done(
        request, process_id, "Exportação recusada", "Formato inválido.", ok=False, process_key="exportar_relatorio"
    )
    raise HTTPException(400, detail="Formato de exportação inválido.")
