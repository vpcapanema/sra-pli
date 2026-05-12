from contextlib import asynccontextmanager
from logging import getLogger
from time import perf_counter
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db
from .bootstrap import init_db
from .rate_limit import limiter, rate_limit_handler
from slowapi.errors import RateLimitExceeded
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
from .routes import revisao_edicao as revisao_edicao_routes
from .routes import central_notificacoes as central_notificacoes_routes
from .routes import alertas_api as alertas_api_routes
from .services.pages import response_home
from .access_control import SraAutorRouteGuardMiddleware

BASE_DIR = Path(__file__).parent

_HTTP_AUDIT_LOG = getLogger("app.http")


# Cache em memoria para o sidebar (ultimo relatorio + primeira secao).
# Essa info quase nao muda: so quando um novo relatorio e criado ou a
# primeira secao de um relatorio e reordenada. TTL curto (30s) garante
# consistencia aceitavel sem pagar ~190ms de RTT Postgres por request.
_sidebar_cache_lock = __import__("threading").Lock()
_sidebar_cache: dict = {"ts": 0.0, "rel_id": None, "sec_id": None}
_SIDEBAR_CACHE_TTL = 30.0  # segundos


def _sidebar_cache_get() -> tuple[int | None, int | None] | None:
    """Retorna (rel_id, sec_id) se cache valido, senao None."""
    with _sidebar_cache_lock:
        if perf_counter() - _sidebar_cache["ts"] < _SIDEBAR_CACHE_TTL:
            return _sidebar_cache["rel_id"], _sidebar_cache["sec_id"]
    return None


def _sidebar_cache_set(rel_id: int | None, sec_id: int | None) -> None:
    with _sidebar_cache_lock:
        _sidebar_cache["ts"] = perf_counter()
        _sidebar_cache["rel_id"] = rel_id
        _sidebar_cache["sec_id"] = sec_id


def sidebar_cache_invalidate() -> None:
    """Invalidacao explicita: chamar apos criar/remover relatorios ou
    reordenar secoes. Proxima request recarregara do banco."""
    with _sidebar_cache_lock:
        _sidebar_cache["ts"] = 0.0


