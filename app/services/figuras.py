"""Upload e download de figuras (rotas em ``app/routes/figuras.py``)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..auth import current_user
from ..models import Figura, Relatorio
from .pages import (
    response_conteudo_upload,
    response_login,
    response_relatorio_detail,
)

_MIMES_PERMITIDOS = ("image/png", "image/jpeg", "image/svg+xml", "image/webp")
_LIMITE_BYTES = 8 * 1024 * 1024
_REF_SECAO_RE = re.compile(r"/relatorios/(\d+)/secoes/(\d+)")


def _client_aceita_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept


def upload_figura(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    request: Request,
    arquivo: UploadFile,
    legenda: str,
    fonte: str,
    db: Session,
):
    user = current_user(request, db)
    if not user:
        if _client_aceita_json(request):
            raise HTTPException(
                status_code=401,
                detail="Sessão expirada. Faça login novamente.",
            )
        return response_login(request)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if arquivo.content_type not in _MIMES_PERMITIDOS:
        raise HTTPException(
            400, "Formato não suportado (use PNG, JPG, SVG ou WEBP)"
        )
    dados = arquivo.file.read()
    if len(dados) > _LIMITE_BYTES:
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
    if _client_aceita_json(request):
        return JSONResponse({"id": fig.id, "nome": fig.nome})
    ref = (request.headers.get("referer") or "").strip()
    secoes_m = _REF_SECAO_RE.search(urlparse(ref).path)
    if secoes_m and int(secoes_m.group(1)) == rel_id:
        return response_conteudo_upload(
            request, db, int(secoes_m.group(1)), int(secoes_m.group(2))
        )
    return response_relatorio_detail(request, db, rel_id)


def baixar_figura(fig_id: int, request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        return response_login(request)
    fig = db.get(Figura, fig_id)
    if not fig:
        raise HTTPException(404)
    return Response(content=fig.dados, media_type=fig.mime)
