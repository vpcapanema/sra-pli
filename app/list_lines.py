"""Linhas de lista em texto bruto: detecção, aninhamento e saída HTML.

Formatação **local** (independente da hierarquia de seções do relatório):
- Nível: múltiplos de 2 espaços iniciais (0, 2, 4, …) = profundidade 0,1,2,…
- Marcador após o recuo, uma linha = um item: ``- ``, ``* ``, ``• ``; ``1.``; ``1)``; ``(1)``;
  ``a)``/``A)``/``a.``/``A.``; ``i)``/``I)``/``i.``/``I.`` (romanos: i, ii, iii, …, iv, …, ix, x, …)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from typing import List

# Romana: padrão comum; evita conflito com "i" solto exceto com . ou )
_ROMAN = r"(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xxi|l|li|c)"
_INDENT = re.compile(r"^((?:  )*)")


@dataclass
class _ListItem:
    level: int
    kind: str  # "ul" | "ol_1" | "ol_a" | "ol_A" | "ol_i" | "ol_I"
    text: str
    children: List["_ListItem"] = field(default_factory=list)


def _strip_marker(rest: str) -> tuple[str | None, str]:
    """Retorna (kind, corpo) ou (None, original) se não for item de lista."""
    s = (rest or "").lstrip()
    if not s:
        return None, rest
    simple = (
        (re.compile(r"^[-*•]\s+(.+)$"), "ul", 1),
        (re.compile(r"^(\d+)[.)]\s+(.+)$"), "ol_1", 2),
        (re.compile(r"^\((\d+)\)\s+(.+)$"), "ol_1", 2),
        (re.compile(r"^([a-z])[.)]\s+(.+)$"), "ol_a", 2),
        (re.compile(r"^([A-Z])[.)]\s+(.+)$"), "ol_A", 2),
    )
    knd: str | None = None
    body = ""
    for pat, kind_code, gix in simple:
        m = pat.match(s)
        if m:
            knd, body = kind_code, m.group(gix).strip()
            break
    if knd is None:
        mro = re.match(r"^(" + _ROMAN + r")[.)]\s+(.+)$", s, re.IGNORECASE)
        if mro and mro.group(1) is not None and mro.group(1) == mro.group(1).lower():
            knd, body = "ol_i", mro.group(2).strip()
    if knd is None:
        mro2 = re.match(r"^(" + _ROMAN.upper() + r")[.)]\s+(.+)$", s)
        if mro2:
            knd, body = "ol_I", mro2.group(2).strip()
    return (knd, body) if knd else (None, rest)


def line_is_list_item(line: str) -> bool:
    """True se a linha (não vazia) for item de lista no formato canônico."""
    if not (line or "").strip():
        return False
    ind = _INDENT.match(line)
    if not ind:
        return False
    rest = line[len(ind.group(1)) :]
    kind, _t = _strip_marker(rest)
    return kind is not None


def list_line_body(line: str) -> str:
    """Texto do item após o marcador, ou a linha em bruto se não reconhecer."""
    if not (line or "").strip():
        return ""
    ind = _INDENT.match(line)
    if not ind:
        return line.strip()
    rest = line[len(ind.group(1)) :]
    kind, text = _strip_marker(rest)
    if kind and text:
        return text
    return line.strip()


def block_is_homogeneous_list(lines: list[str]) -> bool:
    """Cada segmento não vazio parece item de lista (bloco 100% lista)."""
    got = [ln for ln in lines if (ln or "").strip()]
    if not got:
        return False
    return all(line_is_list_item(ln) for ln in got)


def _parse_list_lines(raw_lines: list[str]) -> list[_ListItem]:
    out: list[_ListItem] = []
    for raw in raw_lines:
        if not (raw or "").strip():
            continue
        ind = _INDENT.match(raw)
        if not ind:
            continue
        depth = len(ind.group(1)) // 2
        rest = raw[len(ind.group(1)) :]
        kind, text = _strip_marker(rest)
        if not kind or not text:
            continue
        out.append(_ListItem(level=depth, kind=kind, text=text))
    return out


def _ol_open_tag(kind: str) -> str:
    if kind == "ul":
        return "<" + "ul" + ">"
    att = {
        "ol_1": ' type="1"',
        "ol_a": ' type="a"',
        "ol_A": ' type="A"',
        "ol_i": ' type="i"',
        "ol_I": ' type="I"',
    }.get(kind, ' type="1"')
    return "<" + "ol" + att + ">"


def _rebuild_hierarchy(flat: list[_ListItem]) -> list[_ListItem]:
    for it in flat:
        it.children = []
    roots: list[_ListItem] = []
    last_by_level: dict[int, _ListItem] = {}
    for it in flat:
        if it.level == 0:
            roots.append(it)
            last_by_level = {0: it}
        else:
            parent = last_by_level.get(it.level - 1)
            if parent is not None:
                parent.children.append(it)
            else:
                roots.append(it)
                last_by_level[0] = it
            for k in list(last_by_level):
                if k > it.level:
                    del last_by_level[k]
            last_by_level[it.level] = it
    return roots


def _siblings_to_html(siblings: list[_ListItem]) -> str:
    if not siblings:
        return ""
    parts: list[str] = []
    i = 0
    n = len(siblings)
    while i < n:
        k0 = siblings[i].kind
        j = i + 1
        while j < n and siblings[j].kind == k0:
            j += 1
        group = siblings[i:j]
        tag_open = _ol_open_tag(k0)
        tag_name = "ul" if k0 == "ul" else "ol"
        li_html = []
        for node in group:
            inner = escape(node.text)
            if node.children:
                inner += _siblings_to_html(node.children)
            li_html.append(f"<li>{inner}</li>")
        parts.append(f"{tag_open}{''.join(li_html)}</{tag_name}>")
        i = j
    return "".join(parts)


def _level_normalize_inplace(flat: list[_ListItem]) -> None:
    """Garante que o nível mínimo é 0 (listas só com recuo)."""
    if not flat:
        return
    m = min(f.level for f in flat)
    if m > 0:
        for f in flat:
            f.level -= m


def parse_list_for_docx(conteudo: str) -> list[_ListItem]:
    """Árvore de itens para exportação DOCX (níveis normalizados)."""
    lines = [ln for ln in (conteudo or "").splitlines() if ln.strip()]
    flat = _parse_list_lines(lines)
    if not flat:
        return []
    _level_normalize_inplace(flat)
    return _rebuild_hierarchy(flat)


def list_text_to_html(conteudo: str) -> str:
    """Converte texto só com itens de lista (bloco somente listas) em HTML (ul/ol aninhados)."""
    lines = (conteudo or "").splitlines()
    flat = _parse_list_lines(lines)
    if not flat:
        return ""
    _level_normalize_inplace(flat)
    roots = _rebuild_hierarchy(flat)
    return _siblings_to_html(roots)


def mixed_texto_paragrafos_e_listas_to_html(texto: str) -> str:
    """Mistura parágrafos, ``#``/``##`` e sequências de linhas de lista (todos os marcadores)."""
    if not (texto or "").strip():
        return ""
    linhas = texto.splitlines()
    out: list[str] = []
    i = 0
    para_buf: list[str] = []

    def flush_para() -> None:
        if not para_buf:
            return
        par = " ".join(p.strip() for p in para_buf if p.strip()).strip()
        if par:
            out.append(f"<p>{escape(par)}</p>")
        para_buf.clear()

    while i < len(linhas):
        ln = linhas[i]
        if not (ln or "").strip():
            flush_para()
            i += 1
            continue
        stripped = ln.strip()
        m_h2 = re.match(r"^##\s+(.+)$", stripped)
        m_h1 = re.match(r"^#\s+(.+)$", stripped)
        if m_h2:
            flush_para()
            out.append(f"<h3>{escape(m_h2.group(1).strip())}</h3>")
            i += 1
            continue
        if m_h1:
            flush_para()
            out.append(f"<h2>{escape(m_h1.group(1).strip())}</h2>")
            i += 1
            continue
        if line_is_list_item(ln):
            flush_para()
            j = i
            while j < len(linhas) and line_is_list_item(linhas[j]):
                j += 1
            bloco = "\n".join(linhas[i:j])
            out.append(list_text_to_html(bloco))
            i = j
            continue
        para_buf.append(ln)
        i += 1
    flush_para()
    return "".join(out)
