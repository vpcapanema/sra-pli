# pylint: disable=protected-access,too-many-locals,too-many-branches,too-many-statements
"""Extracao de estrutura (secoes + blocos) a partir de relatorios DOCX.

Substitui a antiga extracao via PDF para a opcao "Relatorio entregue" no
formulario de criacao de relatorio (dashboard). DOCX preserva semantica
(heading, numeracao, listas, tabelas, imagens), o que fornece fidelidade
muito superior ao parsing de texto extraido de PDF.

Fluxo:
  1. ``listar_docx_disponiveis()`` lista DOCX em ``relatorios_entregues/``.
  2. ``extrair_relatorio_docx_disponivel(nome)`` abre o arquivo e retorna
     ``list[dict]`` com ``{secao_numero, secao_titulo, blocos:[...]}``
     compativel com o contrato ja consumido em ``app/routes/relatorios.py``
     (cria secoes + blocos em ``tx_session``).

Reaproveita utilitarios de ``app/routes/importacao.py`` (regex, iteracao
de blocos docx, listas numeradas Word) para manter uma fonte unica de
regras. Aqui nao ha ``Secao`` previa no banco: a arvore e inferida do
proprio DOCX.
"""
from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.table import Table


def _norm_text_(s: str) -> str:
    """Normaliza texto para comparação: strip, lower, sem acentos, espaços colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


from .list_lines import block_is_homogeneous_list, line_is_list_item
from .services.importacao import (
    _FIGURA_PREFIX_RE,
    _FIGURA_RE,
    _FONTE_RE,
    _HEADING_RE,
    _SECTION_NUMBER_RE,
    _TABELA_PREFIX_RE,
    _TABELA_RE,
    _get_w_numpr,
    _iter_docx_blocks,
    _paragraph_images,
    _read_numfmt_from_docx,
    _word_list_canonical_line,
)

PASTA_RELATORIOS = Path(__file__).resolve().parent.parent / "relatorios_entregues"


def listar_docx_disponiveis() -> list[str]:
    """Lista nomes de DOCX em ``relatorios_entregues/`` (ordenados).

    Ignora arquivos temporarios do Word (``~$...``) e extensoes que nao
    sejam ``.docx``.
    """
    if not PASTA_RELATORIOS.is_dir():
        return []
    return sorted(
        p.name
        for p in PASTA_RELATORIOS.iterdir()
        if p.suffix.lower() == ".docx" and not p.name.startswith("~$")
    )


_STYLE_HEADING_LEVEL_RE = re.compile(r"(\d+)")


def _style_heading_level(style_name: str) -> int:
    """Devolve o nivel de heading (1..9) a partir do nome do estilo Word.

    Funciona com ``Heading 1``, ``heading 2``, ``Titulo 1``, ``Título 3``,
    ``Cabecalho 4``, etc. Devolve 0 quando o paragrafo nao e heading.
    """
    s = (style_name or "").strip().lower()
    if not s:
        return 0
    if not (s.startswith("heading") or s.startswith("título") or s.startswith("titulo") or s.startswith("cabeçalho") or s.startswith("cabecalho")):
        return 0
    m = _STYLE_HEADING_LEVEL_RE.search(s)
    if not m:
        return 1
    try:
        lvl = int(m.group(1))
    except ValueError:
        return 1
    return max(1, min(lvl, 9))


def _split_legenda_fonte(line: str) -> tuple[str, str]:
    match = _FONTE_RE.search(line)
    if not match:
        return line.strip(), ""
    return line[: match.start()].strip(), match.group(1).strip()


def _split_figura_fonte(line: str) -> tuple[str, str]:
    legenda, fonte = _split_legenda_fonte(line)
    legenda = _FIGURA_PREFIX_RE.sub("", legenda).strip()
    return legenda, fonte


def _split_tabela_fonte(line: str) -> tuple[str, str]:
    legenda, fonte = _split_legenda_fonte(line)
    legenda = _TABELA_PREFIX_RE.sub("", legenda).strip()
    return legenda, fonte


def _parse_numero_titulo(text: str) -> tuple[str, str]:
    """Extrai ``(numero, titulo)`` de uma linha de heading.

    Exemplos aceitos:
      - "4.4.1 Acompanhamento tecnico"  -> ("4.4.1", "Acompanhamento tecnico")
      - "4 Visao geral"                 -> ("4", "Visao geral")
      - "4.1 - Coordenacao"             -> ("4.1", "Coordenacao")
      - "Apresentacao"                  -> ("", "Apresentacao")
    """
    body = re.sub(r"^#{1,6}\s*", "", (text or "").strip())
    if not body:
        return "", ""
    m = _SECTION_NUMBER_RE.match(body)
    if not m:
        return "", body
    numero = (m.group(1) or "").strip()
    resto = (m.group(2) or "").strip()
    resto = re.sub(r"^[\s\-\u2013\u2014.:]+", "", resto).strip()
    return numero, resto


def _proximo_numero_por_nivel(contadores: dict, nivel: int, ultimo_numero: str) -> str:
    """Gera um numero de secao quando o heading nao tras numero explicito.

    Baseado nos contadores por nivel (``contadores[nivel]``) e no ultimo
    numero emitido, para formar uma cadeia ``X.Y.Z`` coerente.
    """
    nivel = max(1, nivel)
    # Extrai prefixo do ultimo numero ate nivel-1
    partes_prefixo: list[str] = []
    if nivel > 1 and ultimo_numero:
        partes = [p for p in ultimo_numero.split(".") if p]
        partes_prefixo = partes[: nivel - 1]
        # Se o ultimo numero e mais curto que nivel-1, completa com 1
        while len(partes_prefixo) < nivel - 1:
            partes_prefixo.append("1")
    # Limpa contadores de niveis mais profundos
    for k in list(contadores.keys()):
        if k > nivel:
            del contadores[k]
    contadores[nivel] = contadores.get(nivel, 0) + 1
    partes_prefixo.append(str(contadores[nivel]))
    return ".".join(partes_prefixo)


def _abrir_secao(
    resultado: list,
    numero: str,
    titulo: str,
    vistos: set,
) -> dict | None:
    """Cria uma nova entrada de secao e devolve-a, ou ``None`` se duplicada/invalida."""
    numero = (numero or "").strip()
    titulo = (titulo or "").strip()
    if not numero or numero in vistos or len(numero) > 16:
        return None
    vistos.add(numero)
    sec = {
        "secao_numero": numero,
        "secao_titulo": titulo or f"Secao {numero}",
        "blocos": [],
    }
    resultado.append(sec)
    return sec


def _flush_buffer_texto(sec: dict, buf: list) -> None:
    """Consome o buffer de texto e gera bloco ``texto`` ou ``lista``."""
    if sec is None:
        buf.clear()
        return
    clean = [ln.rstrip() for ln in buf if ln.strip()]
    buf.clear()
    if not clean:
        return
    tipo = "lista" if block_is_homogeneous_list(clean) else "texto"
    sec["blocos"].append(
        {
            "tipo": tipo,
            "conteudo": "\n".join(clean),
        }
    )


def _append_tabela_para_secao(sec: dict, linhas: list, legenda: str, fonte: str) -> None:
    if sec is None or not any((ln or "").strip() for ln in linhas):
        return
    conteudo = "\n".join(ln for ln in linhas if (ln or "").strip())
    sec["blocos"].append(
        {
            "tipo": "tabela",
            "conteudo": conteudo,
            "legenda": (legenda or "").strip(),
            "fonte": (fonte or "").strip(),
        }
    )


# Frases de modelos legados (textos exemplo / meta) que devem ser
# silenciosamente ignoradas pelo parser para nao virarem blocos de conteudo.
# Comparacao sempre em _norm_text_ (strip + lower + sem acentos + espacos
# colapsados). Manter apenas frases estaveis; evitar strings genericas.
_RUIDO_MODELO_LEGADO = frozenset(
    _norm_text_(s)
    for s in (
        "bloco: paragrafo (texto)",
        "bloco: listas (nao e numeracao de secoes do relatorio)",
        "bloco: figura (imagem + legenda + fonte)",
        "bloco: tabela (grelha word + legenda + fonte)",
        "clique aqui, depois insera a figura: inserir > imagens...",
        "titulo ancestral (somente contexto neste modelo). escreva o texto na ultima subseccao.",
        "modelo sra (importacao assistida). nao apague as linhas de exemplo antes de preencher.",
        "relatorio de atividades (rascunho para importar no sra)",
        "pli/sp-2050 - conteudo da secao indicada, sem alterar a estrutura.",
        "escreva aqui textos corridos, subtitulos no padrao do word, listas e descricoes detalhadas.",
        "item com marcador (lista real do word, nivel 1).",
        "segundo item (mesmo estilo, nivel 1).",
        "item numerado (lista real com numeros).",
        "segundo item numerado.",
        "figura x.y: descricao clara do que a imagem mostra.",
        "fonte: nome e ano da fonte ou referencia.",
        "tabela x.y: legenda com contexto (substitua x.y se quiser, o sistema ajusta).",
        "fonte: origem dos dados (instituicao, planilha, data).",
        "reserva de espaco: preencha o conteudo desta subseccao.",
        "---",
    )
)


def _eh_ruido_modelo(text: str) -> bool:
    if not text:
        return False
    return _norm_text_(text) in _RUIDO_MODELO_LEGADO


def _append_figura_para_secao(
    sec: dict,
    legenda: str,
    fonte: str,
    dados_imagem: bytes | None,
    mime: str,
) -> int | None:
    """Adiciona bloco figura; devolve o indice do bloco (para legendas tardias)."""
    if sec is None:
        return None
    sec["blocos"].append(
        {
            "tipo": "figura",
            "conteudo": "",
            "legenda": (legenda or "").strip(),
            "fonte": (fonte or "").strip(),
            "dados_imagem": dados_imagem,
            "mime": mime or "image/png",
        }
    )
    return len(sec["blocos"]) - 1


def _b64_to_bytes(b64: str) -> bytes:
    import base64

    try:
        return base64.b64decode(b64 or "")
    except (ValueError, TypeError):
        return b""


def extrair_relatorio_docx(raw: bytes) -> list[dict]:  # noqa: C901
    """Extrai estrutura completa (secoes + blocos) de bytes de um DOCX.

    Retorno: ``list[dict]`` onde cada item tem as chaves
    ``secao_numero``, ``secao_titulo`` e ``blocos``. Cada bloco tem
    ``tipo`` (``texto`` | ``lista`` | ``tabela`` | ``figura``) e campos
    dependentes do tipo. Formato alinhado ao consumido pela rota de
    criacao de relatorio (``app/routes/relatorios.py``).
    """
    document = Document(BytesIO(raw))

    resultado: list[dict] = []
    vistos_numeros: set[str] = set()
    contadores_por_nivel: dict[int, int] = {}
    ultimo_numero = ""
    current_sec: dict | None = None
    buf: list[str] = []
    word_list_counters: dict[tuple[int, int], int] = {}

    last_media_kind = ""  # "figura" ou "tabela"
    last_media_idx: int | None = None
    pending_figure_idx: int | None = None
    pending_table_legenda = ""
    pending_table_fonte = ""

    def _sec_ref() -> dict | None:
        return current_sec

    for element in _iter_docx_blocks(document):
        # ------------------- Tabelas nativas -------------------
        if isinstance(element, Table):
            _flush_buffer_texto(_sec_ref(), buf)
            linhas: list[str] = []
            for row in element.rows:
                cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                if any(cells):
                    linhas.append(" | ".join(cells))
            _append_tabela_para_secao(_sec_ref(), linhas, pending_table_legenda, pending_table_fonte)
            if linhas and current_sec is not None:
                last_media_idx = len(current_sec["blocos"]) - 1
                last_media_kind = "tabela"
            pending_table_legenda = ""
            pending_table_fonte = ""
            continue

        # ------------------- Paragrafos -------------------
        paragraph = element  # type: Paragraph

        # Imagens incorporadas no paragrafo (placeholder; legenda vira depois)
        imgs = _paragraph_images(paragraph)
        if imgs:
            _flush_buffer_texto(_sec_ref(), buf)
            pending_figure_idx = None
            for img in imgs:
                dados = _b64_to_bytes(img.get("image_b64") or "")
                mime = img.get("image_mime") or "image/png"
                pending_figure_idx = _append_figura_para_secao(_sec_ref(), "", "", dados, mime)
                if pending_figure_idx is not None:
                    last_media_idx = pending_figure_idx
                    last_media_kind = "figura"

        text = (paragraph.text or "").strip()

        # Filtra parágrafos cujo conteúdo é ruído de modelos legados
        # (ex.: "Bloco: paragrafo (texto)", "Figura X.Y: ...", "---", etc.).
        if text and _eh_ruido_modelo(text):
            continue

        # Fonte solta apos figura/tabela
        if text.lower().startswith("fonte:") and current_sec is not None and last_media_idx is not None:
            current_sec["blocos"][last_media_idx]["fonte"] = text[6:].strip()
            continue

        # Linha "Figura X.Y: ..." - legenda para figura pendente ou nova
        if text and _FIGURA_RE.match(text):
            _flush_buffer_texto(_sec_ref(), buf)
            legenda, fonte = _split_figura_fonte(text)
            if current_sec is not None:
                if pending_figure_idx is not None:
                    current_sec["blocos"][pending_figure_idx]["legenda"] = legenda
                    current_sec["blocos"][pending_figure_idx]["fonte"] = fonte
                    last_media_idx = pending_figure_idx
                    last_media_kind = "figura"
                    pending_figure_idx = None
                else:
                    # Figura citada sem binario - registra placeholder vazio
                    idx = _append_figura_para_secao(_sec_ref(), legenda, fonte, None, "image/png")
                    if idx is not None:
                        last_media_idx = idx
                        last_media_kind = "figura"
            continue

        # Linha "Tabela X.Y: ..." - legenda para tabela que vem em seguida
        if text and _TABELA_RE.match(text):
            _flush_buffer_texto(_sec_ref(), buf)
            legenda, fonte = _split_tabela_fonte(text)
            if (
                current_sec is not None
                and last_media_kind == "tabela"
                and last_media_idx is not None
                and not current_sec["blocos"][last_media_idx].get("legenda")
            ):
                current_sec["blocos"][last_media_idx]["legenda"] = legenda
                current_sec["blocos"][last_media_idx]["fonte"] = fonte
            else:
                pending_table_legenda = legenda
                pending_table_fonte = fonte
            continue

        # Heading (por estilo Word)
        style_name = ""
        try:
            style_name = (paragraph.style.name or "") if paragraph.style else ""
        except AttributeError:
            style_name = ""
        heading_level = _style_heading_level(style_name)

        # Heading detectado por regex textual (fallback quando estilo nao
        # e Heading/Titulo mas a linha tem "N.N titulo").
        if heading_level == 0 and text and _HEADING_RE.match(text):
            # Usa o numero como nivel aproximado (conta segmentos).
            numero_preview, _ = _parse_numero_titulo(text)
            if numero_preview:
                heading_level = len([p for p in numero_preview.split(".") if p])

        if heading_level > 0 and text:
            _flush_buffer_texto(_sec_ref(), buf)
            numero, titulo = _parse_numero_titulo(text)
            if not numero:
                numero = _proximo_numero_por_nivel(contadores_por_nivel, heading_level, ultimo_numero)
            else:
                # Alinha contadores ao numero explicito
                partes = [int(p) for p in numero.split(".") if p.isdigit()]
                for i, v in enumerate(partes, start=1):
                    contadores_por_nivel[i] = v
                for k in list(contadores_por_nivel.keys()):
                    if k > len(partes):
                        del contadores_por_nivel[k]
            nova = _abrir_secao(resultado, numero, titulo, vistos_numeros)
            if nova is not None:
                current_sec = nova
                ultimo_numero = numero
                pending_figure_idx = None
                last_media_idx = None
                last_media_kind = ""
            continue

        if not text:
            _flush_buffer_texto(_sec_ref(), buf)
            continue

        # Lista numerada/bullet nativa Word
        w_num = _get_w_numpr(paragraph)
        if w_num is not None:
            il, nid = w_num
            numfmt_word = _read_numfmt_from_docx(document, nid, il)
            if buf and not all(line_is_list_item(ln) for ln in buf):
                _flush_buffer_texto(_sec_ref(), buf)
            buf.append(_word_list_canonical_line(text, il, numfmt_word, nid, word_list_counters))
            continue

        # Estilo de lista baseado em nome ("List Paragraph", "Lista")
        style_lower = (style_name or "").lower()
        if "list" in style_lower or "lista" in style_lower:
            if buf and not all(line_is_list_item(ln) for ln in buf):
                _flush_buffer_texto(_sec_ref(), buf)
            buf.append("- " + text.lstrip("-\u2022\u00b7 "))
            continue

        # Texto corrido
        if buf and all(line_is_list_item(ln) for ln in buf):
            _flush_buffer_texto(_sec_ref(), buf)
        buf.append(text)

    _flush_buffer_texto(_sec_ref(), buf)

    # Ordena pela chave do numero (estavel)
    def _sort_key(sec: dict) -> list:
        return [int(x) if x.isdigit() else 0 for x in (sec.get("secao_numero") or "").split(".")]

    resultado.sort(key=_sort_key)
    return resultado


def extrair_relatorio_docx_disponivel(nome_arquivo: str) -> list[dict]:
    """Extrai secoes + blocos de um DOCX da pasta ``relatorios_entregues/``.

    Valida ``nome_arquivo`` contra ``listar_docx_disponiveis()`` para
    evitar path traversal.
    """
    disponiveis = set(listar_docx_disponiveis())
    if nome_arquivo not in disponiveis:
        raise ValueError(f"DOCX nao disponivel: {nome_arquivo}")
    caminho = PASTA_RELATORIOS / nome_arquivo
    with open(caminho, "rb") as fh:
        raw = fh.read()
    return extrair_relatorio_docx(raw)
