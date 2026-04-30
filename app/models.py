from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Index, Integer, String, Text, DateTime, Date, ForeignKey,
    LargeBinary, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", "role", name="uq_users_email_role"), Index("ix_users_email", "email"))
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    # E-mail secundário (obrigatório): contacto alternativo na UI; login continua
    # a usar ``email``.
    email2 = Column(String(255), nullable=False)
    nome = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="autor")  # admin, coordenador, autor
    # Coluna «Relatório» na UI (autores). Abertura, lembretes e última chamada
    # vão aos autores com valor true (lista pode não ter secções atribuídas).
    # Coord/admin desliga para férias/afastamento.
    notificacoes_ativas = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=datetime.utcnow)


class Relatorio(Base):
    __tablename__ = "relatorios"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(64), nullable=False, unique=True)  # ex: D20-13
    titulo = Column(String(255), nullable=False)
    mes_referencia = Column(String(32), nullable=False)       # ex: "Abril/2026"
    periodo_inicio = Column(Date, nullable=False)
    periodo_fim = Column(Date, nullable=False)
    numero_medicao = Column(Integer, nullable=True)
    versao = Column(String(8), nullable=False, default="R00")
    status = Column(String(32), nullable=False, default="aberto")  # aberto, em_revisao, finalizado
    created_at = Column(DateTime, default=datetime.utcnow)

    secoes = relationship("Secao", back_populates="relatorio", cascade="all, delete-orphan", order_by="Secao.ordem")


SECOES_PADRAO = [
    ("1", "Apresentação"),
    ("2", "Histórico do Contrato"),
    ("3", "Relação de Produtos Entregues"),
    ("4", "Visão Geral das Atividades Realizadas"),
    ("4.1", "Coordenação"),
    ("4.2", "Atividades Sistema de Informação"),
    ("4.3", "Comunicação Social"),
    ("4.3.1", "Principais Entregas e Ações Realizadas"),
    ("4.4", "Atividades de Apoio Técnico"),
    ("4.4.1", "Acompanhamento técnico em reuniões de interesse para o PLI"),
    ("4.4.2", "Apoio Administrativo e institucional"),
    ("4.4.3", "Análise do Panorama de Investimentos Estaduais em Rodovias de São Paulo"),
    ("4.4.4", "Preenchimento das fichas de obras rodoviárias – Produto D-10 (Caracterização da oferta futura)"),
    ("4.4.5", "Protótipos de Aplicações do PLI na SEMIL"),
    ("4.4.6", "Avaliação e ajuste dos VDMA das rodovias paulistas"),
    ("4.4.7", "Atividades de padronização e revisão de documentos"),
    ("4.5", "Produtos medidos no período da medição"),
    ("5", "Equipe de Apoio Técnico Mobilizada"),
    ("6", "Gestão de Recursos"),
    ("7", "Cronograma"),
    ("8", "Análise de Risco"),
    ("8.1", "Planilha Medição do Produto D21"),
    ("9", "Próximos Passos"),
    ("10", "Produto D21 – Apoio Técnico"),
    ("10.1", "Declaração de participação dos profissionais de apoio técnico"),
    ("11", "Cronograma Físico-Financeiro: Previsto e Realizado"),
    ("12", "Resumo da Medição"),
    ("13", "Assinaturas"),
]


class Secao(Base):
    __tablename__ = "secoes"
    id = Column(Integer, primary_key=True)
    relatorio_id = Column(Integer, ForeignKey("relatorios.id", ondelete="CASCADE"), nullable=False)
    numero = Column(String(16), nullable=False)   # 1, 2, 4.1, 4.4...
    titulo = Column(String(255), nullable=False)
    ordem = Column(Integer, nullable=False, default=0)
    responsavel_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(32), nullable=False, default="pendente")  # pendente, em_andamento, aprovada

    relatorio = relationship("Relatorio", back_populates="secoes")
    responsavel = relationship("User")
    blocos = relationship("Bloco", back_populates="secao", cascade="all, delete-orphan", order_by="Bloco.ordem")

    __table_args__ = (UniqueConstraint("relatorio_id", "numero", name="uq_secao_rel_num"),)


