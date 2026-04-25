from datetime import datetime

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bloco, Secao
from ..auth import current_user

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

    b.titulo = titulo.strip() or None
    b.conteudo = conteudo
    b.legenda = legenda.strip() or None
    b.fonte = fonte.strip() or None
    b.figura_id = int(figura_id) if figura_id.strip() else None

    b.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{bloco_id}/excluir")
def excluir_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    _check(request, db, rel_id, sec_id)
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    if getattr(b, "bloqueado", False):
        raise HTTPException(403, detail="Bloco está bloqueado e não pode ser excluído.")
    db.delete(b)
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{bloco_id}/confirmar")
def confirmar_bloco(rel_id: int, sec_id: int, bloco_id: int, request: Request, db: Session = Depends(get_db)):
    _check(request, db, rel_id, sec_id)
    b = db.get(Bloco, bloco_id)
    if not b or b.secao_id != sec_id:
        raise HTTPException(404)
    b.bloqueado = True

    b.updated_at = datetime.utcnow()
    db.commit()
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

    blocos = db.query(Bloco).filter(Bloco.secao_id == sec_id).order_by(Bloco.ordem).all()
    idx = next((i for i, bx in enumerate(blocos) if bx.id == bloco_id), -1)
    if idx < 0:
        raise HTTPException(404)
    swap = idx - 1 if direcao == "cima" else idx + 1
    if 0 <= swap < len(blocos):
        blocos[idx].ordem, blocos[swap].ordem = blocos[swap].ordem, blocos[idx].ordem
        db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)
