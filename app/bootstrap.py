from sqlalchemy.orm import Session
from sqlalchemy import text
from .db import engine, SessionLocal, Base
from .models import User, SECOES_PADRAO
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
            conn.execute(
                text("ALTER TABLE blocos ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN DEFAULT false;")
            )
            # Notificações mensais: opt-out dos autores. Default true para os
            # registros existentes não pararem de receber por engano. Postgres
            # >= 11 evita rewrite da tabela quando default é constante.
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN IF NOT EXISTS notificacoes_ativas BOOLEAN "
                    "NOT NULL DEFAULT true;"
                )
            )
    with SessionLocal() as db:
        ensure_admin(db)


def ensure_admin(db: Session) -> None:
    existing = (
        db.query(User)
        .filter(User.email == settings.ADMIN_EMAIL, User.role == "admin")
        .one_or_none()
    )
    if existing:
        return
    admin = User(
        email=settings.ADMIN_EMAIL,
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
            db.query(Relatorio)
            .filter(Relatorio.id != relatorio_id)
            .order_by(Relatorio.created_at.desc())
            .first()
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
