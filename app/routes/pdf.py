from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Relatorio
from ..auth import current_user
from ..pdf_render import render_pdf

router = APIRouter()


@router.get("/relatorios/{rel_id}/pdf")
def gerar_pdf(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    pdf = render_pdf(db, rel)
    fname = f"{rel.codigo}-{rel.versao}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )
