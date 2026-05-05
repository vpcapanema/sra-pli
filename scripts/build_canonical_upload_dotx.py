"""Gera modelos canonicos (.dotx) a partir de um DOCX master real.

Abordagem:
- Usa o DOCX master em ``relatorios_entregues/`` (padrao: primeiro D20-*.docx
  encontrado) como fonte de formatacao canonica.
- Copia integralmente styles.xml, numbering.xml, theme, headers/footers,
  docProps e customXml para os dotx gerados.
- Para cada ``(numero, titulo)`` de ``SECOES_PADRAO``, monta um ``.dotx``
  contendo a fatia do body do master entre o heading da secao e o
  proximo heading de nivel menor ou igual (ou fim do body), com TODO o
  conteudo de autor apagado (textos, imagens, celulas), preservando
  estrutura e estilos (pPr, rPr, pStyle, numPr, tblPr, tblGrid, tcPr,
  trPr, sectPr).
- Gera tambem ``SRA_todas_secoes.dotx`` = copia integral do master com
  o mesmo criterio de limpeza.

Executar::

  .\\.venv\\Scripts\\python.exe scripts/build_canonical_upload_dotx.py
"""
from __future__ import annotations

import copy
import io
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import SECOES_PADRAO  # noqa: E402
from app.notificacoes.modelos import filename_para  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"
ET.register_namespace("w", W_NS)
# Namespaces auxiliares comuns em docx modernos; preservados para fidelidade
for prefix, uri in {
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "v": "urn:schemas-microsoft-com:vml",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}.items():
    try:
        ET.register_namespace(prefix, uri)
    except ValueError:
        pass

RELS_MAIN = "_rels/.rels"
DOC_PART = "word/document.xml"
CT_FILE = "[Content_Types].xml"
DOC_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
TPL_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"

HEADING_STYLE_TO_LEVEL = {f"Ttulo{i}": i for i in range(1, 10)}
# Variacoes que aparecem em documentos brasileiros
HEADING_STYLE_TO_LEVEL.update(
    {
        f"Heading{i}": i for i in range(1, 10)
    }
)
HEADING_STYLE_TO_LEVEL.update(
    {
        f"heading{i}": i for i in range(1, 10)
    }
)

OUT_DIR = ROOT / "modelos_upload_doc_canonicos"
MASTER_DIR = ROOT / "relatorios_entregues"


def _find_master() -> Path:
    """Escolhe o master: prioriza D20-11 se existir, senao primeiro D20-*.docx."""
    cand: list[Path] = []
    for p in sorted(MASTER_DIR.iterdir()):
        if p.suffix.lower() != ".docx" or p.name.startswith("~$"):
            continue
        cand.append(p)
    if not cand:
        raise SystemExit(f"Nenhum DOCX master encontrado em {MASTER_DIR}")
    for p in cand:
        if "D20-11" in p.name:
            return p
    return cand[0]


def _pstyle_val(p: ET.Element) -> str:
    pPr = p.find(f"{W}pPr")
    if pPr is None:
        return ""
    s = pPr.find(f"{W}pStyle")
    return s.get(f"{W}val", "") if s is not None else ""


