# pylint: disable=protected-access
import base64
from dataclasses import dataclass
from difflib import SequenceMatcher
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
from ..db import get_db, tx_session
from ..models import Bloco, Figura, Secao, User
from ..process_events import process_done, process_log, process_start

router = APIRouter(
    prefix="/relatorios/{rel_id}/secoes/{sec_id}/importar",
    tags=["importacao"],
)


VALID_TYPES = {"texto", "lista", "tabela", "figura"}
_HEADING_RE = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+){1,})(?:[.)])?\s*\S.+$")
_FIGURA_RE = re.compile(r"^Figura\s+(?:\d+(?:[-.]\d+)*-?|[-–—])\s*[:–—-]\s*.+", re.IGNORECASE)
_TABELA_RE = re.compile(r"^Tabela\s+(?:\d+(?:[-.]\d+)*-?|[-–—])\s*[:–—-]\s*.+", re.IGNORECASE)
_FONTE_RE = re.compile(r"\bFonte:\s*(.+)$", re.IGNORECASE)
_SECTION_NUMBER_RE = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+)*)(.*)$")
_FIGURA_PREFIX_RE = re.compile(r"^Figura\s+(?:\d+(?:[-.]\d+)*-?|[-–—])\s*[:–—-]\s*", re.IGNORECASE)
_TABELA_PREFIX_RE = re.compile(r"^Tabela\s+(?:\d+(?:[-.]\d+)*-?|[-–—])\s*[:–—-]\s*", re.IGNORECASE)
_TEXT_TABLE_RE = re.compile(r"^\|?.+\|.+\|?.*$")


@dataclass(frozen=True)
class SecaoDestino:
    secao: Secao | None
    numero: str
    titulo: str
    confianca: float
    motivo: str
    acao: str = "usar"


def _norm_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"[–—-]", " ", text)
    text = re.sub(r"[^\w\s.]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _check(request: Request, db: Session, rel_id: int, sec_id: int):
    user = current_user(request, db)
    if not user:
        # Endpoints JSON: 401 explícito (cliente fetch trata e redireciona).
        raise HTTPException(status_code=401, detail="Sessão expirada. Faça login novamente.")
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


def _secoes_taxonomia(db: Session, rel_id: int) -> list[Secao]:
    return (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id)
        .order_by(Secao.ordem, Secao.numero)
        .all()
    )


def _default_destino(sec: Secao, motivo: str = "seção atual do importador") -> SecaoDestino:
    return SecaoDestino(secao=sec, numero=sec.numero, titulo=sec.titulo, confianca=0.55, motivo=motivo)


def _block_base(sec: Secao, destino: SecaoDestino | None = None) -> dict:
    destino = destino or _default_destino(sec)
    return {
        "secao_id": destino.secao.id if destino.secao is not None else "",
        "secao_numero": destino.numero,
        "secao_titulo": destino.titulo,
        "confianca": round(destino.confianca, 2),
        "motivo": destino.motivo,
        "acao_secao": destino.acao,
    }


def _target_section(secoes: list[Secao], fallback: Secao, numero: str | None) -> SecaoDestino:
    numero = (numero or "").strip()
    if not numero:
        return _default_destino(fallback)
    by_numero = {sec.numero.strip(): sec for sec in secoes}
    sec = by_numero.get(numero)
    if sec:
        return SecaoDestino(sec, sec.numero, sec.titulo, 0.99, f"marcador [SECAO] apontou para {numero}")
    return SecaoDestino(None, numero, f"Seção {numero}", 0.72, f"marcador [SECAO:{numero}] criará seção no relatório", "criar")


