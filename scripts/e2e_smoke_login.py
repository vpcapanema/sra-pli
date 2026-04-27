"""Fumo E2E: /health, login (admin de settings ou E2E_*), abertura do dashboard.

Uso:
  E2E_BASE_URL=http://127.0.0.1:8001 .\\.venv\\Scripts\\python.exe scripts/e2e_smoke_login.py
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from app.config import settings  # noqa: E402

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8001")
EMAIL = os.environ.get("E2E_EMAIL", settings.ADMIN_EMAIL)
PASSWORD = os.environ.get("E2E_PASSWORD", settings.ADMIN_PASSWORD)


def _wait_health() -> None:
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
                resp.read()
            return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"Servidor nao responde em {BASE_URL}/health")


def main() -> None:
    _wait_health()
    with sync_playwright() as p:
        with p.chromium.launch(headless=True) as browser:
            with browser.new_context() as context:
                page = context.new_page()
                page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=60000)
                page.locator('input[name="email"]').fill(EMAIL)
                page.locator('input[name="password"]').fill(PASSWORD)
                page.locator('form[action="/login"] button[type="submit"]').click()
                page.wait_for_url("**/dashboard", timeout=60000)
                expect(
                    page.get_by_role("heading", name="Relatórios mensais", exact=True)
                ).to_be_visible(timeout=10000)
    print("OK smoke: health + login + dashboard visivel.")


if __name__ == "__main__":
    main()
