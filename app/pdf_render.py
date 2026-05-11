import base64
import html as _html
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from .models import Relatorio, Figura
from . import ref_resolve
from . import sra_rich_html as srh
from .html_sanitize import sanitize_pdf_html_fragment as _sanitize_pdf_html_fragment
from .list_lines import split_markdown_pipe_row_cells


_RE_TABLE_SEP_MD = re.compile(r"\|?\s*:?-{2,}:?(\s*\|\s*:?-{2,}:?)*\s*\|?")
_RE_TABLE_SEP_ASCII = re.compile(r"\+[-=+\s]+\+?")


@dataclass(frozen=True)
class _RenderCtx:
    """Contexto imutavel compartilhado por todas as chamadas de render dentro
    de um relatorio: cache de figuras (carregado uma vez) e mapas de
    referencias estaveis. Mantem assinaturas das funcoes de render curtas.
    """

    figuras_by_id: dict[int, "Figura"] = field(default_factory=dict)
    mapas: ref_resolve.MapasRef = field(default_factory=ref_resolve.MapasRef)


TEMPLATES_DIR = Path(__file__).parent / "templates"
PROJECT_DIR = Path(__file__).resolve().parents[1]
MODELO_DOCX = PROJECT_DIR / "modelos_consorcio" / "MODELOS" / "Modelo_Capa&Relatorio.docx"
PDF_COVER_IMAGE = PROJECT_DIR / "app" / "static" / "pdf" / "capa_relatorio_entregue.jpg"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _figura_data_uri(fig: Figura) -> str:
    b64 = base64.b64encode(fig.dados).decode("ascii")
    return f"data:{fig.mime};base64,{b64}"


_ASSET_CACHE: dict[str, str] = {}


def _modelo_asset_data_uri(asset_name: str) -> str:
    cached = _ASSET_CACHE.get(asset_name)
    if cached is not None:
        return cached
    try:
        with ZipFile(MODELO_DOCX) as archive:
            data = archive.read(f"word/media/{asset_name}")
    except (FileNotFoundError, KeyError):
        _ASSET_CACHE[asset_name] = ""
        return ""
    b64 = base64.b64encode(data).decode("ascii")
    uri = f"data:image/png;base64,{b64}"
    _ASSET_CACHE[asset_name] = uri
    return uri


def _file_asset_data_uri(path: Path, mime: str) -> str:
    cache_key = f"file:{path}"
    cached = _ASSET_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        _ASSET_CACHE[cache_key] = ""
        return ""
    b64 = base64.b64encode(data).decode("ascii")
    uri = f"data:{mime};base64,{b64}"
    _ASSET_CACHE[cache_key] = uri
    return uri


def _produto_codigo_capa(codigo: str | None) -> str:
    match = re.search(r"D20[-\s]*(\d+)", codigo or "", re.IGNORECASE)
    if match:
        return f"D-20 - {match.group(1)}"
    return (codigo or "").replace("-", " - ")


_RE_FIGURA = re.compile(r"\[\[FIGURA:([^\|\]]+)(?:\|([^\|\]]+))?(?:\|([^\|\]]+))?(?:\|([^\]]*))?\]\]")
_RE_TABELA = re.compile(
    r"\[\[TABELA(?::([^\|\]]+))?(?:\|([^\|\]]+))?(?:\|([^\]]*))?\]\](.*?)\[\[/TABELA\]\]", re.DOTALL
)


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=False)


