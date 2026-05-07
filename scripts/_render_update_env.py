"""Atualiza env vars do servico sra-pli-starter no Render.

Uso: python scripts/_render_update_env.py
Requer: RENDER_API_TOKEN no ambiente/.env
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

TOKEN = os.environ.get("RENDER_API_TOKEN", "").strip()
if not TOKEN:
    sys.exit("RENDER_API_TOKEN nao definido")

SERVICE_ID = "srv-d7oiv8dckfvc73ae73u0"
BASE = f"https://api.render.com/v1/services/{SERVICE_ID}"


def _req(method: str, path: str, body: dict | None = None):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")}


def _upsert(key: str, value: str) -> None:
    status, payload = _req("PUT", f"/env-vars/{key}", {"value": value})
    if status in (200, 201):
        print(f"  OK   {key} atualizada (status={status})")
    else:
        print(f"  FAIL {key}: status={status} payload={payload}")


def main() -> None:
    print("Atualizando env vars do servico", SERVICE_ID)

    # 1) SECRET_KEY forte (64 chars urlsafe)
    nova_secret = secrets.token_urlsafe(48)
    _upsert("SECRET_KEY", nova_secret)

    # 2) SESSION_COOKIE_SECURE obrigatorio em producao
    _upsert("SESSION_COOKIE_SECURE", "true")

    # 3) Sentry (opcional; vazio = off)
    _upsert("SENTRY_DSN", "")
    _upsert("SENTRY_TRACES_SAMPLE_RATE", "0.1")

    print()
    print("Nova SECRET_KEY aplicada (len=%d). Guarde em gestor de senhas se precisar:" % len(nova_secret))
    print(nova_secret)


if __name__ == "__main__":
    main()
