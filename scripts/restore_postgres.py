"""Restaura pickle gerado por dump_postgres.py em um Postgres alvo."""
from __future__ import annotations
import pickle, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, MetaData, Table, text
from app.db import Base
import app.models  # noqa

URL = sys.argv[1]
INP = sys.argv[2]
eng = create_engine(URL.replace("postgresql://", "postgresql+psycopg2://"), isolation_level="AUTOCOMMIT")
print("[1/3] create_all...")
Base.metadata.create_all(eng)
with open(INP, "rb") as f:
    dump = pickle.load(f)
print("[2/3] inserindo...")
md = MetaData(); md.reflect(bind=eng)
with eng.connect() as c:
    # trunca em ordem reversa (filhos antes de pais) para nao violar FKs
    for tname in reversed(dump["tables_order"]):
        if tname in md.tables:
            c.execute(text(f'TRUNCATE TABLE "{tname}" RESTART IDENTITY CASCADE;'))
    # insere em ordem direta (pais antes de filhos)
    for tname in dump["tables_order"]:
        rows = dump["data"].get(tname, [])
        tbl = md.tables.get(tname)
        if tbl is None:
            print(f"  ! tabela ausente no destino: {tname}"); continue
        if rows:
            c.execute(tbl.insert(), rows)
        print(f"  {tname}: {len(rows)}")
print("[3/3] sequences...")
with eng.connect() as c:
    seqs = c.execute(text("""
        SELECT s.relname AS seq, t.relname AS tbl, a.attname AS col
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind='S'
    """)).all()
    for seq, tbl, col in seqs:
        mx = c.execute(text(f'SELECT COALESCE(MAX("{col}"),0) FROM "{tbl}"')).scalar()
        c.execute(text(f"SELECT setval('{seq}', {int(mx)+1}, false)"))
        print(f"  {seq} -> {int(mx)+1}")
print("OK")
