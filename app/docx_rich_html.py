"""HTML rico (blocos marcados ``<!--SRA_RICH-->``) → trechos python-docx."""
from __future__ import annotations

import importlib
import re
from types import ModuleType

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from . import sra_rich_html as srh


def _lazy_docx_render() -> ModuleType:
    """Carrega ``docx_render`` em tempo de execução (evita ciclo na análise estática)."""
    return importlib.import_module(".docx_render", __package__)


def _quill_para_alignment(classes) -> WD_ALIGN_PARAGRAPH | None:
    if not classes:
        return None
    seq = classes if isinstance(classes, list) else str(classes).split()
    for c in seq:
        if c == "ql-align-center":
            return WD_ALIGN_PARAGRAPH.CENTER
        if c == "ql-align-right":
            return WD_ALIGN_PARAGRAPH.RIGHT
        if c == "ql-align-justify":
            return WD_ALIGN_PARAGRAPH.JUSTIFY
        if c == "ql-align-left":
            return WD_ALIGN_PARAGRAPH.LEFT
    return None


def _alignment_from_style(style_val: str | None) -> WD_ALIGN_PARAGRAPH | None:
    if not style_val:
        return None
    style = str(style_val).lower().replace(" ", "")
    mat = re.search(r"text-align:(left|center|right|justify)", style)
    if not mat:
        return None
    key = mat.group(1)
    return {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }.get(key)


def _paragraph_alignment_from_html_node(node) -> WD_ALIGN_PARAGRAPH | None:
    """Alinhamento a partir de classes Quill ou ``style`` do RTE (text-align)."""
    al = _quill_para_alignment(node.get("class"))
    if al is not None:
        return al
    return _alignment_from_style(node.get("style"))


def _fill_paragraph_from_html_node(paragraph, node) -> None:
    """Preenche parágrafo python-docx a partir de nós filhos (ênfase simples)."""
    from bs4 import NavigableString

    for bit in node.children:
        name = getattr(bit, "name", None)
        if name in ("strong", "b"):
            run = paragraph.add_run(bit.get_text())
            run.bold = True
        elif name in ("em", "i"):
            run = paragraph.add_run(bit.get_text())
            run.italic = True
        elif name == "u":
            run = paragraph.add_run(bit.get_text())
            run.underline = True
        elif name in ("s", "strike"):
            run = paragraph.add_run(bit.get_text())
            run.font.strike = True
        elif name == "br":
            paragraph.add_run("\n")
        elif isinstance(bit, NavigableString):
            t = str(bit)
            if t:
                paragraph.add_run(t)


def _docx_rich_blockquote(document: Document, child) -> None:
    dr = _lazy_docx_render()
    quote_para = document.add_paragraph(child.get_text(strip=True))
    quote_para.paragraph_format.left_indent = Pt(18)
    quote_para.paragraph_format.space_before = Pt(6)
    dr.format_docx_body_paragraph(quote_para)


def _docx_rich_img_placeholder(document: Document, child) -> None:
    dr = _lazy_docx_render()
    src = child.get("src") or ""
    alt = (child.get("alt") or "").strip()
    legend = f"[Imagem: {alt}]" if alt else "[Imagem]"
    para = document.add_paragraph(f"{legend} ({src})")
    dr.format_docx_body_paragraph(para)


def _docx_rich_table(document: Document, child) -> None:
    rows_el = child.find_all("tr")
    if not rows_el:
        return
    col_counts = [len(tr.find_all(["td", "th"])) for tr in rows_el]
    max_cols = max(col_counts) if col_counts else 0
    if max_cols <= 0:
        return
    table = document.add_table(rows=len(rows_el), cols=max_cols)
    table.style = "Table Grid"
    for ri, tr in enumerate(rows_el):
        cells = tr.find_all(["td", "th"])
        for ci in range(max_cols):
            cell = table.rows[ri].cells[ci]
            cell.text = cells[ci].get_text(strip=True) if ci < len(cells) else ""


def _add_rich_html_node(document: Document, child) -> None:
    """Um nó de topo filho do wrapper ``div`` (HTML rico → DOCX)."""
    dr = _lazy_docx_render()

    if getattr(child, "name", None) is None:
        return
    name = child.name.lower()
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        lvl = int(name[1])
        dr.format_docx_heading(
            document.add_heading(child.get_text(strip=True), level=lvl),
            lvl,
        )
    elif name == "blockquote":
        _docx_rich_blockquote(document, child)
    elif name == "img":
        _docx_rich_img_placeholder(document, child)
    elif name == "table":
        _docx_rich_table(document, child)
    elif name == "p":
        para = document.add_paragraph()
        _fill_paragraph_from_html_node(para, child)
        al = _paragraph_alignment_from_html_node(child)
        if al is not None:
            para.alignment = al
        dr.format_docx_body_paragraph(para)
    elif name in ("ul", "ol"):
        style = "List Bullet" if name == "ul" else "List Number"
        for li in child.find_all("li", recursive=False):
            item_para = document.add_paragraph(style=style)
            inner = li.find("p", recursive=False)
            src = inner if inner is not None else li
            _fill_paragraph_from_html_node(item_para, src)
            al = _paragraph_alignment_from_html_node(src)
            if al is not None:
                item_para.alignment = al
            dr.format_docx_body_paragraph(item_para)


def add_rich_html_docx(document: Document, html: str) -> None:
    """DOCX a partir de fragmento HTML sanitizado (mesmo subconjunto do PDF)."""
    from bs4 import BeautifulSoup

    clean = srh.sanitize_rich_html_for_pdf(html)
    if not (clean or "").strip():
        return
    soup = BeautifulSoup("<div>" + clean + "</div>", "html.parser")
    root = soup.div
    if root is None:
        return
    for child in root.children:
        _add_rich_html_node(document, child)
