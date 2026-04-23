from sqlalchemy.orm import Session
from .db import engine, SessionLocal, Base
from .models import User, SECOES_PADRAO
from .auth import hash_password
from .config import settings
from . import models  # noqa: F401  garante registro dos modelos


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin(db)


def ensure_admin(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL).one_or_none()
    if existing:
        return
    admin = User(
        email=settings.ADMIN_EMAIL,
        nome="Administrador",
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
