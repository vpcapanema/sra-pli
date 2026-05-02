"""Envio de email do ciclo de notificações via SendGrid.

Modos de operação:

- **Real**: ``SENDGRID_API_KEY`` definido **e** ``NOTIFICAR_SANDBOX=False`` **e**
  ``NOTIFICAR_HABILITADO=True``. Envia de fato pela Web API v3 e retorna o
  ``X-Message-Id`` da resposta.
- **Sandbox**: ``SENDGRID_API_KEY`` ausente **ou** ``NOTIFICAR_SANDBOX=True``.
  Renderiza o template, valida payload, registra log estruturado mas **não**
  entrega. Retorna ``sucesso=True`` com message_id sintético ``sandbox-UUID``.
- **Desligado**: ``NOTIFICAR_HABILITADO=False``. Função vira no-op com
  ``sucesso=False, erro='kill_switch_off'``. Useful para janela de manutenção.

A escolha entre Real/Sandbox/Desligado é determinada por ``modo_atual()`` para
a UI poder exibir o status sem replicar a lógica.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sendgrid.helpers.mail import (
    ClickTracking,
    Content,
    Email,
    Header,
    Mail,
    OpenTracking,
    TrackingSettings,
    To,
)

from ..config import settings

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Assuntos por tipo de mensagem. Mantemos curtos e auto-explicativos para evitar
# truncamento na lista do cliente (mobile mostra ~50 chars).
_ASSUNTOS = {
    "abertura": "[SRA] {codigo}: relatório de {mes} aberto para envio",
    "lembrete": "[SRA] Lembrete: sua parte do {codigo} ainda pendente",
    "ultima_chamada": "[SRA] Última chamada: {codigo} fecha em breve",
    "manual": "[SRA] Ação requerida no relatório {codigo}",
}

_TIPO_TEMPLATES = {
    "abertura": ("email_notificacao.html", "email_notificacao.txt"),
    "lembrete": ("email_notificacao.html", "email_notificacao.txt"),
    "ultima_chamada": ("email_notificacao.html", "email_notificacao.txt"),
    "manual": ("email_notificacao.html", "email_notificacao.txt"),
}


@dataclass(frozen=True)
class ResultadoEnvio:
    sucesso: bool
    message_id: str | None
    erro: str | None
    modo: str  # 'real' | 'sandbox' | 'desligado'


def modo_atual() -> str:
    """Determina em que modo o envio operaria agora."""
    if not settings.NOTIFICAR_HABILITADO:
        return "desligado"
    if not settings.SENDGRID_API_KEY or settings.NOTIFICAR_SANDBOX:
        return "sandbox"
    return "real"


def _assunto_para(tipo: str, contexto: dict[str, Any]) -> str:
    template = _ASSUNTOS.get(tipo, _ASSUNTOS["manual"])
    return template.format(
        codigo=contexto.get("relatorio_codigo", "—"),
        mes=contexto.get("mes_referencia", "—"),
    )


def _renderizar(tipo: str, contexto: dict[str, Any]) -> tuple[str, str]:
    """Devolve (html, texto) renderizado para o ``tipo`` de mensagem.

    O template recebe ``tipo`` no contexto para variar saudação e CTA sem
    precisar de templates separados (mensagens 1 e 2 compartilham corpo).
    """
    html_tpl, txt_tpl = _TIPO_TEMPLATES.get(tipo, _TIPO_TEMPLATES["manual"])
    ctx = {**contexto, "tipo": tipo}
    html = _env.get_template(html_tpl).render(**ctx)
    texto = _env.get_template(txt_tpl).render(**ctx)
    return html, texto


def preview_corpo_notificacao(tipo: str, contexto: dict[str, Any]) -> tuple[str, str]:
    """Mesmo HTML/texto que iria ao SendGrid, sem SMTP — útil para inspecionar
    conteúdo real montado a partir do banco (scripts de teste ponta a ponta).
    """
    if tipo not in _ASSUNTOS:
        raise ValueError(f"tipo_invalido: {tipo}")
    return _renderizar(tipo, contexto)


def preview_assunto_notificacao(tipo: str, contexto: dict[str, Any]) -> str:
    """Assunto como na Mensagem real."""
    return _assunto_para(tipo, contexto)


def _criar_mail_sendgrid(payload: dict[str, str]) -> Mail:
    msg = Mail(
        from_email=Email(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
        to_emails=To(payload["destinatario_email"], payload["destinatario_nome"]),
        subject=payload["assunto"],
    )
    msg.add_content(Content("text/plain", payload["texto"]))
    msg.add_content(Content("text/html", payload["html"]))
    msg.add_header(Header("Importance", "high"))
    msg.add_header(Header("X-Priority", "1"))
    msg.add_header(Header("X-MSMail-Priority", "High"))
    if payload["tipo"] in ("abertura", "lembrete", "ultima_chamada"):
        msg.tracking_settings = TrackingSettings()
        msg.tracking_settings.open_tracking = OpenTracking(True)
        msg.tracking_settings.click_tracking = ClickTracking(False, False)
    return msg


def _message_id_resposta(resp: Any) -> str | None:
    try:
        return resp.headers.get("X-Message-Id")
    except Exception:  # noqa: BLE001
        return None


def _enviar_real(payload: dict[str, str]) -> ResultadoEnvio:
    """Envia via SendGrid Web API v3."""
    try:
        from sendgrid import SendGridAPIClient  # noqa: PLC0415

        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        resp = client.send(_criar_mail_sendgrid(payload))
        message_id = _message_id_resposta(resp)
        if 200 <= resp.status_code < 300:
            return ResultadoEnvio(True, message_id, None, "real")
        return ResultadoEnvio(
            False,
            message_id,
            f"sendgrid_status={resp.status_code} body={resp.body!r}",
            "real",
        )
    except Exception as exc:  # noqa: BLE001
        return ResultadoEnvio(False, None, f"sendgrid_exception: {exc}", "real")


def enviar_notificacao(
    *,
    destinatario_email: str,
    destinatario_nome: str,
    tipo: str,
    contexto: dict[str, Any],
) -> ResultadoEnvio:
    """Renderiza e envia uma notificação. Sempre retorna um ``ResultadoEnvio``,
    nunca levanta — chamador decide o que fazer com erro.
    """
    if tipo not in _ASSUNTOS:
        return ResultadoEnvio(
            False, None, f"tipo_invalido: {tipo}", modo_atual()
        )
    modo = modo_atual()
    if modo == "desligado":
        return ResultadoEnvio(False, None, "kill_switch_off", modo)

    try:
        html, texto = _renderizar(tipo, contexto)
    except Exception as exc:  # noqa: BLE001
        return ResultadoEnvio(False, None, f"render_falhou: {exc}", modo)

    assunto = _assunto_para(tipo, contexto)

    if modo == "sandbox":
        message_id = f"sandbox-{uuid.uuid4()}"
        log.info(
            "[notif/sandbox] %s -> %s | %s | %d chars html",
            tipo, destinatario_email, assunto, len(html),
        )
        return ResultadoEnvio(True, message_id, None, "sandbox")

    return _enviar_real(
        {
            "destinatario_email": destinatario_email,
            "destinatario_nome": destinatario_nome,
            "assunto": assunto,
            "html": html,
            "texto": texto,
            "tipo": tipo,
        }
    )
