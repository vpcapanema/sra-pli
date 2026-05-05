"""Service de blocos: toda a logica de CRUD/lote/reordenacao/confirmacao.

As rotas (``app/routes/blocos.py``) sao casca pura e delegam para este modulo.
"""

from datetime import datetime

from fastapi import HTTPException, Request
from starlette.responses import Response, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..db import tx_session
from ..models import Bloco, Relatorio, Secao, User
from ..numeracao import chave_numero, consolidar_referencias, secao_ids_na_subarvore
from ..notificacoes.service import recompute_status_enviado
from .. import ref_resolve
from ..modo_edicao_blocos import modo_edicao_coordenador_rel, pode_mutar_apesar_de_bloqueado
from .pages import response_conteudo_upload, user_or_login_page


def _hook_recompute_entrega(db: Session, rel_id: int, sec_id: int) -> None:
    """Após bloqueio de bloco(s), tenta promover a entrega do responsável
    da seção para ``enviado``. No-op se a seção não tem responsável."""
    sec = db.get(Secao, sec_id)
    if not sec or not sec.responsavel_id:
        return
    recompute_status_enviado(db, sec.responsavel_id, rel_id)


def _escopo_sec_ids(db: Session, rel_id: int, anc: Secao) -> set[int]:
    secoes = db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    return secao_ids_na_subarvore(secoes, anc.numero or "")


def _require_bloco_na_subarvore(db: Session, rel_id: int, anc: Secao, bloco_id: int) -> Bloco:
    b = db.get(Bloco, bloco_id)
    if not b:
        raise HTTPException(404, detail="Bloco não encontrado.")
    escopo = _escopo_sec_ids(db, rel_id, anc)
    if b.secao_id not in escopo:
        raise HTTPException(404, detail="Bloco não encontrado neste âmbito.")
    return b


def _blocos_selecionados_escopo(db: Session, rel_id: int, anc_sec: Secao, bloco_ids: list[int]) -> list[Bloco]:
    ids = list(dict.fromkeys(bloco_ids))
    if not ids:
        raise HTTPException(400, detail="Selecione ao menos um bloco.")
    escopo = _escopo_sec_ids(db, rel_id, anc_sec)
    blocos = db.query(Bloco).filter(Bloco.id.in_(ids)).all()
    if len(blocos) != len(ids):
        raise HTTPException(404, detail="Um ou mais blocos selecionados não foram encontrados.")
    for b in blocos:
        if b.secao_id not in escopo:
            raise HTTPException(400, detail="Um ou mais blocos não pertencem ao âmbito desta página.")
    return blocos


def _hooks_recompute_entrega_varias_secoes(db: Session, rel_id: int, sec_ids: list[int]) -> None:
    for sid in dict.fromkeys(sec_ids):
        _hook_recompute_entrega(db, rel_id, sid)


def _pode_editar_status(user: User, rel: Relatorio) -> tuple[bool, str]:
    """Decide se o role do user pode editar conteudo deste relatorio.

    Regras (de Relatorio.status):
    - ``aberto``: todos os roles editam.
    - ``em_revisao``: somente ``admin`` e ``coordenador``.
    - ``finalizado``: ninguem edita pela interface; reverter status antes.
    - outro: bloqueia por seguranca.
    """
    status = rel.status
    if status == "aberto":
        return True, ""
    if status == "em_revisao":
        if user.role in ("admin", "coordenador"):
            return True, ""
        return False, "Relatorio em revisao: apenas coordenador/admin podem editar."
    if status == "finalizado":
        return False, "Relatorio finalizado: reverta o status antes de alterar."
    return False, f"Status do relatorio '{status}' nao permite edicao."


def _check(request, db, rel_id, sec_id, *, exigir_editavel: bool = False) -> tuple[User, Secao] | Response:
    """Valida login, posse da secao e (opcional) permissao de edicao.

    ``exigir_editavel=True`` aplica ``_pode_editar_status``: bloqueia autor em
    ``em_revisao`` e qualquer role em ``finalizado``. Sem essa flag, permite
    leitura mesmo em estados onde a edicao esta vedada.

    Se nao houver sessao, devolve a pagina de login (sem HTTP redirect).
    """
    u, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert u is not None
    user = u
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        raise HTTPException(403, detail="Não autorizado")
    if exigir_editavel:
        rel = db.get(Relatorio, rel_id)
        if rel is None:
            raise HTTPException(404)
        ok, motivo = _pode_editar_status(user, rel)
        if not ok:
            raise HTTPException(403, detail=motivo)
    return user, sec


