"""Configuracao do pytest: injeta variaveis minimas para `import app.*` funcionar."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# APP_ENV=test evita validacao de producao em config.py
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://user:pass@localhost:5432/sra_test",
    ),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-nao-usar-em-producao")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-nao-usar")
