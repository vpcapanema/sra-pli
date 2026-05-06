"""Testa que as rotas legadas de PDF redirecionam corretamente (307).

Nao exige banco: usa TestClient do FastAPI + mocks minimos onde preciso.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app_with_pdf_routes():
    """Monta um app minimo com apenas o router de pdf e stubs de dependencias."""
    from app.routes import pdf as pdf_routes
    from app.db import get_db

    class _User:
        id = 1
        role = "admin"

    def _fake_current_user(_request, _db):
        return _User()

    app = FastAPI()
    app.include_router(pdf_routes.router)
    app.dependency_overrides[get_db] = lambda: iter([None])

    # Patch do current_user usado dentro do service
    patcher = patch("app.services.pdf.current_user", side_effect=_fake_current_user)
    patcher.start()
    return app, patcher


def test_rota_pdf_legada_redireciona_307_para_preview():
    app, patcher = _make_app_with_pdf_routes()
    try:
        client = TestClient(app, follow_redirects=False)
        r = client.get("/relatorios/42/pdf")
        assert r.status_code == 307
        assert r.headers["location"].endswith("/relatorios/42/preview")
    finally:
        patcher.stop()


def test_rota_exportar_formato_pdf_redireciona_307_para_docx():
    app, patcher = _make_app_with_pdf_routes()

    class _Rel:
        id = 42
        codigo = "X"
        versao = 1
        secoes = []

    # Mocka o carregamento do relatorio para nao precisar de DB real.
    rel_patcher = patch(
        "app.services.pdf.carregar_relatorio_com_secoes_e_blocos",
        return_value=_Rel(),
    )
    section_patcher = patch(
        "app.services.pdf._section_filter",
        return_value=None,
    )
    rel_patcher.start()
    section_patcher.start()
    try:
        client = TestClient(app, follow_redirects=False)
        r = client.get("/relatorios/42/exportar?formato=pdf&escopo=inteiro")
        assert r.status_code == 307
        loc = r.headers["location"]
        assert "formato=docx" in loc
        assert "escopo=inteiro" in loc
    finally:
        section_patcher.stop()
        rel_patcher.stop()
        patcher.stop()


def test_rota_exportar_assinatura_redireciona_307_para_docx():
    app, patcher = _make_app_with_pdf_routes()
    try:
        client = TestClient(app, follow_redirects=False)
        r = client.get("/relatorios/42/exportar-assinatura")
        assert r.status_code == 307
        loc = r.headers["location"]
        assert "formato=docx" in loc
        assert "escopo=inteiro" in loc
    finally:
        patcher.stop()
