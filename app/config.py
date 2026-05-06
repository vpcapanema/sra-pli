from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres real (Render). Sem fallback: a aplicação exige DATABASE_URL no .env.
    DATABASE_URL: str
    # Defaults inseguros so servem em dev; validacao abaixo bloqueia prod.
    SECRET_KEY: str = "dev-secret-change-me"
    ADMIN_EMAIL: str = "admin@concremat.local"
    ADMIN_PASSWORD: str = "admin123"
    APP_NAME: str = "SRA - Sistema de Relatórios de Atividades"
    APP_ENV: str = "development"

    # ----- Notificações mensais (SendGrid + SMTP fallback) -----
    # Sem chave o módulo opera em sandbox: monta o payload, valida, mas não
    # entrega de fato. Útil em dev/test sem custo nem risco de spam.
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "no-reply@vpc-websistemas.com.br"
    SENDGRID_FROM_NAME: str = "SRA · PLI-SP"
    # Fallback SMTP para domínios DMARC p=reject (gmail.com, outlook.com, etc).
    # Quando o remetente é desses domínios, o SendGrid não pode enviar em nome
    # deles (será dropado por filtros corporativos). Nestes casos usamos SMTP
    # direto do provedor. Preencha se usar remetente @outlook.com / @gmail.com.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""  # ex: relatorio.atividades.pli@outlook.com
    SMTP_PASSWORD: str = ""  # App Password do Outlook/Gmail
    # URL base usada nos links dos emails. Em produção: domínio do Render.
    APP_BASE_URL: str = "https://sra-pli-starter.onrender.com"
    # Limite para analise de TXT/DOCX na importacao assistida (antes da confirmacao).
    IMPORTACAO_ANALISAR_MAX_BYTES: int = 20 * 1024 * 1024
    # Kill switch global. False = nada é enviado nem registrado em
    # NotificacaoEnvio (útil para janelas de manutenção).
    NOTIFICAR_HABILITADO: bool = True
    # Forçar sandbox mesmo com SENDGRID_API_KEY presente. Use em staging.
    NOTIFICAR_SANDBOX: bool = False
    # Token compartilhado dos endpoints de cron (X-Cron-Token). Em prod use
    # uma string longa aleatória; em dev qualquer valor não-vazio basta.
    CRON_TOKEN: str = ""
    # Token simples para autenticar o Event Webhook do SendGrid. Configure no
    # Render e use na URL do webhook: /admin/sendgrid/events?token=...
    SENDGRID_EVENT_WEBHOOK_TOKEN: str = ""
    # Integração opcional com cron-job.org para exibir status real na governança.
    CRONJOB_ORG_API_KEY: str = ""
    CRONJOB_ORG_JOB_ABRIR_PERIODO: int = 7547405
    CRONJOB_ORG_JOB_LEMBRETE_D5: int = 7547406
    CRONJOB_ORG_JOB_LEMBRETE_D8: int = 7547407
    CRONJOB_ORG_JOB_ULTIMA_CHAMADA: int = 7547408
    CRONJOB_ORG_JOB_RETRY_FALHAS: int = 7547409
    # Em produção com HTTPS (ex.: Render): True para cookie de sessão com atributo Secure.
    SESSION_COOKIE_SECURE: bool = False
    # Observabilidade de erros. Sem DSN, Sentry fica off.
    SENTRY_DSN: str = ""
    # Percentual de traces amostradas (0.0 a 1.0). Em prod comece com 0.1.
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _validar_producao(s: "Settings") -> None:
    """Em APP_ENV=production, rejeita defaults inseguros no boot."""
    if (s.APP_ENV or "").strip().lower() != "production":
        return
    erros: list[str] = []
    sk = (s.SECRET_KEY or "").strip()
    sk_bad_prefixes = ("dev-", "local-", "change-me", "test-")
    if (
        not sk
        or len(sk) < 32
        or sk.lower().startswith(sk_bad_prefixes)
    ):
        erros.append(
            "SECRET_KEY em producao precisa ter >=32 chars e nao comecar "
            "com prefixos inseguros (dev-, local-, change-me, test-)"
        )
    if s.ADMIN_PASSWORD in ("", "admin123", "change-me") or len(s.ADMIN_PASSWORD) < 8:
        erros.append("ADMIN_PASSWORD em producao precisa ter >=8 chars e nao ser default")
    if not s.SESSION_COOKIE_SECURE:
        erros.append("SESSION_COOKIE_SECURE deve ser true em producao (HTTPS)")
    if erros:
        raise RuntimeError("Configuracao insegura em producao: " + "; ".join(erros))


settings = Settings()
_validar_producao(settings)
