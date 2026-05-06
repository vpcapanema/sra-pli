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


def listar_pdfs_disponiveis() -> list[str]:
    """Lista nomes de PDFs em ``relatorios_entregues/`` (ordenados)."""
    if not PASTA_RELATORIOS.is_dir():
        return []
    return sorted(p.name for p in PASTA_RELATORIOS.iterdir() if p.suffix.lower() == ".pdf")


def _ler_paginas_iniciais(reader: pypdf.PdfReader, max_paginas: int = 8) -> str:
    partes: list[str] = []
    for i, page in enumerate(reader.pages[:max_paginas]):
        try:
            partes.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - pypdf pode lancar varios tipos
            continue
    return "\n".join(partes)


def _parse_sumario(texto: str) -> list[tuple[str, str]]:
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

    entradas: list[tuple[str, str]] = []
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


def extrair_sumario(fonte: "str | Path | bytes") -> list[tuple[str, str]]:
    """Extrai o sumario de um PDF (path em disco ou bytes em memoria)."""
    if isinstance(fonte, (str, Path)):
        reader = pypdf.PdfReader(str(fonte))
    else:
        reader = pypdf.PdfReader(io.BytesIO(fonte))
    texto = _ler_paginas_iniciais(reader)
    return _parse_sumario(texto)


def extrair_sumario_pdf_disponivel(nome_arquivo: str) -> list[tuple[str, str]]:
    """Extrai sumario de um PDF da pasta ``relatorios_entregues/``.

    Valida o nome para evitar path traversal: aceita apenas nomes presentes
    em ``listar_pdfs_disponiveis()``.
    """
    disponiveis = set(listar_pdfs_disponiveis())
    if nome_arquivo not in disponiveis:
        raise ValueError(f"PDF nao disponivel: {nome_arquivo}")
    return extrair_sumario(PASTA_RELATORIOS / nome_arquivo)


# ---------------------------------------------------------------------------
# Extração completa: seções + conteúdo (blocos de texto, tabela, figura)
# ---------------------------------------------------------------------------

# Regex para cabeçalhos de seção no corpo do PDF (ex: "4.1 Título da Seção")
_RE_CABECALHO_SECAO = re.compile(
    r"^\s*(\d+(?:\.\d+){0,5})\s+(.+?)\s*$"
)


def _ler_pdf_completo(reader: pypdf.PdfReader) -> str:
    """Lê todas as páginas do PDF e retorna o texto concatenado."""
    partes: list[str] = []
    for page in reader.pages:
        try:
            partes.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(partes)


def extrair_secoes_e_conteudo(
    fonte: "str | Path | bytes",
) -> list[tuple[str, str, str]]:
    """Extrai seções com conteúdo completo de um PDF.

    Retorna lista de tuplas ``(numero, titulo, conteudo_html)`` onde
    ``conteudo_html`` é o texto bruto da seção (parágrafos separados por
    ``<p>...</p>``).

    Usa o sumário para saber quais seções existem, depois localiza cada
    cabeçalho no corpo do PDF e captura o texto até o próximo cabeçalho.
    """
    if isinstance(fonte, (str, Path)):
        reader = pypdf.PdfReader(str(fonte))
    else:
        reader = pypdf.PdfReader(io.BytesIO(fonte))

    # 1) Extrai sumário para saber quais seções esperar
    texto_inicio = _ler_paginas_iniciais(reader)
    sumario = _parse_sumario(texto_inicio)
    if not sumario:
        return []

    # 2) Lê PDF completo
    texto_completo = _ler_pdf_completo(reader)
    linhas = texto_completo.splitlines()

    # 3) Monta set de números válidos do sumário
    numeros_validos = {num for num, _ in sumario}

    # 4) Localiza posições dos cabeçalhos no corpo
    posicoes: list[tuple[int, str, str]] = []  # (idx_linha, numero, titulo)
    _nums_vistos: set[str] = set()
    for idx, ln in enumerate(linhas):
        m = _RE_CABECALHO_SECAO.match(ln)
        if m:
            num = m.group(1).strip()
            tit = m.group(2).strip()
            if num in numeros_validos and len(tit) >= 2 and len(num) <= 16:
                if num not in _nums_vistos:
                    _nums_vistos.add(num)
                    posicoes.append((idx, num, tit))

    # 5) Extrai conteúdo entre cabeçalhos
    resultado: list[tuple[str, str, str]] = []
    for i, (idx_linha, num, tit) in enumerate(posicoes):
        # Conteúdo vai da linha após o cabeçalho até o próximo cabeçalho
        fim = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(linhas)
        bloco_linhas = linhas[idx_linha + 1 : fim]
        # Limpa e converte para HTML simples (parágrafos)
        paragrafos: list[str] = []
        buffer: list[str] = []
        for ln in bloco_linhas:
            ln_strip = ln.strip()
            if not ln_strip:
                if buffer:
                    paragrafos.append(" ".join(buffer))
                    buffer = []
            else:
                buffer.append(ln_strip)
        if buffer:
            paragrafos.append(" ".join(buffer))
        # Filtra parágrafos muito curtos (números de página isolados, etc.)
        paragrafos = [p for p in paragrafos if len(p) > 3]
        conteudo_html = "".join(f"<p>{p}</p>" for p in paragrafos)
        resultado.append((num, tit, conteudo_html))

    # 6) Garante que todas as seções do sumário apareçam (mesmo sem conteúdo)
    nums_encontrados = {r[0] for r in resultado}
    for num, tit in sumario:
        if num not in nums_encontrados and len(num) <= 16:
            resultado.append((num, tit, ""))

    def _sort_key(item: tuple[str, str, str]) -> list[int]:
        return [int(x) if x.isdigit() else 0 for x in item[0].split(".")]

    resultado.sort(key=_sort_key)
    return resultado


