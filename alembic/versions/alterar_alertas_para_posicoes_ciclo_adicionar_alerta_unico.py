"""alterar_alertas_para_posicoes_ciclo_adicionar_alerta_unico

Revision ID: alterar_alertas_para_posicoes
Revises: f8a2d1c93b40
Create Date: 2026-05-13 14:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'alterar_alertas_para_posicoes'
down_revision: Union[str, None] = 'f8a2d1c93b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Criar tabela alerta_unico
    op.create_table(
        'alerta_unico',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alerta_id', sa.Integer(), nullable=False),
        sa.Column('tipo_mensagem', sa.String(length=32), nullable=False),
        sa.Column('perfis_destinatarios_json', sa.Text(), nullable=True),
        sa.Column('usuarios_destinatarios_json', sa.Text(), nullable=True),
        sa.Column('data_evento', sa.DateTime(), nullable=True),
        sa.Column('data_alerta', sa.DateTime(), nullable=True),
        sa.Column('data_inicio_disparos', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['alerta_id'], ['alertas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerta_unico_alerta', 'alerta_unico', ['alerta_id'], unique=False)

    # Adicionar campos de posição em alertas
    op.add_column('alertas', sa.Column('inicio_ciclo_evento_posicao', sa.Integer(), nullable=True))
    op.add_column('alertas', sa.Column('fim_ciclo_evento_posicao', sa.Integer(), nullable=True))
    op.add_column('alertas', sa.Column('inicio_ciclo_alerta_posicao', sa.Integer(), nullable=True))
    op.add_column('alertas', sa.Column('fim_ciclo_alerta_posicao', sa.Integer(), nullable=True))

    # Remover campos datetime de alertas
    op.drop_column('alertas', 'data_inicio_disparos')
    op.drop_column('alertas', 'dias_semana')
    op.drop_column('alertas', 'intervalo_horario_inicio')
    op.drop_column('alertas', 'inicio_evento')
    op.drop_column('alertas', 'inicio_alerta')
    op.drop_column('alertas', 'fim_evento')
    op.drop_column('alertas', 'intervalo_horario_fim')
    op.drop_column('alertas', 'fim_alerta')

    # Adicionar data_base_inicio_evento em alerta_fluxos
    op.add_column('alerta_fluxos', sa.Column('data_base_inicio_evento', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remover data_base_inicio_evento de alerta_fluxos
    op.drop_column('alerta_fluxos', 'data_base_inicio_evento')

    # Reverter campos datetime de alertas
    op.add_column('alertas', sa.Column('fim_alerta', sa.DateTime(), nullable=True))
    op.add_column('alertas', sa.Column('intervalo_horario_fim', sa.String(length=5), nullable=True))
    op.add_column('alertas', sa.Column('fim_evento', sa.DateTime(), nullable=True))
    op.add_column('alertas', sa.Column('inicio_alerta', sa.DateTime(), nullable=True))
    op.add_column('alertas', sa.Column('inicio_evento', sa.DateTime(), nullable=True))
    op.add_column('alertas', sa.Column('intervalo_horario_inicio', sa.String(length=5), nullable=True))
    op.add_column('alertas', sa.Column('dias_semana', sa.String(length=32), nullable=True))
    op.add_column('alertas', sa.Column('data_inicio_disparos', sa.DateTime(), nullable=True))

    # Remover campos de posição de alertas
    op.drop_column('alertas', 'fim_ciclo_alerta_posicao')
    op.drop_column('alertas', 'inicio_ciclo_alerta_posicao')
    op.drop_column('alertas', 'fim_ciclo_evento_posicao')
    op.drop_column('alertas', 'inicio_ciclo_evento_posicao')

    # Remover tabela alerta_unico
    op.drop_index('ix_alerta_unico_alerta', table_name='alerta_unico')
    op.drop_table('alerta_unico')
