"""Helpers de resposta HTML compartilhados por várias rotas.

Nome espelha ``routes/pages.py``. Concentra:

* templates Jinja configurados com filtros/globais do projeto;
* funções ``response_*`` que renderizam páginas (dashboard, relatório,
  seção, usuários, edição de usuário, upload);
* gates de autenticação reutilizáveis (``user_or_login_page``,
  ``user_coord_ou_admin_ou_login``, ``usuario_edit_precheck``);
* atalhos de redirecionamento (``response_client_goto``,
  ``url_hub_autor``).

Rotas puras permanecem em ``app/routes/pages.py`` e chamam estes helpers.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload, load_only, selectinload
from sqlalchemy.sql.functions import coalesce
from starlette.responses import RedirectResponse, Response

from ..auth import current_user, pode_editar_perfil_usuario
from ..docx_clone_extractor import listar_docx_disponiveis
from ..jinja_filters import registrar as _registrar_filtros_jinja
from ..jinja_filters import registrar_globais as _registrar_globais_jinja
from ..models import Bloco, Figura, Relatorio, Secao, User
from ..modo_edicao_blocos import modo_edicao_coordenador_rel
from ..notificacoes.ciclo_params import (
    obter_parametros_ciclo,
    periodo_referente_para_data,
)
from ..numeracao import chave_numero, secao_ids_na_subarvore
from ..sumario_extractor import listar_pdfs_disponiveis

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)
_registrar_filtros_jinja(templates.env.filters)
_registrar_globais_jinja(templates.env)

MESES_PT = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

# Última medição já produzida fora do sistema; próximo sugerido = NUMERO_BASE + 1.
NUMERO_BASE = 14


def url_hub_autor(db: Session) -> str | None:
    """Caminho ``/relatorios/{id}`` do relatório mais recente (entrada do autor)."""
    rel = db.query(Relatorio).order_by(Relatorio.created_at.desc()).first()
    if rel is None:
        return None
    return f"/relatorios/{rel.id}"


def _sugestao_proximo_relatorio(
    db: Session,
    relatorios: list[Relatorio] | None = None,
) -> dict:
    hoje = date.today()
    par = obter_parametros_ciclo(db)
    per = periodo_referente_para_data(hoje, par)

    # Próximo número de medição (evita segundo SELECT quando já temos a lista).
    if relatorios is not None:
        nums = [
            r.numero_medicao
            for r in relatorios
            if r.numero_medicao is not None
        ]
        max_num = max(nums) if nums else NUMERO_BASE
    else:
        max_num = (
            db.query(func.max(Relatorio.numero_medicao)).scalar() or NUMERO_BASE
        )
    proximo = max_num + 1
    return {
        "codigo": f"D20-{proximo}",
        "titulo": f"Relatório Mensal D20-{proximo}",
        "mes_referencia": per["mes_referencia"],
        "periodo_inicio": per["periodo_inicio"].isoformat(),
        "periodo_fim": per["periodo_fim"].isoformat(),
        "numero_medicao": proximo,
    }


def response_login(
    request: Request,
    error: str | None = None,
    notice: str | None = None,
    role: str | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "complementos/login.html",
        {"error": error, "notice": notice, "role": role},
        status_code=status_code,
    )


def user_coord_ou_admin_ou_login(
    request: Request, db: Session
) -> User | Response:
    """Sessão obrigatória; apenas coordenador ou admin (403 caso contrário)."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(
            403,
            detail="Acesso restrito a coordenador/admin.",
        )
    return user


def response_client_goto(path: str) -> HTMLResponse:
    """HTML de troca de URL (200) sem 3xx — padrão interno pós-POST (login)."""
    safe_quoted = json.dumps(path)
    cont_link = "<a href=" + safe_quoted + ">Continuar</a>"
    return HTMLResponse(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        "<title>…</title></head><body>"
        f"<script>location.replace({safe_quoted})</script>"
        f"<p>Carregando… {cont_link}</p></body></html>"
    )


