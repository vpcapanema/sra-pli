"""Rotas do ciclo de notificações e entregas mensais.

Tracks 2-3 (escopo atual): leitura do painel de entregas, toggle do opt-out de
notificações por usuário e download autenticado dos modelos ``.dotx`` referenciados
nos emails. As ações que alteram status de entrega e o disparo automático
ficam para as Tracks 4/5.
"""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from ..db import get_db
from ..models import EntregaRelatorio, Relatorio, Secao, User
from ..notificacoes.modelos import DOTX_MEDIA_TYPE, caminho_para, filename_para
from ..notificacoes.ciclo_params import obter_parametros_ciclo
from ..notificacoes.service import (
    alterar_status_entrega,
    notificar_autores_abertura,
    prazos_mensagem_relatorio,
    reenviar_manual,
    reprovar_entrega,
)
from ..services.entregas.lista_painel import montar_lista_entregas
from .pages import (
    response_usuarios,
    templates,
    user_or_login_page,
)


def _redirect_seguro(destino: str) -> str | None:
    """Aceita apenas paths internos para evitar open redirect.

    Form externo poderia injetar `https://evil.tld/...`. Aqui restringimos a
    paths que começam com '/' e não com '//' (que browsers tratam como host).
    Devolve None quando o valor não pode ser confiado, fazendo a rota cair no
    comportamento padrão (renderização inline).
    """
    valor = (destino or "").strip()
    if not valor or not valor.startswith("/") or valor.startswith("//"):
        return None
    return valor


router = APIRouter()


def _coord_or_403(user: User) -> None:
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")


@router.post("/usuarios/{user_id}/notificacoes-toggle")
def usuarios_notificacoes_toggle(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Liga/desliga o opt-out de notificações mensais (restrito a coord/admin).

    Toggle é fim-de-linha: com ``notificacoes_ativas=false`` o utilizador deixa
    de entrar na lista de destinatários do ciclo (abertura, lembretes, etc.).
    """
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
    """Painel das entregas — exclusivo de admin/coordenador.

    A montagem das linhas vem de
    ``services.entregas.lista_painel.montar_lista_entregas`` — mesma fonte
    consumida pelo painel de governança e pela página de Validação e Revisão,
    garantindo que ações em qualquer um dos três locais reflitam nos demais
    sem duplicação de regra. O bloqueio de autor é feito antes pelo
    `SraAutorRouteGuardMiddleware`; este `_coord_or_403` é defesa em
    profundidade caso o middleware seja desviado.
    """
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
            "prazo_limite_conteudo_autor": prazos_ent["prazo_limite_conteudo_autor"],
            "prazo_envio_coord": prazos_ent["prazo_envio"],
        },
    )


@router.get("/relatorios/{rel_id}/entregas")
def entregas_painel(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return response_entregas_painel(request, db, rel_id)


@router.post("/relatorios/{rel_id}/notificar-autores-abertura")
def rota_notificar_autores_abertura(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Dispara e-mail de abertura (Mensagem 1) para todos os autores ativos.

    Ação **assistida** pelo coordenador: ``force=True`` ignora a idempotência
    (não pula quem já recebeu) e força reenvio também ao endereço secundário.
    O cron continua usando o caminho idempotente.
    """
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


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/status")
# pylint: disable=too-many-arguments,too-many-positional-arguments
# Os 6 parâmetros vêm do contrato HTTP (path, body Form, request, dependency).
# Aglutiná-los em dataclass desfigura a injeção do FastAPI sem ganho.
def entrega_atualizar_status(
    rel_id: int,
    entrega_id: int,
    request: Request,
    novo_status: str = Form(...),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    """Coord/admin altera o status de uma linha de entrega.

    ``redirect_to`` (opcional) permite que callers como o painel de
    governança peçam para a rota devolver 303 para a sua URL de origem em
    vez de re-renderizar o painel de entregas inline.
    """
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


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/reenviar")
def entrega_reenviar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    """Coord/admin reenvia Mensagem 2 manualmente para uma entrega.

    ``redirect_to`` segue a mesma convenção da rota de status acima.
    """
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


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/reprovar")
# pylint: disable=too-many-arguments,too-many-positional-arguments
# Mesmo motivo do entrega_atualizar_status: parâmetros vêm do contrato HTTP.
def entrega_reprovar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    motivo: str = Form(...),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    """Coord/admin devolve a parcial ao autor com justificativa obrigatória.

    Volta a entrega para ``aguardando_envio`` e carimba motivo/data/autor da
    reprovação. Justificativa vazia é rejeitada com 400.
    """
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


# ---------------------------------------------------------------------------
# Download autenticado dos modelos ``.dotx`` referenciados nos emails. O nome
# do ficheiro vem de ``app/notificacoes/modelos.py`` (mesma fonte usada por
# ``scripts/build_canonical_upload_dotx.py``).
# ---------------------------------------------------------------------------
@router.get("/relatorios/{rel_id}/secoes/{sec_id}/modelo.dotx")
def baixar_modelo_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Serve o ``.dotx`` modelo da seção. Requer login."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404, detail="Seção não encontrada neste relatório.")
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
