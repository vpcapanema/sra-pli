from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres real (Render). Sem fallback: a aplicação exige DATABASE_URL no .env.
    DATABASE_URL: str
    SECRET_KEY: str = "dev-secret-change-me"
    ADMIN_EMAIL: str = "admin@concremat.local"
    ADMIN_PASSWORD: str = "admin123"
    APP_NAME: str = "SRA - Sistema de Relatórios de Atividades"
    APP_ENV: str = "development"

    # ----- Notificações mensais (SendGrid) -----
    # Sem chave o módulo opera em sandbox: monta o payload, valida, mas não
    # entrega de fato. Útil em dev/test sem custo nem risco de spam.
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "no-reply@concremat.local"
    SENDGRID_FROM_NAME: str = "SRA · PLI-SP"
    # URL base usada nos links dos emails. Em produção: domínio do Render.
    APP_BASE_URL: str = "http://127.0.0.1:8001"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
