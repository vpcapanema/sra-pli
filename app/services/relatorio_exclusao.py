"""Exclusão de relatório inteiro ou de subseção (rotas em ``app/routes/relatorio_exclusao.py``)."""

from __future__ import annotations

from fastapi import HTTPException, Request
import sqlalchemy as sa
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from ..db import tx_session
from ..models import Relatorio, Secao
from ..numeracao import consolidar_referencias, renumerar_relatorio
from .relatorios import (
    _admin_coord_ou_login,
    _admin_coord_relatorio_mutavel,
    _u_or_login,
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
    try:
        from ..main import sidebar_cache_invalidate

        sidebar_cache_invalidate()
    except Exception:
        pass
    return RedirectResponse(url="/dashboard", status_code=303)


def excluir_subsecao(rel_id: int, sec_id: int, request: Request, db: Session):
    redir = _admin_coord_relatorio_mutavel(request, db, rel_id)
    if redir is not None:
        return redir
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
    db.expire_all()
    return RedirectResponse(url=f"/relatorios/{rel_id}", status_code=303)


def excluir_secoes_lote(
    rel_id: int,
    secao_ids: list[int],
    request: Request,
    db: Session,
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    assert u is not None
    if u.role != "coordenador":
        raise HTTPException(403)
    _exigir_relatorio_mutavel = _admin_coord_relatorio_mutavel(
        request,
        db,
        rel_id,
    )
    if _exigir_relatorio_mutavel is not None:
        return _exigir_relatorio_mutavel
    ids = {int(sec_id) for sec_id in secao_ids if int(sec_id) > 0}
    if ids:
        with tx_session() as txdb:
            consolidar_referencias(txdb, rel_id)
            secoes = (
                txdb.query(Secao)
                .filter(Secao.relatorio_id == rel_id, Secao.id.in_(ids))
                .order_by(Secao.numero)
                .all()
            )
            for sec in secoes:
                if "." not in (sec.numero or ""):
                    continue
                txdb.delete(sec)
            txdb.flush()
            renumerar_relatorio(txdb, rel_id)
    db.expire_all()
    return RedirectResponse(url=f"/relatorios/{rel_id}", status_code=303)
