"""Restrições de rota por perfil (ex.: autor só no fluxo de gerenciamento de seção e upload)."""

from __future__ import annotations

import re

from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .db import SessionLocal
from .models import User

# Rotas necessárias ao hub `/relatorios/{id}`, `upload-conteudo`, `modelos-word-importacao` e suporte.
# `/relatorios/{id}/entregas` é restrito a admin/coordenador desde a revisão de
# perfis: autor acompanha sua entrega pelo sumário do relatório (`/relatorios/{id}`)
# e pelo painel da sua seção (`/relatorios/{id}/secoes/{sid}/upload-conteudo`),
# sem precisar do painel agregado de entregas dos autores.
_AUTOR_PATH_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"^/$",
        r"^/painel-upload$",
        r"^/relatorios/\d+$",
        r"^/modelos-word-importacao$",
        r"^/modelos-word-importacao/baixar/.+$",
        r"^/relatorios/\d+/secoes/\d+/upload-conteudo$",
        r"^/relatorios/\d+/secoes/\d+/responsavel$",
        r"^/relatorios/\d+/secoes/\d+/status$",
        r"^/relatorios/\d+/figuras$",
        r"^/figuras/\d+$",
        r"^/relatorios/\d+/secoes/\d+/blocos\.json$",
        r"^/relatorios/\d+/secoes/\d+/importar/analisar$",
        r"^/relatorios/\d+/secoes/\d+/importar/confirmar$",
        r"^/relatorios/\d+/pdf$",
        r"^/relatorios/\d+/preview$",
        r"^/relatorios/\d+/exportar$",
        r"^/relatorios/\d+/secoes/\d+/blocos$",
        r"^/relatorios/\d+/secoes/\d+/blocos/aprovar-lote$",
        r"^/relatorios/\d+/secoes/\d+/blocos/excluir-lote$",
        r"^/relatorios/\d+/secoes/\d+/blocos/\d+/editar$",
        r"^/relatorios/\d+/secoes/\d+/blocos/\d+/excluir$",
        r"^/relatorios/\d+/secoes/\d+/blocos/\d+/confirmar$",
    )
)

_SKIP_PREFIXES: tuple[str, ...] = ("/static/",)
_SKIP_PATHS_EXACT = frozenset({
    "/health",
    "/favicon.ico",
    "/login",
    "/logout",
    "/recuperar-senha",
    "/recuperar-senha/definir",
})


def path_allowed_for_autor(path: str) -> bool:
    return any(r.match(path) is not None for r in _AUTOR_PATH_RES)


def _accept_prefers_json(scope: Scope) -> bool:
    for key, value in scope.get("headers") or []:
        if key == b"accept":
            return b"application/json" in value.lower()
    return False


class SraAutorRouteGuardMiddleware:
    """Bloqueia autores fora do conjunto de URLs de gerenciamento de seção e upload."""

    def __init__(self, asgi_app: ASGIApp) -> None:
        self.asgi_app = asgi_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.asgi_app(scope, receive, send)
            return

        path = scope.get("path") or ""
        sess = scope["session"] if "session" in scope else None
        sem_guarda = (
            path.startswith(_SKIP_PREFIXES)
            or path in _SKIP_PATHS_EXACT
            or sess is None
            or not sess.get("user_id")
        )
        if sem_guarda:
            await self.asgi_app(scope, receive, send)
            return

        role = sess.get("user_role")
        if role is None:
            db = SessionLocal()
            try:
                row = db.get(User, sess["user_id"])
                if row is None:
                    await self.asgi_app(scope, receive, send)
                    return
                role = row.role
                sess["user_role"] = role
            finally:
                db.close()

        if role != "autor" or path_allowed_for_autor(path):
            await self.asgi_app(scope, receive, send)
            return

        msg = (
            "Permissão negada: perfil autor acede apenas ao gerenciamento de seção "
            "e upload e páginas públicas de login."
        )
        if _accept_prefers_json(scope):
            resp = JSONResponse({"detail": msg}, status_code=403)
        else:
            resp = RedirectResponse(url="/", status_code=303)
        await resp(scope, receive, send)
