import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from sqlalchemy.orm import Session

from .models import Figura, Relatorio
from .pdf_render import _RE_FIGURA, _RE_TABELA, _figura_ids_no_texto


def _figura_ids_relatorio(rel: Relatorio, section_ids: set[int] | None) -> set[int]:
    ids: set[int] = set()
    for sec in rel.secoes:
        if section_ids is not None and sec.id not in section_ids:
            continue
        for bloco in sec.blocos:
            if bloco.figura_id:
                ids.add(bloco.figura_id)
            ids.update(_figura_ids_no_texto(bloco.conteudo or ""))
    return ids


def _figura_label(sec_numero: str, counter: int) -> str:
    top = (sec_numero or "").split(".")[0]
    return f"{top}.{counter}" if top else str(counter)


def _set_runs_font(paragraph, *, size_pt: float = 10, bold: bool | None = None, italic: bool | None = None) -> None:
    for run in paragraph.runs:
        run.font.name = "Verdana"
        run.font.size = Pt(size_pt)
        if bold is not None:
            run.font.bold = bold
        if italic is not None:
            run.font.italic = italic


def _format_body_paragraph(paragraph, *, space_after_pt: float = 10) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(0)
    paragraph_format.space_after = Pt(space_after_pt)
    paragraph_format.line_spacing = 1.15
    _set_runs_font(paragraph, size_pt=10)


