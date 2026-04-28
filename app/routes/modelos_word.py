"""Página de ajuda e catálogo de modelos Word (.dotx) para importação assistida."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SECOES_PADRAO
from ..notificacoes.modelos import DOTX_MEDIA_TYPE, MODELOS_DIR, filename_para
from .pages import templates, user_or_login_page

router = APIRouter()

_ARQUIVO_SEGURO = re.compile(r"^[A-Za-z0-9._-]+\.dotx$")

_ALLOWED_DOTX = frozenset(
    ["SRA_todas_secoes.dotx"] + [filename_para(n, t) for n, t in SECOES_PADRAO]
)


def _caminho_resolvido_seguro(nome: str) -> str | None:
    if nome not in _ALLOWED_DOTX or not _ARQUIVO_SEGURO.match(nome):
        return None
    path = (MODELOS_DIR / nome).resolve()
    base = MODELOS_DIR.resolve()
    if path.parent != base or not path.is_file():
        return None
    return str(path)


@router.get("/modelos-word-importacao")
def pagina_modelos_word_importacao(request: Request, db: Session = Depends(get_db)):
    """Tutorial e links para cada ``.dotx`` do catálogo (login obrigatório)."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    linhas = []
    for num, tit in SECOES_PADRAO:
        fn = filename_para(num, tit)
        path = MODELOS_DIR / fn
        nivel = str(num).count(".")
        linhas.append(
            {
                "numero": num,
                "titulo": tit,
                "arquivo": fn,
                "disponivel": path.is_file(),
                "nivel": nivel,
            }
        )
    todas = MODELOS_DIR / "SRA_todas_secoes.dotx"
    return templates.TemplateResponse(
        request,
        "modelos_word_importacao.html",
        {
            "user": user,
            "secoes_catalogo": linhas,
            "todas_secoes_disponivel": todas.is_file(),
        },
    )


@router.get("/modelos-word-importacao/baixar/{arquivo}")
def baixar_modelo_catalogo(
    arquivo: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Download autenticado de um ``.dotx`` listado no catálogo."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    caminho = _caminho_resolvido_seguro(arquivo)
    if caminho is None:
        raise HTTPException(
            404,
            detail=(
                "Ficheiro não encontrado ou não permitido. Gere os modelos com "
                "`scripts/build_canonical_upload_dotx.py`."
            ),
        )
    return FileResponse(
        path=caminho,
        filename=arquivo,
        media_type=DOTX_MEDIA_TYPE,
    )
