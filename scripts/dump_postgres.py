"""Dump todas as tabelas para um pickle local."""
from __future__ import annotations
import pickle, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, MetaData
from app.db import Base
import app.models  # noqa

URL = sys.argv[1]
OUT = sys.argv[2]
eng = create_engine(URL.replace("postgresql://", "postgresql+psycopg2://"), isolation_level="AUTOCOMMIT")
md = MetaData(); md.reflect(bind=eng)
data = {}
with eng.connect() as c:
    for t in md.sorted_tables:
        rows = [dict(r) for r in c.execute(t.select()).mappings()]
        data[t.name] = rows
        print(f"  {t.name}: {len(rows)}")
with open(OUT, "wb") as f:
    pickle.dump({"tables_order": [t.name for t in md.sorted_tables], "data": data}, f)
print(f"OK -> {OUT}")