class Bloco(Base):
    __tablename__ = "blocos"
    id = Column(Integer, primary_key=True)
    secao_id = Column(Integer, ForeignKey("secoes.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(32), nullable=False)  # texto, figura, tabela, lista
    ordem = Column(Integer, nullable=False, default=0)
    titulo = Column(String(255), nullable=True)
    conteudo = Column(Text, nullable=True)        # markdown / html / json
    legenda = Column(String(512), nullable=True)
    fonte = Column(String(255), nullable=True)
    figura_id = Column(Integer, ForeignKey("figuras.id"), nullable=True)
    autor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    bloqueado = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    secao = relationship("Secao", back_populates="blocos")
    figura = relationship("Figura")
    autor = relationship("User")


class Figura(Base):
    __tablename__ = "figuras"
    id = Column(Integer, primary_key=True)
    relatorio_id = Column(Integer, ForeignKey("relatorios.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String(255), nullable=False)
    mime = Column(String(64), nullable=False)
    dados = Column(LargeBinary, nullable=False)
    legenda = Column(String(512), nullable=True)
    fonte = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Ciclo de notificações e entregas mensais
# ---------------------------------------------------------------------------
#
# Modelo: 1 EntregaRelatorio por (relatorio, usuario destinatário). 1:N
# NotificacaoEnvio rastreia cada email disparado (abertura, lembrete, última
# chamada, reenvio manual) — pode haver mais de uma linha por ``tipo`` quando
# existem ``email`` e ``email2``. Status do destinatário evolui de `notificado`
# (após 1ª notificação com sucesso ao **principal**) -> `aguardando_envio`
# (após 2ª ao principal) -> `enviado` (todos
# os blocos das suas seções marcados como bloqueado=true) -> `validado`
# (coord confirma o conteúdo). "Finalizado" continua sendo estado do
# Relatorio inteiro, não do destinatário.
ENTREGA_STATUS_VALIDOS = (
    "notificado",
    "aguardando_envio",
    "enviado",
    "validado",
)
NOTIFICACAO_TIPOS_VALIDOS = (
    "abertura",
    "lembrete",
    "ultima_chamada",
    "manual",
)


class EntregaRelatorio(Base):
    __tablename__ = "entrega_relatorio"
    id = Column(Integer, primary_key=True)
    relatorio_id = Column(
        Integer, ForeignKey("relatorios.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(32), nullable=False, default="notificado", server_default="notificado")
    data_envio = Column(DateTime, nullable=True)
    data_validacao = Column(DateTime, nullable=True)
    validado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    relatorio = relationship("Relatorio")
    user = relationship("User", foreign_keys=[user_id])
    validado_por = relationship("User", foreign_keys=[validado_por_id])
    atualizado_por = relationship("User", foreign_keys=[atualizado_por_id])
    notificacoes = relationship(
        "NotificacaoEnvio",
        back_populates="entrega",
        cascade="all, delete-orphan",
        order_by="NotificacaoEnvio.enviada_em",
    )

    __table_args__ = (
        UniqueConstraint("relatorio_id", "user_id", name="uq_entrega_rel_user"),
    )


class NotificacaoEnvio(Base):
    __tablename__ = "notificacao_envio"
    id = Column(Integer, primary_key=True)
    entrega_id = Column(
        Integer, ForeignKey("entrega_relatorio.id", ondelete="CASCADE"), nullable=False
    )
    tipo = Column(String(32), nullable=False)
    enviada_em = Column(DateTime, nullable=False, default=datetime.utcnow)
    sucesso = Column(Boolean, nullable=False, default=False)
    erro = Column(Text, nullable=True)
    # Snapshot do email no momento do envio: preserva auditoria mesmo se o
    # User trocar de email depois.
    destinatario_email = Column(String(255), nullable=False)
    sendgrid_message_id = Column(String(255), nullable=True)

    entrega = relationship("EntregaRelatorio", back_populates="notificacoes")

    __table_args__ = (
        Index("ix_notif_entrega_data", "entrega_id", "enviada_em"),
    )


class ParametrosCicloNotificacao(Base):
    """Única linha ``id=1``: parâmetros do ciclo mensal editáveis na UI (coord/admin)."""

    __tablename__ = "parametros_ciclo_notificacao"

    id = Column(Integer, primary_key=True)
    ciclo_dia_mes_anterior = Column(Integer, nullable=False, default=11)
    ciclo_dia_mes_atual = Column(Integer, nullable=False, default=11)
    prazo_autor_dia = Column(Integer, nullable=False, default=8)
    prazo_coordenacao_dia = Column(Integer, nullable=False, default=10)
    dias_lembrete_csv = Column(String(128), nullable=False, default="5,8")
    dia_ultima_chamada = Column(Integer, nullable=False, default=10)
    dia_abertura_novo_ciclo = Column(Integer, nullable=False, default=1)
    hora_abertura_brt_hhmm = Column(String(5), nullable=False, default="03:00")
    hora_lembretes_brt_hhmm = Column(String(5), nullable=False, default="09:00")
    hora_retry_brt_hhmm = Column(String(5), nullable=False, default="12:00")
    observacoes_internas = Column(Text, nullable=True)
    atualizado_em = Column(DateTime, nullable=True)
