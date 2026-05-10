# pylint: disable=protected-access,too-many-lines,too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
import base64
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from string import ascii_lowercase, ascii_uppercase
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..db import tx_session
from ..list_lines import (
    block_is_homogeneous_list,
    line_is_list_item,
    list_line_body,
    split_markdown_pipe_row_cells,
)
from ..models import Bloco, Figura, Secao, User
from ..numeracao import chave_numero, consolidar_referencias


VALID_TYPES = {"texto", "lista", "tabela", "figura"}
_HEADING_RE = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+){1,})(?:[.)])?\s*\S.+$")
_FIGURA_RE = re.compile(
    r"^(?:Figura|Fig\.?)\s+(?:n[\u00ba\u00b0o]?\s*)?(?:\d+(?:[-.]\d+)*[.\-]?|[-\u2013\u2014])\s*[:\u2013\u2014.\-]\s*.+",
    re.IGNORECASE,
)
_TABELA_RE = re.compile(
    r"^(?:Tabela|Tab\.?)\s+(?:n[\u00ba\u00b0o]?\s*)?(?:\d+(?:[-.]\d+)*[.\-]?|[-\u2013\u2014])\s*[:\u2013\u2014.\-]\s*.+",
    re.IGNORECASE,
)
_FONTE_RE = re.compile(r"\bFonte:\s*(.+)$", re.IGNORECASE)
_SECTION_NUMBER_RE = re.compile(r"^(?:#{1,6}\s*)?(\d+(?:\.\d+)*)(.*)$")
# Sanitiza prefixos numerados embutidos na legenda. Cobre variacoes comuns:
# "Figura 4.1 -", "Fig. 4-1:", "Figura n\u00ba 4.1.", "Tabela 4-1 \u2014".
# Apos a remocao do prefixo, a numeracao e sempre derivada no render.
_FIGURA_PREFIX_RE = re.compile(
    r"^(?:Figura|Fig\.?)\s+(?:n[\u00ba\u00b0o]?\s*)?(?:\d+(?:[-.]\d+)*[.\-]?|[-\u2013\u2014])\s*[:\u2013\u2014.\-]\s*",
    re.IGNORECASE,
)
_TABELA_PREFIX_RE = re.compile(
    r"^(?:Tabela|Tab\.?)\s+(?:n[\u00ba\u00b0o]?\s*)?(?:\d+(?:[-.]\d+)*[.\-]?|[-\u2013\u2014])\s*[:\u2013\u2014.\-]\s*",
    re.IGNORECASE,
)
_TEXT_TABLE_RE = re.compile(r"^\|?.+\|.+\|?.*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?(\s*\|\s*:?-{2,}:?)*\s*\|?$")
_ASCII_SEP_RE = re.compile(r"^\+[-=+\s]+\+?$")

# Limites de pré-visualização enviados ao frontend (Opção B do review).
# Mantemos pequenos para não inflar o JSON em arquivos grandes.
_PREVIEW_MAX_CHARS = 160
_PREVIEW_MAX_ROWS = 4
_PREVIEW_MAX_COLS = 6


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
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        raise HTTPException(403, detail="Não autorizado")
    return user, sec


def _secoes_taxonomia(db: Session, rel_id: int) -> list[Secao]:
    return db.query(Secao).filter(Secao.relatorio_id == rel_id).order_by(Secao.ordem, Secao.numero).all()


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
    return SecaoDestino(
        None, numero, f"Seção {numero}", 0.72, f"marcador [SECAO:{numero}] criará seção no relatório", "criar"
    )


