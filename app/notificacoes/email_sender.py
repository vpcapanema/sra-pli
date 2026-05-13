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
import smtplib
import uuid
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sendgrid.helpers.mail import (
    ClickTracking,
    Content,
    Email,
    Mail,
    OpenTracking,
    TrackingSettings,
    To,
)

from ..config import settings

log = logging.getLogger(__name__)


# Domínios de e-mail gratuito com DMARC p=reject — não podem ser usados como
# remetente via ESP (SendGrid, Mailgun, etc.) sem ser dropado por filtros
# corporativos (Exchange/Microsoft Defender, Gmail enterprise).
# Solução definitiva: autenticar um domínio próprio no SendGrid.
_DMARC_STRICT_DOMAINS: set[str] = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
}


def _remetente_dmarc_risk() -> str | None:
    """Avisa se o remetente usa domínio com DMARC p=reject.

    SendGrid (ou qualquer ESP) não pode enviar em nome desses domínios;
    filtros corporativos (Exchange/Defender) rejeitam silenciosamente.

    Para @outlook.com / @hotmail.com: mesmo com Single Sender Verification
    ativada no SendGrid, o DMARC do domínio de destino (Concremat) pode
    ainda bloquear. A solução 100% é autenticar um domínio próprio.
    """
    from_email = (settings.SENDGRID_FROM_EMAIL or "").strip().lower()
    if "@" not in from_email:
        return None
    domain = from_email.split("@", 1)[1]
    if domain in _DMARC_STRICT_DOMAINS:
        return (
            f"DMARC_RISK: {settings.SENDGRID_FROM_EMAIL} usa domínio com p=reject. "
            f"Emails serão dropados por filtros corporativos (Exchange/Defender). "
            f"Autentique um domínio próprio no SendGrid (Settings → Sender Authentication)."
        )
    return None


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
    "defcon_nivel1": "[SRA] ALERTA: Prazo de envio encerrado - {codigo}",
    "defcon_nivel2": "[SRA] URGENTE: Entrega atrasada - {codigo}",
    "boas_vindas": "[SRA] Bem-vindo ao Sistema de Relatórios de Atividades",
    "customizado": "[SRA] {assunto}",
    "alerta_configuravel": "[SRA] {alerta_nome}",
}

_TIPO_TEMPLATES = {
    "abertura": ("email_notificacao.html", "email_notificacao.txt"),
    "lembrete": ("email_notificacao.html", "email_notificacao.txt"),
    "ultima_chamada": ("email_notificacao.html", "email_notificacao.txt"),
    "manual": ("email_notificacao.html", "email_notificacao.txt"),
    "defcon_nivel1": ("email_defcon_nivel1.html", "email_defcon_nivel1.txt"),
    "defcon_nivel2": ("email_defcon_nivel2.html", "email_defcon_nivel2.txt"),
    "boas_vindas": ("email_boas_vindas.html", "email_boas_vindas.txt"),
    "customizado": ("email_customizado.html", "email_customizado.txt"),
    "alerta_configuravel": (
        "email_alerta_configuravel.html",
        "email_alerta_configuravel.txt",
    ),
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
    if tipo == "customizado":
        return template.format(assunto=contexto.get("assunto", "Notificação"))
    if tipo == "alerta_configuravel":
        return template.format(alerta_nome=contexto.get("alerta_nome", "Alerta"))
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
    # Headers de alta prioridade removidos - gateway da Concremat bloqueia
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


def _enviar_smtp(
    *,
    destinatario_email: str,
    destinatario_nome: str,
    assunto: str,
    html: str,
    texto: str,
) -> ResultadoEnvio:
    """Envia direto via SMTP do provedor (Outlook/Gmail).

    Usado como fallback quando o remetente é de domínio DMARC p=reject
    (gmail.com, outlook.com, etc.) — nestes casos o SendGrid seria dropado.
    """
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD
    if not all([host, user, password]):
        return ResultadoEnvio(
            False,
            None,
            "smtp_nao_configurado: definir SMTP_HOST, SMTP_USER e SMTP_PASSWORD",
            "smtp",
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = f"{settings.SENDGRID_FROM_NAME} <{settings.SENDGRID_FROM_EMAIL}>"
    msg["To"] = f"{destinatario_nome} <{destinatario_email}>"
    msg["Importance"] = "high"
    msg["X-Priority"] = "1"
    msg["X-MSMail-Priority"] = "High"

    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return ResultadoEnvio(True, None, None, "smtp")
    except Exception as exc:  # noqa: BLE001
        return ResultadoEnvio(False, None, f"smtp_exception: {exc}", "smtp")


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
        return ResultadoEnvio(False, None, f"tipo_invalido: {tipo}", modo_atual())
    aviso_dmarc = _remetente_dmarc_risk()
    if aviso_dmarc:
        log.warning("[notif] %s", aviso_dmarc)
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
            tipo,
            destinatario_email,
            assunto,
            len(html),
        )
        return ResultadoEnvio(True, message_id, None, "sandbox")

    # Fallback SMTP para domínios DMARC strict — o SendGrid não pode enviar em
    # nome de gmail.com/outlook.com sem ser dropado por filtros corporativos.
    if _remetente_dmarc_risk():
        log.info(
            "[notif/smtp] %s -> %s | %s | remetente=%s",
            tipo,
            destinatario_email,
            assunto,
            settings.SENDGRID_FROM_EMAIL,
        )
        return _enviar_smtp(
            destinatario_email=destinatario_email,
            destinatario_nome=destinatario_nome,
            assunto=assunto,
            html=html,
            texto=texto,
        )

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