def _format_list_paragraph(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph_format = paragraph.paragraph_format
    paragraph_format.left_indent = Cm(1.27)
    paragraph_format.first_line_indent = Cm(-0.63)
    paragraph_format.space_before = Pt(0)
    paragraph_format.space_after = Pt(6)
    paragraph_format.line_spacing = 1.15
    _set_runs_font(paragraph, size_pt=10)


def _format_heading(paragraph, level: int) -> None:
    sizes = {1: 13, 2: 12, 3: 11, 4: 10}
    indents = {1: 0, 2: 0, 3: 0.5, 4: 1.0}
    paragraph_format = paragraph.paragraph_format
    paragraph_format.left_indent = Cm(indents.get(level, 1.5))
    paragraph_format.space_before = Pt(0 if level == 1 else 10)
    paragraph_format.space_after = Pt(10)
    paragraph_format.line_spacing = 1.15
    paragraph_format.keep_with_next = True
    _set_runs_font(paragraph, size_pt=sizes.get(level, 10), bold=True, italic=level >= 4)


def _format_caption(paragraph, *, bold: bool = False) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(0)
    paragraph_format.space_after = Pt(6)
    paragraph_format.line_spacing = 1.15
    _set_runs_font(paragraph, size_pt=9, bold=bold)


def _configure_document_styles(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Verdana"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(10)
    normal.paragraph_format.line_spacing = 1.15

    list_style = styles["List Paragraph"]
    list_style.font.name = "Verdana"
    list_style.font.size = Pt(10)
    list_style.paragraph_format.left_indent = Cm(1.27)
    list_style.paragraph_format.first_line_indent = Cm(-0.63)
    list_style.paragraph_format.space_after = Pt(6)
    list_style.paragraph_format.line_spacing = 1.15

    for level in range(1, 5):
        style = styles[f"Heading {level}"]
        style.font.name = "Verdana"
        style.font.size = Pt({1: 13, 2: 12, 3: 11, 4: 10}[level])
        style.font.bold = True
        style.font.italic = level >= 4
        style.paragraph_format.left_indent = Cm({1: 0, 2: 0, 3: 0.5, 4: 1.0}[level])
        style.paragraph_format.space_before = Pt(0 if level == 1 else 10)
        style.paragraph_format.space_after = Pt(10)
        style.paragraph_format.line_spacing = 1.15
        style.paragraph_format.keep_with_next = True


def _add_texto(document: Document, texto: str) -> None:
    for raw in (texto or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            _format_heading(document.add_heading(line[3:].strip(), level=3), 3)
        elif line.startswith("# "):
            _format_heading(document.add_heading(line[2:].strip(), level=2), 2)
        elif line.startswith("- "):
            _format_list_paragraph(document.add_paragraph(line[2:].strip(), style="List Bullet"))
        else:
            paragraph = document.add_paragraph(line)
            _format_body_paragraph(paragraph)


def _add_table(document: Document, conteudo: str, legenda: str | None, fonte: str | None, numero: str) -> None:
    if legenda:
        _format_caption(document.add_paragraph(f"Tabela {numero} - {legenda}"), bold=True)
    linhas = [ln for ln in (conteudo or "").splitlines() if ln.strip()]
    linhas = [ln for ln in linhas if not re.fullmatch(r"-+(\s*\|\s*-+)*", ln.strip())]
    if linhas:
        cells = [[cell.strip() for cell in ln.strip().strip("|").split("|")] for ln in linhas]
        cols = max(len(row) for row in cells)
        table = document.add_table(rows=len(cells), cols=cols)
        table.style = "Table Grid"
        for row_idx, row in enumerate(cells):
            for col_idx in range(cols):
                cell = table.cell(row_idx, col_idx)
                cell.text = row[col_idx] if col_idx < len(row) else ""
                for paragraph in cell.paragraphs:
                    _format_body_paragraph(paragraph, space_after_pt=0)
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if fonte:
        _format_caption(document.add_paragraph(f"Fonte: {fonte}"))


def _add_figura(document: Document, figura: Figura | None, legenda: str | None, fonte: str | None, numero: str) -> None:
    if figura is not None:
        try:
            document.add_picture(BytesIO(figura.dados), width=Cm(16))
            document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            document.paragraphs[-1].paragraph_format.space_after = Pt(6)
        except Exception:  # noqa: BLE001
            _format_caption(document.add_paragraph(f"[Figura #{figura.id} não pôde ser inserida no DOCX]"))
    else:
        _format_caption(document.add_paragraph("[Figura importada sem imagem vinculada]"))
    if legenda:
        paragraph = document.add_paragraph(f"Figura {numero} - {legenda}")
        _format_caption(paragraph, bold=True)
    if fonte:
        paragraph = document.add_paragraph(f"Fonte: {fonte}")
        _format_caption(paragraph)


def _add_texto_com_marcadores(
    document: Document,
    conteudo: str,
    figuras_by_id: dict[int, Figura],
    fig_counter: int,
    tab_counter: int,
    sec_numero: str,
) -> tuple[int, int]:
    parts: list[tuple[str, str]] = []
    last = 0
    for match in _RE_TABELA.finditer(conteudo or ""):
        parts.append(("texto", conteudo[last:match.start()]))
        idx_raw = (match.group(1) or "").strip()
        g2 = match.group(2)
        g3 = match.group(3)
        legenda = (g3 if g2 in ("S", "I") else (g2 or g3 or "")).strip()
        tab_counter += 1
        numero = idx_raw or _figura_label(sec_numero, tab_counter)
        parts.append(("tabela", (match.group(4) or "", legenda, "", numero)))
        last = match.end()
    parts.append(("texto", conteudo[last:]))

    for kind, value in parts:
        if kind == "tabela":
            corpo, legenda, fonte, numero = value
            _add_table(document, corpo, legenda, fonte, numero)
            continue
        chunk = value
        sub_last = 0
        for match in _RE_FIGURA.finditer(chunk):
            _add_texto(document, chunk[sub_last:match.start()])
            g1 = (match.group(1) or "").strip()
            g2 = match.group(2)
            g3 = match.group(3)
            g4 = match.group(4)
            idx_raw = ""
            figura_id = 0
            legenda = ""
            if g4 is not None and g3 in ("S", "I"):
                idx_raw = g1
                figura_id = int(g2 or "0") if (g2 or "").isdigit() else 0
                legenda = (g4 or "").strip()
            elif g3 is not None and (g2 or "").isdigit():
                idx_raw = g1
                figura_id = int(g2 or "0")
                legenda = (g3 or "").strip()
            elif g2 is not None:
                figura_id = int(g1 or "0") if g1.isdigit() else 0
                legenda = (g2 or "").strip()
            else:
                figura_id = int(g1 or "0") if g1.isdigit() else 0
            fig_counter += 1
            numero = idx_raw or _figura_label(sec_numero, fig_counter)
            _add_figura(document, figuras_by_id.get(figura_id), legenda, "", numero)
            sub_last = match.end()
        _add_texto(document, chunk[sub_last:])
    return fig_counter, tab_counter


def render_docx(db: Session, rel: Relatorio, section_ids: set[int] | None = None) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.8)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.bottom_margin = Cm(2.2)

    _configure_document_styles(document)

    _format_heading(document.add_heading(rel.titulo, level=0), 1)
    _format_body_paragraph(document.add_paragraph(f"{rel.codigo} - {rel.mes_referencia} - {rel.versao}"))
    _format_body_paragraph(document.add_paragraph(f"Período: {rel.periodo_inicio.strftime('%d/%m/%Y')} a {rel.periodo_fim.strftime('%d/%m/%Y')}"))

    figura_ids = _figura_ids_relatorio(rel, section_ids)
    figuras_by_id = {
        figura.id: figura for figura in db.query(Figura).filter(Figura.id.in_(figura_ids)).all()
    } if figura_ids else {}

    fig_by_top: dict[str, int] = {}
    tab_by_top: dict[str, int] = {}
    for sec in rel.secoes:
        if section_ids is not None and sec.id not in section_ids:
            continue
        top = (sec.numero or "").split(".")[0]
        fig_counter = fig_by_top.get(top, 0)
        tab_counter = tab_by_top.get(top, 0)
        heading_level = min(sec.numero.count(".") + 1, 4)
        _format_heading(document.add_heading(f"{sec.numero} {sec.titulo}", level=heading_level), heading_level)
        if not sec.blocos:
            _format_body_paragraph(document.add_paragraph("- sem conteúdo nesta seção -"))
            continue
        for bloco in sec.blocos:
            if bloco.titulo:
                _format_heading(document.add_heading(bloco.titulo, level=4), 4)
            if bloco.tipo == "figura":
                fig_counter += 1
                _add_figura(document, figuras_by_id.get(bloco.figura_id or 0), bloco.legenda, bloco.fonte, _figura_label(sec.numero, fig_counter))
            elif bloco.tipo == "tabela":
                tab_counter += 1
                _add_table(document, bloco.conteudo or "", bloco.legenda, bloco.fonte, _figura_label(sec.numero, tab_counter))
            elif bloco.tipo == "lista":
                for line in (bloco.conteudo or "").splitlines():
                    item = re.sub(r"^-\s+", "", line.strip())
                    if item:
                        _format_list_paragraph(document.add_paragraph(item, style="List Bullet"))
            else:
                fig_counter, tab_counter = _add_texto_com_marcadores(
                    document, bloco.conteudo or "", figuras_by_id, fig_counter, tab_counter, sec.numero
                )
        fig_by_top[top] = fig_counter
        tab_by_top[top] = tab_counter

    output = BytesIO()
    document.save(output)
    return output.getvalue()
