from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres real (Render). Sem fallback: a aplicação exige DATABASE_URL no .env.
    DATABASE_URL: str
    SECRET_KEY: str = "dev-secret-change-me"
    ADMIN_EMAIL: str = "admin@concremat.local"
    ADMIN_PASSWORD: str = "admin123"
    APP_NAME: str = "SRA - Sistema de Relatórios de Atividades"
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
