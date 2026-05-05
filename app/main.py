from contextlib import asynccontextmanager
from logging import getLogger
from time import perf_counter
from datetime import datetime
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
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
from .routes import dev_ui
from .services import dev_ui as dev_ui_service
from .routes import governanca_relatorio as governanca_relatorio_routes
from .routes import sendgrid_events as sendgrid_events_routes
from .routes import mapa_aplicacao as mapa_aplicacao_routes
from .routes import validacao_revisao as validacao_revisao_routes
from .services.pages import response_home
from .access_control import SraAutorRouteGuardMiddleware

BASE_DIR = Path(__file__).parent

_HTTP_AUDIT_LOG = getLogger("app.http")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


@app.middleware("http")
async def sra_http_audit_log(request: Request, call_next):
    """Regista duração de pedidos nas áreas de relatório, utilizadores e upload (nível INFO)."""
    path = request.url.path
    instrumentar = (
        path.startswith("/relatorios")
        or path.startswith("/usuarios")
        or path.endswith("/upload-conteudo")
        or ("/importar/" in path)
        or ("/relatorios/" in path)
    )
    if not instrumentar or path.startswith("/static/"):
        return await call_next(request)
    t0 = perf_counter()
    response = await call_next(request)
    ms = (perf_counter() - t0) * 1000
    code = getattr(response, "status_code", "?")
    _HTTP_AUDIT_LOG.info("%s %s → %s (%.0f ms)", request.method, path, code, ms)
    return response


@app.middleware("http")
async def sra_dev_preview_nav_context(request: Request, call_next):
    """Expõe se rotas /dev de pré-visualização estão ativas (menu lateral)."""
    request.state.sra_modais_preview_allowed = dev_ui_service.modais_preview_allowed()
    return await call_next(request)


@app.middleware("http")
async def sra_hub_sidebar_context(request: Request, call_next):
    """IDs do relatório mais recente + primeira secção (ordem) para a sidebar.

    Evita links ``/painel-upload#…`` que perdem o fragmento após redirecionamento
    3xx e permite âncoras corretas em páginas sem ``rel`` no contexto do template.
    """
    request.state.sra_hub_rel_id = None
    request.state.sra_hub_primeira_secao_id = None
    path = request.url.path
    if request.method == "GET" and request.session.get("user_id") and not path.startswith("/static"):
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    """
                    SELECT r.id, (
                        SELECT s.id FROM secoes s
                        WHERE s.relatorio_id = r.id
                        ORDER BY s.ordem, s.id
                        LIMIT 1
                    )
                    FROM relatorios r
                    ORDER BY r.created_at DESC
                    LIMIT 1
                    """
                )
            ).first()
            if row and row[0] is not None:
                request.state.sra_hub_rel_id = int(row[0])
                if row[1] is not None:
                    request.state.sra_hub_primeira_secao_id = int(row[1])
        finally:
            db.close()
    return await call_next(request)


# Depois de todos os @app.middleware("http"): insert(0) empurra para o início de user_middleware;
# assim SessionMiddleware e SraAutor ficam mais externos que os BaseHTTPMiddleware acima.
app.add_middleware(SraAutorRouteGuardMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.SESSION_COOKIE_SECURE,
)

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


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_config():
    """Retorna configuração para Chrome DevTools Remote Debugging."""
    return {
        "port": 9222,
        "version": "1.0",
    }


app.include_router(auth_routes.router)
app.include_router(governanca_relatorio_routes.router)
app.include_router(page_routes.router)
app.include_router(mapa_aplicacao_routes.router)
app.include_router(rel_routes.router)
app.include_router(relatorio_exclusao_routes.router, prefix="/relatorios", tags=["relatorios"])
app.include_router(bloco_routes.router)
app.include_router(cron_admin_routes.router)
app.include_router(sendgrid_events_routes.router)
app.include_router(figura_routes.router)
app.include_router(importacao_routes.router)
app.include_router(modelos_word_routes.router)
app.include_router(notif_routes.router)
app.include_router(pdf_routes.router)
app.include_router(validacao_revisao_routes.router)
app.include_router(dev_ui.router)
