from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user
from ..docx_render import render_docx
from ..pdf_render import render_pdf, render_html
from ..process_events import process_done, process_log, process_start

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
def gerar_pdf(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    process_id = process_start(request, "Geração de PDF", f"Montando {rel.codigo}-{rel.versao}.")
    process_log(request, process_id, "Renderizando HTML e convertendo com WeasyPrint.")
    pdf = render_pdf(db, rel)
    fname = f"{rel.codigo}-{rel.versao}.pdf"
    process_done(request, process_id, "PDF pronto", fname)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/relatorios/{rel_id}/preview", response_class=HTMLResponse)
def preview_html(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    process_id = process_start(request, "Pré-visualização", f"Renderizando HTML de {rel.codigo}.")
    html = render_html(db, rel)
    process_done(request, process_id, "Pré-visualização pronta", f"{rel.codigo}-{rel.versao}")
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
        raise HTTPException(303, headers={"Location": "/login"})
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    section_ids = _section_filter(rel, escopo, secao_ids)
    suffix = "-secoes" if section_ids else ""
    process_id = process_start(request, "Exportação de relatório", f"Formato: {formato.upper()}.")
    if section_ids:
        process_log(request, process_id, f"Exportando {len(section_ids)} seção(ões) selecionada(s).")
    else:
        process_log(request, process_id, "Exportando relatório inteiro.")
    if formato == "pdf":
        pdf = render_pdf(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.pdf"
        process_done(request, process_id, "Exportação pronta", fname)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    if formato == "docx":
        docx = render_docx(db, rel, section_ids)
        fname = f"{rel.codigo}-{rel.versao}{suffix}.docx"
        process_done(request, process_id, "Exportação pronta", fname)
        return Response(
            content=docx,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    process_done(request, process_id, "Exportação recusada", "Formato inválido.", ok=False)
    raise HTTPException(400, detail="Formato de exportação inválido.")