def _impacta_numeracao(tipo: str, conteudo: str | None) -> bool:
    """Indica se o bloco afeta a numeracao derivada de figura/tabela."""
    if tipo in ("figura", "tabela"):
        return True
    if not conteudo:
        return False
    return "[[FIGURA:" in conteudo or "[[TABELA" in conteudo


def campos_json_bloco_transversal(b: Bloco) -> dict:
    """Campos partilhados pelos payloads JSON de blocos (por secção / confirmados)."""
    return {
        "id": b.id,
        "tipo": b.tipo,
        "ordem": b.ordem,
        "titulo": b.titulo or "",
        "conteudo": b.conteudo or "",
        "legenda": b.legenda or "",
        "fonte": b.fonte or "",
        "figura_id": b.figura_id,
        "autor_nome": b.autor.nome if b.autor else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def listar_blocos_json(rel_id: int, sec_id: int, request: Request, db: Session):
    """Retorna os blocos da subárvore da secção alvo (âncora + descendentes PLI)."""
    chk = _check(request, db, rel_id, sec_id)
    if isinstance(chk, Response):
        return chk
    user, sec = chk
    rel = ref_resolve.carregar_relatorio_com_secoes_e_blocos(db, rel_id)
    if rel is None:
        raise HTTPException(404)
    pode_status, motivo_status = _pode_editar_status(user, rel)
    mapas_ref = ref_resolve.calcular_mapas_referencia(rel.secoes)
    escopo = secao_ids_na_subarvore(rel.secoes, sec.numero or "")
    escopo_sql = escopo if escopo else {-1}
    blocos_raw = (
        db.query(Bloco)
        .options(joinedload(Bloco.autor), joinedload(Bloco.secao))
        .filter(Bloco.secao_id.in_(escopo_sql))
        .all()
    )
    blocos_raw.sort(
        key=lambda b: (
            chave_numero(b.secao.numero if b.secao else ""),
            b.ordem or 0,
            b.id,
        )
    )
    payload = {
        "secao": {
            "id": sec.id,
            "numero": sec.numero,
            "titulo": sec.titulo,
            "responsavel_id": sec.responsavel_id,
            "status": sec.status,
        },
        "relatorio": {"status": rel.status},
        "pode_editar_secao": pode_status,
        "motivo_bloqueio": motivo_status,
        "modo_edicao_coordenador_ativo": modo_edicao_coordenador_rel(request, user, rel_id),
        "ref_mapas": ref_resolve.mapas_para_json(mapas_ref),
        "blocos": [
            {
                **campos_json_bloco_transversal(b),
                "secao_id": b.secao_id,
                "secao_numero": (b.secao.numero if b.secao else "") or "",
                "bloqueado": bool(b.bloqueado),
                "pode_editar": pode_status
                and (not bool(b.bloqueado) or pode_mutar_apesar_de_bloqueado(request, user, rel_id, rel.status)),
            }
            for b in blocos_raw
        ],
    }
    return JSONResponse(payload)


def criar_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    rel_id: int,
    sec_id: int,
    request: Request,
    tipo: str,
    titulo: str,
    conteudo: str,
    legenda: str,
    fonte: str,
    figura_id: str,
    db: Session,
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, sec = chk
    if tipo not in ("texto", "figura", "tabela", "lista"):
        raise HTTPException(400)

    ordem = (db.query(func.max(Bloco.ordem)).filter(Bloco.secao_id == sec_id).scalar() or -1) + 1
    sec_status_atual = sec.status
    with tx_session() as txdb:
        if _impacta_numeracao(tipo, conteudo):
            consolidar_referencias(txdb, rel_id)
        bloco = Bloco(
            secao_id=sec_id,
            tipo=tipo,
            ordem=ordem,
            titulo=titulo.strip() or None,
            conteudo=conteudo,
            legenda=legenda.strip() or None,
            fonte=fonte.strip() or None,
            figura_id=int(figura_id) if figura_id.strip() else None,
            autor_id=user.id,
        )
        txdb.add(bloco)
        if sec_status_atual == "pendente":
            txdb.query(Secao).filter(Secao.id == sec_id).update(
                {Secao.status: "em_andamento"}, synchronize_session=False
            )
    return response_conteudo_upload(request, db, rel_id, sec_id)


def aprovar_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int],
    db: Session,
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    _, anc_sec = chk
    blocos = _blocos_selecionados_escopo(db, rel_id, anc_sec, bloco_ids)
    ids = [bloco.id for bloco in blocos]
    agora = datetime.utcnow()
    with tx_session() as txdb:
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).update(
            {Bloco.bloqueado: True, Bloco.updated_at: agora},
            synchronize_session=False,
        )
    _hooks_recompute_entrega_varias_secoes(db, rel_id, [b.secao_id for b in blocos])
    return response_conteudo_upload(request, db, rel_id, sec_id)


