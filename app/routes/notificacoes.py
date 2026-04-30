"""Rotas do ciclo de notificações e entregas mensais.

Tracks 2-3 (escopo atual): leitura do painel de entregas, toggle do opt-out de
notificações por usuário e download autenticado dos modelos ``.dotx`` referenciados
nos emails. As ações que alteram status de entrega e o disparo automático
ficam para as Tracks 4/5.
"""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
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
)
from .pages import (
    response_usuarios,
    templates,
    user_or_login_page,
)

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


def _montar_linha_entrega(
    entrega: EntregaRelatorio, sec_counts: dict[int, int]
) -> dict:
    """Achata ``EntregaRelatorio`` para o template, derivando notif1/2/3/última
    da relação 1:N ``notificacoes`` (já ordenada por ``enviada_em``)."""
    enviadas = [n for n in entrega.notificacoes if n.sucesso]
    notif1 = enviadas[0].enviada_em if len(enviadas) >= 1 else None
    notif2 = enviadas[1].enviada_em if len(enviadas) >= 2 else None
    notif3 = enviadas[2].enviada_em if len(enviadas) >= 3 else None
    ultima = enviadas[-1].enviada_em if enviadas else None
    u = entrega.user
    return {
        "entrega_id": entrega.id,
        "user_id": u.id if u else None,
        "nome": u.nome if u else "—",
        "email": u.email if u else "—",
        "perfil": u.role if u else "—",
        "secoes_count": sec_counts.get(u.id, 0) if u else 0,
        "notif1": notif1,
        "notif2": notif2,
        "notif3": notif3,
        "ultima": ultima,
        "data_envio": entrega.data_envio,
        "status": entrega.status,
    }


def response_entregas_painel(
    request: Request, db: Session, rel_id: int
) -> Response:
    """Painel das entregas de um relatório. Coord/admin veem todas as linhas;
    autores veem apenas a sua. Agregação dos timestamps das notificações é
    feita em Python (≤ ~30 linhas/relatório torna SQL agregado sobre-engenharia).
    """
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None

    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")

    q = (
        db.query(EntregaRelatorio)
        .options(
            selectinload(EntregaRelatorio.user),
            selectinload(EntregaRelatorio.notificacoes),
        )
        .filter(EntregaRelatorio.relatorio_id == rel_id)
    )
    if user.role not in ("admin", "coordenador"):
        q = q.filter(EntregaRelatorio.user_id == user.id)
    entregas = q.all()
    entregas.sort(key=lambda e: (e.user.nome if e.user else ""))

    sec_counts: dict[int, int] = dict(
        db.query(
            Secao.responsavel_id,
            func.count(Secao.id),  # pylint: disable=not-callable
        )
        .filter(Secao.relatorio_id == rel_id, Secao.responsavel_id.isnot(None))
        .group_by(Secao.responsavel_id)
        .all()
    )

    linhas = [_montar_linha_entrega(e, sec_counts) for e in entregas]

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
            "pode_acoes": user.role in ("admin", "coordenador"),
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
    """Dispara e-mail de abertura (Mensagem 1) para responsáveis já atribuídos."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")
    notificar_autores_abertura(db, rel_id)
    return RedirectResponse(url=f"/relatorios/{rel_id}", status_code=303)


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/status")
def entrega_atualizar_status(
    rel_id: int,
    entrega_id: int,
    request: Request,
    novo_status: str = Form(...),
    db: Session = Depends(get_db),
):
    """Coord/admin altera o status de uma linha de entrega."""
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
    return response_entregas_painel(request, db, rel_id)


@router.post("/relatorios/{rel_id}/entregas/{entrega_id}/reenviar")
def entrega_reenviar(
    rel_id: int,
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Coord/admin reenvia Mensagem 2 manualmente para uma entrega."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    _coord_or_403(user)
    entrega = db.get(EntregaRelatorio, entrega_id)
    if not entrega or entrega.relatorio_id != rel_id:
        raise HTTPException(404, detail="Entrega não encontrada.")
    reenviar_manual(db, entrega)
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