# ---------------------------------------------------------------------------
# Extração avançada com PyMuPDF: texto, tabelas e figuras
# ---------------------------------------------------------------------------

def _extrair_blocos_avancado(
    fonte: "str | Path | bytes",
) -> "list[dict]":
    """Extrai blocos estruturados (texto, tabela, figura) de um PDF usando PyMuPDF.

    Retorna lista de dicts com:
      - secao_numero: str
      - secao_titulo: str
      - blocos: list[dict] cada um com {tipo, conteudo, legenda, dados_imagem, mime}

    ``tipo`` pode ser: "texto", "tabela", "figura".
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Fallback: se PyMuPDF não estiver instalado, usa extração simples
        return []

    try:
        if isinstance(fonte, bytes):
            doc = fitz.open(stream=fonte, filetype="pdf")
        else:
            doc = fitz.open(str(fonte))
    except Exception:  # noqa: BLE001
        return []

    # 1) Extrair sumário usando pypdf (já funciona bem)
    if isinstance(fonte, (str, Path)):
        reader = pypdf.PdfReader(str(fonte))
    else:
        reader = pypdf.PdfReader(io.BytesIO(fonte))
    texto_inicio = _ler_paginas_iniciais(reader)
    sumario = _parse_sumario(texto_inicio)
    if not sumario:
        doc.close()
        return []

    numeros_validos = {num for num, _ in sumario}

    # 2) Percorrer páginas e extrair blocos de texto, tabelas e imagens
    # Primeiro coleta todo texto com marcadores de seção
    texto_completo_linhas: list[str] = []
    imagens_por_pagina: "dict[int, list[dict]]" = {}

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Texto
        texto_pagina = page.get_text("text") or ""
        texto_completo_linhas.extend(texto_pagina.splitlines())
        # Imagens
        img_list = page.get_images(full=True)
        if img_list:
            imagens_pagina = []
            for img_info in img_list:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if base_image and base_image.get("image"):
                        imagens_pagina.append({
                            "dados": base_image["image"],
                            "mime": f"image/{base_image.get('ext', 'png')}",
                            "largura": base_image.get("width", 0),
                            "altura": base_image.get("height", 0),
                        })
                except Exception:  # noqa: BLE001
                    continue
            if imagens_pagina:
                imagens_por_pagina[page_num] = imagens_pagina

    # 3) Tentar extrair tabelas com pdfplumber
    tabelas_por_pagina: "dict[int, list[str]]" = {}
    try:
        import pdfplumber

        if isinstance(fonte, bytes):
            pdf_plumber = pdfplumber.open(io.BytesIO(fonte))
        else:
            pdf_plumber = pdfplumber.open(str(fonte))

        for page_num, page in enumerate(pdf_plumber.pages):
            tabelas = page.extract_tables()
            if tabelas:
                tabelas_html = []
                for tabela in tabelas:
                    if not tabela or not tabela[0]:
                        continue
                    html = "<table><thead><tr>"
                    # Primeira linha como cabeçalho
                    for cel in tabela[0]:
                        html += f"<th>{cel or ''}</th>"
                    html += "</tr></thead><tbody>"
                    for row in tabela[1:]:
                        html += "<tr>"
                        for cel in row:
                            html += f"<td>{cel or ''}</td>"
                        html += "</tr>"
                    html += "</tbody></table>"
                    tabelas_html.append(html)
                if tabelas_html:
                    tabelas_por_pagina[page_num] = tabelas_html
        pdf_plumber.close()
    except ImportError:
        pass

    # 4) Localizar seções e associar conteúdo
    linhas = texto_completo_linhas
    posicoes: list[tuple[int, str, str]] = []
    _nums_vistos_av: set[str] = set()
    for idx, ln in enumerate(linhas):
        m = _RE_CABECALHO_SECAO.match(ln)
        if m:
            num = m.group(1).strip()
            tit = m.group(2).strip()
            if num in numeros_validos and len(tit) >= 2 and len(num) <= 16:
                if num not in _nums_vistos_av:
                    _nums_vistos_av.add(num)
                    posicoes.append((idx, num, tit))

    # 5) Montar resultado por seção
    resultado: list[dict] = []
    for i, (idx_linha, num, tit) in enumerate(posicoes):
        fim = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(linhas)
        bloco_linhas = linhas[idx_linha + 1 : fim]

        blocos_secao: list[dict] = []

        # Texto: parágrafos
        paragrafos: list[str] = []
        buffer: list[str] = []
        for ln in bloco_linhas:
            ln_strip = ln.strip()
            if not ln_strip:
                if buffer:
                    paragrafos.append(" ".join(buffer))
                    buffer = []
            else:
                buffer.append(ln_strip)
        if buffer:
            paragrafos.append(" ".join(buffer))
        paragrafos = [p for p in paragrafos if len(p) > 3]

        if paragrafos:
            conteudo_html = "".join(f"<p>{p}</p>" for p in paragrafos)
            blocos_secao.append({
                "tipo": "texto",
                "conteudo": conteudo_html,
            })

        resultado.append({
            "secao_numero": num,
            "secao_titulo": tit,
            "blocos": blocos_secao,
        })

    # 6) Distribuir tabelas e imagens entre as seções (heurística por página)
    # Para cada página com tabelas/imagens, associar à seção mais provável
    # baseado na ordem de aparição
    # (simplificação: adiciona tabelas e imagens na ordem em que aparecem)
    total_tabelas: list[str] = []
    for pg in sorted(tabelas_por_pagina.keys()):
        total_tabelas.extend(tabelas_por_pagina[pg])

    total_imagens: list[dict] = []
    for pg in sorted(imagens_por_pagina.keys()):
        total_imagens.extend(imagens_por_pagina[pg])

    # Distribui tabelas entre seções que têm conteúdo textual (heurística)
    if total_tabelas and resultado:
        tabela_idx = 0
        for sec in resultado:
            if tabela_idx >= len(total_tabelas):
                break
            for _ in range(total_tabelas.__len__()):
                if tabela_idx >= len(total_tabelas):
                    break
                sec["blocos"].append({
                    "tipo": "tabela",
                    "conteudo": total_tabelas[tabela_idx],
                })
                tabela_idx += 1
                break  # max 1 tabela por seção nesta heurística simples

    # Imagens: filtra imagens muito pequenas (ícones, logos) e distribui
    imagens_validas = [
        img for img in total_imagens
        if img["largura"] > 100 and img["altura"] > 100
    ]
    if imagens_validas and resultado:
        img_idx = 0
        for sec in resultado:
            if img_idx >= len(imagens_validas):
                break
            sec["blocos"].append({
                "tipo": "figura",
                "dados_imagem": imagens_validas[img_idx]["dados"],
                "mime": imagens_validas[img_idx]["mime"],
            })
            img_idx += 1

    # 7) Garante que todas as seções do sumário apareçam
    nums_encontrados = {r["secao_numero"] for r in resultado}
    for num, tit in sumario:
        if num not in nums_encontrados and len(num) <= 16:
            resultado.append({
                "secao_numero": num,
                "secao_titulo": tit,
                "blocos": [],
            })

    # Ordena
    def _sort_key(item: dict) -> list[int]:
        return [int(x) if x.isdigit() else 0 for x in item["secao_numero"].split(".")]

    resultado.sort(key=_sort_key)
    doc.close()
    return resultado


def extrair_completo_pdf_disponivel(
    nome_arquivo: str,
) -> "list[dict]":
    """Extrai seções + blocos (texto, tabela, figura) de um PDF da pasta
    ``relatorios_entregues/``.

    Valida o nome para evitar path traversal.
    Retorna lista de dicts com {secao_numero, secao_titulo, blocos}.
    """
    disponiveis = set(listar_pdfs_disponiveis())
    if nome_arquivo not in disponiveis:
        raise ValueError(f"PDF nao disponivel: {nome_arquivo}")
    caminho = PASTA_RELATORIOS / nome_arquivo
    resultado = _extrair_blocos_avancado(caminho)
    if not resultado:
        # Fallback para extração simples se PyMuPDF não disponível
        secoes = extrair_secoes_e_conteudo(caminho)
        return [
            {"secao_numero": num, "secao_titulo": tit, "blocos": [{"tipo": "texto", "conteudo": cont}] if cont else []}
            for num, tit, cont in secoes
        ]
    return resultado
