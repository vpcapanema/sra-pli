"""Pré-visualização de UI e e-mails (rotas em ``app/routes/dev_ui.py``)."""

from __future__ import annotations

import base64
import html
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..jinja_filters import registrar_globais as _registrar_globais_jinja
from ..models import SECOES_PADRAO, Relatorio, Secao, User
from ..notificacoes.email_context_arvore import (
    arvore_secoes_padrao_para_preview,
    format_arvore_secoes_email_plaintext,
)
from ..notificacoes.email_sender import (
    preview_assunto_notificacao,
    preview_corpo_notificacao,
)
from ..notificacoes.service import _montar_contexto_email
from .pages import response_login

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)
_registrar_globais_jinja(templates.env)


_TIPOS_EMAIL_PREVIEW = frozenset({"abertura", "lembrete", "ultima_chamada"})
_TIPOS_EMAIL_ORDEM = ("abertura", "lembrete", "ultima_chamada")
_PREVIEW_EMAIL_SINGLE_PATH = "/dev/preview-email-notificacao"
_PREVIEW_RELATORIO_ID_FAKE = 22
_LABELS_TIPO_EMAIL: dict[str, str] = {
    "abertura": "Abertura do ciclo (notificação 1)",
    "lembrete": "Lembrete (notificação 2)",
    "ultima_chamada": "Última chamada (notificação 3)",
}

