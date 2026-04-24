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


_RE_FIGURA = re.compile(r"\[\[FIGURA:(\d+)(?:\|([^\]]*))?\]\]")
_RE_TABELA = re.compile(r"\[\[TABELA(?:\|([^\]]*))?\]\](.*?)\[\[/TABELA\]\]", re.DOTALL)


def _esc(s: str) -> str:
    return _html.escape(s or "", quote=False)


def _render_tabela_html(corpo: str, legenda: str, numero: int) -> str:
    linhas_brutas = [ln for ln in corpo.splitlines() if ln.strip()]
    # Descarta linhas separadoras de markdown (--- | --- ...)
    linhas = [ln for ln in linhas_brutas if not re.fullmatch(r"\s*-{2,}(\s*\|\s*-{2,})*\s*", ln)]
    if not linhas:
        return ""
    cab = [c.strip() for c in linhas[0].split("|")]
    corpo_linhas = [
        [c.strip() for c in ln.split("|")] for ln in linhas[1:]
    ]
    out = ['<div class="tabela">']
    if legenda:
        out.append(f'<div class="cap">Tabela {numero} — {_esc(legenda)}</div>')
    else:
        out.append(f'<div class="cap">Tabela {numero}</div>')
    out.append("<table><thead><tr>")
    for c in cab:
        out.append(f"<th>{_esc(c)}</th>")
    out.append("</tr></thead><tbody>")
    for row in corpo_linhas:
        out.append("<tr>")
        for c in row:
            out.append(f"<td>{_esc(c)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _render_figura_html(db: Session, fig_id: int, legenda: str, numero: int) -> str:
    fig = db.get(Figura, fig_id)
    if fig is None:
        return f'<p class="empty-section">[Figura #{fig_id} não encontrada]</p>'
    src = _figura_data_uri(fig)
    cap = f"Figura {numero}"
    if legenda:
        cap += f" — {_esc(legenda)}"
    return (
        f'<div class="figura"><img src="{src}" alt="">'
        f'<div class="cap">{cap}</div></div>'
    )


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


def _render_texto_html(db: Session, conteudo: str, fig_counter: int, tab_counter: int):
    """Processa marcadores [[FIGURA:..]] e [[TABELA..]] e formatação leve.

    Retorna (html, fig_counter, tab_counter) atualizados.
    """
    if not conteudo:
        return "", fig_counter, tab_counter

    # 1) Substitui tabelas (pode conter | que conflita com texto, processado primeiro)
    parts: list = []
    last = 0
    for m in _RE_TABELA.finditer(conteudo):
        parts.append(("texto", conteudo[last:m.start()]))
        legenda = (m.group(1) or "").strip()
        corpo = m.group(2) or ""
        tab_counter += 1
        parts.append(("html", _render_tabela_html(corpo, legenda, tab_counter)))
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
            try:
                fid = int(mf.group(1))
            except ValueError:
                fid = 0
            legenda = (mf.group(2) or "").strip()
            fig_counter += 1
            out_html.append(_render_figura_html(db, fid, legenda, fig_counter))
            sub_last = mf.end()
        resto = chunk[sub_last:]
        out_html.append(_render_paragrafos_e_listas(resto))

    return "".join(out_html), fig_counter, tab_counter


def _montar_contexto(db: Session, rel: Relatorio):
    secoes = []
    fig_counter = 0
    tab_counter = 0
    for sec in rel.secoes:
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
                item["numero"] = fig_counter
                item["src"] = _figura_data_uri(b.figura)
            elif b.tipo == "tabela":
                tab_counter += 1
                item["numero"] = tab_counter
            elif b.tipo == "lista":
                # Mantém compatibilidade com blocos antigos do tipo lista pura.
                itens = [ln.strip() for ln in (b.conteudo or "").splitlines() if ln.strip()]
                # Suporta marcador "- "
                itens = [re.sub(r"^-\s+", "", it) for it in itens]
                item["lista_html"] = "<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in itens) + "</ul>"
            else:  # texto (com marcadores) ou qualquer outro
                html_render, fig_counter, tab_counter = _render_texto_html(
                    db, b.conteudo or "", fig_counter, tab_counter
                )
                item["html"] = html_render
            blocos_render.append(item)
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
