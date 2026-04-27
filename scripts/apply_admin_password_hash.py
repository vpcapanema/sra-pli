"""Aplica hash bcrypt ao usuario admin (email em settings.ADMIN_EMAIL).

Uso:
  .\\.venv\\Scripts\\python.exe scripts/apply_admin_password_hash.py

O hash e o esperado no banco; apos aplicar, confira se ADMIN_PASSWORD no .env
corresponde a esse hash (senao o login continua falhando).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth import verify_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402

# Hash informado pelo operador (bcrypt).
TARGET_HASH = (
    "$2b$12$biYgQZ5ihRpxvKoF02b0iOGyQBboR7koavscTcE/TQSjUnO9b3wU2"
)


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == settings.ADMIN_EMAIL).one_or_none()
        if not user:
            print(f"ERRO: usuario {settings.ADMIN_EMAIL!r} nao encontrado.")
            sys.exit(1)
        user.password_hash = TARGET_HASH
        db.commit()
        print(f"OK: password_hash atualizado para {settings.ADMIN_EMAIL!r}.")
    finally:
        db.close()

    env_ok = verify_password(settings.ADMIN_PASSWORD, TARGET_HASH)
    if env_ok:
        print("OK: ADMIN_PASSWORD do .env confere com o hash aplicado.")
    else:
        print(
            "AVISO: ADMIN_PASSWORD no .env NAO confere com este hash. "
            "Atualize o .env com a senha em texto plano correta ou gere novo hash."
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
