from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./sra.db"
    SECRET_KEY: str = "dev-secret-change-me"
    ADMIN_EMAIL: str = "admin@concremat.local"
    ADMIN_PASSWORD: str = "admin123"
    APP_NAME: str = "SRA - Sistema de Relatórios de Atividades"
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
