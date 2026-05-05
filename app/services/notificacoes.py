"""Rotas do ciclo de notificações e entregas mensais (lógica).

Lógica das rotas em ``app/routes/notificacoes.py``.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from ..models import EntregaRelatorio, Relatorio, Secao, User
from ..notificacoes.ciclo_params import obter_parametros_ciclo
from ..notificacoes.modelos import DOTX_MEDIA_TYPE, caminho_para, filename_para
from ..notificacoes.service import (
    alterar_status_entrega,
    notificar_autores_abertura,
    prazos_mensagem_relatorio,
    reenviar_manual,
    reprovar_entrega,
)
from .pages import response_usuarios, templates, user_or_login_page
from .entregas.lista_painel import montar_lista_entregas


def _redirect_seguro(destino: str) -> str | None:
    """Aceita apenas paths internos para evitar open redirect."""
    valor = (destino or "").strip()
    if not valor or not valor.startswith("/") or valor.startswith("//"):
        return None
    return valor


def _coord_or_403(user: User) -> None:
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")


def usuarios_notificacoes_toggle(
    user_id: int, request: Request, db: Session
):
    """Liga/desliga o opt-out de notificações mensais (restrito a coord/admin)."""
    viewer, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert viewer is not None
    _coord_or_403(viewer)
    alvo = db.get(User, user_id)
    if not alvo:
        raise HTTPException(404, detail="Usuário não encontrado.")
    alvo.notificacoes_ativas = not bool(alvo.notificacoes_ativas)
    db.commit()
    return response_usuarios(request, db)


def response_entregas_painel(
    request: Request, db: Session, rel_id: int
) -> Response:
    """Painel das entregas — exclusivo de admin/coordenador."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)

    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")

    linhas, pode_acoes = montar_lista_entregas(db, rel, user)

    primeira_sec = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id)
        .order_by(Secao.ordem)
        .first()
    )
    link_upload_exemplo = (
        f"/relatorios/{rel.id}/secoes/{primeira_sec.id}/upload-conteudo"
        if primeira_sec
        else "/painel-upload"
    )
    par_gr = obter_parametros_ciclo(db)
    prazos_ent = prazos_mensagem_relatorio(rel, parametros=par_gr)

    return templates.TemplateResponse(
        request,
        "complementos/entregas_painel.html",
        {
            "user": user,
            "rel": rel,
            "linhas": linhas,
            "pode_acoes": pode_acoes,
            "link_upload_exemplo": link_upload_exemplo,
            "prazo_limite_conteudo_autor": prazos_ent[
                "prazo_limite_conteudo_autor"
            ],
            "prazo_envio_coord": prazos_ent["prazo_envio"],
        },
    )


def entregas_painel(rel_id: int, request: Request, db: Session):
    return response_entregas_painel(request, db, rel_id)


def rota_notificar_autores_abertura(
    rel_id: int, request: Request, db: Session
):
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")
    notificar_autores_abertura(db, rel_id, force=True)
    return RedirectResponse(url=f"/relatorios/{rel_id}", status_code=303)


def entrega_atualizar_status(
    rel_id: int,
    entrega_id: int,
    request: Request,
    novo_status: str,
    redirect_to: str,
    db: Session,
):
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    entrega = db.get(EntregaRelatorio, entrega_id)
    if not entrega or entrega.relatorio_id != rel_id:
        raise HTTPException(404, detail="Entrega não encontrada.")
    try:
        alterar_status_entrega(db, entrega, novo_status, coord=user)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    destino = _redirect_seguro(redirect_to)
    if destino:
        return RedirectResponse(url=destino, status_code=303)
    return response_entregas_painel(request, db, rel_id)


def entrega_reenviar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    redirect_to: str,
    db: Session,
):
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    entrega = db.get(EntregaRelatorio, entrega_id)
    if not entrega or entrega.relatorio_id != rel_id:
        raise HTTPException(404, detail="Entrega não encontrada.")
    reenviar_manual(db, entrega)
    destino = _redirect_seguro(redirect_to)
    if destino:
        return RedirectResponse(url=destino, status_code=303)
    return response_entregas_painel(request, db, rel_id)


def entrega_reprovar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    motivo: str,
    redirect_to: str,
    db: Session,
):
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    entrega = db.get(EntregaRelatorio, entrega_id)
    if not entrega or entrega.relatorio_id != rel_id:
        raise HTTPException(404, detail="Entrega não encontrada.")
    try:
        reprovar_entrega(db, entrega, motivo, coord=user)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    destino = _redirect_seguro(redirect_to)
    if destino:
        return RedirectResponse(url=destino, status_code=303)
    return response_entregas_painel(request, db, rel_id)


def baixar_modelo_secao(
    rel_id: int, sec_id: int, request: Request, db: Session
):
    """Serve o ``.dotx`` modelo da seção. Requer login."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    del user
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(
            404, detail="Seção não encontrada neste relatório."
        )
    arquivo = caminho_para(sec.numero, sec.titulo)
    if not arquivo.is_file():
        raise HTTPException(
            404,
            detail=(
                "Modelo .dotx não disponível no servidor. Rode "
                "`scripts/build_canonical_upload_dotx.py` para gerar."
            ),
        )
    return FileResponse(
        path=str(arquivo),
        filename=filename_para(sec.numero, sec.titulo),
        media_type=DOTX_MEDIA_TYPE,
    )