# Sentry: ativa apenas se SENTRY_DSN estiver configurado.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,
        )
    except Exception:  # noqa: BLE001
        getLogger("app.sentry").exception(
            "Falha ao inicializar Sentry; seguindo sem ele"
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
    except Exception:  # noqa: BLE001
        # Falha de DDL nao deve derrubar o processo em loop no healthcheck.
        # Log estruturado e app sobe; rotas que dependem do schema iram falhar
        # de forma observavel, em vez do container reiniciar para sempre.
        getLogger("app.bootstrap").exception(
            "init_db falhou; app subira mesmo assim"
        )
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Rate-limit (slowapi). As decoracoes @limiter.limit nas rotas exigem
# que o limiter esteja em app.state e que o handler 429 esteja registrado.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


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
    _HTTP_AUDIT_LOG.info(
        "%s %s → %s (%.0f ms)", request.method, path, code, ms
    )
    return response


@app.middleware("http")
async def sra_dev_preview_nav_context(request: Request, call_next):
    """Expõe se rotas /dev de pré-visualização estão ativas (menu lateral)."""
    request.state.sra_modais_preview_allowed = (
        dev_ui_service.modais_preview_allowed()
    )
    return await call_next(request)


@app.middleware("http")
async def sra_hub_sidebar_context(request: Request, call_next):
    """IDs do relatório mais recente + primeira secção (ordem) para a sidebar.

    Evita links ``/painel-upload#…`` que perdem o fragmento após redirecionamento
    3xx e permite âncoras corretas em páginas sem ``rel`` no contexto do template.

    Perf: cache em memória com TTL curto para evitar abrir uma segunda conexão
    ao Postgres em CADA request autenticado (economia ~190ms/request).
    """
    request.state.sra_hub_rel_id = None
    request.state.sra_hub_primeira_secao_id = None
    path = request.url.path
    if (
        request.method == "GET"
        and request.session.get("user_id")
        and not path.startswith("/static")
    ):
        cached = _sidebar_cache_get()
        if cached is not None:
            rel_id, sec_id = cached
        else:
            db = SessionLocal()
            try:
                row = db.execute(text("""
                        SELECT r.id, (
                            SELECT s.id FROM secoes s
                            WHERE s.relatorio_id = r.id
                            ORDER BY s.ordem, s.id
                            LIMIT 1
                        )
                        FROM relatorios r
                        ORDER BY r.created_at DESC
                        LIMIT 1
                        """)).first()
            except SQLAlchemyError:
                getLogger("app.sidebar").exception(
                    "Falha ao carregar contexto da sidebar"
                )
                row = None
            finally:
                db.close()
            rel_id = int(row[0]) if row and row[0] is not None else None
            sec_id = int(row[1]) if row and row[1] is not None else None
            _sidebar_cache_set(rel_id, sec_id)
        request.state.sra_hub_rel_id = rel_id
        request.state.sra_hub_primeira_secao_id = sec_id
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

app.mount(
    "/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static"
)


_ERROR_LOG = getLogger("app.error")


def _erro_html(titulo: str, mensagem: str, status: int) -> HTMLResponse:
    cabecalho_h1 = f"<h{1}>{titulo}</h{1}>"
    html = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<title>{titulo} · SRA</title>"
        "<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;"
        "max-width:640px;margin:12vh auto;padding:0 24px;color:#1f2937}"
        "h1{font-size:1.5rem;margin-bottom:.5rem}"
        "p{color:#4b5563;line-height:1.5}"
        "a{color:#1d4ed8;text-decoration:none}</style></head><body>"
        + cabecalho_h1
        + "\n"
        f"<p>{mensagem}</p>"
        '<p><a href="/">Voltar ao início</a></p>'
        "</body></html>"
    )
    return HTMLResponse(html, status_code=status)


@app.exception_handler(HTTPException)
async def sra_http_exception_handler(request: Request, exc: HTTPException):
    # Preserva 3xx (redirects) e respostas estruturadas para APIs/JSON.
    if exc.status_code < 400 or request.url.path.startswith("/admin/cron"):
        raise exc
    if exc.status_code == 404:
        return _erro_html(
            "Página não encontrada",
            "O recurso solicitado não existe ou foi movido.",
            404,
        )
    if exc.status_code == 403:
        return _erro_html(
            "Acesso negado",
            "Você não tem permissão para acessar este recurso.",
            403,
        )
    if exc.status_code == 401:
        return _erro_html(
            "Sessão expirada", "Faça login novamente para continuar.", 401
        )


@app.exception_handler(Exception)
async def sra_unhandled_exception_handler(request: Request, exc: Exception):
    _ERROR_LOG.exception("unhandled: %s %s", request.method, request.url.path)
    return _erro_html(
        "Erro interno",
        "Ocorreu uma falha ao processar sua solicitação. A equipe técnica já foi notificada.",
        500,
    )


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return response_home(request, db)


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


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
app.include_router(central_notificacoes_routes.router)
app.include_router(alertas_api_routes.router)
app.include_router(governanca_relatorio_routes.router)
app.include_router(page_routes.router)
app.include_router(mapa_aplicacao_routes.router)
app.include_router(rel_routes.router)
app.include_router(
    relatorio_exclusao_routes.router, prefix="/relatorios", tags=["relatorios"]
)
app.include_router(bloco_routes.router)
app.include_router(cron_admin_routes.router)
app.include_router(sendgrid_events_routes.router)
app.include_router(figura_routes.router)
app.include_router(importacao_routes.router)
app.include_router(modelos_word_routes.router)
app.include_router(notif_routes.router)
app.include_router(pdf_routes.router)
app.include_router(revisao_edicao_routes.router)
app.include_router(dev_ui.router)
