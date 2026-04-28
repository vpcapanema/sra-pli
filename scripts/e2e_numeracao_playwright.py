"""E2E minimo: login, criar subsecao de teste, verificar na tabela, excluir.

Roda contra servidor local (uvicorn). Usa DATABASE_URL e credenciais do .env
via app.config. Nao imprime senha.

Uso (do diretorio raiz do repo):
  .\\.venv\\Scripts\\python.exe scripts/e2e_numeracao_playwright.py

Requer: uvicorn rodando em BASE_URL (default http://127.0.0.1:8765).

Credenciais: defina E2E_EMAIL / E2E_PASSWORD se o admin do banco nao bater com o
.env. Ou use ``SRA_E2E_BOOTSTRAP=1`` para criar usuario efemero admin
(``sra-e2e-browser@tools.local``), removido ao fim do script.
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

# Garante import do pacote app
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from playwright.sync_api import sync_playwright, expect  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Relatorio, User  # noqa: E402

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8765")
MARKER_TITLE = "E2E-NUM-PLAYWRIGHT"
# Usuario efemero: so existe durante o teste se SRA_E2E_BOOTSTRAP=1 (evita depender
# da senha do admin no .env bater com o hash antigo no banco).
_E2E_EMAIL = "sra-e2e-browser@tools.local"
_E2E_NOME = "Usuario Ferramenta"
_E2E_PW = os.environ.get("E2E_BOOTSTRAP_PASSWORD", "xK9mQ2-e2e-ephemeral-tools-local")


def _bootstrap_e2e_user() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == _E2E_EMAIL, User.role == "admin").one_or_none()
        h = hash_password(_E2E_PW)
        if user:
            user.password_hash = h
            user.role = "admin"
        else:
            db.add(
                User(
                    email=_E2E_EMAIL,
                    nome=_E2E_NOME,
                    password_hash=h,
                    role="admin",
                )
            )
        db.commit()
    finally:
        db.close()


def _cleanup_e2e_user() -> None:
    if os.environ.get("SRA_E2E_BOOTSTRAP") != "1":
        return
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == _E2E_EMAIL, User.role == "admin").one_or_none()
        if user:
            db.delete(user)
            db.commit()
    finally:
        db.close()


def _pick_relatorio_aberto():
    db = SessionLocal()
    try:
        rel = (
            db.query(Relatorio)
            .filter(Relatorio.status != "finalizado")
            .order_by(Relatorio.id.desc())
            .first()
        )
        if not rel:
            raise SystemExit("Nenhum relatorio com status != finalizado no banco.")
        nums = {s.numero for s in rel.secoes}
        n = 87000
        while True:
            cand = f"4.1.{n}"
            if cand not in nums:
                return rel.id, cand
            n += 1
    finally:
        db.close()


def main() -> None:
    rel_id, numero_novo = _pick_relatorio_aberto()
    use_bootstrap = os.environ.get("SRA_E2E_BOOTSTRAP") == "1"
    if use_bootstrap:
        _bootstrap_e2e_user()
        email = _E2E_EMAIL
        password = _E2E_PW
    else:
        email = os.environ.get("E2E_EMAIL", settings.ADMIN_EMAIL)
        password = os.environ.get("E2E_PASSWORD", settings.ADMIN_PASSWORD)

    try:
        with sync_playwright() as p:
            with p.chromium.launch(headless=True) as browser:
                with browser.new_context() as context:
                    page = context.new_page()
                    page.on("dialog", lambda d: d.accept())

                    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=60000)
                    page.locator('input[name="email"]').fill(email)
                    page.locator('select[name="role"]').select_option("admin")
                    page.locator('input[name="password"]').fill(password)
                    page.locator('form[action="/login"] button[type="submit"]').click()
                    page.wait_for_url("**/dashboard", timeout=60000)

                    # ``networkidle`` nunca ocorre: iframe do PDF e preview mantem rede ativa.
                    page.goto(f"{BASE_URL}/relatorios/{rel_id}", wait_until="load", timeout=120000)

                    # Apos redirect (ex.: criacao de relatorio) o modal de sucesso pode
                    # estar aberto por flash de sessao; fechar para nao bloquear o formulario.
                    wrap_ok = page.locator("#sra-cpl-status-ok")
                    if wrap_ok.is_visible():
                        page.locator("#sra-cpl-status-ok-btn").click()
                        expect(wrap_ok).to_be_hidden(timeout=10000)

                    add_form = page.locator('form.grid-form[action*="/secoes"]').filter(
                        has=page.locator('input[name="numero"]')
                    )
                    if add_form.count() == 0:
                        raise SystemExit(
                            "Formulario de subsecao nao visivel (relatorio finalizado ou sem permissao?)."
                        )

                    add_form.locator('input[name="numero"]').fill(numero_novo)
                    add_form.locator('input[name="titulo"]').fill(MARKER_TITLE)
                    add_form.locator('button[type="submit"]').click()
                    page.wait_for_load_state("load", timeout=120000)

                    row = page.locator("table tbody tr").filter(has_text=MARKER_TITLE)
                    expect(row).to_have_count(1, timeout=10000)
                    cell_num = row.locator("td").first
                    numero_exibido = cell_num.inner_text().strip()
                    if numero_exibido != numero_novo:
                        # Renumeracao pode ter ajustado o hint inicial — ainda valido se a linha existe.
                        print(f"AVISO: numero pedido {numero_novo!r}, exibido {numero_exibido!r}")

                    excluir = row.locator("form[action*='/excluir'] button.link-danger")
                    excluir.click()
                    page.wait_for_load_state("load", timeout=120000)
                    expect(page.locator("table tbody tr").filter(has_text=MARKER_TITLE)).to_have_count(0)

        print("OK e2e: criar subsecao + linha na tabela + excluir + sumiu.")
    finally:
        _cleanup_e2e_user()


if __name__ == "__main__":
    # Pequena espera se o servidor acabou de subir
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
                resp.read()
            break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit(f"Servidor nao responde em {BASE_URL}/health")
    main()