def excluir_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int],
    db: Session,
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, anc_sec = chk
    rel_status = anc_sec.relatorio.status if anc_sec.relatorio is not None else None
    blocos = _blocos_selecionados_escopo(db, rel_id, anc_sec, bloco_ids)
    if any(
        getattr(bloco, "bloqueado", False) and not pode_mutar_apesar_de_bloqueado(request, user, rel_id, rel_status)
        for bloco in blocos
    ):
        raise HTTPException(403, detail="Blocos bloqueados não podem ser excluídos.")
    ids = [bloco.id for bloco in blocos]
    afeta_numeracao = any(_impacta_numeracao(b.tipo, b.conteudo) for b in blocos)
    with tx_session() as txdb:
        if afeta_numeracao:
            consolidar_referencias(txdb, rel_id)
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).delete(synchronize_session=False)
    return response_conteudo_upload(request, db, rel_id, sec_id)


def editar_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    titulo: str,
    conteudo: str,
    legenda: str,
    fonte: str,
    figura_id: str,
    db: Session,
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, anc_sec = chk
    rel_status = anc_sec.relatorio.status if anc_sec.relatorio is not None else None
    b = _require_bloco_na_subarvore(db, rel_id, anc_sec, bloco_id)
    if getattr(b, "bloqueado", False) and not pode_mutar_apesar_de_bloqueado(request, user, rel_id, rel_status):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser editado.")

    b.titulo = titulo.strip() or None
    b.conteudo = conteudo
    b.legenda = legenda.strip() or None
    b.fonte = fonte.strip() or None
    b.figura_id = int(figura_id) if figura_id.strip() else None

    b.updated_at = datetime.utcnow()
    db.commit()
    return response_conteudo_upload(request, db, rel_id, sec_id)


def excluir_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, anc_sec = chk
    rel_status = anc_sec.relatorio.status if anc_sec.relatorio is not None else None
    b = _require_bloco_na_subarvore(db, rel_id, anc_sec, bloco_id)
    if getattr(b, "bloqueado", False) and not pode_mutar_apesar_de_bloqueado(request, user, rel_id, rel_status):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser excluído.")
    afeta_numeracao = _impacta_numeracao(b.tipo, b.conteudo)
    with tx_session() as txdb:
        if afeta_numeracao:
            consolidar_referencias(txdb, rel_id)
        bloco_tx = txdb.get(Bloco, bloco_id)
        if bloco_tx is not None:
            txdb.delete(bloco_tx)
    return response_conteudo_upload(request, db, rel_id, sec_id)


def confirmar_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    _, anc_sec = chk
    b = _require_bloco_na_subarvore(db, rel_id, anc_sec, bloco_id)
    b.bloqueado = True

    b.updated_at = datetime.utcnow()
    db.commit()
    _hook_recompute_entrega(db, rel_id, b.secao_id)
    return response_conteudo_upload(request, db, rel_id, sec_id)


def mover_bloco(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    direcao: str,
    db: Session,
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, anc_sec = chk
    rel_status = anc_sec.relatorio.status if anc_sec.relatorio is not None else None
    b = _require_bloco_na_subarvore(db, rel_id, anc_sec, bloco_id)
    if getattr(b, "bloqueado", False) and not pode_mutar_apesar_de_bloqueado(request, user, rel_id, rel_status):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser movido.")

    sid_real = b.secao_id
    blocos = db.query(Bloco).filter(Bloco.secao_id == sid_real).order_by(Bloco.ordem).all()
    idx = next((i for i, bx in enumerate(blocos) if bx.id == bloco_id), -1)
    if idx < 0:
        raise HTTPException(404)
    swap = idx - 1 if direcao == "cima" else idx + 1
    if 0 <= swap < len(blocos):
        a_id, a_ord = blocos[idx].id, blocos[idx].ordem
        b_id, b_ord = blocos[swap].id, blocos[swap].ordem
        with tx_session() as txdb:
            if _impacta_numeracao(blocos[idx].tipo, blocos[idx].conteudo) or _impacta_numeracao(
                blocos[swap].tipo, blocos[swap].conteudo
            ):
                consolidar_referencias(txdb, rel_id)
            txdb.query(Bloco).filter(Bloco.id == a_id).update({Bloco.ordem: b_ord}, synchronize_session=False)
            txdb.query(Bloco).filter(Bloco.id == b_id).update({Bloco.ordem: a_ord}, synchronize_session=False)
    return response_conteudo_upload(request, db, rel_id, sec_id)
