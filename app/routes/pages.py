import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session, load_only, selectinload
from sqlalchemy.sql.functions import coalesce
from starlette.responses import Response
from ..db import get_db
from ..models import Bloco, Figura, Relatorio, Secao, User
from ..auth import current_user, pode_editar_perfil_usuario
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


def response_login(request: Request, error: str | None = None, status_code: int = 200) -> Response:
    return templates.TemplateResponse(
        request, "login.html", {"error": error}, status_code=status_code
    )


def response_client_goto(path: str) -> HTMLResponse:
    """Muda a URL no browser (200) sem `RedirectResponse` 3xx — útil pós-POST (login, etc.)."""
    safe_quoted = json.dumps(path)
    cont_link = "<a href=" + safe_quoted + ">Continuar</a>"
    return HTMLResponse(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        "<title>…</title></head><body>"
        f"<script>location.replace({safe_quoted})</script>"
        f"<p>Carregando… {cont_link}</p></body></html>"
    )


def response_home(request: Request, db: Session) -> Response:
    if request.session.get("user_id"):
        return response_dashboard(request, db)
    return response_login(request)


def response_dashboard(request: Request, db: Session) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
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


def response_relatorio_detail(request: Request, db: Session, rel_id: int) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
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
        return response_dashboard(request, db)
    sra_fim = request.session.pop("sra_fim_pendente", None)
    return templates.TemplateResponse(
        request, "relatorio_detail.html", {"user": user, "rel": rel, "sra_fim_pendente": sra_fim}
    )


def _media_counts(db: Session, rel_id: int, sec_id: int) -> dict:
    """Conta figuras/tabelas (próprias e inline em texto) numa única query agregada.

    Evita trazer todo o `Bloco.conteudo` para a aplicação. Funciona em Postgres
    e SQLite: usa apenas `length`/`replace` + integer division por 9/10
    (tamanho dos marcadores `[[FIGURA:`, `[[TABELA:`, `[[TABELA|`, `[[TABELA]]`).
    """
    conteudo = coalesce(Bloco.conteudo, "")
    base_len = func.length(conteudo)
    fig_in_text = (base_len - func.length(func.replace(conteudo, "[[FIGURA:", ""))) / 9
    tab_in_text_a = (base_len - func.length(func.replace(conteudo, "[[TABELA:", ""))) / 9
    tab_in_text_b = (base_len - func.length(func.replace(conteudo, "[[TABELA|", ""))) / 9
    tab_in_text_c = (base_len - func.length(func.replace(conteudo, "[[TABELA]]", ""))) / 10

    fig_per_block = case((Bloco.tipo == "figura", 1), else_=0) + fig_in_text
    tab_per_block = (
        case((Bloco.tipo == "tabela", 1), else_=0)
        + tab_in_text_a
        + tab_in_text_b
        + tab_in_text_c
    )
    fig_in_sec = case((Bloco.secao_id == sec_id, fig_per_block), else_=0)
    tab_in_sec = case((Bloco.secao_id == sec_id, tab_per_block), else_=0)

    row = (
        db.query(
            coalesce(func.sum(fig_in_sec), 0).label("fig_base"),
            coalesce(func.sum(tab_in_sec), 0).label("tab_base"),
            coalesce(func.sum(fig_per_block), 0).label("fig_global_base"),
            coalesce(func.sum(tab_per_block), 0).label("tab_global_base"),
        )
        .select_from(Bloco)
        .join(Secao, Secao.id == Bloco.secao_id)
        .filter(Secao.relatorio_id == rel_id)
        .one()
    )
    return {
        "fig_base": int(row.fig_base or 0),
        "tab_base": int(row.tab_base or 0),
        "fig_global_base": int(row.fig_global_base or 0),
        "tab_global_base": int(row.tab_global_base or 0),
    }


def response_secao_edit(request: Request, db: Session, rel_id: int, sec_id: int) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
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
        return response_dashboard(request, db)
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        return response_relatorio_detail(request, db, rel.id)
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


def response_usuarios(
    request: Request, db: Session, error: str | None = None
) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
    usuarios = db.query(User).order_by(User.nome).all()
    return templates.TemplateResponse(
        request, "usuarios.html", {"user": user, "usuarios": usuarios, "error": error}
    )


def response_usuario_edit(
    request: Request,
    db: Session,
    user_id: int,
    *,
    ok: str | None = None,
    error: str | None = None,
) -> Response:
    viewer = current_user(request, db)
    if not viewer:
        return response_login(request)
    alvo = db.get(User, user_id)
    if not alvo:
        return response_usuarios(request, db)
    if not pode_editar_perfil_usuario(viewer, alvo):
        return response_usuarios(request, db)
    ok_effective = ok if ok is not None else request.query_params.get("ok")
    return templates.TemplateResponse(
        request,
        "usuario_edit.html",
        {"user": viewer, "alvo": alvo, "error": error, "ok": ok_effective},
    )


def user_or_login_page(
    request: Request, db: Session
) -> tuple[User, None] | tuple[None, Response]:
    """Sem HTTP redirect: devolve a página de login (200) se não houver sessão."""
    u = current_user(request, db)
    if not u:
        return None, response_login(request)
    return u, None


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    return response_dashboard(request, db)


@router.get("/relatorios/{rel_id}")
def relatorio_detail(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return response_relatorio_detail(request, db, rel_id)


@router.get("/relatorios/{rel_id}/secoes/{sec_id}")
def secao_edit(rel_id: int, sec_id: int, request: Request, db: Session = Depends(get_db)):
    return response_secao_edit(request, db, rel_id, sec_id)
