"""Exclusão de relatório inteiro ou de subseção (rotas em ``app/routes/relatorio_exclusao.py``)."""

from __future__ import annotations

from fastapi import HTTPException, Request
import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db import tx_session
from ..models import Relatorio, Secao
from ..numeracao import consolidar_referencias, renumerar_relatorio
from .pages import response_dashboard, response_relatorio_detail
from .relatorios import (
    _admin_coord_ou_login,
    _admin_coord_relatorio_mutavel,
)


def excluir_relatorio(rel_id: int, request: Request, db: Session):
    u, p = _admin_coord_ou_login(request, db)
    del u
    if p is not None:
        return p
    # Não usar ``with db.begin()`` aqui: ``_u_or_login`` já disparou SELECT na
    # sessão ``db`` e o SQLAlchemy recusa um segundo ``begin()`` na mesma
    # Session. DELETE em sessão dedicada (transação explícita); CASCADE no
    # Postgres.
    with tx_session() as txdb:
        result = txdb.execute(sa.delete(Relatorio).where(Relatorio.id == rel_id))
        deleted = result.rowcount
        if deleted == 0:
            raise HTTPException(404)
    db.expire_all()
    return response_dashboard(request, db)


def excluir_subsecao(rel_id: int, sec_id: int, request: Request, db: Session):
    redir = _admin_coord_relatorio_mutavel(request, db, rel_id)
    if redir is not None:
        return redir
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if "." not in (sec.numero or ""):
        raise HTTPException(
            400, detail="Não é possível excluir seções de primeiro nível"
        )
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        sec_tx = txdb.get(Secao, sec_id)
        if sec_tx is not None:
            txdb.delete(sec_tx)
            txdb.flush()
        renumerar_relatorio(txdb, rel_id)
    return response_relatorio_detail(request, db, rel_id)
