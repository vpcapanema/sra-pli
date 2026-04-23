from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    relatorios = db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "relatorios": relatorios}
    )


@router.get("/relatorios/{rel_id}")
def relatorio_detail(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        "relatorio_detail.html", {"request": request, "user": user, "rel": rel}
    )


@router.get("/relatorios/{rel_id}/secoes/{sec_id}")
def secao_edit(rel_id: int, sec_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    rel = db.get(Relatorio, rel_id)
    sec = db.get(Secao, sec_id)
    if not rel or not sec or sec.relatorio_id != rel.id:
        return RedirectResponse("/dashboard", status_code=303)
    figuras = rel.id  # passamos o id; template fará lookup via endpoint /figuras
    from ..models import Figura, User
    figs = db.query(Figura).filter(Figura.relatorio_id == rel.id).order_by(Figura.created_at).all()
    autores = db.query(User).order_by(User.nome).all()
    return templates.TemplateResponse(
        "secao_edit.html",
        {"request": request, "user": user, "rel": rel, "sec": sec, "figuras": figs, "autores": autores},
    )