def _preencher_secao_vazia_com_atual(sec_atual: Secao, blocks: list[dict]) -> list[dict]:
    """Usa a seção aberta no upload como fallback de numeração.

    Se o parser detectou algum índice compatível com a seção atual, preserva os
    índices explícitos e preenche só vazios. Se nenhum índice detectado pertence
    à seção atual/subárvore, assume que o arquivo usa numeração local/incorreta e
    sugere a seção aberta para todos os blocos extraídos.
    """
    numero_atual = (sec_atual.numero or "").strip()
    if not numero_atual:
        return blocks
    titulo_atual = sec_atual.titulo or f"Seção {numero_atual}"
    numeros_detectados = {
        str(b.get("secao_numero") or "").strip() for b in blocks if str(b.get("secao_numero") or "").strip()
    }
    tem_alinhado = any(n == numero_atual or n.startswith(numero_atual + ".") for n in numeros_detectados)
    forcar_secao_atual = bool(numeros_detectados) and not tem_alinhado
    out: list[dict] = []
    for b in blocks:
        num = str(b.get("secao_numero") or "").strip()
        if num and not forcar_secao_atual:
            out.append(b)
        else:
            nb = dict(b)
            nb["secao_numero"] = numero_atual
            nb["secao_id"] = sec_atual.id
            nb["secao_titulo"] = titulo_atual
            nb["acao_secao"] = "usar"
            nb["motivo"] = "seção atual do upload aplicada como referência"
            nb["confianca"] = max(float(nb.get("confianca") or 0), 0.9)
            out.append(nb)
    return out


def _match_secao_linha(
    secoes: list[Secao],
    text: str,
    *,
    heading_context: bool = False,
    usa_numeracao_relativa: bool = False,
    sec_base: Secao | None = None,
) -> SecaoDestino | None:
    body = re.sub(r"^#{1,6}\s*", "", text.strip())
    if not body:
        return None
    by_numero = {sec.numero.strip(): sec for sec in secoes}
    match = _SECTION_NUMBER_RE.match(body)
    if match:
        numero = match.group(1).strip()
        resto = (match.group(2) or "").strip()

        # Converte número relativo para absoluto se necessário
        if usa_numeracao_relativa and sec_base and _is_numero_relativo(numero, by_numero.keys(), sec_base):
            numero_convertido = _convert_numero_relativo(numero, sec_base)
            numero = numero_convertido
            # Se o número convertido não existe no relatório, cria SecaoDestino para criação
            if numero not in by_numero:
                return SecaoDestino(
                    None,
                    numero,
                    resto.strip() or f"Seção {numero}",
                    0.84,
                    f"seção {numero} criada a partir de posição hierárquica relativa",
                    "criar",
                )

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
            proximo = body[len(sec_numero) : len(sec_numero) + 1]
            if proximo in {"", " ", "-", "–", "—"} or (proximo and not re.match(r"[\d.]", proximo)):
                sec = by_numero[sec_numero]
                titulo = body[len(sec_numero) :].strip(" -–—\t") or sec.titulo
                acao = "renomear" if _norm_text(titulo) and _norm_text(titulo) != _norm_text(sec.titulo) else "usar"
                return SecaoDestino(
                    sec,
                    sec.numero,
                    titulo,
                    0.9,
                    f"número de seção {sec_numero} reconhecido mesmo sem espaçamento",
                    acao,
                )
        resto_norm = _norm_text(resto)
        if resto_norm and (heading_context or "." in numero or (len(numero) <= 2 and resto[:1].isupper())):
            return SecaoDestino(
                None, numero, resto.strip(), 0.84, f"seção {numero} identificada no arquivo enviado", "criar"
            )
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
            return SecaoDestino(
                best_sec,
                best_sec.numero,
                best_sec.titulo,
                best_score,
                "título parecido com uma seção real do relatório",
            )
    return None


def _usuario_pode_estruturar(user: User, sec_atual: Secao, numero: str) -> bool:
    if user.role in ("admin", "coordenador"):
        return True
    numero = (numero or "").strip()
    atual = (sec_atual.numero or "").strip()
    return bool(numero == atual or numero.startswith(atual + "."))


def _split_numero_parts(numero: str) -> list[int]:
    parts: list[int] = []
    for p in (numero or "").split("."):
        if p == "":
            continue
        try:
            parts.append(int(p))
        except ValueError:
            return []
    return parts