def _render_tabela_inner_html(corpo: str, legenda: str, numero, posicao: str = "S") -> str:
    """Renderiza apenas o miolo: legenda e corpo tabular, sem a envoltura .tabela (wrapper)."""
    linhas_brutas = [ln for ln in (corpo or "").splitlines() if ln.strip()]

    def _is_separator(ln: str) -> bool:
        s = ln.strip()
        if not s:
            return True
        # Linha de separador markdown: ---, ---|---, |---|---|, com `:` opcional
        # para alinhamento (`|:---:|---:|`).
        if _RE_TABLE_SEP_MD.fullmatch(s):
            return True
        # ascii art: +---+---+   ou  +===+===+
        if _RE_TABLE_SEP_ASCII.fullmatch(s):
            return True
        return False

    linhas = [ln for ln in linhas_brutas if not _is_separator(ln)]
    if not linhas:
        return ""
    cab = split_markdown_pipe_row_cells(linhas[0])
    corpo_linhas = [split_markdown_pipe_row_cells(ln) for ln in linhas[1:]]
    if legenda:
        cap_html = f'<div class="cap">Tabela {numero} — {_esc(legenda)}</div>'
    else:
        cap_html = f'<div class="cap">Tabela {numero}</div>'
    tab_parts = ["<table><thead><tr>"]
    for c in cab:
        tab_parts.append(f"<th>{_esc(c)}</th>")
    tab_parts.append("</tr></thead><tbody>")
    for row in corpo_linhas:
        tab_parts.append("<tr>")
        for c in row:
            tab_parts.append(f"<td>{_esc(c)}</td>")
        tab_parts.append("</tr>")
    tab_parts.append("</tbody></table>")
    table_html = "".join(tab_parts)
    if posicao == "I":
        return f"{table_html}{cap_html}"
    return f"{cap_html}{table_html}"


def _render_tabela_html(corpo: str, legenda: str, numero, posicao: str = "S") -> str:
    inner = _render_tabela_inner_html(corpo, legenda, numero, posicao)
    if not inner:
        return ""
    return f'<div class="tabela">{inner}</div>'


def _render_figura_html(figuras_by_id: dict[int, Figura], fig_id: int, legenda: str, numero, posicao: str = "I") -> str:
    fig = figuras_by_id.get(fig_id)
    if fig is None:
        return f'<p class="empty-section">[Figura #{fig_id} não encontrada]</p>'
    src = _figura_data_uri(fig)
    cap = f"Figura {numero}"
    if legenda:
        cap += f" — {_esc(legenda)}"
    cap_html = f'<div class="cap">{cap}</div>'
    img_html = f'<img src="{src}" alt="">'
    if posicao == "I":
        return f'<div class="figura">{img_html}{cap_html}</div>'
    return f'<div class="figura">{cap_html}{img_html}</div>'


def _render_paragrafos_e_listas(texto: str) -> str:
    """Converte texto bruto (títulos #/##, listas com vários marcadores) em HTML."""
    from .list_lines import mixed_texto_paragrafos_e_listas_to_html

    return mixed_texto_paragrafos_e_listas_to_html(texto)


def _figura_ids_no_texto(conteudo: str) -> set[int]:
    ids: set[int] = set()
    for mf in _RE_FIGURA.finditer(conteudo or ""):
        g1 = (mf.group(1) or "").strip()
        g2 = mf.group(2)
        g3 = mf.group(3)
        g4 = mf.group(4)
        raw_id = ""
        if g4 is not None and g3 in ("S", "I"):
            raw_id = g2 or ""
        elif g3 is not None and (g2 or "").isdigit():
            raw_id = g2 or ""
        else:
            raw_id = g1
        if raw_id.isdigit():
            ids.add(int(raw_id))
    return ids


def _label_secao(sec_top: str, n: int) -> str:
    """Rótulo PLI alinhado a ``ref_resolve.label_numero_pli``."""
    return ref_resolve.label_numero_pli(sec_top, n)


def _idx_efetivo(idx_raw: str, derivado: str) -> str:
    """Delega a ``ref_resolve.idx_efetivo_marcador`` (ver docstring lá)."""
    return ref_resolve.idx_efetivo_marcador(idx_raw, derivado)


def _safe_int(valor: str | None) -> int:
    """``int(valor)`` tolerante: vazio/invalido vira 0 sem propagar excecao."""
    try:
        return int((valor or "").strip())
    except ValueError:
        return 0


def _parse_figura_marker(match: re.Match) -> tuple[str, int, str, str]:
    """Decompoe ``[[FIGURA:..]]`` em ``(idx_raw, fid, posicao, legenda)``.

    Suporta os tres formatos historicamente emitidos pela UI:
      - ``idx | id | pos(S/I) | leg`` (atual)
      - ``idx | id | leg`` (v2: id numerico em g2)
      - ``id | leg`` (legado)
    """
    g1 = (match.group(1) or "").strip()
    g2 = match.group(2)
    g3 = match.group(3)
    g4 = match.group(4)
    if g4 is not None and g3 in ("S", "I"):
        return g1, _safe_int(g2), g3, (g4 or "").strip()
    if g3 is not None and (g2 or "").isdigit():
        return g1, _safe_int(g2), "I", (g3 or "").strip()
    if g2 is not None:
        return "", _safe_int(g1), "I", (g2 or "").strip()
    return "", _safe_int(g1), "I", ""


