from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .bootstrap import init_db
from .routes import auth as auth_routes
from .routes import pages as page_routes
from .routes import relatorios as rel_routes
from .routes import blocos as bloco_routes
from .routes import figuras as figura_routes
from .routes import importacao as importacao_routes
from .routes import pdf as pdf_routes
from .routes import processos as processos_routes
from .routes import dev_ui
from .routes.pages import response_home
from .process_events import configure_logging_bridge

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    configure_logging_bridge()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax", https_only=False)

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
app.include_router(bloco_routes.router)
app.include_router(figura_routes.router)
app.include_router(importacao_routes.router)
app.include_router(pdf_routes.router)
app.include_router(processos_routes.router)
app.include_router(dev_ui.router)