_PREVIEW_EMAIL_DESLIGADO_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pré-visualização de e-mail · indisponível</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem;
           background: #f4f6f9; color: #1a1a2e; line-height: 1.5; }
    main { max-width: 36rem; margin: 0 auto; background: #fff;
            padding: 1.5rem 1.75rem; border-radius: 8px;
            border: 1px solid #d5dce6; }
    code { background: #eef1f5; padding: 2px 6px; border-radius: 4px;
            font-size: 0.9em; }
    pre { background: #1c3d59; color: #e8eef5; padding: 1rem;
           border-radius: 6px; overflow: auto; font-size: 0.85rem; }
  </style>
</head>
<body>
  <main>
    <h1 style="margin-top:0;font-size:1.25rem;">Pré-visualização de e-mail desligada</h1>
    <p>
      A rota <code>/dev/preview-email-notificacao</code> só é exposta quando
      <code>APP_ENV=development</code> <strong>ou</strong> quando
      <code>SRA_MODAL_PREVIEW=1</code> está definido no ambiente.
    </p>
    <p>No arquivo <code>.env</code> (ou nas variáveis do processo), use por exemplo:</p>
    <pre>APP_ENV=development
# ou, em qualquer ambiente:
SRA_MODAL_PREVIEW=1</pre>
    <p>Reinicie o Uvicorn após alterar. Em produção, prefira manter o preview
      desligado (<code>SRA_MODAL_PREVIEW=0</code>).</p>
  </main>
</body>
</html>
"""


def modais_preview_allowed() -> bool:
    v = (os.environ.get("SRA_MODAL_PREVIEW", "") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return (getattr(settings, "APP_ENV", None) or "").lower() == "development"


def _contexto_preview_email_fake(user: Any) -> dict[str, Any]:
    """Dados fictícios coerentes com o template; URLs usam ``APP_BASE_URL``."""
    base = settings.APP_BASE_URL.rstrip("/")
    nome = (user.nome or "Destinatário").strip()
    rid = _PREVIEW_RELATORIO_ID_FAKE
    titulos = dict(SECOES_PADRAO)
    ids_por_numero = {num: 10_000 + i for i, (num, _) in enumerate(SECOES_PADRAO)}
    arvore = arvore_secoes_padrao_para_preview(rid)
    return {
        "destinatario_nome": nome,
        "relatorio_codigo": "R-MED-022 · Abril/2026",
        "relatorio_titulo": "Relatório mensal de atividades (pré-visualização)",
        "mes_referencia": "Abril/2026",
        "prazo_envio": "10/05/2026 23:59",
        "prazo_limite_conteudo_autor": "08/05/2026 23:59",
        "link_relatorio_painel": f"{base}/relatorios/{rid}",
        "link_modelos_word_ajuda": f"{base}/modelos-word-importacao",
        "link_login_sra": f"{base}/login",
        "link_painel_upload": f"{base}/painel-upload",
        "arvore_secoes_links": arvore,
        "arvore_modelos_dotx_texto": format_arvore_secoes_email_plaintext(
            arvore, apenas_dotx=True
        ),
        "minhas_secoes": [
            {
                "numero": "4.4.1",
                "titulo": titulos["4.4.1"],
                "contexto": f"4.4 {titulos['4.4']}",
                "link_upload": (
                    f"{base}/relatorios/{rid}/secoes/"
                    f"{ids_por_numero['4.4.1']}/upload-conteudo"
                ),
                "link_dotx": (
                    f"{base}/relatorios/{rid}/secoes/"
                    f"{ids_por_numero['4.4.1']}/modelo.dotx"
                ),
            },
            {
                "numero": "4.4.7",
                "titulo": titulos["4.4.7"],
                "contexto": f"4.4 {titulos['4.4']}",
                "link_upload": (
                    f"{base}/relatorios/{rid}/secoes/"
                    f"{ids_por_numero['4.4.7']}/upload-conteudo"
                ),
                "link_dotx": (
                    f"{base}/relatorios/{rid}/secoes/"
                    f"{ids_por_numero['4.4.7']}/modelo.dotx"
                ),
            },
        ],
    }


def _contexto_preview_email_db(
    db: Session, user: User, relatorio_id: int
) -> dict[str, Any] | None:
    rel = db.get(Relatorio, relatorio_id)
    if not rel:
        return None
    todas_list = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel.id)
        .order_by(Secao.ordem)
        .all()
    )
    if not todas_list:
        return None
    todas_map = {s.numero: s for s in todas_list}
    minhas = [s for s in todas_list if s.responsavel_id == user.id]
    if not minhas:
        limite = min(2, len(todas_list))
        minhas = todas_list[:limite]
    return _montar_contexto_email(  # pylint: disable=protected-access
        db,
        rel,
        user,
        minhas,
        todas_map,
    )


def _contexto_preview_email(
    db: Session, user: User, relatorio_id: int | None
) -> dict[str, Any]:
    if relatorio_id is not None:
        ctx = _contexto_preview_email_db(db, user, relatorio_id)
        if ctx is not None:
            return ctx
    return _contexto_preview_email_fake(user)


def _preview_email_query(
    *, raw: str, tipo: str, relatorio_id: int | None
) -> str:
    parts: dict[str, str] = {"raw": raw, "tipo": tipo}
    if relatorio_id is not None:
        parts["relatorio_id"] = str(relatorio_id)
    return urlencode(parts)


def _iframe_src_data_html(email_html: str) -> str:
    b64 = base64.b64encode(email_html.encode("utf-8")).decode("ascii")
    return html.escape(f"data:text/html;charset=utf-8;base64,{b64}", quote=True)


def _html_preview_shell(
    assunto: str, tipo: str, raw_url: str, html_body: str
) -> str:
    seguro_assunto = html.escape(assunto, quote=False)
    seguro_tipo = html.escape(tipo, quote=False)
    seguro_raw_url = html.escape(raw_url, quote=True)
    seguro_iframe_src = _iframe_src_data_html(html_body)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pré-visualização · E-mail SRA</title>
  <style>
    body {{ margin:0; font-family:system-ui,sans-serif; }}
    .bar {{ background:#1c3d59;color:#fff;padding:12px 16px;font-size:14px;line-height:1.45; }}
    .bar a {{ color:#9fdaff; }}
    iframe {{ width:100%; border:0; height:calc(100vh - 52px); display:block; background:#eef1f5; }}
  </style>
</head>
<body>
  <div class="bar">
    <strong>Assunto:</strong> {seguro_assunto}
    · tipo=<code>{seguro_tipo}</code>
    · <a href="{seguro_raw_url}" target="_blank" rel="noopener noreferrer">Abrir só o HTML do e-mail</a>
  </div>
  <iframe title="Corpo do e-mail" src="{seguro_iframe_src}"></iframe>
</body>
</html>
"""


def _fragmento_preview_email_por_tipo(
    tipo: str,
    scheme: str,
    netloc: str,
    ctx: dict[str, Any],
    relatorio_id: int | None,
) -> tuple[str, str]:
    html_body, _ = preview_corpo_notificacao(tipo, ctx)
    assunto = preview_assunto_notificacao(tipo, ctx)
    raw_url = (
        f"{scheme}://{netloc}{_PREVIEW_EMAIL_SINGLE_PATH}"
        f"?{_preview_email_query(raw='1', tipo=tipo, relatorio_id=relatorio_id)}"
    )
    seg_iframe_src = _iframe_src_data_html(html_body)
    seg_assunto = html.escape(assunto, quote=False)
    seg_raw = html.escape(raw_url, quote=True)
    seg_tipo = html.escape(tipo, quote=False)
    label = html.escape(_LABELS_TIPO_EMAIL[tipo], quote=False)
    nav = f'<a href="#prev-email-{tipo}">{label}</a>'
    section = f"""
  <section id="prev-email-{tipo}" style="margin-bottom:56px;scroll-margin-top:16px;">
    <h2 style="font-size:18px;color:#1c3d59;border-bottom:2px solid #d5dce6;padding-bottom:8px;margin:0 0 10px;">
      {label} <span style="font-size:14px;font-weight:400;color:#4f5d6e;">({seg_tipo})</span>
    </h2>
    <p style="margin:0 0 12px;font-size:14px;line-height:1.5;">
      <strong>Assunto:</strong> {seg_assunto}<br>
      <a href="{seg_raw}" target="_blank" rel="noopener noreferrer">Abrir só o HTML desta mensagem (nova aba)</a>
    </p>
    <iframe title="Prévia {seg_tipo}" src="{seg_iframe_src}"
      style="width:100%;border:1px solid #d5dce6;border-radius:4px;height:min(85vh,920px);display:block;background:#eef1f5;"></iframe>
  </section>
"""
    return nav, section


def _html_preview_todas_mensagens(
    request: Request,
    ctx: dict[str, Any],
    relatorio_id: int | None,
) -> str:
    scheme = request.url.scheme
    netloc = request.url.netloc
    nav_links: list[str] = []
    secoes: list[str] = []
    for tipo in _TIPOS_EMAIL_ORDEM:
        nav, sec = _fragmento_preview_email_por_tipo(
            tipo, scheme, netloc, ctx, relatorio_id
        )
        nav_links.append(nav)
        secoes.append(sec)
    nav = " · ".join(nav_links)
    corpo_secoes = "".join(secoes)
    link_uma = html.escape(
        f"{scheme}://{netloc}{_PREVIEW_EMAIL_SINGLE_PATH}", quote=True
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Pré-visualização · Todas as mensagens do ciclo</title>
  <style>
    body {{ margin:0; font-family:system-ui,sans-serif; background:#f4f6f9; color:#1a1a2e; }}
    .bar {{ background:#1c3d59;color:#fff;padding:12px 16px;font-size:14px;line-height:1.5; }}
    .bar a {{ color:#9fdaff; }}
    main {{ max-width:1280px; margin:0 auto; padding:20px 16px 48px; }}
    .lead {{ font-size:14px; margin:0 0 16px; color:#334155; }}
  </style>
</head>
<body>
  <div class="bar">
    <strong>Todas as mensagens de e-mail do ciclo</strong>
    · mesmo render de produção (<code>email_notificacao.html</code> / SendGrid)
    · <a href="{link_uma}">Só uma mensagem (troque <code>?tipo=</code>)</a>
  </div>
  <main>
    <p class="lead">
      Cada bloco abaixo corresponde a um valor de <code>tipo</code> no envio. Índice:
      {nav}
    </p>
    {corpo_secoes}
  </main>
</body>
</html>
"""


def dev_modais_previews(request: Request, db: Session):
    if not modais_preview_allowed():
        raise HTTPException(status_code=404, detail="Não disponível")
    user = current_user(request, db)
    if not user:
        return response_login(request)
    return templates.TemplateResponse(
        request,
        "complementos/dev_modais.html",
        {
            "request": request,
            "user": user,
        },
    )


def dev_preview_email_notificacao(
    request: Request,
    db: Session,
    *,
    raw: bool,
    tipo: str,
    relatorio_id: int | None,
):
    if not modais_preview_allowed():
        return HTMLResponse(
            content=_PREVIEW_EMAIL_DESLIGADO_HTML,
            status_code=200,
            media_type="text/html; charset=utf-8",
        )
    user = current_user(request, db)
    if not user:
        return response_login(request)

    if tipo not in _TIPOS_EMAIL_PREVIEW:
        raise HTTPException(status_code=400, detail="tipo inválido")

    ctx = _contexto_preview_email(db, user, relatorio_id)
    html_body, _ = preview_corpo_notificacao(tipo, ctx)
    assunto = preview_assunto_notificacao(tipo, ctx)

    if raw:
        return HTMLResponse(
            content=html_body, media_type="text/html; charset=utf-8"
        )

    qs_raw = _preview_email_query(raw="1", tipo=tipo, relatorio_id=relatorio_id)
    raw_url = (
        f"{request.url.scheme}://{request.url.netloc}"
        f"{_PREVIEW_EMAIL_SINGLE_PATH}?{qs_raw}"
    )
    shell = _html_preview_shell(assunto, tipo, raw_url, html_body)
    return HTMLResponse(content=shell, media_type="text/html; charset=utf-8")


def dev_preview_emails_notificacao_todas(
    request: Request,
    db: Session,
    *,
    relatorio_id: int | None,
):
    if not modais_preview_allowed():
        return HTMLResponse(
            content=_PREVIEW_EMAIL_DESLIGADO_HTML,
            status_code=200,
            media_type="text/html; charset=utf-8",
        )
    user = current_user(request, db)
    if not user:
        return response_login(request)

    ctx = _contexto_preview_email(db, user, relatorio_id)
    page = _html_preview_todas_mensagens(request, ctx, relatorio_id)
    return HTMLResponse(content=page, media_type="text/html; charset=utf-8")
