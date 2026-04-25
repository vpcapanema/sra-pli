# pylint: disable=protected-access
import base64
import re
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Bloco, Figura, Secao

router = APIRouter(
    prefix="/relatorios/{rel_id}/secoes/{sec_id}/importar",
    tags=["importacao"],
)


VALID_TYPES = {"texto", "lista", "tabela", "figura"}
_SECAO_RE = re.compile(r"^(\d+(?:\.\d+)*)(?:\s+|\s*[–-]\s*)(.+)?$")
_HEADING_RE = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+){1,})(?:[.)])?\s+.+$")
_FIGURA_RE = re.compile(r"^Figura\s+\d+(?:[-.]\d+)*\s*[:–-]\s*.+", re.IGNORECASE)
_FONTE_RE = re.compile(r"\bFonte:\s*(.+)$", re.IGNORECASE)
_SECTION_LINE_RE = re.compile(r"^(\d+(?:\.\d+)+)(?:\s*[–-]\s*|\s+)?(.+)?$")


def _check(request: Request, db: Session, rel_id: int, sec_id: int):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={"Location": "/login"})
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if (
        user.role == "autor"
        and sec.responsavel_id is not None
        and sec.responsavel_id != user.id
    ):
        raise HTTPException(403, detail="Não autorizado")
    return user, sec


def _target_section(db: Session, rel_id: int, sec_id: int, numero: str | None):
    if not numero:
        return db.get(Secao, sec_id)
    sec = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id, Secao.numero == numero.strip())
        .one_or_none()
    )
    return sec or db.get(Secao, sec_id)


def _append_table(blocks: list[dict], sec: Secao, linhas: list[str], legenda: str = ""):
    if not any(ln.strip() for ln in linhas):
        return
    blocks.append(
        {
            "secao_id": sec.id,
            "secao_numero": sec.numero,
            "secao_titulo": sec.titulo,
            "tipo": "tabela",
            "titulo": "",
            "conteudo": "\n".join(ln for ln in linhas if ln.strip()),
            "legenda": legenda,
            "fonte": "",
        }
    )


def _append_figure_placeholder(
    blocks: list[dict],
    sec: Secao,
    legenda: str,
    fonte: str,
    image_b64: str = "",
    image_mime: str = "",
    image_name: str = "",
):
    blocks.append(
        {
            "secao_id": sec.id,
            "secao_numero": sec.numero,
            "secao_titulo": sec.titulo,
            "tipo": "figura",
            "titulo": "",
            "conteudo": "",
            "legenda": legenda.strip(),
            "fonte": fonte.strip(),
            "image_b64": image_b64,
            "image_mime": image_mime,
            "image_name": image_name,
        }
    )


def _find_section_line(db: Session, rel_id: int, text: str):
    body = re.sub(r"^#{1,6}\s*", "", text.strip())
    match = _SECTION_LINE_RE.match(body)
    if not match:
        return None
    sec = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id, Secao.numero == match.group(1))
        .one_or_none()
    )
    return sec


