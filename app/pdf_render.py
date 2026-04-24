import base64
import html as _html
import re
from datetime import date
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from .models import Relatorio, Figura

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _figura_data_uri(fig: Figura) -> str:
    b64 = base64.b64encode(fig.dados).decode("ascii")
    return f"data:{fig.mime};base64,{b64}"


_RE_FIGURA = re.compile(r"\[\[FIGURA:([^\|\]]+)(?:\|([^\|\]]+))?(?:\|([^\|\]]+))?(?:\|([^\]]*))?\]\]")
_RE_TABELA = re.compile(r"\[\[TABELA(?::([^\|\]]+))?(?:\|([^\|\]]+))?(?:\|([^\]]*))?\]\](.*?)\[\[/TABELA\]\]", re.DOTALL)


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=False)


def _render_tabela_html(corpo: str, legenda: str, numero, posicao: str = "S") -> str:
    linhas_brutas = [ln for ln in corpo.splitlines() if ln.strip()]

    def _is_separator(ln: str) -> bool:
        s = ln.strip()
        if not s:
            return True
        # markdown: --- | --- | ---
        if re.fullmatch(r"-{2,}(\s*\|\s*-{2,})*", s):
            return True
        # ascii art: +---+---+   ou  +===+===+
        if re.fullmatch(r"\+[-=+\s]+\+?", s):
            return True
        return False

    def _split_cells(ln: str) -> list[str]:
        s = ln.strip()
        # remove pipes externos: |a|b|c|  ->  a|b|c
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    linhas = [ln for ln in linhas_brutas if not _is_separator(ln)]
    if not linhas:
        return ""
    cab = _split_cells(linhas[0])
    corpo_linhas = [_split_cells(ln) for ln in linhas[1:]]
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
        return f'<div class="tabela">{table_html}{cap_html}</div>'
    return f'<div class="tabela">{cap_html}{table_html}</div>'


def _render_figura_html(db: Session, fig_id: int, legenda: str, numero, posicao: str = "S") -> str:
    fig = db.get(Figura, fig_id)
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
    """Converte texto bruto (com # / ## / - ) em HTML (h2/h3/ul/p)."""
    if not texto.strip():
        return ""
    linhas = texto.splitlines()
    out = []
    i = 0
    para_buf: list[str] = []

    def flush_para():
        if para_buf:
            par = " ".join(l.strip() for l in para_buf).strip()
            if par:
                out.append(f"<p>{_esc(par)}</p>")
            para_buf.clear()

    while i < len(linhas):
        ln = linhas[i]
        stripped = ln.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        m_h1 = re.match(r"^#\s+(.+)$", stripped)
        m_h2 = re.match(r"^##\s+(.+)$", stripped)
        m_li = re.match(r"^-\s+(.+)$", stripped)
        if m_h2:
            flush_para()
            out.append(f"<h3>{_esc(m_h2.group(1).strip())}</h3>")
            i += 1
        elif m_h1:
            flush_para()
            out.append(f"<h2>{_esc(m_h1.group(1).strip())}</h2>")
            i += 1
        elif m_li:
            flush_para()
            out.append("<ul>")
            while i < len(linhas):
                m = re.match(r"^-\s+(.+)$", linhas[i].strip())
                if not m:
                    break
                out.append(f"<li>{_esc(m.group(1).strip())}</li>")
                i += 1
            out.append("</ul>")
        else:
            para_buf.append(ln)
            i += 1
    flush_para()
    return "".join(out)


