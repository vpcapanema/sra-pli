"""Resolução do nome de ficheiro ``.dotx`` para uma seção.

Esta é a fonte única de verdade — o build script
(``scripts/build_canonical_upload_dotx.py``) também importa daqui para
garantir que o ficheiro gerado e o link no email coincidem.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Pasta onde o build script grava os ``.dotx`` gerados.
MODELOS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "modelos_upload_doc_canonicos"
)

DOTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.template.main+xml"
)


def slug_titulo(titulo: str) -> str:
    """Normaliza um título para slug ASCII compatível com nome de ficheiro.

    Decompose em NFD, remove combining marks (acentos), substitui
    sequências de chars não permitidos por ``_``, mantém ``.``, ``_`` e ``-``.
    """
    nfd = unicodedata.normalize("NFD", titulo)
    ascii_only = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", ascii_only).strip("_")
    if not slug:
        return "secao"
    return slug[:100]


def filename_para(numero: str, titulo: str) -> str:
    """Devolve o filename ``.dotx`` exato para uma seção."""
    safe_num = re.sub(r"[^\d.]+", "", numero) or "sec"
    return f"secao_{safe_num.replace('.', '_')}_{slug_titulo(titulo)}.dotx"


def caminho_para(numero: str, titulo: str) -> Path:
    """Path completo para o ficheiro ``.dotx``."""
    return MODELOS_DIR / filename_para(numero, titulo)
