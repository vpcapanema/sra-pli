"""Rotas da governança técnica do relatório."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from ..db import get_db
from ..models import EntregaRelatorio, User
from ..notificacoes.ciclo_params import try_salvar_parametros_ciclo_form_post_campos
from ..services.governanca.acesso_permissoes import (
    coordenador_admin_ou_login,
    pode_editar_usuario_governanca,
)
from ..services.governanca.contexto_pagina import montar_contexto_governanca
from ..services.governanca.entregas_edicao import (
    DadosEdicaoEntrega,
    salvar_entrega_governanca,
)
from ..services.governanca.execucao_manual_jobs import (
    TIPOS_NOTIFICACAO_MANUAL,
    executar_abrir_periodo_manual,
    executar_notificacao_manual,
    executar_retry_manual,
)
from ..services.governanca.redirecionamentos import redirect_governanca
from ..services.governanca.usuarios_edicao import (
    DadosEdicaoUsuario,
    alternar_notificacoes_relatorio,
    salvar_usuario_governanca,
)
from .pages import templates

router = APIRouter(tags=["governanca"])


def _viewer_ou_resposta(request: Request, db: Session) -> tuple[User | None, object | None]:
    user, resposta = coordenador_admin_ou_login(request, db)
    return user, resposta


@router.get("/governanca-relatorio")
def governanca_relatorio_page(request: Request, db: Session = Depends(get_db)):
    user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    assert user is not None
    return templates.TemplateResponse(
        request,
        "complementos/governanca_relatorio.html",
        montar_contexto_governanca(request, db, user),
    )


@router.post("/governanca-relatorio/parametros-ciclo")
def governanca_salvar_parametros_ciclo(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    request: Request,
    db: Session = Depends(get_db),
    ciclo_dia_prev: str = Form(""),
    ciclo_dia_atual: str = Form(""),
    prazo_autor: str = Form(""),
    prazo_coord: str = Form(""),
    dias_lembrete_csv: str = Form(""),
    dia_ultima: str = Form(""),
    dia_abertura: str = Form(""),
    hora_aber: str = Form(""),
    hora_lem: str = Form(""),
    hora_ret: str = Form(""),
    observacoes: str = Form(""),
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


@router.post("/governanca-relatorio/entrega/{entrega_id}")
def governanca_entrega_salvar(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Form(...),
    data_envio: str = Form(""),
    data_validacao: str = Form(""),
    validado_por_id: str = Form(""),
    relatorio_filtro_id: str = Form(""),
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
        destino = f"/governanca-relatorio?erro={erro}&relatorio_id={quote(relatorio_filtro_id)}"
        return RedirectResponse(url=destino, status_code=303)
    return redirect_governanca("entrega", relatorio_filtro_id)


@router.post("/governanca-relatorio/usuario/{user_id}")
def governanca_usuario_salvar(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(...),
    role: str = Form(""),
    notificacoes_ativas: str = Form("1"),
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
        return RedirectResponse(url=f"/governanca-relatorio?erro={erro}", status_code=303)
    return redirect_governanca("usuario")


@router.post("/governanca-relatorio/usuario/{user_id}/toggle-relatorio")
def governanca_toggle_relatorio_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
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
            url="/governanca-relatorio?erro=sem+permissao+para+este+utilizador#ss-usuarios-notificados",
            status_code=303,
        )
    alternar_notificacoes_relatorio(alvo)
    db.commit()
    return RedirectResponse(
        url="/governanca-relatorio?ok=toggle#ss-usuarios-notificados",
        status_code=303,
    )


@router.post("/governanca-relatorio/testar/abrir-periodo")
def governanca_testar_abrir_periodo(
    request: Request,
    db: Session = Depends(get_db),
    force: str = Form("1"),
    base_relatorio_id: str = Form(""),
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
    return RedirectResponse(url="/governanca-relatorio#ss-testar-sistema", status_code=303)


@router.post("/governanca-relatorio/testar/notificar")
def governanca_testar_notificar(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str = Form(...),
    relatorio_id: int = Form(...),
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    if tipo not in TIPOS_NOTIFICACAO_MANUAL:
        return RedirectResponse(
            url="/governanca-relatorio?erro=tipo+de+notificacao+invalido#ss-testar-sistema",
            status_code=303,
        )
    executar_notificacao_manual(request, db, tipo=tipo, relatorio_id=relatorio_id)
    return RedirectResponse(url="/governanca-relatorio#ss-testar-sistema", status_code=303)


@router.post("/governanca-relatorio/testar/retry")
def governanca_testar_retry(
    request: Request,
    db: Session = Depends(get_db),
):
    _user, resposta = _viewer_ou_resposta(request, db)
    if resposta is not None:
        return resposta
    executar_retry_manual(request, db)
    return RedirectResponse(url="/governanca-relatorio#ss-testar-sistema", status_code=303)
