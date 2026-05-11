"""E2E test: revisão editorial — captura estado real do visualizador.

Faz login, abre /relatorios/62/revisao-edicao, espera paginação,
captura erros JS, mede dimensões das folhas, salva screenshot.
"""

from __future__ import annotations

import base64
import json

from itsdangerous import TimestampSigner
from playwright.sync_api import sync_playwright

from app.config import settings
from app.db import SessionLocal
from app.models import User

BASE = "http://127.0.0.1:8001"


def admin_session_cookie() -> str:
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.role == "admin").first()
    finally:
        db.close()
    if u is None:
        raise SystemExit("Sem admin no DB.")
    payload = {"user_id": u.id, "user_role": "admin"}
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    signer = TimestampSigner(settings.SECRET_KEY)
    return signer.sign(data).decode()


def main() -> int:
    cookie_value = admin_session_cookie()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": "session",
                    "value": cookie_value,
                    "domain": "127.0.0.1",
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()

        console: list[str] = []
        page.on(
            "console",
            lambda m: console.append(f"[{m.type}] {m.text}"),
        )
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Sanity: dashboard primeiro
        page.goto(f"{BASE}/dashboard", wait_until="domcontentloaded", timeout=20000)
        print(f"[1] dashboard url={page.url}")
        if "/login" in page.url:
            print("Cookie session inválido — login redirect")
            return 1
        page.goto(
            f"{BASE}/relatorios/62/revisao-edicao",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_selector(".rev-sheet", timeout=15000)
        page.wait_for_timeout(3500)

        info = page.evaluate(
            """
            () => {
              const sheets = Array.from(document.querySelectorAll('.rev-sheet'));
              const data = sheets.map((s, i) => ({
                idx: i,
                cls: s.className,
                orient: s.dataset.orientacao || '',
                paginated: s.dataset.revPaginated || '',
                w: s.offsetWidth,
                h: s.offsetHeight,
                sections: Array.from(s.querySelectorAll('section.secao')).map(x => x.id || x.getAttribute('data-rev-secao-numero')),
                blocos: s.querySelectorAll('.bloco').length,
              }));
              return data;
            }
            """
        )

        # Captura screenshot do scroll interno (topo)
        page.evaluate("document.querySelector('.rev-doc__scroll')?.scrollTo(0, 0)")
        page.locator(".rev-doc__scroll").screenshot(path="artifacts/revisao_top.png")
        # Verifica ORDEM das seções (numero da primeira seção de cada folha)
        ordem = page.evaluate(
            """
            () => {
              const sheets = Array.from(document.querySelectorAll('.rev-preview-root > .rev-sheet'));
              return sheets.map((s, i) => {
                const sec = s.querySelector('section.secao[data-rev-secao-numero]');
                return sec ? sec.getAttribute('data-rev-secao-numero') : '';
              });
            }
            """
        )
        first_num_por_folha = [(i, n) for i, n in enumerate(ordem) if n]
        print("\n--- Ordem das primeiras seções por folha ---")
        for i, n in first_num_por_folha[:15]:
            print(f"  folha[{i}] -> sec {n}")
        print(f"  ... ({len(first_num_por_folha)} folhas com seções)")

        # Detecta inversões de ordem
        def secnum_key(s):
            try:
                return [int(p) for p in s.split(".")]
            except Exception:
                return [0]

        inv = 0
        prev = None
        for i, n in first_num_por_folha:
            cur = secnum_key(n)
            if prev is not None and cur < prev:
                inv += 1
                print(f"  ORDEM INVERTIDA: folha[{i}] sec {n} vem após {'.'.join(map(str, prev))}")
            prev = cur
        print(f"  Total inversões de ordem: {inv}")
        # Screenshot do scroll em vários pontos
        for slug, sel in [
            ("sec1", "#sec-1"),
            ("sec3", "#sec-3"),
            ("sec4", "#sec-4"),
            ("sec4-4", "#sec-4-4"),
            ("sumario", ".rev-preview-root > .rev-sheet:nth-child(3)"),
        ]:
            try:
                page.evaluate(
                    "(s)=>document.querySelector(s)?.scrollIntoView({block:'start'})",
                    sel,
                )
                page.wait_for_timeout(250)
                page.locator(".rev-doc__scroll").screenshot(path=f"artifacts/revisao_{slug}.png")
            except Exception as e:  # noqa: BLE001
                print(f"  screenshot {slug} falhou: {e}")
        # Análise de sobreposição vertical das folhas
        layout = page.evaluate(
            """
            () => {
              const sheets = Array.from(document.querySelectorAll('.rev-preview-root > .rev-sheet'));
              return sheets.map((s, i) => {
                const r = s.getBoundingClientRect();
                return { i: i, top: r.top + (window.scrollY || 0), bottom: r.bottom + (window.scrollY || 0), h: r.height };
              });
            }
            """
        )
        overlaps = 0
        for a, b in zip(layout, layout[1:]):
            if b["top"] < a["bottom"] - 1:
                overlaps += 1
                print(
                    f"OVERLAP entre folha[{a['i']}] (bottom {a['bottom']:.1f}) e folha[{b['i']}] (top {b['top']:.1f})"
                )
        print(f"\nTotal folhas: {len(info)} | sobreposições verticais: {overlaps}")
        for s in info:
            print(
                f"  [{s['idx']}] {s['cls'][:50]!r} orient={s['orient']} "
                f"paginated={s['paginated']} {s['w']}x{s['h']}px "
                f"secs={len(s['sections'])} blocos={s['blocos']}"
            )

        if page_errors:
            print("\n--- pageerror ---")
            for e in page_errors:
                print(e)
        if console:
            print("\n--- console (últimas 30) ---")
            for line in console[-30:]:
                print(line)

        browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
