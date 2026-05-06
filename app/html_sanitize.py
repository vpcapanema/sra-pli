"""Sanitização de fragmentos HTML destinados ao preview A4 e ao DOCX."""
from __future__ import annotations

import re

_RE_QL_ALIGN_CLASS_PDF = re.compile(
    r'class\s*=\s*"(?!ql-align-(?:center|right|justify|left)\b)[^"]*"',
    flags=re.IGNORECASE,
)
_RE_QL_ALIGN_CLASS_PDF2 = re.compile(
    r"class\s*=\s*'(?!ql-align-(?:center|right|justify|left)\b)[^']*'",
    flags=re.IGNORECASE,
)


def _condense_inline_style_to_text_align_only(style_body: str) -> str:
    """Mantém só ``text-align`` (atributo ``style`` completo ou string vazia)."""
    tm = re.search(r"text-align\s*:\s*(left|center|right|justify)", style_body, re.I)
    if not tm:
        return ""
    rest = re.sub(
        r"text-align\s*:\s*(?:left|center|right|justify)\s*;?",
        "",
        style_body,
        flags=re.I,
    )
    rest = re.sub(r"\s*;+\s*", ";", rest).strip("; \t\r\n")
    if rest:
        return ""
    return f' style="text-align: {tm.group(1).lower()}"'


def sanitize_pdf_html_fragment(
    fragment: str, *, preserve_quill_align: bool = False
) -> str:
    """Remove formatação inline típica de Word/HTML colado.

    Com ``preserve_quill_align=True``, mantém ``class="ql-align-*"`` (legado Quill) e
    ``style="text-align:…"`` coerente com o subconjunto permitido no bleach (editor rico).
    """
    if not (fragment or "").strip():
        return ""
    s = fragment
    if preserve_quill_align:
        s = re.sub(
            r'\sstyle\s*=\s*"([^"]*)"',
            lambda m: _condense_inline_style_to_text_align_only(m.group(1)),
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r"\sstyle\s*=\s*'([^']*)'",
            lambda m: _condense_inline_style_to_text_align_only(m.group(1)),
            s,
            flags=re.IGNORECASE,
        )
    else:
        for _ in range(8):
            antes = s
            s = re.sub(r'\sstyle\s*=\s*"[^"]*"', "", s, flags=re.IGNORECASE)
            s = re.sub(r"\sstyle\s*=\s*'[^']*'", "", s, flags=re.IGNORECASE)
            if s == antes:
                break
    if preserve_quill_align:
        s = _RE_QL_ALIGN_CLASS_PDF.sub("", s)
        s = _RE_QL_ALIGN_CLASS_PDF2.sub("", s)
        s = re.sub(r'\sclass\s*=\s*""', "", s, flags=re.IGNORECASE)
        s = re.sub(r"\sclass\s*=\s*''", "", s, flags=re.IGNORECASE)
    else:
        s = re.sub(r'\sclass\s*=\s*"[^"]*"', "", s, flags=re.IGNORECASE)
        s = re.sub(r"\sclass\s*=\s*'[^']*'", "", s, flags=re.IGNORECASE)
    s = re.sub(r'\salign\s*=\s*"[^"]*"', "", s, flags=re.IGNORECASE)
    s = re.sub(r"\salign\s*=\s*'[^']*'", "", s, flags=re.IGNORECASE)
    for attr in ("face", "color", "size", "bgcolor"):
        s = re.sub(rf'\s{attr}\s*=\s*"[^"]*"', "", s, flags=re.IGNORECASE)
        s = re.sub(rf"\s{attr}\s*=\s*'[^']*'", "", s, flags=re.IGNORECASE)
    return s
