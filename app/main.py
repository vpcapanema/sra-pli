from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from .config import settings
from .bootstrap import init_db
from .routes import auth as auth_routes
from .routes import pages as page_routes
from .routes import relatorios as rel_routes
from .routes import blocos as bloco_routes
from .routes import figuras as figura_routes
from .routes import pdf as pdf_routes

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax", https_only=False)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/")
def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


app.include_router(auth_routes.router)
app.include_router(page_routes.router)
app.include_router(rel_routes.router)
app.include_router(bloco_routes.router)
app.include_router(figura_routes.router)
app.include_router(pdf_routes.router)
