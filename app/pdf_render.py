import base64
from datetime import date
from io import BytesIO
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS
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
            blocos_render.append(item)
        secoes.append({
            "numero": sec.numero,
            "titulo": sec.titulo,
            "blocos": blocos_render,
        })

    template = _env.get_template("pdf/relatorio.html")
    html_str = template.render(
        rel=rel,
        secoes=secoes,
        hoje=date.today(),
    )
    pdf_bytes = HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
    return pdf_bytes