def _text_of(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _norm(s: str) -> str:
    s = _strip_accents(s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _heading_level(p: ET.Element) -> int:
    return HEADING_STYLE_TO_LEVEL.get(_pstyle_val(p), 0)


def _clear_paragraph_text(p: ET.Element, *, is_heading: bool = False) -> None:
    """Apaga o texto/imagens/conteudo de um paragrafo, mantendo estilos.

    Para headings: limita a remover imagens/graphics mas preserva o texto
    e estilos (o heading e o "titulo" da secao).
    """
    # Remove imagens / desenhos
    for tag in (f"{W}drawing", f"{W}pict", f"{W}object"):
        for parent in list(p.iter()):
            for child in list(parent):
                if child.tag == tag:
                    parent.remove(child)
    if is_heading:
        return
    # Zera textos dos runs
    for t in p.iter(f"{W}t"):
        t.text = ""
    # Remove tabs e breaks dentro dos runs (nao necessario manter texto vazio)
    for r in p.findall(f"{W}r"):
        # remove conteudo auxiliar mantendo rPr
        for child in list(r):
            if child.tag not in (f"{W}rPr", f"{W}t"):
                r.remove(child)
        # Garante que exista 1 w:t vazio para nao ficar run completamente vazio
        if r.find(f"{W}t") is None:
            t_el = ET.SubElement(r, f"{W}t")
            t_el.text = ""
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    # Remove sdt filhos (content controls com conteudo de autor)
    for child in list(p):
        if child.tag == f"{W}sdt":
            p.remove(child)


def _clear_table_content(tbl: ET.Element) -> None:
    """Mantem estrutura da tabela, limpa textos e imagens das celulas."""
    for tc in tbl.iter(f"{W}tc"):
        # Remove imagens
        for drawing in list(tc.iter(f"{W}drawing")):
            parent = _find_parent(tc, drawing)
            if parent is not None:
                parent.remove(drawing)
        # Zera textos dos paragrafos da celula
        for p in tc.findall(f"{W}p"):
            _clear_paragraph_text(p)


def _find_parent(root: ET.Element, child: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for c in list(parent):
            if c is child:
                return parent
    return None


def _clean_children(children: list[ET.Element]) -> list[ET.Element]:
    """Limpa recursivamente uma lista de elementos (paragrafos/tabelas/sectPr)."""
    cleaned: list[ET.Element] = []
    for el in children:
        tag = el.tag
        if tag == f"{W}p":
            el2 = copy.deepcopy(el)
            _clear_paragraph_text(el2, is_heading=_heading_level(el2) > 0)
            cleaned.append(el2)
        elif tag == f"{W}tbl":
            el2 = copy.deepcopy(el)
            _clear_table_content(el2)
            cleaned.append(el2)
        else:
            # sectPr, sdt block, etc. - manter estrutura (sectPr preserva orientacao)
            cleaned.append(copy.deepcopy(el))
    return cleaned


def _build_slice_for_section(
    body_children: list[ET.Element],
    sec_numero: str,
    sec_titulo: str,
) -> list[ET.Element]:
    """Retorna os elementos XML da fatia da secao ``sec_numero`` do master.

    Estrategia de match: conta os headings na ordem em que aparecem e
    gera numeracao ``a.b.c`` por contadores (como no master). Compara
    com ``sec_numero``. Quando acha, coleta ate o proximo heading de
    nivel <= ao encontrado.

    Fallback: se o numero nao existir no master, devolve lista vazia
    (o caller gera esqueleto minimo).
    """
    counters = [0] * 10
    start = -1
    start_level = 0
    end = len(body_children)
    for i, el in enumerate(body_children):
        if el.tag != f"{W}p":
            continue
        lvl = _heading_level(el)
        if lvl <= 0:
            continue
        for k in range(lvl + 1, 10):
            counters[k] = 0
        counters[lvl] += 1
        numero = ".".join(str(counters[k]) for k in range(1, lvl + 1))
        if start < 0 and numero == sec_numero:
            start = i
            start_level = lvl
            continue
        if start >= 0 and lvl <= start_level:
            end = i
            break
    if start < 0:
        return []
    return _clean_children(body_children[start:end])


def _build_standalone_heading(sec_numero: str, sec_titulo: str, style_id: str) -> list[ET.Element]:
    """Esqueleto minimo quando a secao nao existe no master."""
    p = ET.Element(f"{W}p")
    pPr = ET.SubElement(p, f"{W}pPr")
    ps = ET.SubElement(pPr, f"{W}pStyle")
    ps.set(f"{W}val", style_id)
    r = ET.SubElement(p, f"{W}r")
    t = ET.SubElement(r, f"{W}t")
    t.text = sec_titulo
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    empty = ET.Element(f"{W}p")
    return [p, empty]


def _level_to_style(level: int) -> str:
    return f"Ttulo{max(1, min(level, 9))}"


def _parse_document(master_bytes: bytes) -> tuple[ET.Element, list[ET.Element], ET.Element]:
    """Devolve (root, body_children, final_sectPr) do document.xml do master."""
    with zipfile.ZipFile(io.BytesIO(master_bytes)) as z:
        xml_bytes = z.read(DOC_PART)
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{W}body")
    children = list(body)
    final_sectPr = None
    if children and children[-1].tag == f"{W}sectPr":
        final_sectPr = children[-1]
    return root, children, final_sectPr


def _serialize_document_with_body(root: ET.Element, body_children: list[ET.Element], final_sectPr: ET.Element | None) -> bytes:
    """Reconstroi o document.xml substituindo o <w:body> pelos children fornecidos."""
    new_root = copy.deepcopy(root)
    body = new_root.find(f"{W}body")
    # limpa children
    for ch in list(body):
        body.remove(ch)
    for el in body_children:
        body.append(copy.deepcopy(el))
    # garante sectPr final
    has_final = any(
        el.tag == f"{W}sectPr" for el in body
    ) or (
        len(body) > 0
        and body[-1].tag == f"{W}p"
        and body[-1].find(f"{W}pPr/{W}sectPr") is not None
    )
    if not has_final and final_sectPr is not None:
        body.append(copy.deepcopy(final_sectPr))
    body_xml = ET.tostring(new_root, encoding="UTF-8")
    if not body_xml.startswith(b"<?xml"):
        body_xml = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body_xml
    return body_xml


def _convert_content_types(ct_bytes: bytes) -> bytes:
    """Troca o content type do documento principal para template."""
    text = ct_bytes.decode("utf-8")
    text = text.replace(DOC_CT, TPL_CT)
    return text.encode("utf-8")


def _convert_rels_main(rels_bytes: bytes) -> bytes:
    """Mantem .rels inalterado (officeDocument type continua valendo)."""
    return rels_bytes


def _write_dotx(master_bytes: bytes, new_document_xml: bytes, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(master_bytes)) as src, zipfile.ZipFile(
        out_path, "w", zipfile.ZIP_DEFLATED
    ) as dst:
        for name in src.namelist():
            if name == DOC_PART:
                dst.writestr(DOC_PART, new_document_xml)
            elif name == CT_FILE:
                dst.writestr(CT_FILE, _convert_content_types(src.read(name)))
            elif name == RELS_MAIN:
                dst.writestr(RELS_MAIN, _convert_rels_main(src.read(name)))
            else:
                dst.writestr(name, src.read(name))


def main() -> int:
    master_path = _find_master()
    print(f"[master] {master_path.name}")
    master_bytes = master_path.read_bytes()
    root, body_children, final_sectPr = _parse_document(master_bytes)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Remove dotx antigos
    for old in OUT_DIR.glob("*.dotx"):
        try:
            old.unlink()
        except OSError:
            pass

    gerados = 0

    # 1) SRA_todas_secoes.dotx = master inteiro limpo
    todos_limpos = _clean_children(body_children)
    all_xml = _serialize_document_with_body(root, todos_limpos, final_sectPr)
    _write_dotx(master_bytes, all_xml, OUT_DIR / "SRA_todas_secoes.dotx")
    gerados += 1
    print("[ok]  SRA_todas_secoes.dotx")

    # 2) Um .dotx por secao do padrao
    nao_no_master: list[str] = []
    for numero, titulo in SECOES_PADRAO:
        slice_children = _build_slice_for_section(body_children, numero, titulo)
        used_style = _level_to_style(len([x for x in numero.split(".") if x]))
        if not slice_children:
            slice_children = _build_standalone_heading(numero, titulo, used_style)
            nao_no_master.append(numero)
        new_xml = _serialize_document_with_body(root, slice_children, final_sectPr)
        out_name = filename_para(numero, titulo)
        _write_dotx(master_bytes, new_xml, OUT_DIR / out_name)
        gerados += 1
        print(f"[ok]  {out_name}")

    if nao_no_master:
        print("[nota] Secoes nao presentes no master (esqueleto minimo):", ", ".join(nao_no_master))

    print(f"\nTotal gerado: {gerados} arquivos em {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
