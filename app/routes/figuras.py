import re
from urllib.parse import urlparse

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Figura, Relatorio
from ..auth import current_user
from . import pages

router = APIRouter(tags=["figuras"])


@router.post("/relatorios/{rel_id}/figuras")
def upload_figura(
    rel_id: int,
    request: Request,
    arquivo: UploadFile = File(...),
    legenda: str = Form(""),
    fonte: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        accept = (request.headers.get("accept") or "").lower()
        if "application/json" in accept:
            raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
        return pages.response_login(request)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if arquivo.content_type not in ("image/png", "image/jpeg", "image/svg+xml", "image/webp"):
        raise HTTPException(400, "Formato não suportado (use PNG, JPG, SVG ou WEBP)")
    dados = arquivo.file.read()
    if len(dados) > 8 * 1024 * 1024:
        raise HTTPException(400, "Figura > 8 MB")
    fig = Figura(
        relatorio_id=rel_id,
        nome=arquivo.filename or "figura",
        mime=arquivo.content_type,
        dados=dados,
        legenda=legenda.strip() or None,
        fonte=fonte.strip() or None,
    )
    db.add(fig)
    db.commit()
    db.refresh(fig)
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"id": fig.id, "nome": fig.nome})
    ref = (request.headers.get("referer") or "").strip()
    secoes_m = re.search(r"/relatorios/(\d+)/secoes/(\d+)", urlparse(ref).path)
    if secoes_m and int(secoes_m.group(1)) == rel_id:
        return pages.response_conteudo_upload(
            request, db, int(secoes_m.group(1)), int(secoes_m.group(2))
        )
    return pages.response_relatorio_detail(request, db, rel_id)


@router.get("/figuras/{fig_id}")
def baixar_figura(fig_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return pages.response_login(request)
    fig = db.get(Figura, fig_id)
    if not fig:
        raise HTTPException(404)
    return Response(content=fig.dados, media_type=fig.mime)