def _normalize_heading_line(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    body = re.sub(r"^#{1,6}\s*", "", stripped)
    if not _HEADING_RE.match(body):
        return None
    if stripped.startswith("#"):
        return stripped
    return "## " + body


def _split_figura_fonte(line: str) -> tuple[str, str]:
    match = _FONTE_RE.search(line)
    if not match:
        return line.strip(), ""
    return line[: match.start()].strip(), match.group(1).strip()


def _flush_text(blocks: list[dict], sec: Secao, linhas: list[str]) -> None:
    clean = [ln.rstrip() for ln in linhas if ln.strip()]
    if not clean:
        linhas.clear()
        return
    pending: list[str] = []
    idx = 0
    while idx < len(clean):
        current = clean[idx].strip()
        if _FIGURA_RE.match(current):
            if pending:
                _flush_text(blocks, sec, pending)
                pending.clear()
            legenda, fonte = _split_figura_fonte(current)
            if not fonte and idx + 1 < len(clean) and clean[idx + 1].strip().lower().startswith("fonte:"):
                fonte = clean[idx + 1].strip()[6:].strip()
                idx += 1
            _append_figure_placeholder(blocks, sec, legenda, fonte)
        else:
            pending.append(clean[idx])
        idx += 1
    if len(pending) != len(clean):
        if pending:
            _flush_text(blocks, sec, pending)
        linhas.clear()
        return
    tipo = "lista" if all(ln.strip().startswith("-") for ln in clean) else "texto"
    blocks.append(
        {
            "secao_id": sec.id,
            "secao_numero": sec.numero,
            "secao_titulo": sec.titulo,
            "tipo": tipo,
            "titulo": "",
            "conteudo": "\n".join(clean),
            "legenda": "",
            "fonte": "",
        }
    )
    linhas.clear()


def _parse_import_text(texto: str, db: Session, rel_id: int, sec_id: int) -> list[dict]:
    current_sec = db.get(Secao, sec_id)
    blocks: list[dict] = []
    buf: list[str] = []
    in_table = False
    table_lines: list[str] = []
    table_legenda = ""

    for raw in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.upper().startswith("[SECAO:") and stripped.endswith("]"):
            if in_table:
                _append_table(blocks, current_sec, table_lines, table_legenda)
                table_lines.clear()
                table_legenda = ""
                in_table = False
            _flush_text(blocks, current_sec, buf)
            numero = stripped[7:-1].strip()
            current_sec = _target_section(db, rel_id, sec_id, numero)
            continue

        if stripped.upper().startswith("[TABELA") and stripped.endswith("]"):
            _flush_text(blocks, current_sec, buf)
            in_table = True
            table_lines = []
            table_legenda = ""
            if stripped.upper().startswith("[TABELA:"):
                table_legenda = stripped[8:-1].strip()
            continue

        if stripped.upper() == "[/TABELA]":
            if in_table:
                _append_table(blocks, current_sec, table_lines, table_legenda)
                table_lines.clear()
                table_legenda = ""
                in_table = False
            continue

        if in_table:
            if stripped and not set(stripped.replace("|", "").strip()) <= {"-", ":"}:
                table_lines.append(line)
            continue

        if not stripped:
            _flush_text(blocks, current_sec, buf)
            continue

        sec_from_line = _find_section_line(db, rel_id, stripped)
        if sec_from_line:
            _flush_text(blocks, current_sec, buf)
            current_sec = sec_from_line
            continue

        heading = _normalize_heading_line(stripped)
        if heading:
            _flush_text(blocks, current_sec, buf)
            buf.append(heading)
            _flush_text(blocks, current_sec, buf)
            continue

        if stripped.startswith("#") and buf:
            _flush_text(blocks, current_sec, buf)
        buf.append(line)

    if in_table:
        _append_table(blocks, current_sec, table_lines, table_legenda)
    _flush_text(blocks, current_sec, buf)
    return blocks


def _iter_docx_blocks(document):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _paragraph_images(paragraph: Paragraph) -> list[dict]:
    images = []
    for run in paragraph.runs:
        for blip in run._element.xpath(".//a:blip"):
            rel_id = blip.get(qn("r:embed"))
            if not rel_id:
                continue
            part = paragraph.part.related_parts.get(rel_id)
            if not part:
                continue
            mime = getattr(part, "content_type", "image/png")
            ext = mime.split("/")[-1].replace("jpeg", "jpg")
            images.append(
                {
                    "image_b64": base64.b64encode(part.blob).decode("ascii"),
                    "image_mime": mime,
                    "image_name": f"figura_importada.{ext}",
                }
            )
    return images


def _section_from_heading(db: Session, rel_id: int, sec_id: int, text: str):
    match = _SECAO_RE.match(text.strip())
    if not match:
        return None
    sec = _target_section(db, rel_id, sec_id, match.group(1))
    return sec if sec and sec.numero == match.group(1) else None


def _parse_docx(raw: bytes, db: Session, rel_id: int, sec_id: int) -> list[dict]:
    document = Document(BytesIO(raw))
    current_sec = db.get(Secao, sec_id)
    blocks: list[dict] = []
    buf: list[str] = []
    pending_figure_idx: int | None = None

    for element in _iter_docx_blocks(document):
        if isinstance(element, Table):
            _flush_text(blocks, current_sec, buf)
            linhas = []
            for row in element.rows:
                cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                if any(cells):
                    linhas.append(" | ".join(cells))
            _append_table(blocks, current_sec, linhas)
            continue

        images = _paragraph_images(element)
        if images:
            _flush_text(blocks, current_sec, buf)
            pending_figure_idx = None
            for image in images:
                _append_figure_placeholder(blocks, current_sec, "", "", **image)
                pending_figure_idx = len(blocks) - 1

        text = element.text.strip()
        if not text:
            _flush_text(blocks, current_sec, buf)
            continue

        if _FIGURA_RE.match(text):
            _flush_text(blocks, current_sec, buf)
            legenda, fonte = _split_figura_fonte(text)
            if pending_figure_idx is not None:
                blocks[pending_figure_idx]["legenda"] = legenda
                blocks[pending_figure_idx]["fonte"] = fonte
                pending_figure_idx = None
            else:
                _append_figure_placeholder(blocks, current_sec, legenda, fonte)
            continue

        if text.upper().startswith("[SECAO:") and text.endswith("]"):
            _flush_text(blocks, current_sec, buf)
            current_sec = _target_section(db, rel_id, sec_id, text[7:-1].strip())
            continue

        sec_from_line = _find_section_line(db, rel_id, text)
        if sec_from_line:
            _flush_text(blocks, current_sec, buf)
            current_sec = sec_from_line
            pending_figure_idx = None
            continue

        style = (element.style.name or "").lower() if element.style else ""
        if style.startswith("heading") or style.startswith("título"):
            sec = _section_from_heading(db, rel_id, sec_id, text)
            if sec:
                _flush_text(blocks, current_sec, buf)
                current_sec = sec
                continue
            _flush_text(blocks, current_sec, buf)
            prefix = "# " if any(x in style for x in ("1", "título 1")) else "## "
            buf.append(prefix + text)
            _flush_text(blocks, current_sec, buf)
            continue

        heading = _normalize_heading_line(text)
        if heading:
            _flush_text(blocks, current_sec, buf)
            buf.append(heading)
            _flush_text(blocks, current_sec, buf)
            continue

        if "list" in style or "lista" in style:
            if buf and not all(ln.strip().startswith("-") for ln in buf):
                _flush_text(blocks, current_sec, buf)
            buf.append("- " + text.lstrip("-•· "))
        else:
            if buf and all(ln.strip().startswith("-") for ln in buf):
                _flush_text(blocks, current_sec, buf)
            buf.append(text)

    _flush_text(blocks, current_sec, buf)
    return blocks


@router.post("/analisar")
async def analisar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _check(request, db, rel_id, sec_id)
    nome = arquivo.filename or ""
    raw = await arquivo.read()
    if len(raw) > 5_000_000:
        raise HTTPException(400, detail="Arquivo muito grande para importação assistida.")
    if nome.lower().endswith(".docx"):
        blocks = _parse_docx(raw, db, rel_id, sec_id)
        return JSONResponse({"blocks": blocks, "total": len(blocks)})
    if nome.lower().endswith(".txt"):
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = raw.decode("latin-1")
        blocks = _parse_import_text(texto, db, rel_id, sec_id)
        return JSONResponse({"blocks": blocks, "total": len(blocks)})
    raise HTTPException(400, detail="Envie um arquivo .txt ou .docx.")


@router.post("/confirmar")
async def confirmar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, _sec = _check(request, db, rel_id, sec_id)
    payload = await request.json()
    blocks = payload.get("blocks") or []
    selected_items = []
    target_ids: set[int] = set()
    for item in blocks:
        if not item.get("selecionado", True):
            continue
        try:
            target_id = int(item.get("secao_id") or sec_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, detail="Seção de destino inválida.") from exc
        selected_items.append((item, target_id))
        target_ids.add(target_id)

    secoes = {
        sec.id: sec
        for sec in db.query(Secao)
        .filter(Secao.relatorio_id == rel_id, Secao.id.in_(target_ids))
        .all()
    } if target_ids else {}
    ordens: dict[int, int] = {}
    ordem_rows = []
    if target_ids:
        ordem_rows = (
            db.query(Bloco.secao_id, Bloco.ordem)
            .filter(Bloco.secao_id.in_(target_ids))
            .all()
        )
    for secao_id, ordem_atual in ordem_rows:
        ordens[secao_id] = max(ordens.get(secao_id, 0), (ordem_atual or -1) + 1)
    created = 0

    for item, target_id in selected_items:
        sec = secoes.get(target_id)
        if not sec:
            raise HTTPException(400, detail="Seção de destino inválida.")
        if (
            user.role == "autor"
            and sec.responsavel_id is not None
            and sec.responsavel_id != user.id
        ):
            raise HTTPException(403, detail="Não autorizado para uma seção selecionada.")
        tipo = (item.get("tipo") or "texto").strip().lower()
        if tipo not in VALID_TYPES:
            tipo = "texto"
        figura_id = None
        if tipo == "figura" and item.get("image_b64"):
            try:
                dados = base64.b64decode(item.get("image_b64"), validate=True)
            except Exception as exc:
                raise HTTPException(400, detail="Imagem importada inválida.") from exc
            fig = Figura(
                relatorio_id=rel_id,
                nome=(item.get("image_name") or "figura_importada").strip(),
                mime=(item.get("image_mime") or "image/png").strip(),
                dados=dados,
                legenda=(item.get("legenda") or "").strip() or None,
                fonte=(item.get("fonte") or "").strip() or None,
            )
            db.add(fig)
            db.flush()
            figura_id = fig.id
        ordem = ordens.get(sec.id, 0)
        ordens[sec.id] = ordem + 1
        db.add(
            Bloco(
                secao_id=sec.id,
                tipo=tipo,
                ordem=ordem,
                titulo=(item.get("titulo") or "").strip() or None,
                conteudo=item.get("conteudo") or "",
                legenda=(item.get("legenda") or "").strip() or None,
                fonte=(item.get("fonte") or "").strip() or None,
                figura_id=figura_id,
                autor_id=user.id,
            )
        )
        if sec.status == "pendente":
            sec.status = "em_andamento"
        created += 1

    db.commit()
    return JSONResponse({"created": created})