def _parse_tabela_marker(match: re.Match) -> tuple[str, str, str, str]:
    """Decompoe ``[[TABELA:..]]..[[/TABELA]]`` em ``(idx_raw, posicao, legenda, corpo)``."""
    idx_raw = (match.group(1) or "").strip()
    g2 = match.group(2)
    g3 = match.group(3)
    if g2 in ("S", "I"):
        posicao = g2
        legenda = (g3 or "").strip()
    else:
        posicao = "I"
        legenda = (g2 or g3 or "").strip()
    return idx_raw, posicao, legenda, match.group(4) or ""


def _render_texto_html(  # pylint: disable=too-many-locals
    ctx: _RenderCtx,
    conteudo: str,
    fig_counter: int,
    tab_counter: int,
    sec_numero: str = "",
):
    """Processa marcadores [[FIGURA:..]], [[TABELA..]], [[REF:..]] e markdown leve.

    Retorna ``(html, fig_counter, tab_counter)`` atualizados.

    Convencao de numeracao em ``[[FIGURA:idx|...]]`` / ``[[TABELA:idx|...]]``:
      - ``idx`` formado so por algarismos (ex.: ``5``): sequencial global -- preservado.
      - qualquer outro (vazio, ``4.1``, ``4-1``, ...): numero derivado
        ``capitulo.sequencia`` pelo contador da secao (``idx_efetivo_marcador``).

    Marcadores ``[[REF:..]]`` sao resolvidos antes do processamento usando
    os mapas estaveis em ``ctx.mapas``.
    """
    if not conteudo:
        return "", fig_counter, tab_counter

    if not ctx.mapas.vazio():
        conteudo = ref_resolve.resolver_referencias(conteudo, ctx.mapas)

    rich = srh.is_rich_html_storage(conteudo)
    conteudo_corpo = srh.storage_body(conteudo) if rich else conteudo

    def _text_chunk_para_html(chunk: str) -> str:
        if rich:
            return srh.sanitize_rich_html_for_pdf(chunk)
        return _render_paragrafos_e_listas(chunk)

    sec_top = (sec_numero or "").split(".")[0]

    parts: list = []
    last = 0
    for m in _RE_TABELA.finditer(conteudo_corpo):
        parts.append(("texto", conteudo_corpo[last : m.start()]))
        idx_raw, posicao, legenda, corpo = _parse_tabela_marker(m)
        tab_counter += 1
        numero = _idx_efetivo(idx_raw, _label_secao(sec_top, tab_counter))
        parts.append(("html", _render_tabela_html(corpo, legenda, numero, posicao)))
        last = m.end()
    parts.append(("texto", conteudo_corpo[last:]))

    out_html: list[str] = []
    for kind, chunk in parts:
        if kind == "html":
            out_html.append(chunk)
            continue
        sub_last = 0
        for mf in _RE_FIGURA.finditer(chunk):
            out_html.append(_text_chunk_para_html(chunk[sub_last : mf.start()]))
            idx_raw, fid, posicao, legenda = _parse_figura_marker(mf)
            fig_counter += 1
            numero = _idx_efetivo(idx_raw, _label_secao(sec_top, fig_counter))
            out_html.append(_render_figura_html(ctx.figuras_by_id, fid, legenda, numero, posicao))
            sub_last = mf.end()
        out_html.append(_text_chunk_para_html(chunk[sub_last:]))

    return "".join(out_html), fig_counter, tab_counter


