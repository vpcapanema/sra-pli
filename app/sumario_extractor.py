"""Extracao do SUMARIO (TOC) de relatorios PDF.

Duas fontes possiveis:
  - PDFs ja existentes em ``relatorios_entregues/`` (lista fixa em disco)
  - Upload de PDF feito pelo usuario (bytes em memoria)

A funcao ``extrair_sumario`` recebe um caminho ou bytes, lê as primeiras
paginas do PDF, identifica a pagina com a palavra ``SUMARIO`` e extrai
todas as entradas no formato ``N.N.N  Titulo .... 99``.
"""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Tuple

import pypdf

PASTA_RELATORIOS = Path(__file__).resolve().parent.parent / "relatorios_entregues"

# Linha tipica: "4.4.6.1 Os tratamentos de dados realizados foram: ........ 39"
# Exigimos pontilhado (>=3 pontos/espacos) + numero de pagina no fim, que e o
# que distingue uma entrada do SUMARIO de um titulo no corpo do relatorio.
_RE_LINHA_SUMARIO = re.compile(
    r"^\s*(\d+(?:\.\d+){0,5})\s+(.+?)\s*[.\u2026][.\u2026\s]{2,}\s*(\d{1,4})\s*$"
)


def _strip_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def listar_pdfs_disponiveis() -> List[str]:
    """Lista nomes de PDFs em ``relatorios_entregues/`` (ordenados)."""
    if not PASTA_RELATORIOS.is_dir():
        return []
    return sorted(p.name for p in PASTA_RELATORIOS.iterdir() if p.suffix.lower() == ".pdf")


def _ler_paginas_iniciais(reader: pypdf.PdfReader, max_paginas: int = 8) -> str:
    partes: List[str] = []
    for i, page in enumerate(reader.pages[:max_paginas]):
        try:
            partes.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - pypdf pode lancar varios tipos
            continue
    return "\n".join(partes)


def _parse_sumario(texto: str) -> List[Tuple[str, str]]:
    """Extrai entradas (numero, titulo) do bloco do SUMARIO."""
    linhas = texto.splitlines()
    # Localiza a palavra SUMARIO (sem acento) na lista de linhas
    inicio = -1
    for idx, ln in enumerate(linhas):
        if "SUMARIO" in _strip_acentos(ln).upper():
            inicio = idx + 1
            break
    if inicio < 0:
        return []

    entradas: List[Tuple[str, str]] = []
    vistos: set[str] = set()
    for ln in linhas[inicio:]:
        m = _RE_LINHA_SUMARIO.match(ln)
        if not m:
            continue
        numero = m.group(1).strip()
        titulo = m.group(2).strip().rstrip(".").strip()
        if not titulo or len(titulo) < 2:
            continue
        if numero in vistos:
            # Apareceu de novo: provavelmente ja entramos no corpo do relatorio
            break
        vistos.add(numero)
        entradas.append((numero, titulo))
    return entradas


def extrair_sumario(fonte: "str | Path | bytes") -> List[Tuple[str, str]]:
    """Extrai o sumario de um PDF (path em disco ou bytes em memoria)."""
    if isinstance(fonte, (str, Path)):
        reader = pypdf.PdfReader(str(fonte))
    else:
        reader = pypdf.PdfReader(io.BytesIO(fonte))
    texto = _ler_paginas_iniciais(reader)
    return _parse_sumario(texto)


def extrair_sumario_pdf_disponivel(nome_arquivo: str) -> List[Tuple[str, str]]:
    """Extrai sumario de um PDF da pasta ``relatorios_entregues/``.

    Valida o nome para evitar path traversal: aceita apenas nomes presentes
    em ``listar_pdfs_disponiveis()``.
    """
    disponiveis = set(listar_pdfs_disponiveis())
    if nome_arquivo not in disponiveis:
        raise ValueError(f"PDF nao disponivel: {nome_arquivo}")
    return extrair_sumario(PASTA_RELATORIOS / nome_arquivo)
