"""Carregamento padronizado de relatório com seções, blocos e responsáveis.

Usado pelas checagens de validação/revisão para evitar consultas divergentes.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from ...models import Relatorio, Secao


def load_relatorio_secoes_blocos_responsavel(db: Session, rel_id: int) -> Relatorio:
    return (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).options(
                selectinload(Secao.blocos),
                selectinload(Secao.responsavel),
            ),
        )
        .filter(Relatorio.id == rel_id)
        .one()
    )
