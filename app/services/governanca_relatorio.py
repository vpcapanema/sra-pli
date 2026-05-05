"""Governança técnica do relatório (lógica das rotas em ``routes/governanca_relatorio.py``).

Este módulo orquestra as regras já isoladas em ``services/governanca/*``
(pasta de sub-serviços) e concentra a camada HTTP: resposta HTML, redirects,
checagem de viewer e formatação de URLs de erro.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from ..models import EntregaRelatorio, User
from ..notificacoes.ciclo_params import try_salvar_parametros_ciclo_form_post_campos
from .pages import templates
from .governanca.acesso_permissoes import (
    coordenador_admin_ou_login,
    pode_editar_usuario_governanca,
)
from .governanca.contexto_pagina import montar_contexto_governanca
from .governanca.entregas_edicao import (
    DadosEdicaoEntrega,
    salvar_entrega_governanca,
)
from .governanca.execucao_manual_jobs import (
    TIPOS_NOTIFICACAO_MANUAL,
    executar_abrir_periodo_manual,
    executar_notificacao_manual,
    executar_retry_manual,
)
from .governanca.redirecionamentos import redirect_governanca
from .governanca.usuarios_edicao import (
    DadosEdicaoUsuario,
    alternar_notificacoes_relatorio,
    salvar_usuario_governanca,
)


def _viewer_ou_resposta(
    request: Request, db: Session
) -> tuple[User | None, object | None]:
    user, resposta = coordenador_admin_ou_login(request, db)
    return user, resposta


def governanca_relatorio_page(request: Request, db: Session):
    user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    assert user is not None
    return templates.TemplateResponse(
        request,
        "complementos/governanca_relatorio.html",
        montar_contexto_governanca(request, db, user),
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def governanca_salvar_parametros_ciclo(
    request: Request,
    db: Session,
    *,
    ciclo_dia_prev: str,
    ciclo_dia_atual: str,
    prazo_autor: str,
    prazo_coord: str,
    dias_lembrete_csv: str,
    dia_ultima: str,
    dia_abertura: str,
    hora_aber: str,
    hora_lem: str,
    hora_ret: str,
    observacoes: str,
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    erro = try_salvar_parametros_ciclo_form_post_campos(
        db,
        ciclo_dia_prev=ciclo_dia_prev,
        ciclo_dia_atual=ciclo_dia_atual,
        prazo_autor=prazo_autor,
        prazo_coord=prazo_coord,
        dias_lembrete_csv=dias_lembrete_csv,
        dia_ultima=dia_ultima,
        dia_abertura=dia_abertura,
        hora_aber=hora_aber,
        hora_lem=hora_lem,
        hora_ret=hora_ret,
        observacoes=observacoes,
    )
    if erro:
        destino = f"/governanca-relatorio?erro={quote(erro)}"
        return RedirectResponse(url=destino, status_code=303)
    return redirect_governanca("ciclo")


# pylint: disable=too-many-arguments,too-many-positional-arguments
def governanca_entrega_salvar(
    entrega_id: int,
    request: Request,
    db: Session,
    *,
    status: str,
    data_envio: str,
    data_validacao: str,
    validado_por_id: str,
    relatorio_filtro_id: str,
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    entrega = db.get(EntregaRelatorio, entrega_id)
    if not entrega:
        raise HTTPException(404, detail="Entrega não encontrada.")
    erro = salvar_entrega_governanca(
        db,
        entrega,
        request,
        DadosEdicaoEntrega(
            status=status,
            data_envio=data_envio,
            data_validacao=data_validacao,
            validado_por_id=validado_por_id,
        ),
    )
    if erro:
        destino = (
            f"/governanca-relatorio?erro={erro}"
            f"&relatorio_id={quote(relatorio_filtro_id)}"
        )
        return RedirectResponse(url=destino, status_code=303)
    return redirect_governanca("entrega", relatorio_filtro_id)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def governanca_usuario_salvar(
    user_id: int,
    request: Request,
    db: Session,
    *,
    nome: str,
    email: str,
    email2: str,
    role: str,
    notificacoes_ativas: str,
):
    viewer, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    assert viewer is not None
    alvo = db.get(User, user_id)
    if not alvo:
        raise HTTPException(404, detail="Utilizador não encontrado.")
    erro = salvar_usuario_governanca(
        request,
        db,
        viewer,
        alvo,
        DadosEdicaoUsuario(
            nome=nome,
            email=email,
            email2=email2,
            role=role,
            notificacoes_ativas=notificacoes_ativas,
        ),
    )
    if erro:
        return RedirectResponse(
            url=f"/governanca-relatorio?erro={erro}",
            status_code=303,
        )
    return redirect_governanca("usuario")


def governanca_toggle_relatorio_user(
    user_id: int, request: Request, db: Session
):
    viewer, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    assert viewer is not None
    alvo = db.get(User, user_id)
    if not alvo:
        raise HTTPException(404, detail="Usuário não encontrado.")
    if not pode_editar_usuario_governanca(viewer, alvo):
        return RedirectResponse(
            url=(
                "/governanca-relatorio?erro=sem+permissao+para+este+utilizador"
                "#ss-usuarios-notificados"
            ),
            status_code=303,
        )
    alternar_notificacoes_relatorio(alvo)
    db.commit()
    return RedirectResponse(
        url="/governanca-relatorio?ok=toggle#ss-usuarios-notificados",
        status_code=303,
    )


def governanca_testar_abrir_periodo(
    request: Request,
    db: Session,
    *,
    force: str,
    base_relatorio_id: str,
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    executar_abrir_periodo_manual(
        request,
        db,
        force=force,
        base_relatorio_id=base_relatorio_id,
    )
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )


def governanca_testar_notificar(
    request: Request,
    db: Session,
    *,
    tipo: str,
    relatorio_id: int,
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    if tipo not in TIPOS_NOTIFICACAO_MANUAL:
        return RedirectResponse(
            url=(
                "/governanca-relatorio?erro=tipo+de+notificacao+invalido"
                "#ss-testar-sistema"
            ),
            status_code=303,
        )
    executar_notificacao_manual(
        request, db, tipo=tipo, relatorio_id=relatorio_id
    )
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )


def governanca_testar_retry(request: Request, db: Session):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    executar_retry_manual(request, db)
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )
