from sqlalchemy.orm import Session
from sqlalchemy import text
from .db import engine, SessionLocal, Base
from .models import ParametrosCicloNotificacao, User, SECOES_PADRAO
from .auth import hash_password
from .config import settings
from . import models  # noqa: F401  garante registro dos modelos


# Regex Postgres equivalente ao validador Python (formatar_nome_pessoa).
# Mantemos isolado para evitar drop+recreate a cada boot. Se o regex mudar,
# rode uma migração manual: DROP CONSTRAINT + ADD CONSTRAINT (ou bumpe o nome).
_USERS_NOME_REGEX = (
    "^[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+"
    "(\\s(do|da|de|dos|das|du|e|di|del|la|von|van)|"
    "\\s[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+)+$"
)
_USERS_NOME_CHK_DDL = f"""
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_nome_format_chk'
  ) THEN
    ALTER TABLE users
      ADD CONSTRAINT users_nome_format_chk
      CHECK (nome ~ '{_USERS_NOME_REGEX}');
  END IF;
END$$;
"""
# E-mail pode repetir entre perfis distintos; par (email, role) é único.
_USERS_DROP_EMAIL_UNIQUE_DDL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key'
  ) THEN
    ALTER TABLE users DROP CONSTRAINT users_email_key;
  END IF;
END$$;
"""
_USERS_ADD_EMAIL_ROLE_UQ_DDL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_email_role'
  ) THEN
    ALTER TABLE users ADD CONSTRAINT uq_users_email_role UNIQUE (email, role);
  END IF;
END$$;
"""
# Versões antigas criaram ix_users_email como UNIQUE; CREATE INDEX IF NOT EXISTS
# não substitui índice existente, daí o 500 ao inserir o mesmo e-mail com outro perfil.
_USERS_DROP_IX_EMAIL_DDL = "DROP INDEX IF EXISTS ix_users_email;"
_USERS_IX_EMAIL_DDL = "CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);"


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        # Idempotente: só executa DDL real se a coluna/constraint não existirem ainda.
        with engine.begin() as conn:
            conn.execute(text(_USERS_NOME_CHK_DDL))
            conn.execute(text(_USERS_DROP_EMAIL_UNIQUE_DDL))
            conn.execute(text(_USERS_DROP_IX_EMAIL_DDL))
            conn.execute(text(_USERS_ADD_EMAIL_ROLE_UQ_DDL))
            conn.execute(text(_USERS_IX_EMAIL_DDL))
            conn.execute(text("ALTER TABLE blocos ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN DEFAULT false;"))
            conn.execute(
                text("ALTER TABLE blocos ADD COLUMN IF NOT EXISTS origem VARCHAR(32) NOT NULL DEFAULT 'manual';")
            )
            # Notificações mensais: opt-out dos autores. Default true para os
            # registros existentes não pararem de receber por engano. Postgres
            # >= 11 evita rewrite da tabela quando default é constante.
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS notificacoes_ativas BOOLEAN NOT NULL DEFAULT true;")
            )
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email2 VARCHAR(255);"))
            conn.execute(text("UPDATE users SET email2 = email WHERE email2 IS NULL OR TRIM(email2) = '';"))
            conn.execute(text("ALTER TABLE users ALTER COLUMN email2 SET NOT NULL;"))
            conn.execute(text("ALTER TABLE notificacao_envio ADD COLUMN IF NOT EXISTS provedor_status VARCHAR(32);"))
            conn.execute(text("ALTER TABLE notificacao_envio ADD COLUMN IF NOT EXISTS provedor_status_em TIMESTAMP;"))
            conn.execute(text("ALTER TABLE notificacao_envio ADD COLUMN IF NOT EXISTS provedor_motivo TEXT;"))
            conn.execute(text("ALTER TABLE notificacao_envio ADD COLUMN IF NOT EXISTS aberto_em TIMESTAMP;"))
            # Reprovação pelo coordenador (página Validação e Revisão).
            # Sobrescritos a cada nova reprovação; histórico completo fica fora
            # desta v1 para manter o schema simples.
            conn.execute(text("ALTER TABLE entrega_relatorio ADD COLUMN IF NOT EXISTS motivo_reprovacao TEXT;"))
            conn.execute(text("ALTER TABLE entrega_relatorio ADD COLUMN IF NOT EXISTS data_reprovacao TIMESTAMP;"))
            conn.execute(
                text(
                    "ALTER TABLE entrega_relatorio "
                    "ADD COLUMN IF NOT EXISTS reprovado_por_id INTEGER "
                    "REFERENCES users(id);"
                )
            )
            conn.execute(text("ALTER TABLE secoes ADD COLUMN IF NOT EXISTS ordem INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE secoes ADD COLUMN IF NOT EXISTS observacao_validacao TEXT;"))
            # Orientação A4 por seção (espelha w:pgSz/w:orient do DOCX).
            conn.execute(
                text("ALTER TABLE secoes ADD COLUMN IF NOT EXISTS orientacao VARCHAR(16) NOT NULL DEFAULT 'portrait';")
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS ciclo_dia_mes_anterior INTEGER NOT NULL DEFAULT 11;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS ciclo_dia_mes_atual INTEGER NOT NULL DEFAULT 11;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS prazo_autor_dia INTEGER NOT NULL DEFAULT 8;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS prazo_coordenacao_dia INTEGER NOT NULL DEFAULT 10;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS dias_lembrete_csv VARCHAR(128) NOT NULL DEFAULT '5,8';"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS dia_ultima_chamada INTEGER NOT NULL DEFAULT 10;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS dia_abertura_novo_ciclo INTEGER NOT NULL DEFAULT 1;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS hora_abertura_brt_hhmm VARCHAR(5) NOT NULL DEFAULT '03:00';"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS hora_lembretes_brt_hhmm VARCHAR(5) NOT NULL DEFAULT '09:00';"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE parametros_ciclo_notificacao "
                    "ADD COLUMN IF NOT EXISTS hora_retry_brt_hhmm VARCHAR(5) NOT NULL DEFAULT '12:00';"
                )
            )
            conn.execute(
                text("ALTER TABLE parametros_ciclo_notificacao ADD COLUMN IF NOT EXISTS observacoes_internas TEXT;")
            )
            conn.execute(
                text("ALTER TABLE parametros_ciclo_notificacao ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP;")
            )
    with SessionLocal() as db:
        ensure_admin(db)
        ensure_parametros_ciclo_notificacao(db)


def ensure_parametros_ciclo_notificacao(db: Session) -> None:
    """Garante a linha singleton de parâmetros do ciclo mensal (id=1)."""
    if db.get(ParametrosCicloNotificacao, 1) is None:
        db.add(ParametrosCicloNotificacao(id=1))
        db.commit()


def ensure_admin(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL, User.role == "admin").one_or_none()
    if existing:
        return
    admin = User(
        email=settings.ADMIN_EMAIL,
        email2=settings.ADMIN_EMAIL.strip().lower(),
        nome="Administrador do Sistema",
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        role="admin",
    )
    db.add(admin)
    db.commit()


def criar_secoes_padrao(
    db: Session,
    relatorio_id: int,
    secoes_explicitas: "list[tuple[str, str]] | None" = None,
) -> None:
    """Cria as seções de um relatório novo.

    Ordem de prioridade da fonte:
      1. ``secoes_explicitas`` (quando fornecida — ex.: extraída de um PDF).
      2. Estrutura do relatório anterior mais recente no banco.
      3. ``SECOES_PADRAO`` (semente embutida).
    """
    from .models import Secao, Relatorio

    if secoes_explicitas:
        base = list(secoes_explicitas)
    else:
        anterior = (
            db.query(Relatorio).filter(Relatorio.id != relatorio_id).order_by(Relatorio.created_at.desc()).first()
        )
        if anterior is not None and anterior.secoes:
            base = [(s.numero, s.titulo) for s in sorted(anterior.secoes, key=lambda x: x.ordem)]
        else:
            base = list(SECOES_PADRAO)
    for i, (numero, titulo) in enumerate(base):
        ja = db.query(Secao).filter_by(relatorio_id=relatorio_id, numero=numero).first()
        if ja:
            continue
        db.add(Secao(relatorio_id=relatorio_id, numero=numero, titulo=titulo, ordem=i))
    # Caller é responsável pelo commit (pode estar dentro de uma tx_session).
    db.flush()
