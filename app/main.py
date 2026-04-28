from contextlib import asynccontextmanager
from logging import getLogger
from time import perf_counter
from datetime import datetime
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .bootstrap import init_db
from .routes import auth as auth_routes
from .routes import pages as page_routes
from .routes import relatorio_exclusao as relatorio_exclusao_routes
from .routes import relatorios as rel_routes
from .routes import blocos as bloco_routes
from .routes import figuras as figura_routes
from .routes import cron_admin as cron_admin_routes
from .routes import importacao as importacao_routes
from .routes import modelos_word as modelos_word_routes
from .routes import notificacoes as notif_routes
from .routes import pdf as pdf_routes
from .routes import processos as processos_routes
from .routes import dev_ui
from .routes.pages import response_home
from .access_control import SraAutorRouteGuardMiddleware
from .process_events import configure_logging_bridge, process_session_id

BASE_DIR = Path(__file__).parent

_HTTP_AUDIT_LOG = getLogger("app.http")


class SraEnsureProcessSessionMiddleware:
    """ASGI: corre *dentro* do SessionMiddleware (ver ordem em add_middleware abaixo).

    Middlewares declarados com @app.middleware("http") ficam à frente do
    SessionMiddleware na pilha e não têm ``scope["session"]`` — daí o 500.
    """

    def __init__(self, asgi_app: ASGIApp) -> None:
        self.asgi_app = asgi_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path") or ""
            if not path.startswith("/static/") and "session" in scope:
                sess = scope["session"]
                if sess.get("user_id"):
                    process_session_id(Request(scope))
        await self.asgi_app(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    configure_logging_bridge()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


@app.middleware("http")
async def sra_http_audit_log(request: Request, call_next):
    """Regista duração de pedidos nas áreas de relatório, utilizadores e upload (nível INFO → SSE)."""
    path = request.url.path
    instrumentar = (
        path.startswith("/relatorios")
        or path.startswith("/usuarios")
        or path.endswith("/upload-conteudo")
        or "/importar/" in path
    )
    if not instrumentar or path.startswith("/static/"):
        return await call_next(request)
    t0 = perf_counter()
    response = await call_next(request)
    ms = (perf_counter() - t0) * 1000
    code = getattr(response, "status_code", "?")
    _HTTP_AUDIT_LOG.info("%s %s → %s (%.0f ms)", request.method, path, code, ms)
    return response


# Ordem add_middleware (insert no início): [Session, Ensure, Autor] → execução
# SessionMiddleware → SraEnsureProcessSessionMiddleware → SraAutorRouteGuardMiddleware → rotas.
app.add_middleware(SraAutorRouteGuardMiddleware)
app.add_middleware(SraEnsureProcessSessionMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax", https_only=False)


@app.middleware("http")
async def sra_dev_preview_nav_context(request: Request, call_next):
    """Expõe se rotas /dev de pré-visualização estão ativas (menu lateral)."""
    request.state.sra_modais_preview_allowed = dev_ui.modais_preview_allowed()
    return await call_next(request)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return response_home(request, db)


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


@app.get("/favicon.ico")
def favicon_ico():
    return FileResponse(
        str(BASE_DIR / "static" / "favicon.svg"),
        media_type="image/svg+xml",
    )


app.include_router(auth_routes.router)
app.include_router(page_routes.router)
app.include_router(rel_routes.router)
app.include_router(
    relatorio_exclusao_routes.router, prefix="/relatorios", tags=["relatorios"]
)
app.include_router(bloco_routes.router)
app.include_router(cron_admin_routes.router)
app.include_router(figura_routes.router)
app.include_router(importacao_routes.router)
app.include_router(modelos_word_routes.router)
app.include_router(notif_routes.router)
app.include_router(pdf_routes.router)
app.include_router(processos_routes.router)
app.include_router(dev_ui.router)
