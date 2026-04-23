from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, ForeignKey, LargeBinary, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    nome = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="autor")  # admin, coordenador, autor
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
    ("2", "Histórico"),
    ("3", "Relação de Produtos Entregues"),
    ("4.1", "Coordenação"),
    ("4.2", "Sistema de Informação"),
    ("4.3", "Comunicação Social"),
    ("4.4", "Apoio Técnico"),
    ("5", "Gestão de Recursos"),
    ("6", "Cronograma"),
    ("7", "Análise de Risco"),
    ("8", "Próximos Passos"),
    ("9", "Equipe"),
    ("10", "Produto D21"),
    ("11", "Cronograma Físico-Financeiro"),
    ("12", "Resumo da Medição"),
    ("13", "Apêndices"),
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
