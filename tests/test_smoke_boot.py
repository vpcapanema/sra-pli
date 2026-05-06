"""Smoke: importar app.main nao deve quebrar."""
from __future__ import annotations


def test_import_app_main():
    import app.main  # noqa: F401
    assert hasattr(app.main, "app")  # noqa: F821


def test_health_endpoint_existe():
    from app.main import app
    rotas = [r.path for r in app.routes]
    assert "/health" in rotas


def test_rate_limiter_ativo():
    from app.main import app
    from app.rate_limit import limiter
    assert app.state.limiter is limiter