def response_home(request: Request, db: Session) -> Response:
    if not request.session.get("user_id"):
        return response_login(request)
    user = current_user(request, db)
    if user and user.role == "autor":
        hub = url_hub_autor(db)
        if hub:
            return RedirectResponse(url=hub, status_code=303)
        return response_painel_upload(request, db)
    return response_dashboard(request, db)


def response_dashboard(request: Request, db: Session) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
    relatorios = (
        db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    )
    sugestao = _sugestao_proximo_relatorio(db, relatorios)
    pdfs_disponiveis = listar_pdfs_disponiveis()
    docxs_disponiveis = listar_docx_disponiveis()
    return templates.TemplateResponse(
        request,
        "complementos/dashboard.html",
        {
            "user": user,
            "relatorios": relatorios,
            "sugestao": sugestao,
            "pdfs_disponiveis": pdfs_disponiveis,
            "docxs_disponiveis": docxs_disponiveis,
        },
    )


def response_painel_upload(request: Request, db: Session) -> Response:
    """Redireciona ao sumário do relatório mais recente (hub do grupo upload)."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = db.query(Relatorio).order_by(Relatorio.created_at.desc()).first()
    if not rel:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url=f"/relatorios/{rel.id}", status_code=303)


def response_relatorio_detail(
    request: Request, db: Session, rel_id: int
) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
    rel = (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).selectinload(Secao.responsavel),
            selectinload(Relatorio.secoes)
            .selectinload(Secao.blocos)
            .load_only(Bloco.id, Bloco.secao_id),
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    if not rel:
        return response_dashboard(request, db)
    return templates.TemplateResponse(
        request,
        "complementos/relatorio_detail.html",
        {"user": user, "rel": rel},
    )


def _media_counts(
    db: Session, rel_id: int, sec_ids_escopo: set[int]
) -> dict:
    """Conta figuras/tabelas (próprias e inline em texto) em uma query agregada.

    Evita trazer ``Bloco.conteudo`` inteiro à aplicação; funciona em Postgres
    e SQLite via ``length``/``replace`` + divisão inteira por 9/10 (tamanho
    dos marcadores ``[[FIGURA:``, ``[[TABELA:``, ``[[TABELA|``,
    ``[[TABELA]]``).
    """
    conteudo = coalesce(Bloco.conteudo, "")
    base_len = func.length(conteudo)
    fig_in_text = (
        base_len - func.length(func.replace(conteudo, "[[FIGURA:", ""))
    ) / 9
    tab_in_text_a = (
        base_len - func.length(func.replace(conteudo, "[[TABELA:", ""))
    ) / 9
    tab_in_text_b = (
        base_len - func.length(func.replace(conteudo, "[[TABELA|", ""))
    ) / 9
    tab_in_text_c = (
        base_len - func.length(func.replace(conteudo, "[[TABELA]]", ""))
    ) / 10

    fig_per_block = case((Bloco.tipo == "figura", 1), else_=0) + fig_in_text
    tab_per_block = (
        case((Bloco.tipo == "tabela", 1), else_=0)
        + tab_in_text_a
        + tab_in_text_b
        + tab_in_text_c
    )
    ids_escopo_sql = sec_ids_escopo if sec_ids_escopo else {-1}
    fig_in_sec = case(
        (Bloco.secao_id.in_(ids_escopo_sql), fig_per_block), else_=0
    )
    tab_in_sec = case(
        (Bloco.secao_id.in_(ids_escopo_sql), tab_per_block), else_=0
    )

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


def _response_secao_page(
    request: Request,
    db: Session,
    rel_id: int,
    sec_id: int,
    template_name: str,
) -> Response:
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
                Secao.responsavel_id,
            ),
            selectinload(Relatorio.secoes)
            .selectinload(Secao.responsavel)
            .load_only(User.id, User.nome),
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    sec = (
        db.query(Secao)
        .options(
            selectinload(Secao.responsavel).load_only(User.id, User.nome),
        )
        .filter(Secao.id == sec_id, Secao.relatorio_id == rel_id)
        .one_or_none()
    )
    if not rel or not sec or sec.relatorio_id != rel.id:
        return response_dashboard(request, db)
    if (
        user.role == "autor"
        and sec.responsavel_id is not None
        and sec.responsavel_id != user.id
    ):
        return response_relatorio_detail(request, db, rel.id)
    figs = (
        db.query(Figura)
        .options(
            load_only(
                Figura.id, Figura.nome, Figura.relatorio_id, Figura.created_at
            )
        )
        .filter(Figura.relatorio_id == rel.id)
        .order_by(Figura.created_at)
        .all()
    )
    autores = (
        db.query(User).options(load_only(User.id, User.nome)).order_by(User.nome).all()
    )
    sec_ids_escopo = secao_ids_na_subarvore(rel.secoes, sec.numero or "")
    media_counts = _media_counts(db, rel.id, sec_ids_escopo)
    escopo_sql = sec_ids_escopo if sec_ids_escopo else {-1}
    blocos_escopo = (
        db.query(Bloco)
        .options(joinedload(Bloco.autor), joinedload(Bloco.secao))
        .join(Secao, Secao.id == Bloco.secao_id)
        .filter(Secao.relatorio_id == rel.id, Secao.id.in_(escopo_sql))
        .all()
    )
    blocos_escopo.sort(
        key=lambda b: (
            chave_numero(b.secao.numero if b.secao else ""),
            b.ordem or 0,
            b.id,
        )
    )
    preview_url = f"/relatorios/{rel.id}/preview?" + "&".join(
        f"secao_ids={sid}" for sid in sorted(sec_ids_escopo)
    )
    # "Upado" = qualquer bloco cuja origem NÃO seja clone/importação do DOCX/PDF.
    origens_clonadas = {"clonado", "docx_import", "pdf_import"}
    sec_tem_upload = any(
        (b.origem or "manual") not in origens_clonadas for b in blocos_escopo
    )
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "user": user,
            "rel": rel,
            "sec": sec,
            "figuras": figs,
            "autores": autores,
            "media_counts": media_counts,
            "modo_edicao_blocos": modo_edicao_coordenador_rel(
                request, user, rel.id
            ),
            "mostrar_botao_modo_edicao": user.role == "coordenador",
            "blocos_escopo": blocos_escopo,
            "sec_ids_subarvore": sec_ids_escopo,
            "preview_url": preview_url,
            "sec_tem_upload": sec_tem_upload,
        },
    )


def response_conteudo_upload(
    request: Request, db: Session, rel_id: int, sec_id: int
) -> Response:
    """Gestão da secção: coordenação, importação assistida, blocos e editor."""
    return _response_secao_page(
        request,
        db,
        rel_id,
        sec_id,
        "complementos/secao_edit_conteudo_upload.html",
    )


def response_usuarios(
    request: Request, db: Session, error: str | None = None
) -> Response:
    user = current_user(request, db)
    if not user:
        return response_login(request)
    usuarios = db.query(User).order_by(User.nome).all()
    return templates.TemplateResponse(
        request,
        "complementos/usuarios.html",
        {"user": user, "usuarios": usuarios, "error": error},
    )


def usuario_edit_precheck(
    request: Request, db: Session, user_id: int
) -> Response | tuple[User, User]:
    """Sessão válida e permissão para editar ``user_id``; senão página de erro."""
    viewer = current_user(request, db)
    if not viewer:
        return response_login(request)
    alvo = db.get(User, user_id)
    if not alvo:
        return response_usuarios(request, db)
    if not pode_editar_perfil_usuario(viewer, alvo):
        return response_usuarios(request, db)
    return viewer, alvo


def response_usuario_edit(
    request: Request,
    db: Session,
    user_id: int,
    *,
    ok: str | None = None,
    error: str | None = None,
) -> Response:
    pre = usuario_edit_precheck(request, db, user_id)
    if isinstance(pre, Response):
        return pre
    viewer, alvo = pre
    ok_effective = ok if ok is not None else request.query_params.get("ok")
    return templates.TemplateResponse(
        request,
        "complementos/usuario_edit.html",
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