def sincronizar_indices_importacao(
    rel_id: int,
    sec_id: int,
    payload: dict,
    request: Request,
    db: Session,
):
    """Reaplica a numeração da pré-visualização a partir do primeiro índice informado.

    Uso: o frontend envia o valor digitado no primeiro campo ``import-secao-num-*`` e o
    snapshot atual de ``importBlocks``; o endpoint devolve a mesma lista com
    ``secao_numero`` ajustado de forma estável, preservando o deslocamento relativo.
    """
    user, sec = _check(request, db, rel_id, sec_id)

    blocks = payload.get("blocks") if isinstance(payload, dict) else None
    base_numero = str(payload.get("primeiro_numero") or "").strip() if isinstance(payload, dict) else ""
    if not blocks or not isinstance(blocks, list):
        raise HTTPException(status_code=400, detail="Payload inválido: 'blocks' obrigatório.")
    if not base_numero:
        raise HTTPException(status_code=400, detail="Informe o primeiro número de seção.")

    base_parts = _split_numero_parts(base_numero)
    if not base_parts:
        raise HTTPException(status_code=400, detail="Número de seção inválido.")

    primeiro_block = blocks[0] if blocks else {}
    origem_numero = str(primeiro_block.get("secao_numero") or "").strip()
    origem_parts = _split_numero_parts(origem_numero) or base_parts

    base_len = min(len(base_parts), len(origem_parts)) or len(base_parts)
    origem_anchor = origem_parts[base_len - 1] if len(origem_parts) >= base_len else base_parts[base_len - 1]

    mapping: dict[str, str] = {}
    for blk in blocks:
        old_raw = str(blk.get("secao_numero") or "").strip()
        old_parts = _split_numero_parts(old_raw)
        if not old_parts:
            mapping[old_raw] = base_numero
            continue
        if len(old_parts) < base_len:
            mapping[old_raw] = base_numero
            continue
        delta = old_parts[base_len - 1] - origem_anchor
        new_parts = list(base_parts)
        # Garante comprimento mínimo para posicionar o delta.
        while len(new_parts) < base_len:
            new_parts.append(1)
        new_parts[base_len - 1] = base_parts[base_len - 1] + delta
        if len(old_parts) > base_len:
            new_parts.extend(old_parts[base_len:])
        mapping[old_raw] = ".".join(str(p) for p in new_parts)

    out_blocks: list[dict] = []
    for blk in blocks:
        nb = dict(blk)
        old_raw = str(blk.get("secao_numero") or "").strip()
        nb["secao_numero"] = mapping.get(old_raw, base_numero)
        out_blocks.append(nb)

    return JSONResponse({"blocks": out_blocks, "secao_numero_atual": sec.numero})


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

    # Se a seção atual já tiver um responsável atribuído, usar esse mesmo responsável
    # para as novas seções criadas durante a importação (atribuição automática)
    # Caso contrário, usar o usuário atual como responsável
    responsavel_padrao = sec_atual.responsavel_id if sec_atual.responsavel_id else user.id

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
                responsavel_id=responsavel_padrao,
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
    if user.role == "autor" and sec.responsavel_id is not None and sec.responsavel_id != user.id:
        raise HTTPException(403, detail="Não autorizado para uma seção selecionada.")
    return sec


def _reordenar_secoes(db: Session, rel_id: int) -> None:
    secoes = db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    for ordem, sec in enumerate(sorted(secoes, key=lambda item: chave_numero(item.numero))):
        sec.ordem = ordem


def _finalizar_persistencia_importacao(txdb: Session, rel_id: int) -> None:
    """Reordena as secoes e consolida referencias textuais ("Figura 4.1",
    "Tabela 4-1", "Secao X.Y") em marcadores estaveis ``[[REF:..]]``,
    protegendo as referencias contra renumeracoes futuras. Deve rodar apos
    todos os blocos da importacao terem sido inseridos."""
    _reordenar_secoes(txdb, rel_id)
    consolidar_referencias(txdb, rel_id)