def _render_bloco_item(
    bloco,
    ctx: _RenderCtx,
    contadores: dict[str, int],
    sec_top: str,
    sec_numero: str,
    sec_titulo: str,
) -> dict:
    """Renderiza um unico bloco em sua representacao de template, atualizando
    ``contadores`` (chaves ``"fig"``/``"tab"``) in-place. Centraliza a logica
    para manter ``_montar_contexto`` enxuto e legivel.
    """
    legenda = ref_resolve.resolver_referencias(bloco.legenda, ctx.mapas) if bloco.legenda else bloco.legenda
    # Marcadores estruturais ([[FIGURA:..]], [[TABELA..]], [[REF:..]]) são
    # *consumidos* no render — editar inline o HTML resolvido e salvar de
    # volta destruiria a relação com figuras/tabelas/referências. A página
    # de Revisão editorial usa esta flag para vetar Quill nesses blocos e
    # apontar o usuário para o Editor de Conteúdo.
    bruto = bloco.conteudo or ""
    tem_marcador_estrutural = "[[FIGURA:" in bruto or "[[TABELA" in bruto or "[[REF:" in bruto
    editavel_inline = bloco.tipo in ("texto", "lista") and not tem_marcador_estrutural
    titulo_bloco = bloco.titulo
    if _normalizar_titulo(titulo_bloco) == _normalizar_titulo(sec_titulo):
        titulo_bloco = None
    item: dict = {
        "bloco_id": bloco.id,
        "tipo": bloco.tipo,
        "titulo": titulo_bloco,
        "conteudo": bruto,
        "legenda": legenda,
        "fonte": bloco.fonte,
        "bloqueado": bool(getattr(bloco, "bloqueado", False)),
        "editavel_inline": editavel_inline,
        "tem_marcador_estrutural": tem_marcador_estrutural,
    }

    def _label(n: int) -> str:
        return ref_resolve.label_numero_pli(sec_top, n)

    if bloco.tipo == "figura":
        contadores["fig"] += 1
        item["numero"] = _label(contadores["fig"])
        fig = ctx.figuras_by_id.get(bloco.figura_id) if bloco.figura_id else None
        item["src"] = _figura_data_uri(fig) if fig is not None else None
    elif bloco.tipo == "tabela":
        contadores["tab"] += 1
        item["numero"] = _label(contadores["tab"])
        item["tabela_html"] = _render_tabela_inner_html(bloco.conteudo or "", legenda or "", item["numero"], "S")
    elif bloco.tipo == "lista":
        from .list_lines import list_text_to_html

        bruto = ref_resolve.resolver_referencias(bloco.conteudo or "", ctx.mapas)
        if srh.is_rich_html_storage(bruto):
            item["lista_html"] = srh.sanitize_rich_html_for_pdf(srh.storage_body(bruto))
        else:
            item["lista_html"] = _sanitize_pdf_html_fragment(list_text_to_html(bruto) or "")
    else:
        html_render, contadores["fig"], contadores["tab"] = _render_texto_html(
            ctx,
            bloco.conteudo or "",
            contadores["fig"],
            contadores["tab"],
            sec_numero,
        )
        if srh.is_rich_html_storage(bloco.conteudo or ""):
            item["html"] = _remover_titulo_inicial_duplicado(html_render, sec_titulo)
        else:
            item["html"] = _remover_titulo_inicial_duplicado(_sanitize_pdf_html_fragment(html_render), sec_titulo)
    return item


