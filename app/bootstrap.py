from sqlalchemy.orm import Session
from sqlalchemy import text
from .db import engine, SessionLocal, Base
from .models import User, SECOES_PADRAO
from .auth import hash_password
from .config import settings
from . import models  # noqa: F401  garante registro dos modelos


# Regex Postgres equivalente ao validador Python (formatar_nome_pessoa).
_USERS_NOME_CHK = (
    "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_nome_format_chk; "
    "ALTER TABLE users ADD CONSTRAINT users_nome_format_chk CHECK ("
    "nome ~ '^[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+"
    "(\\s(do|da|de|dos|das|du|e|di|del|la|von|van)|"
    "\\s[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+)+$'"
    ");"
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(_USERS_NOME_CHK))
    with SessionLocal() as db:
        ensure_admin(db)


def ensure_admin(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).one_or_none()
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


def criar_secoes_padrao(db: Session, relatorio_id: int) -> None:
    from .models import Secao
    for i, (numero, titulo) in enumerate(SECOES_PADRAO):
        ja = db.query(Secao).filter_by(relatorio_id=relatorio_id, numero=numero).first()
        if ja:
            continue
        db.add(Secao(relatorio_id=relatorio_id, numero=numero, titulo=titulo, ordem=i))
    db.commit()
