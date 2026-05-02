"""
Migra schema + dados do Postgres SOURCE para o TARGET.

Uso:
    python scripts/migrate_postgres.py \
        --source "postgresql://user:pass@host:5432/db?sslmode=require" \
        --target "postgresql://user:pass@host:5432/db?sslmode=require"

Estratégia:
1. Usa SQLAlchemy/Base.metadata para criar o schema no TARGET (idempotente).
2. Para cada tabela na ordem topológica, copia linhas em lotes via psycopg2 COPY.
3. Reseta sequences para MAX(id)+1 no TARGET.
"""
from __future__ import annotations
import argparse
import sys

from sqlalchemy import create_engine, MetaData, Table, text

# garante import do pacote app
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base  # noqa: E402
import app.models  # noqa: F401,E402  registra as tabelas no Base.metadata
from scripts.postgres_seq_discovery import POSTGRES_SEQUENCE_COLUMN_MAP_SQL  # noqa: E402


def _normalize(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _enriquecer_chunk_users_email2(tbl_name: str, chunk: list[dict]) -> None:
    """Fonte antiga sem ``email2``: preenche com ``email`` para o alvo NOT NULL."""
    if tbl_name != "users":
        return
    for row in chunk:
        if not row.get("email2"):
            row["email2"] = row.get("email") or ""


def main() -> int:  # pylint: disable=too-many-locals
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--batch", type=int, default=1000)
    args = p.parse_args()

    src = create_engine(_normalize(args.source), isolation_level="AUTOCOMMIT")
    tgt = create_engine(_normalize(args.target), isolation_level="AUTOCOMMIT")

    print(f"[1/4] Criando schema no TARGET ({len(Base.metadata.tables)} tabelas)...")
    Base.metadata.create_all(tgt)

    md = MetaData()
    md.reflect(bind=src)

    # ordem topologica conforme FKs
    ordered = md.sorted_tables
    print(f"[2/4] Ordem de copia: {[t.name for t in ordered]}")

    print("[3/4] Copiando linhas...")
    with src.connect() as sconn, tgt.connect() as tconn:
        # Desabilita FKs no target durante carga
        tconn.execute(text("SET session_replication_role = 'replica';"))
        try:
            for tbl in ordered:
                # trunca destino para idempotencia
                tconn.execute(text(f'TRUNCATE TABLE "{tbl.name}" RESTART IDENTITY CASCADE;'))

                rows = list(sconn.execute(tbl.select()).mappings())
                if not rows:
                    print(f"   - {tbl.name}: 0 linhas")
                    continue
                # insert em lotes
                tgt_tbl = Table(tbl.name, MetaData(), autoload_with=tgt)
                for i in range(0, len(rows), args.batch):
                    chunk = [dict(r) for r in rows[i : i + args.batch]]
                    _enriquecer_chunk_users_email2(tbl.name, chunk)
                    tconn.execute(tgt_tbl.insert(), chunk)
                print(f"   - {tbl.name}: {len(rows)} linhas")
        finally:
            tconn.execute(text("SET session_replication_role = 'origin';"))

    print("[4/4] Resetando sequences...")
    with tgt.connect() as tconn:
        seqs = tconn.execute(text(POSTGRES_SEQUENCE_COLUMN_MAP_SQL)).all()
        for seq, tbl, col in seqs:
            mx = tconn.execute(text(f'SELECT COALESCE(MAX("{col}"), 0) FROM "{tbl}"')).scalar()
            tconn.execute(text(f"SELECT setval('{seq}', {int(mx) + 1}, false)"))
            print(f"   - {seq} -> {int(mx) + 1}")

    print("OK. Migracao concluida.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
