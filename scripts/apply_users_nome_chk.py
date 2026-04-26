"""Aplica a CHECK constraint users_nome_format_chk no Postgres.

Normaliza nomes existentes para o padrão 'Vinicius do Prado Capanema' e cria
a constraint. Use uma única vez (idempotente).

Conexão: lê de `DATABASE_URL` (mesma var usada pela app). Aceita os formatos
`postgresql://...` e `postgresql+psycopg2://...`.
"""
import os
import re
import sys

import psycopg2

PARTS = {"do", "da", "de", "dos", "das", "du", "e", "di", "del", "la", "von", "van"}


def _resolve_dsn() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit(
            "DATABASE_URL nao definida. Exporte a URL do Postgres antes de rodar este script."
        )
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://") :]
    return url


def fmt(s: str) -> str:
    ws = [w for w in re.split(r"\s+", (s or "").strip()) if w]
    if not ws:
        ws = ["Usuario", "Sistema"]
    elif len(ws) < 2:
        ws = ws + ["Silva"]
    out = []
    for i, w in enumerate(ws):
        b = w.lower()
        if i > 0 and b in PARTS:
            out.append(b)
        else:
            out.append(b[:1].upper() + b[1:])
    return " ".join(out)


DDL = (
    "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_nome_format_chk;"
    "ALTER TABLE users ADD CONSTRAINT users_nome_format_chk CHECK ("
    "nome ~ '^[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+"
    "(\\s(do|da|de|dos|das|du|e|di|del|la|von|van)|"
    "\\s[A-ZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ][a-záàâãäéèêëíìîïóòôõöúùûüçñ]+)+$'"
    ");"
)


def main() -> int:
    conn = psycopg2.connect(_resolve_dsn(), sslmode="require", connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM users")
    rows = cur.fetchall()
    print("users antes:", rows)
    for uid, nm in rows:
        novo = fmt(nm)
        if novo != nm:
            cur.execute("UPDATE users SET nome=%s WHERE id=%s", (novo, uid))
            print(f"fix id={uid}: {nm!r} -> {novo!r}")
    conn.commit()
    cur.execute(DDL)
    conn.commit()
    cur.execute("SELECT conname FROM pg_constraint WHERE conname=%s", ("users_nome_format_chk",))
    print("constraint:", cur.fetchone())
    cur.execute("SELECT id, nome FROM users")
    print("users depois:", cur.fetchall())
    conn.close()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