def _match_secao_linha(secoes: list[Secao], text: str, *, heading_context: bool = False) -> SecaoDestino | None:
    body = re.sub(r"^#{1,6}\s*", "", text.strip())
    if not body:
        return None
    by_numero = {sec.numero.strip(): sec for sec in secoes}
    match = _SECTION_NUMBER_RE.match(body)
    if match:
        numero = match.group(1).strip()
        resto = (match.group(2) or "").strip()
        sec = by_numero.get(numero)
        if sec:
            titulo_norm = _norm_text(sec.titulo)
            resto_norm = _norm_text(resto)
            if not resto_norm:
                return SecaoDestino(sec, sec.numero, sec.titulo, 0.96, f"número de seção {numero} reconhecido")
            similaridade = SequenceMatcher(None, resto_norm, titulo_norm).ratio()
            if similaridade >= 0.72 or heading_context:
                acao = "usar" if similaridade >= 0.72 else "renomear"
                motivo = (
                    f"número {numero} e título compatíveis com seção real"
                    if acao == "usar"
                    else f"número {numero} existe, mas o arquivo traz novo título"
                )
                titulo = resto.strip() or sec.titulo
                return SecaoDestino(sec, sec.numero, titulo, 0.94 if acao == "usar" else 0.82, motivo, acao)
        for sec_numero in sorted(by_numero, key=len, reverse=True):
            if not body.startswith(sec_numero):
                continue
            proximo = body[len(sec_numero): len(sec_numero) + 1]
            if proximo in {"", " ", "-", "–", "—"} or (proximo and not re.match(r"[\d.]", proximo)):
                sec = by_numero[sec_numero]
                titulo = body[len(sec_numero):].strip(" -–—\t") or sec.titulo
                acao = "renomear" if _norm_text(titulo) and _norm_text(titulo) != _norm_text(sec.titulo) else "usar"
                return SecaoDestino(sec, sec.numero, titulo, 0.9, f"número de seção {sec_numero} reconhecido mesmo sem espaçamento", acao)
        resto_norm = _norm_text(resto)
        if resto_norm and (heading_context or "." in numero or (len(numero) <= 2 and resto[:1].isupper())):
            return SecaoDestino(None, numero, resto.strip(), 0.84, f"seção {numero} identificada no arquivo enviado", "criar")
    titulo_norm = _norm_text(body)
    if heading_context and titulo_norm:
        best_score = -1.0
        best_sec: Secao | None = None
        for sec in secoes:
            sec_titulo = _norm_text(sec.titulo)
            if titulo_norm == sec_titulo:
                return SecaoDestino(sec, sec.numero, sec.titulo, 0.92, "título igual a uma seção real do relatório")
            score = SequenceMatcher(None, titulo_norm, sec_titulo).ratio()
            if score > best_score:
                best_score = score
                best_sec = sec
        if best_sec is not None and best_score >= 0.86:
            return SecaoDestino(best_sec, best_sec.numero, best_sec.titulo, best_score, "título parecido com uma seção real do relatório")
    return None


def _secao_sort_key(numero: str) -> tuple:
    parts = []
    for part in (numero or "").split("."):
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part.lower()))
    return tuple(parts)


def _usuario_pode_estruturar(user: User, sec_atual: Secao, numero: str) -> bool:
    if user.role in ("admin", "coordenador"):
        return True
    numero = (numero or "").strip()
    atual = (sec_atual.numero or "").strip()
    return bool(numero == atual or numero.startswith(atual + "."))


def _resolver_secao_importada(
    db: Session,
    rel_id: int,
    sec_atual: Secao,
    user: User,
    item: dict,
    secoes_by_id: dict[int, Secao],
    secoes_by_numero: dict[str, Secao],
) -> Secao:
    numero = str(item.get("secao_numero") or "").strip()
    titulo = str(item.get("secao_titulo") or "").strip()
    secao_id_raw = item.get("secao_id")

    sec: Secao | None = None
    if numero:
        sec = secoes_by_numero.get(numero)
        if sec is None:
            if not _usuario_pode_estruturar(user, sec_atual, numero):
                raise HTTPException(403, detail="Não autorizado para criar seção fora da seção atual.")
            sec = Secao(
                relatorio_id=rel_id,
                numero=numero,
                titulo=titulo or f"Seção {numero}",
                ordem=0,
                responsavel_id=user.id if user.role == "autor" else None,
            )
            db.add(sec)
            db.flush()
            secoes_by_id[sec.id] = sec
            secoes_by_numero[sec.numero] = sec
        elif titulo and _norm_text(titulo) != _norm_text(sec.titulo):
            if not _usuario_pode_estruturar(user, sec_atual, numero):
                raise HTTPException(403, detail="Não autorizado para renomear seção fora da seção atual.")
            sec.titulo = titulo
    elif secao_id_raw:
        try:
            sec = secoes_by_id.get(int(secao_id_raw))
        except (TypeError, ValueError):
            sec = None
    else:
        sec = sec_atual

    if sec is None or sec.relatorio_id != rel_id:
        raise HTTPException(400, detail="Seção de destino inválida.")
    if (
        user.role == "autor"
        and sec.responsavel_id is not None
        and sec.responsavel_id != user.id
    ):
        raise HTTPException(403, detail="Não autorizado para uma seção selecionada.")
    return sec


