from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path
from datetime import date

from ..db import get_db
from ..models import Relatorio, Secao
from ..auth import current_user

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Última medição já produzida fora do sistema; próximo sugerido = NUMERO_BASE + 1.
NUMERO_BASE = 14


def _sugestao_proximo_relatorio(db: Session) -> dict:
    hoje = date.today()
    # Período: dia 11 do mês anterior → dia 11 do mês atual.
    if hoje.month == 1:
        ini = date(hoje.year - 1, 12, 11)
    else:
        ini = date(hoje.year, hoje.month - 1, 11)
    fim = date(hoje.year, hoje.month, 11)

    # Próximo número de medição.
    max_num = db.query(func.max(Relatorio.numero_medicao)).scalar() or NUMERO_BASE
    proximo = max_num + 1
    return {
        "codigo": f"D20-{proximo}",
        "titulo": f"Relatório Mensal D20-{proximo}",
        "mes_referencia": f"{MESES_PT[fim.month - 1]}/{fim.year}",
        "periodo_inicio": ini.isoformat(),
        "periodo_fim": fim.isoformat(),
        "numero_medicao": proximo,
    }


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    relatorios = db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    sugestao = _sugestao_proximo_relatorio(db)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "relatorios": relatorios, "sugestao": sugestao},
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
