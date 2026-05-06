"""Carregamento padronizado de relatório com seções, blocos e responsáveis.

Usado pelas checagens de validação/revisão para evitar consultas divergentes.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ...models import Relatorio, Secao


def load_relatorio_secoes_blocos_responsavel(db: Session, rel_id: int) -> Relatorio:
    rel = (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).options(
                selectinload(Secao.blocos),
                selectinload(Secao.responsavel),
            ),
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    if rel is None:
        raise HTTPException(404, detail="Relatório não encontrado.")
    return rel
