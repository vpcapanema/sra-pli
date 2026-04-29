"""Rotas POST de exclusão de relatório inteiro ou de subseção."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db, tx_session
from ..models import Relatorio, Secao

from ..numeracao import consolidar_referencias, renumerar_relatorio
from .pages import response_dashboard, response_relatorio_detail
from .relatorios import (
    _exigir_relatorio_editavel,
    _u_or_login,
)

router = APIRouter()


@router.post("/{rel_id}/excluir")
def excluir_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    with tx_session() as txdb:
        rel_tx = txdb.get(Relatorio, rel_id)
        if rel_tx is not None:
            txdb.delete(rel_tx)
    return response_dashboard(request, db)


@router.post("/{rel_id}/secoes/{sec_id}/excluir")
def excluir_subsecao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if "." not in (sec.numero or ""):
        raise HTTPException(400, detail="Não é possível excluir seções de primeiro nível")
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        sec_tx = txdb.get(Secao, sec_id)
        if sec_tx is not None:
            txdb.delete(sec_tx)
            txdb.flush()
        renumerar_relatorio(txdb, rel_id)
    return response_relatorio_detail(request, db, rel_id)