def _normalizar_titulo(valor: str | None) -> str:
    texto = re.sub(r"<[^>]+>", " ", valor or "")
    texto = _html.unescape(texto)
    texto = re.sub(r"^\s*#+\s*", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip().casefold()
    return texto


def _remover_titulo_inicial_duplicado(html_fragment: str, sec_titulo: str) -> str:
    if not html_fragment:
        return html_fragment
    padrao = re.compile(r"^\s*<(h[1-6]|p)\b[^>]*>(.*?)</\1>\s*", re.IGNORECASE | re.DOTALL)
    match = padrao.match(html_fragment)
    if not match:
        return html_fragment
    if _normalizar_titulo(match.group(2)) != _normalizar_titulo(sec_titulo):
        return html_fragment
    return html_fragment[match.end() :]


def _preview_sheet_groups(secoes: list[dict]) -> list[list[dict]]:
    """Agrupa seções para folhas na pré-visualização em ecrã (nível 1 = nova folha)."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for sec in secoes:
        num = sec.get("numero") or ""
        nivel = num.count(".") + 1
        if nivel == 1 and current:
            groups.append(current)
            current = [sec]
        else:
            current.append(sec)
    if current:
        groups.append(current)
    return groups


def _montar_contexto(  # pylint: disable=too-many-locals
    db: Session,
    rel: Relatorio,
    section_ids: set[int] | None = None,
    preview_context: str = "default",
    bloco_ids: list[int] | None = None,
):
    figura_ids: set[int] = set()
    secoes_relatorio = [sec for sec in rel.secoes if section_ids is None or sec.id in section_ids]
    for sec in secoes_relatorio:
        blocos_filtrados = sec.blocos
        if bloco_ids:
            blocos_filtrados = [b for b in sec.blocos if b.id in bloco_ids]
        for b in blocos_filtrados:
            if b.figura_id:
                figura_ids.add(b.figura_id)
            figura_ids.update(_figura_ids_no_texto(b.conteudo or ""))
    figuras_by_id = (
        {fig.id: fig for fig in db.query(Figura).filter(Figura.id.in_(figura_ids)).all()} if figura_ids else {}
    )

    ctx = _RenderCtx(
        figuras_by_id=figuras_by_id,
        mapas=ref_resolve.calcular_mapas_referencia(secoes_relatorio),
    )

    # Contadores por top-level da secao: tudo dentro de "4" e "4.1.2"
    # compartilham o mesmo contador, reiniciado quando muda o top-level.
    secoes = []
    fig_by_top: dict[str, int] = {}
    tab_by_top: dict[str, int] = {}
    for sec in secoes_relatorio:
        sec_top = (sec.numero or "").split(".")[0]
        contadores = {
            "fig": fig_by_top.get(sec_top, 0),
            "tab": tab_by_top.get(sec_top, 0),
        }
        blocos_para_render = sec.blocos
        if bloco_ids:
            blocos_para_render = [b for b in sec.blocos if b.id in bloco_ids]
        blocos_render = [
            _render_bloco_item(b, ctx, contadores, sec_top, sec.numero, sec.titulo) for b in blocos_para_render
        ]
        fig_by_top[sec_top] = contadores["fig"]
        tab_by_top[sec_top] = contadores["tab"]
        secoes.append(
            {
                "id": sec.id,
                "numero": sec.numero,
                "titulo": sec.titulo,
                "blocos": blocos_render,
            }
        )
    sumario_items = []
    for s in secoes:
        nivel_real = s["numero"].count(".") + 1
        nivel = min(nivel_real, 3)
        classe_profundidade = " deep" if nivel_real >= 4 else ""
        sec_id = "sec-" + re.sub(r"[^0-9A-Za-z_-]+", "-", s["numero"])
        sumario_items.append(
            f'<li class="lvl-{nivel}{classe_profundidade}"><a href="#{sec_id}">'
            f'<span class="num">{s["numero"]}</span><span class="ttl">{_esc(s["titulo"])}</span>'
            f'<span class="dots"></span><span class="pg"></span></a></li>'
        )
    sumario_html = "<ol>" + "".join(sumario_items) + "</ol>"
    medicao = rel.numero_medicao or ""
    if not medicao:
        match = re.search(r"D20[-\s]*(\d+)", rel.codigo or "", re.IGNORECASE)
        medicao = match.group(1) if match else ""
    return {
        "rel": rel,
        "secoes": secoes,
        "secoes_preview_grupos": _preview_sheet_groups(secoes),
        "sumario_html": sumario_html,
        "hoje": date.today(),
        "medicao": medicao,
        "cover_bg_src": _file_asset_data_uri(PDF_COVER_IMAGE, "image/jpeg"),
        "cover_produto": _produto_codigo_capa(rel.codigo),
        "header_logos_src": _modelo_asset_data_uri("image2.png"),
        "pli_line_src": _modelo_asset_data_uri("image3.png"),
        "preview_context": preview_context,
    }


def render_html(
    db: Session,
    rel: Relatorio,
    section_ids: set[int] | None = None,
    preview_context: str = "default",
    bloco_ids: list[int] | None = None,
) -> str:
    template = _env.get_template("pdf/relatorio.html")
    return template.render(**_montar_contexto(db, rel, section_ids, preview_context, bloco_ids))
