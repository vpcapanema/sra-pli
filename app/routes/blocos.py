from datetime import datetime

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from starlette.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db, tx_session
from ..models import Bloco, Relatorio, Secao, User
from ..numeracao import consolidar_referencias
from ..process_events import process_done, process_log, process_start
from .pages import response_secao_edit, user_or_login_page

router = APIRouter(prefix="/relatorios/{rel_id}/secoes/{sec_id}/blocos", tags=["blocos"])


def _check(
    request, db, rel_id, sec_id, *, exigir_editavel: bool = False
) -> tuple[User, Secao] | Response:
    """Valida login, posse da secao e (opcional) status mutavel do relatorio.

    ``exigir_editavel=True`` bloqueia mutacoes estruturais (criar/excluir/mover
    bloco) em relatorios finalizados; o usuario precisa reverter o status
    antes de mexer na estrutura que afeta numeracao de figuras/tabelas.

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
        if rel is not None and rel.status == "finalizado":
            raise HTTPException(
                400,
                detail=(
                    "Relatorio finalizado: reverta o status antes de alterar a estrutura."
                ),
            )
    return user, sec


def _impacta_numeracao(tipo: str, conteudo: str | None) -> bool:
    """Indica se o bloco afeta a numeracao derivada de figura/tabela.

    Blocos do tipo ``figura``/``tabela`` sempre afetam; blocos de texto que
    contem markers ``[[FIGURA:..]]``/``[[TABELA:..]]`` inline tambem.
    """
    if tipo in ("figura", "tabela"):
        return True
    if not conteudo:
        return False
    return "[[FIGURA:" in conteudo or "[[TABELA" in conteudo


@router.post("")
def criar_bloco(
    rel_id: int,
    sec_id: int,
    request: Request,
    tipo: str = Form(...),
    titulo: str = Form(""),
    conteudo: str = Form(""),
    legenda: str = Form(""),
    fonte: str = Form(""),
    figura_id: str = Form(""),
    db: Session = Depends(get_db),
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    user, sec = chk
    if tipo not in ("texto", "figura", "tabela", "lista"):
        raise HTTPException(400)
    process_id = process_start(request, "Bloco de conteúdo", f"Criando bloco do tipo {tipo}.")
    ordem = (db.query(func.max(Bloco.ordem)).filter(Bloco.secao_id == sec_id).scalar() or -1) + 1
    sec_status_atual = sec.status
    with tx_session() as txdb:
        # Antes de inserir um novo alvo numeravel, consolida referencias
        # textuais para que apontem aos IDs estaveis atuais; assim a insercao
        # nao bagunca refs como "Figura 4.2" que passariam a apontar para
        # outro bloco apos o shift de numeracao.
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
    process_done(request, process_id, "Bloco criado", f"Seção {sec.numero} atualizada.")
    return response_secao_edit(request, db, rel_id, sec_id)


def _blocos_selecionados(db: Session, sec_id: int, bloco_ids: list[int]) -> list[Bloco]:
    ids = list(dict.fromkeys(bloco_ids))
    if not ids:
        raise HTTPException(400, detail="Selecione ao menos um bloco.")
    blocos = db.query(Bloco).filter(Bloco.secao_id == sec_id, Bloco.id.in_(ids)).all()
    if len(blocos) != len(ids):
        raise HTTPException(404, detail="Um ou mais blocos selecionados não foram encontrados.")
    return blocos


@router.post("/aprovar-lote")
def aprovar_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    chk = _check(request, db, rel_id, sec_id)
    if isinstance(chk, Response):
        return chk
    blocos = _blocos_selecionados(db, sec_id, bloco_ids)
    process_id = process_start(request, "Aprovação em lote", f"Bloqueando {len(blocos)} bloco(s).")
    ids = [bloco.id for bloco in blocos]
    agora = datetime.utcnow()
    with tx_session() as txdb:
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).update(
            {Bloco.bloqueado: True, Bloco.updated_at: agora},
            synchronize_session=False,
        )
    process_done(request, process_id, "Blocos aprovados", f"{len(blocos)} bloco(s) bloqueado(s).")
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/excluir-lote")
def excluir_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    blocos = _blocos_selecionados(db, sec_id, bloco_ids)
    process_id = process_start(request, "Exclusão em lote", f"Validando {len(blocos)} bloco(s).")
    if any(getattr(bloco, "bloqueado", False) for bloco in blocos):
        process_done(request, process_id, "Exclusão recusada", "Há bloco bloqueado na seleção.", ok=False)
        raise HTTPException(403, detail="Blocos bloqueados não podem ser excluídos.")
    process_log(
        request,
        process_id,
        "Em sequência, o sistema exclui os blocos selecionados, atualizando contadores e referências quando necessário.",
        etapa="Exclusão em lote",
    )
    ids = [bloco.id for bloco in blocos]
    afeta_numeracao = any(_impacta_numeracao(b.tipo, b.conteudo) for b in blocos)
    with tx_session() as txdb:
        if afeta_numeracao:
            consolidar_referencias(txdb, rel_id)
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).delete(synchronize_session=False)
    process_done(request, process_id, "Blocos excluídos", f"{len(blocos)} bloco(s) removido(s).")
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/{bloco_id}/editar")
def editar_bloco(
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    titulo: str = Form(""),
    conteudo: str = Form(""),
    legenda: str = Form(""),
    fonte: str = Form(""),
    figura_id: str = Form(""),
    db: Session = Depends(get_db),
):
    chk = _check(request, db, rel_id, sec_id)
    if isinstance(chk, Response):
        return chk
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    if getattr(b, "bloqueado", False):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser editado.")
    process_id = process_start(request, "Edição de bloco", f"Atualizando bloco #{bloco_id}.")

    b.titulo = titulo.strip() or None
    b.conteudo = conteudo
    b.legenda = legenda.strip() or None
    b.fonte = fonte.strip() or None
    b.figura_id = int(figura_id) if figura_id.strip() else None

    b.updated_at = datetime.utcnow()
    db.commit()
    process_done(request, process_id, "Bloco atualizado", f"Bloco #{bloco_id} salvo.")
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/{bloco_id}/excluir")
def excluir_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    if getattr(b, "bloqueado", False):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser excluído.")
    process_id = process_start(request, "Exclusão de bloco", f"Removendo bloco #{bloco_id}.")
    afeta_numeracao = _impacta_numeracao(b.tipo, b.conteudo)
    with tx_session() as txdb:
        if afeta_numeracao:
            consolidar_referencias(txdb, rel_id)
        bloco_tx = txdb.get(Bloco, bloco_id)
        if bloco_tx is not None:
            txdb.delete(bloco_tx)
    process_done(request, process_id, "Bloco excluído", f"Bloco #{bloco_id} removido.")
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/{bloco_id}/confirmar")
def confirmar_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    chk = _check(request, db, rel_id, sec_id)
    if isinstance(chk, Response):
        return chk
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    process_id = process_start(request, "Confirmação de bloco", f"Bloqueando bloco #{bloco_id}.")
    b.bloqueado = True

    b.updated_at = datetime.utcnow()
    db.commit()
    process_done(request, process_id, "Bloco confirmado", f"Bloco #{bloco_id} bloqueado para revisão.")
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/{bloco_id}/mover")
def mover_bloco(
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    direcao: str = Form(...),
    db: Session = Depends(get_db),
):
    chk = _check(request, db, rel_id, sec_id, exigir_editavel=True)
    if isinstance(chk, Response):
        return chk
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    if getattr(b, "bloqueado", False):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser movido.")
    process_id = process_start(request, "Movimentação de bloco", f"Movendo bloco #{bloco_id}.")

    blocos = db.query(Bloco).filter(Bloco.secao_id == sec_id).order_by(Bloco.ordem).all()
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
            txdb.query(Bloco).filter(Bloco.id == a_id).update(
                {Bloco.ordem: b_ord}, synchronize_session=False
            )
            txdb.query(Bloco).filter(Bloco.id == b_id).update(
                {Bloco.ordem: a_ord}, synchronize_session=False
            )
        process_done(request, process_id, "Bloco movido", f"Direção: {direcao}.")
    else:
        process_done(request, process_id, "Movimento ignorado", "Bloco já está no limite da lista.")
    return response_secao_edit(request, db, rel_id, sec_id)
