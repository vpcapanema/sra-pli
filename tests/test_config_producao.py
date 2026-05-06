"""Smoke unitario: verifica que validacao de producao bloqueia defaults inseguros."""
from __future__ import annotations

import os
import importlib

import pytest


def _reload_config_with_env(**kwargs) -> None:
    """Recarrega app.config com variaveis de ambiente limpas."""
    for k, v in kwargs.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import app.config as cfg
    importlib.reload(cfg)


def test_config_dev_aceita_defaults():
    """Em APP_ENV != production, defaults inseguros sao aceitos."""
    _reload_config_with_env(
        APP_ENV="development",
        SECRET_KEY="dev-secret-change-me",
        ADMIN_PASSWORD="admin123",
    )
    import app.config as cfg
    assert cfg.settings.SECRET_KEY == "dev-secret-change-me"


def test_config_producao_rejeita_secret_key_default():
    """Em APP_ENV=production, SECRET_KEY default deve falhar no boot."""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _reload_config_with_env(
            APP_ENV="production",
            SECRET_KEY="dev-secret-change-me",
            ADMIN_PASSWORD="senha-forte-aleatoria-32char",
            SESSION_COOKIE_SECURE="true",
        )


def test_config_producao_rejeita_admin_password_default():
    """Em APP_ENV=production, ADMIN_PASSWORD default deve falhar no boot."""
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        _reload_config_with_env(
            APP_ENV="production",
            SECRET_KEY="chave-forte-aleatoria-32char-xyz",
            ADMIN_PASSWORD="admin123",
            SESSION_COOKIE_SECURE="true",
        )


def test_config_producao_rejeita_cookie_inseguro():
    """Em APP_ENV=production, SESSION_COOKIE_SECURE=false deve falhar."""
    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        _reload_config_with_env(
            APP_ENV="production",
            SECRET_KEY="chave-forte-aleatoria-32char-xyz",
            ADMIN_PASSWORD="senha-forte-aleatoria-32char",
            SESSION_COOKIE_SECURE="false",
        )


def test_config_producao_aceita_valores_seguros():
    """Em APP_ENV=production com valores corretos, carrega normalmente."""
    _reload_config_with_env(
        APP_ENV="production",
        SECRET_KEY="chave-forte-aleatoria-32char-xyz",
        ADMIN_PASSWORD="senha-forte-aleatoria-32char",
        SESSION_COOKIE_SECURE="true",
    )
    import app.config as cfg
    assert cfg.settings.APP_ENV == "production"
    assert cfg.settings.SESSION_COOKIE_SECURE is True


def teardown_module(_module):
    """Restaura APP_ENV=test para nao contaminar outros testes."""
    _reload_config_with_env(
        APP_ENV="test",
        SECRET_KEY="test-secret-key-nao-usar-em-producao",
        ADMIN_PASSWORD="test-admin-nao-usar",
        SESSION_COOKIE_SECURE=None,
    )
