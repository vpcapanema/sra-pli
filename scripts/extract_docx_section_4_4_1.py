"""Extrai apenas a secao 4.4.1 para um novo DOCX preservando formato e medias."""

from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    return "{" + W_NS + "}" + tag  # noqa: T001


def _local(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1] if elem.tag else ""


def _register_namespaces_from_document_head(raw_text: str, max_len: int = 12000) -> None:
    """Regista xmlns do documento para o ElementTree nao reescrever ns0:/ns1:."""

    head = raw_text[:max_len]
    for match in re.finditer(r"xmlns:([A-Za-z0-9]+)=\"([^\"]+)\"", head):
        prefix, uri = match.group(1), match.group(2)
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass


def extract_body_slice_indices(
    children_without_sect_pr: list[ET.Element],
) -> tuple[int, int]:
    """Resolve indices da secao 4.4.1 ate antes do titulo 4.4.2."""

    bk_441_start = "_Toc382894708"
    bk_442_title = "_Toc1803238809"
    start_i: int | None = None
    end_i: int | None = None

    for i, child in enumerate(children_without_sect_pr):
        serialized = ET.tostring(child, encoding="unicode")
        if start_i is None and bk_441_start in serialized and "tulo3" in serialized:
            if "Acompanhamento técnico" in "".join(child.itertext()):
                start_i = i
                continue

        if start_i is not None and end_i is None and bk_442_title in serialized:
            if "Titulo3" in serialized and "Apoio Administrativo e institucional" in "".join(
                child.itertext()
            ):
                end_i = i
                break

    if start_i is None or end_i is None:
        msg = (
            f"não foi possível resolver limites "
            f"(start_i={start_i}, end_i={end_i})."
        )
        raise ValueError(msg)

    return start_i, end_i


def _produce_section_document_xml_blob(source_docx: Path) -> bytes:
    with zipfile.ZipFile(source_docx, "r") as z_in:
        doc_xml = z_in.read("word/document.xml")

    decoded = doc_xml.decode("utf-8")
    _register_namespaces_from_document_head(decoded)

    root = ET.fromstring(doc_xml)
    body = root.find(f".//{_q('body')}")
    if body is None:
        raise ValueError("document.xml sem w:body")

    children = list(body)
    if not children or _local(children[-1]) != "sectPr":
        raise ValueError("ultimo filho de w:body deveria ser sectPr")

    sect_pr = children[-1]
    start_i, end_i = extract_body_slice_indices(children[:-1])
    sliced = children[start_i:end_i]

    for node in list(body):
        body.remove(node)

    for paragraph in sliced:
        body.append(copy.deepcopy(paragraph))
    body.append(copy.deepcopy(sect_pr))

    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _write_docx_replacing_document_xml(
    source_docx: Path,
    destination_docx: Path,
    new_document_xml: bytes,
) -> None:
    fd, raw_path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    tmp_path = Path(raw_path)

    try:
        with zipfile.ZipFile(source_docx, "r") as z_read:
            with zipfile.ZipFile(
                tmp_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as z_write:
                for info in z_read.infolist():
                    payload = (
                        new_document_xml
                        if info.filename == "word/document.xml"
                        else z_read.read(info.filename)
                    )
                    z_write.writestr(info, payload)
        shutil.move(str(tmp_path), destination_docx)
    finally:
        tmp_path.unlink(missing_ok=True)


def build_document_only_section(
    source_docx: Path,
    destination_docx: Path,
) -> None:
    out_bytes = _produce_section_document_xml_blob(source_docx)
    _write_docx_replacing_document_xml(source_docx, destination_docx, out_bytes)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    source = repo / "arquivos teste" / "D20-12 - R01 - 30012_REV.docx"
    dest = repo / "arquivos teste" / "D20-12 - R01 - 30012_REV_apenas_secao_4_4_1.docx"
    build_document_only_section(source, dest)
    print(f"Escrito: {dest}")


if __name__ == "__main__":
    main()