def _render_texto_html(db: Session, conteudo: str, fig_counter: int, tab_counter: int, sec_numero: str = ""):
    """Processa marcadores [[FIGURA:..]] e [[TABELA..]] e formatação leve.

    Retorna (html, fig_counter, tab_counter) atualizados.
    O índice exibido vem do próprio marker (que já foi composto pelo editor com
    o primeiro nível da seção, ex.: "4.1", ou um número global no modo "continuar").
    Se o marker for legado e não trouxer índice, usa contador local da seção.
    """
    if not conteudo:
        return "", fig_counter, tab_counter

    sec_top = (sec_numero or "").split(".")[0]

    def _label_local(prefix_top: str, n: int) -> str:
        return f"{prefix_top}.{n}" if prefix_top else str(n)

    # 1) Substitui tabelas (pode conter | que conflita com texto, processado primeiro)
    parts: list = []
    last = 0
    for m in _RE_TABELA.finditer(conteudo):
        parts.append(("texto", conteudo[last:m.start()]))
        idx_raw = (m.group(1) or "").strip()
        g2 = m.group(2)
        g3 = m.group(3)
        # Disambigua g2: se for "S"/"I" é a posição, senão é a legenda (formato antigo).
        if g2 in ("S", "I"):
            posicao = g2
            legenda = (g3 or "").strip()
        else:
            posicao = "S"
            legenda = (g2 or g3 or "").strip()
        corpo = m.group(4) or ""
        tab_counter += 1
        numero = idx_raw if idx_raw else _label_local(sec_top, tab_counter)
        parts.append(("html", _render_tabela_html(corpo, legenda, numero, posicao)))
        last = m.end()
    parts.append(("texto", conteudo[last:]))

    # 2) Em cada parte de texto, substitui [[FIGURA:..]] e renderiza markdown leve
    out_html: list[str] = []
    for kind, chunk in parts:
        if kind == "html":
            out_html.append(chunk)
            continue
        # Processa figuras
        sub_last = 0
        for mf in _RE_FIGURA.finditer(chunk):
            antes = chunk[sub_last:mf.start()]
            out_html.append(_render_paragrafos_e_listas(antes))
            g1 = (mf.group(1) or "").strip()
            g2 = mf.group(2)
            g3 = mf.group(3)
            g4 = mf.group(4)
            # Detecta o formato pelos grupos presentes:
            #   4 grupos: idx | id | pos(S/I) | leg
            #   3 grupos com g2 numérico: idx | id | leg                 (v2)
            #   3 grupos com g1 numérico só: id | leg                    (legado)
            fid = 0
            idx_raw = ""
            posicao = "S"
            legenda = ""
            if g4 is not None and g3 in ("S", "I"):
                idx_raw = g1
                try:
                    fid = int(g2 or "0")
                except ValueError:
                    fid = 0
                posicao = g3
                legenda = (g4 or "").strip()
            elif g3 is not None and (g2 or "").isdigit():
                idx_raw = g1
                try:
                    fid = int(g2)
                except ValueError:
                    fid = 0
                legenda = (g3 or "").strip()
            elif g2 is not None:
                # formato legado [[FIGURA:<id>|<leg>]]
                try:
                    fid = int(g1)
                except ValueError:
                    fid = 0
                legenda = (g2 or "").strip()
            else:
                try:
                    fid = int(g1)
                except ValueError:
                    fid = 0
            fig_counter += 1
            numero = idx_raw if idx_raw else _label_local(sec_top, fig_counter)
            out_html.append(_render_figura_html(db, fid, legenda, numero, posicao))
            sub_last = mf.end()
        resto = chunk[sub_last:]
        out_html.append(_render_paragrafos_e_listas(resto))

    return "".join(out_html), fig_counter, tab_counter


def _montar_contexto(db: Session, rel: Relatorio):
    secoes = []
    # Contadores por top-level da seção (ex.: tudo dentro de "4" e "4.1.2"
    # compartilham o mesmo contador, reiniciado quando muda o top-level).
    fig_by_top: dict = {}
    tab_by_top: dict = {}
    for sec in rel.secoes:
        sec_top = (sec.numero or "").split(".")[0]
        fig_counter = fig_by_top.get(sec_top, 0)
        tab_counter = tab_by_top.get(sec_top, 0)

        def _label(prefix: str, n: int) -> str:
            return f"{sec_top}.{n}" if sec_top else str(n)

        blocos_render = []
        for b in sec.blocos:
            item = {
                "tipo": b.tipo,
                "titulo": b.titulo,
                "conteudo": b.conteudo or "",
                "legenda": b.legenda,
                "fonte": b.fonte,
            }
            if b.tipo == "figura" and b.figura is not None:
                fig_counter += 1
                item["numero"] = _label("F", fig_counter)
                item["src"] = _figura_data_uri(b.figura)
            elif b.tipo == "tabela":
                tab_counter += 1
                item["numero"] = _label("T", tab_counter)
            elif b.tipo == "lista":
                # Mantém compatibilidade com blocos antigos do tipo lista pura.
                itens = [ln.strip() for ln in (b.conteudo or "").splitlines() if ln.strip()]
                # Suporta marcador "- "
                itens = [re.sub(r"^-\s+", "", it) for it in itens]
                item["lista_html"] = "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in itens) + "</ul>"
            else:  # texto (com marcadores) ou qualquer outro
                html_render, fig_counter, tab_counter = _render_texto_html(
                    db, b.conteudo or "", fig_counter, tab_counter, sec.numero
                )
                item["html"] = html_render
            blocos_render.append(item)
        fig_by_top[sec_top] = fig_counter
        tab_by_top[sec_top] = tab_counter
        secoes.append({
            "numero": sec.numero,
            "titulo": sec.titulo,
            "blocos": blocos_render,
        })
    sumario_items = []
    for s in secoes:
        nivel = s["numero"].count(".") + 1
        sumario_items.append(
            f'<li class="lvl-{nivel}"><span class="num">{s["numero"]}</span>'
            f'<span class="ttl">{s["titulo"]}</span></li>'
        )
    sumario_items.append(
        '<li class="lvl-1"><span class="num">—</span>'
        '<span class="ttl">Página de assinaturas</span></li>'
    )
    sumario_html = "<ol>" + "".join(sumario_items) + "</ol>"
    return {"rel": rel, "secoes": secoes, "sumario_html": sumario_html, "hoje": date.today()}


def render_html(db: Session, rel: Relatorio) -> str:
    template = _env.get_template("pdf/relatorio.html")
    return template.render(**_montar_contexto(db, rel))


def render_pdf(db: Session, rel: Relatorio) -> bytes:
    html_str = render_html(db, rel)
    from weasyprint import HTML  # import tardio: GTK não necessário fora do /pdf
    return HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