def _truncate_preview(text: str, limit: int = _PREVIEW_MAX_CHARS) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _segmentar_texto(linhas: list[str]) -> list[dict]:
    """Quebra um bloco de texto em segmentos visuais (parágrafo / subtítulo /
    título / lista) sem alterar o ``conteudo`` salvo no banco. Usado apenas
    para enriquecer o JSON de revisão da importação (Opção B do review)."""
    segs: list[dict] = []
    par_buf: list[str] = []
    list_buf: list[str] = []

    def _flush_par():
        if par_buf:
            joined = " ".join(par_buf).strip()
            segs.append({"kind": "paragrafo", "preview": _truncate_preview(joined), "count": len(par_buf)})
            par_buf.clear()

    def _flush_list():
        if list_buf:
            preview = "; ".join(list_line_body(item) for item in list_buf if item.strip())
            segs.append({"kind": "lista", "preview": _truncate_preview(preview), "count": len(list_buf)})
            list_buf.clear()

    for raw in linhas:
        line = (raw or "").strip()
        if not line:
            continue
        if line.startswith("# "):
            _flush_par()
            _flush_list()
            segs.append({"kind": "titulo", "preview": _truncate_preview(line[2:].strip()), "count": 1})
            continue
        if line.startswith("## "):
            _flush_par()
            _flush_list()
            segs.append({"kind": "subtitulo", "preview": _truncate_preview(line[3:].strip()), "count": 1})
            continue
        if line_is_list_item(raw):
            _flush_par()
            list_buf.append(raw)
            continue
        # Fim de uma lista interrompida por parágrafo.
        _flush_list()
        par_buf.append(line)

    _flush_par()
    _flush_list()
    return segs


