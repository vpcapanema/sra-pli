from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response, HTMLResponse
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user
from ..pdf_render import render_pdf, render_html

router = APIRouter()


def _get_relatorio_completo(db: Session, rel_id: int) -> Relatorio | None:
    return (
        db.query(Relatorio)
        .options(selectinload(Relatorio.secoes).selectinload(Secao.blocos))
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )


@router.get("/relatorios/{rel_id}/pdf")
def gerar_pdf(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    pdf = render_pdf(db, rel)
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
        raise HTTPException(303, headers={"Location": "/login"})
    rel = _get_relatorio_completo(db, rel_id)
    if not rel:
        raise HTTPException(404)
    return HTMLResponse(render_html(db, rel))
