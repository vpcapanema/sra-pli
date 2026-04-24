"""Aplica a CHECK constraint users_nome_format_chk no Postgres do Render.

Normaliza nomes existentes para o padrão 'Vinicius do Prado Capanema' e cria
a constraint. Use uma única vez (idempotente).
"""
import os
import re
import sys

import psycopg2

PARTS = {"do", "da", "de", "dos", "das", "du", "e", "di", "del", "la", "von", "van"}


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
    conn = psycopg2.connect(
        host="dpg-d7l67l9j2pic73cl15m0-a.oregon-postgres.render.com",
        port=5432,
        user="sra",
        password="5snFWwPqRTF6Ky9JbjMXOvXZFObvByfl",
        dbname="sra_93i5",
        sslmode="require",
        connect_timeout=15,
    )
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
