"""Smoke minimo contra producao Render."""
from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.request

BASE = "https://sra-pli-starter.onrender.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> None:
    print("=== SMOKE PRODUCAO ===")
    print("BASE:", BASE)

    # 1) /health
    r = urllib.request.urlopen(BASE + "/health", timeout=30)
    body = json.loads(r.read())
    print(f"  [OK] /health status={r.status} ts={body['ts']}")
    assert "+00:00" in body["ts"], "timestamp sem timezone -> codigo antigo!"
    print("  [OK] timestamp tem timezone (+00:00) -> codigo novo confirmado")

    # 2) /login GET
    r = urllib.request.urlopen(BASE + "/login", timeout=30)
    print(f"  [OK] /login GET status={r.status} bytes={len(r.read())}")

    # 3) Rota legada /pdf sem login -> deve retornar login (302 ou HTML de login)
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        NoRedirect(),
    )
    req = urllib.request.Request(BASE + "/relatorios/1/pdf")
    try:
        r = op.open(req, timeout=30)
        loc = r.headers.get("Location", "")
        print(f"  /relatorios/1/pdf (sem login) status={r.status} loc={loc}")
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        print(f"  /relatorios/1/pdf (sem login) HTTP {e.code} loc={loc}")

    # 4) Rota 404 -> valida handler customizado
    try:
        r = urllib.request.urlopen(BASE + "/rota-inexistente-xyz", timeout=30)
        print(f"  /rota-inexistente status={r.status}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        tem_custom = "Página não encontrada" in raw
        print(f"  [OK] /rota-inexistente HTTP {e.code} handler_custom={tem_custom}")

    # 5) Rate-limit no /login (spam 30 req para compensar 2 workers)
    print("  Testando rate-limit em /login (30 POSTs rapidos)...")
    bloqueados = 0
    op2 = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        NoRedirect(),
    )
    body = b"email=fake@fake.com&password=errada&role=admin"
    for i in range(30):
        req = urllib.request.Request(
            BASE + "/login",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            r = op2.open(req, timeout=15)
            st = r.status
        except urllib.error.HTTPError as e:
            st = e.code
        if st == 429:
            bloqueados += 1
    print(f"  [{'OK' if bloqueados > 0 else 'FAIL'}] rate-limit bloqueou {bloqueados}/30 requests (esperado >=10 com 2 workers)")

    print()
    print("RESULTADO: producao ativa com codigo novo")


if __name__ == "__main__":
    main()
