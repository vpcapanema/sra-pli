"""Consulta reutilizavel: sequences Postgres associadas a tabela e coluna."""

from __future__ import annotations

POSTGRES_SEQUENCE_COLUMN_MAP_SQL = """
SELECT s.relname AS seq, t.relname AS tbl, a.attname AS col
FROM pg_class s
JOIN pg_depend d ON d.objid = s.oid
JOIN pg_class t ON t.oid = d.refobjid
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
WHERE s.relkind = 'S'
"""
