import base64
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


def render_pdf(db: Session, rel: Relatorio) -> bytes:
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
                itens = [ln.strip() for ln in (b.conteudo or "").splitlines() if ln.strip()]
                item["lista_html"] = "<ul>" + "".join(f"<li>{i}</li>" for i in itens) + "</ul>"
            blocos_render.append(item)
        secoes.append({
            "numero": sec.numero,
            "titulo": sec.titulo,
            "blocos": blocos_render,
        })

    template = _env.get_template("pdf/relatorio.html")
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
    html_str = template.render(
        rel=rel,
        secoes=secoes,
        sumario_html=sumario_html,
        hoje=date.today(),
    )
    from weasyprint import HTML  # import tardio: GTK não necessário fora do /pdf
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
    return pdf_bytes