def _is_table_separator(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    return bool(_TABLE_SEP_RE.fullmatch(s) or _ASCII_SEP_RE.fullmatch(s))


def _tabela_preview(conteudo: str) -> dict:
    """Constrói um preview compacto da tabela para o frontend renderizar como
    mini-table (Opção B). Limita a ``_PREVIEW_MAX_ROWS`` x ``_PREVIEW_MAX_COLS``
    para manter o JSON enxuto."""
    raw_lines = [ln for ln in (conteudo or "").splitlines() if ln.strip()]
    lines = [ln for ln in raw_lines if not _is_table_separator(ln)]
    if not lines:
        return {
            "headers": [],
            "rows": [],
            "total_rows": 0,
            "total_cols": 0,
            "truncated_rows": False,
            "truncated_cols": False,
        }
    cells = [split_markdown_pipe_row_cells(ln) for ln in lines]
    cols_total = max((len(r) for r in cells), default=0)
    headers_full = (cells[0] + [""] * cols_total)[:cols_total]
    rows_full = [(r + [""] * cols_total)[:cols_total] for r in cells[1:]]
    truncated_cols = cols_total > _PREVIEW_MAX_COLS
    truncated_rows = len(rows_full) > _PREVIEW_MAX_ROWS
    headers = headers_full[:_PREVIEW_MAX_COLS]
    rows = [r[:_PREVIEW_MAX_COLS] for r in rows_full[:_PREVIEW_MAX_ROWS]]
    return {
        "headers": headers,
        "rows": rows,
        "total_rows": len(rows_full),
        "total_cols": cols_total,
        "truncated_rows": truncated_rows,
        "truncated_cols": truncated_cols,
    }


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
    conteudo = "\n".join(ln for ln in linhas if ln.strip())
    block.update(
        {
            "tipo": "tabela",
            "titulo": "",
            "conteudo": conteudo,
            "legenda": legenda,
            "fonte": fonte,
            "tabela_preview": _tabela_preview(conteudo),
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
    tipo = "lista" if block_is_homogeneous_list(clean) else "texto"
    block = _block_base(sec, destino)
    block.update(
        {
            "tipo": tipo,
            "titulo": "",
            "conteudo": "\n".join(clean),
            "legenda": "",
            "fonte": "",
            "subtipos": _segmentar_texto(clean),
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


def _get_w_int_attr(p_el, local: str) -> int:
    if p_el is None:
        return 0
    ch = p_el.find(qn(f"w:{local}"))
    if ch is None:
        return 0
    a = ch.get(qn("w:val")) or ch.get("val")
    if a is None:
        return 0
    try:
        return int(a)
    except (TypeError, ValueError):
        return 0


def _get_w_numpr(paragraph: Paragraph) -> tuple[int, int] | None:
    ppr = paragraph._p.find(qn("w:pPr"))
    if ppr is None:
        return None
    numpr = ppr.find(qn("w:numPr"))
    if numpr is None:
        return None
    return _get_w_int_attr(numpr, "ilvl"), _get_w_int_attr(numpr, "numId")


def _read_numfmt_from_docx(document: Document, num_id: int, ilvl: int) -> str:
    out = "decimal"
    np = getattr(document.part, "numbering_part", None)
    if np is None:
        return out
    try:
        root = np._element
        abs_id: str | None = None
        for num in root.iter(qn("w:num")):
            a = num.get(qn("w:numId")) or num.get("numId")
            if a is not None and int(a) == int(num_id):
                an = num.find(qn("w:abstractNumId"))
                if an is not None:
                    abs_id = an.get(qn("w:val")) or an.get("val") or "0"
                break
        if abs_id is not None:
            for ab in root.iter(qn("w:abstractNum")):
                a = ab.get(qn("w:abstractNumId")) or ab.get("abstractNumId")
                if a is None or str(a) != str(abs_id):
                    continue
                for lvl in ab.iter(qn("w:lvl")):
                    li = lvl.get(qn("w:ilvl")) or lvl.get("ilvl") or "0"
                    if int(li) != int(ilvl):
                        continue
                    nfmt = lvl.find(qn("w:numFmt"))
                    if nfmt is not None:
                        v = nfmt.get(qn("w:val")) or nfmt.get("val")
                        out = (v or "decimal").lower()
                break
    except (OSError, ValueError, TypeError, AttributeError):
        out = "decimal"
    return out


def _romano_curto_m(n: int) -> str:
    if n < 1:
        return "i"
    p = 1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1
    s = "m", "cm", "d", "cd", "c", "xc", "l", "xl", "x", "ix", "v", "iv", "i"
    t, out = n, []
    for v, ch in zip(p, s):
        while t >= v:
            t -= v
            out.append(ch)
    return "".join(out)


def _word_list_canonical_line(
    text: str, ilvl: int, nfmt: str, num_id: int, counters: dict[tuple[int, int], int]
) -> str:
    nfmt = (nfmt or "decimal").lower()
    sp = "  " * int(ilvl)
    body = text.lstrip()
    if nfmt in ("bullet", "none", "symbol", "image", "picture"):
        return f"{sp}- {body}"
    key = (int(num_id), int(ilvl))
    counters[key] = counters.get(key, 0) + 1
    n = counters[key]
    if nfmt in ("decimal", "ordinal", "000"):
        line = f"{sp}{n}. {body}"
    elif nfmt in ("lowerletter", "lowletter", "lowercaseletter"):
        ch = ascii_lowercase[(n - 1) % 26] if n <= 26 else "z"
        line = f"{sp}{ch}) {body}"
    elif nfmt in ("upperletter", "uppercaseletter", "caps"):
        ch = ascii_uppercase[(n - 1) % 26] if n <= 26 else "Z"
        line = f"{sp}{ch}) {body}"
    elif nfmt in ("lowerroman", "roman"):
        line = f"{sp}{_romano_curto_m(n)}. {body}"
    elif nfmt in ("upperroman",):
        line = f"{sp}{_romano_curto_m(n).upper()}. {body}"
    else:
        line = f"{sp}{n}. {body}"
    return line


def _convert_numero_relativo(numero_relativo: str, sec_base: Secao) -> str:
    """Converte um número relativo de seção para absoluto baseado na seção base.

    Exemplo: se sec_base.numero = "4.4.8":
    - numero_relativo = "1" -> retorna "4.4.8" (seção base)
    - numero_relativo = "2" -> retorna "4.4.9" (próximo irmão)
    - numero_relativo = "3" -> retorna "4.4.10" (segundo irmão após)
    - numero_relativo = "1.1" -> retorna "4.4.8.1" (subnível da base)
    - numero_relativo = "2.1" -> retorna "4.4.9.1" (subnível do próximo irmão)

    O número relativo indica o deslocamento a partir da seção base.
    """
    if not sec_base.numero:
        return numero_relativo

    partes_base = _split_numero_parts(sec_base.numero)
    partes_relativo = _split_numero_parts(numero_relativo)

    if not partes_relativo:
        return sec_base.numero

    # Calcula o deslocamento no primeiro nível
    deslocamento = partes_relativo[0] - 1

    # Aplica o deslocamento ao último nível da base
    if partes_base:
        partes_base[-1] += deslocamento

    # Se tem múltiplos níveis (ex: "1.1", "2.1"), adiciona os níveis restantes como subníveis
    if len(partes_relativo) > 1:
        partes_base.extend(partes_relativo[1:])

    return ".".join(str(p) for p in partes_base)


def _is_numero_relativo(numero: str, secoes_existentes: set[str], sec_base: Secao | None = None) -> bool:
    """Verifica se um número de seção deve ser interpretado como posição hierárquica relativa.

    Um número é considerado relativo se não existe como seção absoluta no relatório.
    Quando uma seção base é fornecida, assume que todos os números devem ser interpretados
    como relativos à essa base (para upload em seção específica).
    """
    if not numero:
        return False

    # Se temos uma seção base, assume que todos os números são relativos
    if sec_base and sec_base.numero:
        return True

    # Se o número não existe como seção absoluta no relatório, é considerado relativo
    return numero not in secoes_existentes


def _parse_docx(raw: bytes, db: Session, rel_id: int, sec_id: int) -> list[dict]:
    document = Document(BytesIO(raw))
    secoes = _secoes_taxonomia(db, rel_id)
    current_sec = db.get(Secao, sec_id)
    if not current_sec:
        return []
    # Guarda a seção original como base fixa para conversão de números relativos
    sec_original = current_sec
    current_destino = _default_destino(current_sec)
    blocks: list[dict] = []
    buf: list[str] = []
    pending_figure_idx: int | None = None
    last_media_idx: int | None = None
    pending_table_legenda = ""
    pending_table_fonte = ""
    word_list_counters: dict[tuple[int, int], int] = {}

    # Detecta se o arquivo usa numeração relativa (começa com 1 e não existe no relatório)
    secoes_existentes = {sec.numero for sec in secoes}
    usa_numeracao_relativa = False

    # Primeira passagem para detectar numeração relativa
    for element in _iter_docx_blocks(document):
        if isinstance(element, Table):
            continue
        text = element.text.strip()
        if text:
            match = _SECTION_NUMBER_RE.match(text)
            if match:
                numero = match.group(1).strip()
                if _is_numero_relativo(numero, secoes_existentes, sec_original):
                    usa_numeracao_relativa = True
                    break

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
            if (
                last_media_idx is not None
                and blocks[last_media_idx].get("tipo") == "tabela"
                and not blocks[last_media_idx].get("legenda")
            ):
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

        sec_from_line = _match_secao_linha(
            secoes, text, usa_numeracao_relativa=usa_numeracao_relativa, sec_base=sec_original
        )
        if sec_from_line:
            _flush_text(blocks, current_sec, buf, current_destino)
            current_destino = sec_from_line
            if current_destino.secao is not None:
                current_sec = current_destino.secao
            pending_figure_idx = None
            last_media_idx = None
            continue

        w_num = _get_w_numpr(element)
        if w_num is not None:
            il, nid = w_num
            numfmt_word = _read_numfmt_from_docx(document, nid, il)
            if buf and not all(line_is_list_item(ln) for ln in buf):
                _flush_text(blocks, current_sec, buf, current_destino)
            buf.append(_word_list_canonical_line(text, il, numfmt_word, nid, word_list_counters))
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
            if buf and not all(line_is_list_item(ln) for ln in buf):
                _flush_text(blocks, current_sec, buf, current_destino)
            buf.append("- " + text.lstrip("-•· "))
        else:
            if buf and all(line_is_list_item(ln) for ln in buf):
                _flush_text(blocks, current_sec, buf, current_destino)
            buf.append(text)

    _flush_text(blocks, current_sec, buf, current_destino)
    return blocks


async def analisar_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    arquivo: UploadFile,
    db: Session,
):
    _check(request, db, rel_id, sec_id)
    raw = await arquivo.read()
    max_bytes = settings.IMPORTACAO_ANALISAR_MAX_BYTES
    if len(raw) > max_bytes:
        limite_mb = max(max_bytes // (1024 * 1024), 1)
        detail = f"Arquivo muito grande para importação assistida (máx. {limite_mb} MB)."
        raise HTTPException(400, detail=detail)
    nome = (arquivo.filename or "").lower()
    if nome.endswith(".docx"):
        blocks = _parse_docx(raw, db, rel_id, sec_id)
    elif nome.endswith(".txt"):
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = raw.decode("latin-1")
        blocks = _parse_import_text(texto, db, rel_id, sec_id)
    else:
        raise HTTPException(400, detail="Envie um arquivo .txt ou .docx.")

    # Sugere a numeração da seção atual para blocos sem número explícito.
    sec_atual = db.get(Secao, sec_id)
    if sec_atual:
        blocks = _preencher_secao_vazia_com_atual(sec_atual, blocks)

    return JSONResponse({"blocks": blocks, "total": len(blocks)})


async def preview_importacao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session,
):
    """Simula a importação sem persistir, retornando preview da estrutura resultante."""
    user, sec_atual = _check(request, db, rel_id, sec_id)
    payload = await request.json()
    blocks = payload.get("blocks") or []
    responsavel_id_enviado = payload.get("responsavel_id")
    selected_items = [item for item in blocks if item.get("selecionado") is not False]

    # Carrega seções atuais para simulação
    secoes_relatorio = db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    secoes_by_numero = {sec.numero: sec for sec in secoes_relatorio}

    # Simula criação/renomeio de seções
    secoes_simuladas = []
    novas_secoes = []
    secoes_renomeadas = []

    for item in selected_items:
        numero = str(item.get("secao_numero") or "").strip()
        titulo = str(item.get("secao_titulo") or "").strip()
        existente = secoes_by_numero.get(numero) if numero else None
        titulo_anterior = existente.titulo if existente is not None else ""

        if numero and existente is None:
            # Nova seção seria criada
            novas_secoes.append(
                {
                    "numero": numero,
                    "titulo": titulo or f"Seção {numero}",
                    "responsavel_id": int(responsavel_id_enviado) if responsavel_id_enviado else user.id,
                    "status": "em_andamento",
                    "blocos_inseridos": 1,
                }
            )
        elif numero and titulo and _norm_text(titulo) != _norm_text(titulo_anterior):
            # Seção seria renomeada
            secoes_renomeadas.append(
                {"numero": numero, "titulo_anterior": titulo_anterior, "titulo_novo": titulo, "blocos_inseridos": 1}
            )
        else:
            # Seção existente receberia blocos
            secoes_simuladas.append(
                {
                    "numero": existente.numero,
                    "titulo": existente.titulo,
                    "responsavel_id": existente.responsavel_id,
                    "status": existente.status,
                    "blocos_inseridos": 1,
                }
            )

    return JSONResponse(
        {
            "novas_secoes": novas_secoes,
            "secoes_renomeadas": secoes_renomeadas,
            "secoes_atualizadas": secoes_simuladas,
            "total_blocos": len(selected_items),
            "total_secoes_criadas": len(novas_secoes),
            "total_secoes_renomeadas": len(secoes_renomeadas),
        }
    )


def _limpar_blocos_secao_importacao(txdb: Session, sec_ids: set[int]) -> None:
    """Remove blocos (e figuras só ligadas a eles) antes de gravar a importação.

    Assim o DOCX importado substitui o conteúdo clonado do período anterior na
    mesma seção, em vez de acumular blocos duplicados."""
    if not sec_ids:
        return
    blocos = txdb.query(Bloco).filter(Bloco.secao_id.in_(sec_ids)).all()
    fig_ids = {b.figura_id for b in blocos if b.figura_id}
    for bl in blocos:
        txdb.delete(bl)
    txdb.flush()
    for fid in fig_ids:
        fig = txdb.get(Figura, fid)
        if fig:
            txdb.delete(fig)


async def confirmar_importacao(  # pylint: disable=too-many-locals,too-many-statements
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session,
):
    user, sec_atual = _check(request, db, rel_id, sec_id)
    payload = await request.json()
    blocks = payload.get("blocks") or []
    responsavel_id_enviado = payload.get("responsavel_id")
    selected_items = [item for item in blocks if item.get("selecionado") is not False]

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
            sec = _resolver_secao_importada(txdb, rel_id, sec_atual_tx, user, item, secoes_by_id, secoes_by_numero)
            if numero and existente is None:
                structural_keys.add(("criar", numero))
            elif numero and titulo and _norm_text(titulo) != _norm_text(titulo_anterior):
                structural_keys.add(("renomear", numero))
            resolved_items.append((item, sec))

        target_ids = {sec.id for _, sec in resolved_items}
        _limpar_blocos_secao_importacao(txdb, target_ids)
        ordem_rows = (
            (txdb.query(Bloco.secao_id, Bloco.ordem).filter(Bloco.secao_id.in_(target_ids)).all()) if target_ids else []
        )
        ordens: dict[int, int] = {}
        for secao_id, ordem_atual in ordem_rows:
            ordens[secao_id] = max(ordens.get(secao_id, 0), (ordem_atual or -1) + 1)

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
                    origem="upload",
                )
            )
            if sec.status == "pendente":
                sec.status = "em_andamento"
            # Se a seção existente não tem responsável, atribui o responsável selecionado no formulário
            if sec.responsavel_id is None:
                if responsavel_id_enviado:
                    try:
                        sec.responsavel_id = int(responsavel_id_enviado)
                    except (ValueError, TypeError):
                        sec.responsavel_id = user.id
                else:
                    sec.responsavel_id = user.id
            created += 1

        # Após criar todos os blocos, consolida referências textuais para marcadores estáveis
        # Isso garante que referências a figuras, tabelas e seções sejam atualizadas
        # de acordo com a nova realidade hierárquica após a conversão de números relativos
        consolidar_referencias(txdb, rel_id)

        counts = Counter(sec.id for _, sec in resolved_items)
        por_secao_rows = []
        for sid in sorted(counts.keys()):
            row_sec = txdb.get(Secao, sid)
            if row_sec:
                por_secao_rows.append(
                    {
                        "secao_id": sid,
                        "numero": row_sec.numero,
                        "titulo": row_sec.titulo,
                        "inseridos": counts[sid],
                    }
                )

        txdb.flush()
        _finalizar_persistencia_importacao(txdb, rel_id)

    structural_changes = len(structural_keys)
    return JSONResponse(
        {
            "created": created,
            "section_changes": structural_changes,
            "por_secao": por_secao_rows,
        }
    )
