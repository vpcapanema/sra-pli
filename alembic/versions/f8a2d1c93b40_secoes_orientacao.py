"""secoes.orientacao

Revision ID: f8a2d1c93b40
Revises: b361b68fd684
Create Date: 2026-05-11 13:35:00.000000

Adiciona coluna `orientacao` em `secoes` para espelhar `w:pgSz/w:orient` do
DOCX de referência (D20-13). Valores: 'portrait' (210x297mm, padrão) e
'landscape' (297x210mm, usado em cronogramas / planilhas largas).

O bootstrap.py já aplica o mesmo DDL idempotente; esta migration formaliza
a mudança no histórico Alembic para ambientes que rodam `alembic upgrade
head` (ex.: produção/render).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a2d1c93b40"
down_revision: Union[str, None] = "b361b68fd684"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "secoes",
        sa.Column(
            "orientacao",
            sa.String(length=16),
            nullable=False,
            server_default="portrait",
        ),
    )


def downgrade() -> None:
    op.drop_column("secoes", "orientacao")
