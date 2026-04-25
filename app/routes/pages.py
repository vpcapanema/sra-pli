from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, load_only, selectinload
from sqlalchemy import func
from pathlib import Path
from datetime import date

from ..db import get_db
from ..models import Bloco, Figura, Relatorio, Secao, User
from ..auth import current_user
from ..sumario_extractor import listar_pdfs_disponiveis

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
    pdfs_disponiveis = listar_pdfs_disponiveis()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "relatorios": relatorios,
            "sugestao": sugestao,
            "pdfs_disponiveis": pdfs_disponiveis,
        },
    )


@router.get("/relatorios/{rel_id}")
def relatorio_detail(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    rel = (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).selectinload(Secao.responsavel),
            selectinload(Relatorio.secoes).selectinload(Secao.blocos).load_only(Bloco.id, Bloco.secao_id),
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    if not rel:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "relatorio_detail.html", {"user": user, "rel": rel}
    )


def _media_counts(db: Session, rel_id: int, sec_id: int) -> dict:
    rows = (
        db.query(Secao.id, Bloco.tipo, Bloco.conteudo)
        .join(Bloco, Bloco.secao_id == Secao.id)
        .filter(Secao.relatorio_id == rel_id)
        .all()
    )
    counts = {"fig_base": 0, "tab_base": 0, "fig_global_base": 0, "tab_global_base": 0}
    for current_sec_id, tipo, conteudo in rows:
        text = conteudo or ""
        fig_count = (1 if tipo == "figura" else 0) + text.count("[[FIGURA:")
        tab_count = (
            (1 if tipo == "tabela" else 0)
            + text.count("[[TABELA:")
            + text.count("[[TABELA|")
            + text.count("[[TABELA]]")
        )
        counts["fig_global_base"] += fig_count
        counts["tab_global_base"] += tab_count
        if current_sec_id == sec_id:
            counts["fig_base"] += fig_count
            counts["tab_base"] += tab_count
    return counts


@router.get("/relatorios/{rel_id}/secoes/{sec_id}")
def secao_edit(rel_id: int, sec_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    rel = (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).load_only(
                Secao.id,
                Secao.relatorio_id,
                Secao.numero,
                Secao.titulo,
                Secao.ordem,
            )
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    sec = (
        db.query(Secao)
        .options(selectinload(Secao.blocos).selectinload(Bloco.autor).load_only(User.id, User.nome))
        .filter(Secao.id == sec_id, Secao.relatorio_id == rel_id)
        .one_or_none()
    )
    if not rel or not sec or sec.relatorio_id != rel.id:
        return RedirectResponse("/dashboard", status_code=303)
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        return RedirectResponse(f"/relatorios/{rel.id}", status_code=303)
    figs = (
        db.query(Figura)
        .options(load_only(Figura.id, Figura.nome, Figura.relatorio_id, Figura.created_at))
        .filter(Figura.relatorio_id == rel.id)
        .order_by(Figura.created_at)
        .all()
    )
    autores = db.query(User).options(load_only(User.id, User.nome)).order_by(User.nome).all()
    media_counts = _media_counts(db, rel.id, sec.id)
    return templates.TemplateResponse(
        request,
        "secao_edit.html",
        {
            "user": user,
            "rel": rel,
            "sec": sec,
            "figuras": figs,
            "autores": autores,
            "media_counts": media_counts,
        },
    )
