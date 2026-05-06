"""baseline

Revision ID: b361b68fd684
Revises:
Create Date: 2026-05-06 00:21:20.542324

Baseline vazio: marca o schema atual (aplicado via bootstrap.py DDL) como
ponto zero do historico Alembic.

Em ambientes existentes (producao, dev), rode uma vez:
    alembic stamp head

Isso grava b361b68fd684 em alembic_version sem alterar o schema. A partir
dai, todas as mudancas de schema devem vir como novas migrations
(`alembic revision --autogenerate -m "..."` + `alembic upgrade head`).

O bootstrap.py continua ativo como safety net idempotente, mas novas
colunas/constraints devem ir por migration (revisado em PR).
"""
from typing import Sequence, Union  # noqa: F401

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = "b361b68fd684"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
