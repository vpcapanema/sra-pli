"""Mapa das páginas HTML em ``templates/complementos``."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..mapa_aplicacao_catalog import PaginaComplementoMeta, meta_por_arquivo
from ..models import User
from .pages import templates, user_coord_ou_admin_ou_login

router = APIRouter()

_APP_PKG = Path(__file__).resolve().parent.parent
_COMPLEMENTOS_DIR = _APP_PKG / "templates" / "complementos"


def _href_exemplo_com_hub(request: Request, href: str) -> str:
    """Troca ``/relatorios/1`` e ``/secoes/1`` do catálogo pelo hub da barra lateral (evita 404)."""
    rel_id = getattr(request.state, "sra_hub_rel_id", None)
    sec_id = getattr(request.state, "sra_hub_primeira_secao_id", None)
    out = href
    if rel_id is not None:
        if out == "/relatorios/1":
            out = f"/relatorios/{rel_id}"
        elif out.startswith("/relatorios/1/"):
            out = f"/relatorios/{rel_id}/" + out.removeprefix("/relatorios/1/")
    if sec_id is not None and "/secoes/1/" in out:
        out = out.replace("/secoes/1/", f"/secoes/{sec_id}/")
    return out


def _referenciado_em_codigo(nome_ficheiro: str) -> bool:
    needle_d = f'"complementos/{nome_ficheiro}"'
    needle_s = f"'complementos/{nome_ficheiro}'"
    for path in _APP_PKG.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        texto = path.read_text(encoding="utf-8")
        if needle_d in texto or needle_s in texto:
            return True
    return False


def _meta_padrao(nome_ficheiro: str) -> PaginaComplementoMeta:
    curto = nome_ficheiro.removesuffix(".html").replace("_", " ").strip() or nome_ficheiro
    titulo = curto[:1].upper() + curto[1:] if curto else nome_ficheiro
    return PaginaComplementoMeta(
        nome_ficheiro,
        titulo,
        "/",
        "Não catalogado em ``mapa_aplicacao_catalog``",
        "—",
    )


@router.get("/mapa-aplicacao")
def mapa_aplicacao_pagina(request: Request, db: Session = Depends(get_db)):
    """Página interna com cartões para cada ficheiro em ``templates/complementos``."""
    authz = user_coord_ou_admin_ou_login(request, db)
    if not isinstance(authz, User):
        return authz
    user = authz

    metas = meta_por_arquivo()
    paginas: list[dict[str, str | bool]] = []
    for path in sorted(_COMPLEMENTOS_DIR.glob("*.html")):
        nome = path.name
        meta = metas.get(nome) or _meta_padrao(nome)
        href = _href_exemplo_com_hub(request, meta.href_exemplo)
        paginas.append(
            {
                "arquivo": meta.arquivo,
                "nome": meta.nome_exibicao,
                "href": href,
                "restricao": meta.restricao,
                "rotas": meta.rotas_resumo,
                "em_uso": _referenciado_em_codigo(nome),
            }
        )

    return templates.TemplateResponse(
        request,
        "mapa_aplicacao.html",
        {"user": user, "paginas": paginas},
    )
