from datetime import datetime

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bloco, Secao
from ..auth import current_user
from ..process_events import process_done, process_log, process_start

router = APIRouter(prefix="/relatorios/{rel_id}/secoes/{sec_id}/blocos", tags=["blocos"])


def _check(request, db, rel_id, sec_id):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        raise HTTPException(403, detail="Não autorizado")
    return user, sec


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
    user, sec = _check(request, db, rel_id, sec_id)
    if tipo not in ("texto", "figura", "tabela", "lista"):
        raise HTTPException(400)
    process_id = process_start(request, "Bloco de conteúdo", f"Criando bloco do tipo {tipo}.")
    ordem = (db.query(func.max(Bloco.ordem)).filter(Bloco.secao_id == sec_id).scalar() or -1) + 1
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
    db.add(bloco)
    if sec.status == "pendente":
        sec.status = "em_andamento"
    db.commit()
    process_done(request, process_id, "Bloco criado", f"Seção {sec.numero} atualizada.")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


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
    _check(request, db, rel_id, sec_id)
    blocos = _blocos_selecionados(db, sec_id, bloco_ids)
    process_id = process_start(request, "Aprovação em lote", f"Bloqueando {len(blocos)} bloco(s).")
    agora = datetime.utcnow()
    for bloco in blocos:
        bloco.bloqueado = True
        bloco.updated_at = agora
    db.commit()
    process_done(request, process_id, "Blocos aprovados", f"{len(blocos)} bloco(s) bloqueado(s).")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/excluir-lote")
def excluir_blocos_lote(
    rel_id: int,
    sec_id: int,
    request: Request,
    bloco_ids: list[int] = Form(...),
    db: Session = Depends(get_db),
):
    _check(request, db, rel_id, sec_id)
    blocos = _blocos_selecionados(db, sec_id, bloco_ids)
    process_id = process_start(request, "Exclusão em lote", f"Validando {len(blocos)} bloco(s).")
    if any(getattr(bloco, "bloqueado", False) for bloco in blocos):
        process_done(request, process_id, "Exclusão recusada", "Há bloco bloqueado na seleção.", ok=False)
        raise HTTPException(403, detail="Blocos bloqueados não podem ser excluídos.")
    process_log(request, process_id, "Removendo blocos selecionados.")
    for bloco in blocos:
        db.delete(bloco)
    db.commit()
    process_done(request, process_id, "Blocos excluídos", f"{len(blocos)} bloco(s) removido(s).")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


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
    _check(request, db, rel_id, sec_id)
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
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{bloco_id}/excluir")
def excluir_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    _check(request, db, rel_id, sec_id)
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    if getattr(b, "bloqueado", False):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser excluído.")
    process_id = process_start(request, "Exclusão de bloco", f"Removendo bloco #{bloco_id}.")
    db.delete(b)
    db.commit()
    process_done(request, process_id, "Bloco excluído", f"Bloco #{bloco_id} removido.")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{bloco_id}/confirmar")
def confirmar_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    _check(request, db, rel_id, sec_id)
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    process_id = process_start(request, "Confirmação de bloco", f"Bloqueando bloco #{bloco_id}.")
    b.bloqueado = True

    b.updated_at = datetime.utcnow()
    db.commit()
    process_done(request, process_id, "Bloco confirmado", f"Bloco #{bloco_id} bloqueado para revisão.")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{bloco_id}/mover")
def mover_bloco(
    rel_id: int,
    sec_id: int,
    bloco_id: int,
    request: Request,
    direcao: str = Form(...),
    db: Session = Depends(get_db),
):
    _check(request, db, rel_id, sec_id)
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
        blocos[idx].ordem, blocos[swap].ordem = blocos[swap].ordem, blocos[idx].ordem
        db.commit()
        process_done(request, process_id, "Bloco movido", f"Direção: {direcao}.")
    else:
        process_done(request, process_id, "Movimento ignorado", "Bloco já está no limite da lista.")
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)
