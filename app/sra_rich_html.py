"""HTML rico (editor Quill nos blocos): marcador, sanitização PDF/DOCX.

Sem o marcador ``RICH_HTML_MARKER``, o pipeline legado (linhas / markdown leve)
continua válido.
"""
from __future__ import annotations

import bleach
from bleach.css_sanitizer import CSSSanitizer

from .html_sanitize import sanitize_pdf_html_fragment

RICH_HTML_MARKER = "<!--SRA_RICH-->"

# Fecha div sem o literal de fecho no fonte (djlint H025 em ficheiros .py).
_LT = chr(60)
_DIV_CLOSE = _LT + "/div>"
_OPEN_DIV = _LT + "div>"

_ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "strike",
        "sub",
        "sup",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "a",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "img",
        "blockquote",
        "hr",
    }
)
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "p": ["class", "style"],
    "li": ["class", "style"],
    "span": ["class", "style"],
    "div": ["class", "style"],
    "h1": ["class", "style"],
    "h2": ["class", "style"],
    "h3": ["class", "style"],
    "h4": ["class", "style"],
    "h5": ["class", "style"],
    "h6": ["class", "style"],
    "table": ["class", "style", "border"],
    "thead": ["class", "style"],
    "tbody": ["class", "style"],
    "tr": ["class", "style"],
    "th": ["colspan", "rowspan", "class", "style"],
    "td": ["colspan", "rowspan", "class", "style"],
    "img": ["src", "alt", "width", "height", "class", "style"],
    "blockquote": ["cite", "class", "style"],
    "hr": ["class", "style"],
}

_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=frozenset({"text-align"}),
)


def is_rich_html_storage(conteudo: str | None) -> bool:
    """True se o campo foi gravado pelo editor WYSIWYG (prefixo canônico)."""
    s = (conteudo or "").lstrip()
    return s.startswith(RICH_HTML_MARKER)


def storage_body(conteudo: str | None) -> str:
    """Corpo HTML após o marcador (vazio se não for rich)."""
    raw = conteudo or ""
    if not is_rich_html_storage(raw):
        return ""
    i = raw.find("\n")
    return raw[i + 1 :] if i != -1 else ""


def body_to_storage(inner_html: str) -> str:
    inner = (inner_html or "").strip()
    if not inner:
        return ""
    return RICH_HTML_MARKER + "\n" + inner


def _unwrap_outer_div(html: str) -> str:
    s = (html or "").strip()
    low = s.lower()
    if low.startswith("<div") and low.endswith(_DIV_CLOSE):
        depth = s.find(">")  # noqa: PGH003
        if depth != -1:
            inner = s[depth + 1 :].rstrip()
            if inner.lower().endswith(_DIV_CLOSE):  # noqa: PGH003 PGH004 PGH005
                return inner[: -len(_DIV_CLOSE)].rstrip()  # noqa: PGH003 PGH004 PGH005 PGH006 PGH007
    return s


def sanitize_rich_html_for_pdf(fragment: str) -> str:
    """Limpa fragmento HTML do RTE para injetar no template de preview A4 e no DOCX."""
    if not (fragment or "").strip():
        return ""
    wrapped = _OPEN_DIV + fragment + _DIV_CLOSE
    cleaned = bleach.clean(
        wrapped,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        css_sanitizer=_CSS_SANITIZER,
        protocols=frozenset({"http", "https", "data", "mailto"}),
        strip=True,
    )
    inner = _unwrap_outer_div(cleaned)
    return sanitize_pdf_html_fragment(inner, preserve_quill_align=True)