def _reordenar_secoes(db: Session, rel_id: int) -> None:
    secoes = db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    for ordem, sec in enumerate(sorted(secoes, key=lambda item: _secao_sort_key(item.numero))):
        sec.ordem = ordem


def _append_table(
    blocks: list[dict],
    sec: Secao,
    linhas: list[str],
    legenda: str = "",
    fonte: str = "",
    destino: SecaoDestino | None = None,
):
    if not any(ln.strip() for ln in linhas):
        return
    block = _block_base(sec, destino)
    block.update(
        {
            "tipo": "tabela",
            "titulo": "",
            "conteudo": "\n".join(ln for ln in linhas if ln.strip()),
            "legenda": legenda,
            "fonte": fonte,
        }
    )
    blocks.append(block)


def _append_figure_placeholder(
    blocks: list[dict],
    sec: Secao,
    legenda: str,
    fonte: str,
    image_b64: str = "",
    image_mime: str = "",
    image_name: str = "",
    destino: SecaoDestino | None = None,
):
    block = _block_base(sec, destino)
    block.update(
        {
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
    blocks.append(block)


def _normalize_heading_line(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    body = re.sub(r"^#{1,6}\s*", "", stripped)
    if not _HEADING_RE.match(body):
        return None
    if stripped.startswith("#"):
        return stripped
    match = _SECTION_NUMBER_RE.match(body)
    if match and match.group(2) and not match.group(2).startswith((" ", "\t")):
        body = f"{match.group(1)} {match.group(2).strip()}"
    return "## " + body


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


def _is_text_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if set(stripped.replace("|", "").strip()) <= {"-", ":"}:
        return True
    return bool(_TEXT_TABLE_RE.match(stripped))


def _flush_text(blocks: list[dict], sec: Secao, linhas: list[str], destino: SecaoDestino | None = None) -> None:
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
                _flush_text(blocks, sec, pending, destino)
                pending.clear()
            legenda, fonte = _split_figura_fonte(current)
            if not fonte and idx + 1 < len(clean) and clean[idx + 1].strip().lower().startswith("fonte:"):
                fonte = clean[idx + 1].strip()[6:].strip()
                idx += 1
            _append_figure_placeholder(blocks, sec, legenda, fonte, destino=destino)
        elif _TABELA_RE.match(current) and idx + 1 < len(clean) and _is_text_table_line(clean[idx + 1]):
            if pending:
                _flush_text(blocks, sec, pending, destino)
                pending.clear()
            legenda, fonte = _split_tabela_fonte(current)
            table_lines: list[str] = []
            idx += 1
            while idx < len(clean) and _is_text_table_line(clean[idx]):
                if not set(clean[idx].replace("|", "").strip()) <= {"-", ":"}:
                    table_lines.append(clean[idx])
                idx += 1
            if not fonte and idx < len(clean) and clean[idx].strip().lower().startswith("fonte:"):
                fonte = clean[idx].strip()[6:].strip()
            else:
                idx -= 1
            _append_table(blocks, sec, table_lines, legenda, fonte, destino=destino)
        else:
            pending.append(clean[idx])
        idx += 1
    if len(pending) != len(clean):
        if pending:
            _flush_text(blocks, sec, pending, destino)
        linhas.clear()
        return
    tipo = "lista" if all(ln.strip().startswith("-") for ln in clean) else "texto"
    block = _block_base(sec, destino)
    block.update(
        {
            "tipo": tipo,
            "titulo": "",
            "conteudo": "\n".join(clean),
            "legenda": "",
            "fonte": "",
        }
    )
    blocks.append(block)
    linhas.clear()


def _parse_import_text(texto: str, db: Session, rel_id: int, sec_id: int) -> list[dict]:
    secoes = _secoes_taxonomia(db, rel_id)
    current_sec = db.get(Secao, sec_id)
    if not current_sec:
        return []
    current_destino = _default_destino(current_sec)
    blocks: list[dict] = []
    buf: list[str] = []
    in_table = False
    table_explicit = False
    table_lines: list[str] = []
    table_legenda = ""
    table_fonte = ""
    pending_table_legenda = ""
    pending_table_fonte = ""

    for raw in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.upper().startswith("[SECAO:") and stripped.endswith("]"):
            if in_table:
                _append_table(blocks, current_sec, table_lines, table_legenda, table_fonte, current_destino)
                table_lines.clear()
                table_legenda = ""
                table_fonte = ""
                in_table = False
                table_explicit = False
            _flush_text(blocks, current_sec, buf, current_destino)
            numero = stripped[7:-1].strip()
            current_destino = _target_section(secoes, current_sec, numero)
            if current_destino.secao is not None:
                current_sec = current_destino.secao
            continue

        if stripped.upper().startswith("[TABELA") and stripped.endswith("]"):
            _flush_text(blocks, current_sec, buf, current_destino)
            in_table = True
            table_explicit = True
            table_lines = []
            table_legenda = ""
            table_fonte = ""
            if stripped.upper().startswith("[TABELA:"):
                table_legenda = stripped[8:-1].strip()
            continue

        if stripped.upper() == "[/TABELA]":
            if in_table:
                _append_table(blocks, current_sec, table_lines, table_legenda, table_fonte, current_destino)
                table_lines.clear()
                table_legenda = ""
                table_fonte = ""
                in_table = False
                table_explicit = False
            continue

        if in_table:
            if stripped.lower().startswith("fonte:"):
                table_fonte = stripped[6:].strip()
                continue
            if table_explicit:
                if stripped and not set(stripped.replace("|", "").strip()) <= {"-", ":"}:
                    table_lines.append(line)
                continue
            if stripped and _is_text_table_line(stripped):
                if not set(stripped.replace("|", "").strip()) <= {"-", ":"}:
                    table_lines.append(line)
                continue
            _append_table(blocks, current_sec, table_lines, table_legenda, table_fonte, current_destino)
            table_lines.clear()
            table_legenda = ""
            table_fonte = ""
            in_table = False
            table_explicit = False

        if not stripped:
            _flush_text(blocks, current_sec, buf, current_destino)
            continue

        sec_from_line = _match_secao_linha(secoes, stripped, heading_context=stripped.startswith("#"))
        if sec_from_line:
            _flush_text(blocks, current_sec, buf, current_destino)
            current_destino = sec_from_line
            if current_destino.secao is not None:
                current_sec = current_destino.secao
            pending_table_legenda = ""
            pending_table_fonte = ""
            continue

        heading = _normalize_heading_line(stripped)
        if heading:
            _flush_text(blocks, current_sec, buf, current_destino)
            buf.append(heading)
            _flush_text(blocks, current_sec, buf, current_destino)
            continue

        if _TABELA_RE.match(stripped):
            _flush_text(blocks, current_sec, buf, current_destino)
            pending_table_legenda, pending_table_fonte = _split_tabela_fonte(stripped)
            continue

        if _is_text_table_line(stripped):
            _flush_text(blocks, current_sec, buf, current_destino)
            table_lines = [line] if not set(stripped.replace("|", "").strip()) <= {"-", ":"} else []
            table_legenda = pending_table_legenda
            table_fonte = pending_table_fonte
            pending_table_legenda = ""
            pending_table_fonte = ""
            in_table = True
            table_explicit = False
            continue

        if stripped.startswith("#") and buf:
            _flush_text(blocks, current_sec, buf, current_destino)
        buf.append(line)

    if in_table:
        _append_table(blocks, current_sec, table_lines, table_legenda, table_fonte, current_destino)
    _flush_text(blocks, current_sec, buf, current_destino)
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


def _section_from_heading(secoes: list[Secao], text: str):
    return _match_secao_linha(secoes, text, heading_context=True)


def _parse_docx(raw: bytes, db: Session, rel_id: int, sec_id: int) -> list[dict]:
    document = Document(BytesIO(raw))
    secoes = _secoes_taxonomia(db, rel_id)
    current_sec = db.get(Secao, sec_id)
    if not current_sec:
        return []
    current_destino = _default_destino(current_sec)
    blocks: list[dict] = []
    buf: list[str] = []
    pending_figure_idx: int | None = None
    last_media_idx: int | None = None
    pending_table_legenda = ""
    pending_table_fonte = ""

    for element in _iter_docx_blocks(document):
        if isinstance(element, Table):
            _flush_text(blocks, current_sec, buf, current_destino)
            linhas = []
            for row in element.rows:
                cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                if any(cells):
                    linhas.append(" | ".join(cells))
            _append_table(blocks, current_sec, linhas, pending_table_legenda, pending_table_fonte, current_destino)
            last_media_idx = len(blocks) - 1 if linhas else last_media_idx
            pending_table_legenda = ""
            pending_table_fonte = ""
            continue

        images = _paragraph_images(element)
        if images:
            _flush_text(blocks, current_sec, buf, current_destino)
            pending_figure_idx = None
            for image in images:
                _append_figure_placeholder(blocks, current_sec, "", "", **image, destino=current_destino)
                pending_figure_idx = len(blocks) - 1
                last_media_idx = pending_figure_idx

        text = element.text.strip()
        if not text:
            _flush_text(blocks, current_sec, buf, current_destino)
            continue

        if text.lower().startswith("fonte:") and last_media_idx is not None:
            blocks[last_media_idx]["fonte"] = text[6:].strip()
            continue

        if _FIGURA_RE.match(text):
            _flush_text(blocks, current_sec, buf, current_destino)
            legenda, fonte = _split_figura_fonte(text)
            if pending_figure_idx is not None:
                blocks[pending_figure_idx]["legenda"] = legenda
                blocks[pending_figure_idx]["fonte"] = fonte
                last_media_idx = pending_figure_idx
                pending_figure_idx = None
            else:
                _append_figure_placeholder(blocks, current_sec, legenda, fonte, destino=current_destino)
                last_media_idx = len(blocks) - 1
            continue

        if _TABELA_RE.match(text):
            _flush_text(blocks, current_sec, buf, current_destino)
            legenda, fonte = _split_tabela_fonte(text)
            if last_media_idx is not None and blocks[last_media_idx].get("tipo") == "tabela" and not blocks[last_media_idx].get("legenda"):
                blocks[last_media_idx]["legenda"] = legenda
                blocks[last_media_idx]["fonte"] = fonte
            else:
                pending_table_legenda = legenda
                pending_table_fonte = fonte
            continue

        if text.upper().startswith("[SECAO:") and text.endswith("]"):
            _flush_text(blocks, current_sec, buf, current_destino)
            current_destino = _target_section(secoes, current_sec, text[7:-1].strip())
            if current_destino.secao is not None:
                current_sec = current_destino.secao
            pending_figure_idx = None
            last_media_idx = None
            continue

        sec_from_line = _match_secao_linha(secoes, text)
        if sec_from_line:
            _flush_text(blocks, current_sec, buf, current_destino)
            current_destino = sec_from_line
            if current_destino.secao is not None:
                current_sec = current_destino.secao
            pending_figure_idx = None
            last_media_idx = None
            continue

        style = (element.style.name or "").lower() if element.style else ""
        if style.startswith("heading") or style.startswith("título"):
            sec_destino = _section_from_heading(secoes, text)
            if sec_destino:
                _flush_text(blocks, current_sec, buf, current_destino)
                current_destino = sec_destino
                if current_destino.secao is not None:
                    current_sec = current_destino.secao
                continue
            _flush_text(blocks, current_sec, buf, current_destino)
            prefix = "# " if any(x in style for x in ("1", "título 1")) else "## "
            buf.append(prefix + text)
            _flush_text(blocks, current_sec, buf, current_destino)
            continue

        heading = _normalize_heading_line(text)
        if heading:
            _flush_text(blocks, current_sec, buf, current_destino)
            buf.append(heading)
            _flush_text(blocks, current_sec, buf, current_destino)
            continue

        if "list" in style or "lista" in style:
            if buf and not all(ln.strip().startswith("-") for ln in buf):
                _flush_text(blocks, current_sec, buf, current_destino)
            buf.append("- " + text.lstrip("-•· "))
        else:
            if buf and all(ln.strip().startswith("-") for ln in buf):
                _flush_text(blocks, current_sec, buf, current_destino)
            buf.append(text)

    _flush_text(blocks, current_sec, buf, current_destino)
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
    process_id = process_start(request, "Análise de importação", f"Lendo {nome or 'arquivo enviado'}")
    raw = await arquivo.read()
    if len(raw) > 5_000_000:
        process_done(request, process_id, "Arquivo recusado", "Arquivo muito grande para importação assistida.", ok=False)
        raise HTTPException(400, detail="Arquivo muito grande para importação assistida.")
    if nome.lower().endswith(".docx"):
        process_log(request, process_id, "Extraindo parágrafos, tabelas e imagens do DOCX.")
        blocks = _parse_docx(raw, db, rel_id, sec_id)
        process_done(request, process_id, "Análise concluída", f"{len(blocks)} bloco(s) detectado(s).")
        return JSONResponse({"blocks": blocks, "total": len(blocks)})
    if nome.lower().endswith(".txt"):
        process_log(request, process_id, "Decodificando TXT e classificando blocos por seção.")
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = raw.decode("latin-1")
        blocks = _parse_import_text(texto, db, rel_id, sec_id)
        process_done(request, process_id, "Análise concluída", f"{len(blocks)} bloco(s) detectado(s).")
        return JSONResponse({"blocks": blocks, "total": len(blocks)})
    process_done(request, process_id, "Arquivo recusado", "Formato inválido para importação.", ok=False)
    raise HTTPException(400, detail="Envie um arquivo .txt ou .docx.")


@router.post("/confirmar")
async def confirmar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user, sec_atual = _check(request, db, rel_id, sec_id)
    payload = await request.json()
    blocks = payload.get("blocks") or []
    process_id = process_start(request, "Confirmação de importação", "Validando blocos selecionados.")
    selected_items = [item for item in blocks if item.get("selecionado", True)]

    structural_keys: set[tuple[str, str]] = set()
    created = 0

    # Multi-statement: criar/renomear seções, inserir Figuras+Blocos e reordenar
    # tudo em uma única transação. Caso qualquer passo falhe, revertemos para
    # evitar estado parcial (importações são uma das poucas operações que tocam
    # várias tabelas em sequência).
    with tx_session() as txdb:
        secoes_relatorio = txdb.query(Secao).filter(Secao.relatorio_id == rel_id).all()
        secoes_by_id = {sec.id: sec for sec in secoes_relatorio}
        secoes_by_numero = {sec.numero: sec for sec in secoes_relatorio}
        sec_atual_tx = txdb.get(Secao, sec_id) or sec_atual

        resolved_items: list[tuple[dict, Secao]] = []
        for item in selected_items:
            numero = str(item.get("secao_numero") or "").strip()
            titulo = str(item.get("secao_titulo") or "").strip()
            existente = secoes_by_numero.get(numero) if numero else None
            titulo_anterior = existente.titulo if existente is not None else ""
            sec = _resolver_secao_importada(
                txdb, rel_id, sec_atual_tx, user, item, secoes_by_id, secoes_by_numero
            )
            if numero and existente is None:
                structural_keys.add(("criar", numero))
            elif numero and titulo and _norm_text(titulo) != _norm_text(titulo_anterior):
                structural_keys.add(("renomear", numero))
            resolved_items.append((item, sec))

        target_ids = {sec.id for _, sec in resolved_items}
        ordem_rows = (
            txdb.query(Bloco.secao_id, Bloco.ordem)
            .filter(Bloco.secao_id.in_(target_ids))
            .all()
        ) if target_ids else []
        ordens: dict[int, int] = {}
        for secao_id, ordem_atual in ordem_rows:
            ordens[secao_id] = max(ordens.get(secao_id, 0), (ordem_atual or -1) + 1)
        process_log(request, process_id, f"{len(selected_items)} bloco(s) selecionado(s) para gravação.")

        for item, sec in resolved_items:
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
                txdb.add(fig)
                txdb.flush()
                figura_id = fig.id
            ordem = ordens.get(sec.id, 0)
            ordens[sec.id] = ordem + 1
            txdb.add(
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

        txdb.flush()
        _reordenar_secoes(txdb, rel_id)

    detalhe = f"{created} bloco(s) criado(s)."
    structural_changes = len(structural_keys)
    if structural_changes:
        detalhe += f" {structural_changes} ajuste(s) de seção aplicado(s)."
    process_done(request, process_id, "Importação concluída", detalhe)
    return JSONResponse({"created": created, "section_changes": structural_changes})
