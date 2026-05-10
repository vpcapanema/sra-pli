"""Smoke HTTP contra servidor em execucao.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\_smoke_http.py
"""
from __future__ import annotations

import http.cookiejar
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.config import settings  # noqa: E402

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8001")
EMAIL = os.environ.get("E2E_EMAIL", settings.ADMIN_EMAIL)
PASSWORD = os.environ.get("E2E_PASSWORD", settings.ADMIN_PASSWORD)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(follow_redirects: bool = True) -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(cj)]
    if not follow_redirects:
        handlers.append(NoRedirect())
    op = urllib.request.build_opener(*handlers)
    op.cj = cj
    return op


def _request(op, method: str, path: str, data: bytes | None = None,
             headers: dict | None = None, allow_errors: bool = True,
             timeout: int = 15):
    url = BASE + path if path.startswith("/") else path
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        resp = op.open(req, timeout=timeout)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        if allow_errors:
            return e.code, dict(e.headers or {}), e.read()
        raise


def _login(op) -> None:
    body = urllib.parse.urlencode({
        "email": EMAIL,
        "password": PASSWORD,
        "role": "admin",
    }).encode("utf-8")
    status, _hdrs, payload = _request(
        op, "POST", "/login",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # login_submit retorna HTMLResponse 200 com location.replace("/dashboard")
    if status != 200:
        raise SystemExit(f"login falhou: status={status}")
    txt = payload.decode("utf-8", errors="replace")
    if "/dashboard" not in txt and "/painel-upload" not in txt:
        raise SystemExit(f"login falhou: sem redirect script. body={txt[:200]}")


def _first_rel_id(op) -> int | None:
    """Tenta descobrir um rel_id via dashboard (HTML)."""
    status, _, body = _request(op, "GET", "/dashboard")
    if status != 200:
        return None
    import re
    html = body.decode("utf-8", errors="replace")
    m = re.search(r"/relatorios/(\d+)(?:/preview|/editar|/revisao-edicao|\"|\?)", html)
    if m:
        return int(m.group(1))
    return None


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "XX"
    line = "  [" + mark + "] " + label
    if detail:
        line = line + " -> " + detail
    print(line)
    return ok


def main() -> int:
    print("BASE:", BASE)
    print("USER:", EMAIL)
    ok_total = True

    # 1) health
    op0 = _opener()
    status, _, body = _request(op0, "GET", "/health")
    ok_total &= check("GET /health", status == 200, f"status={status}")

    # 2) login page
    op = _opener(follow_redirects=False)
    status, _, _ = _request(op, "GET", "/login")
    ok_total &= check("GET /login", status == 200, f"status={status}")

    # 3) login
    _login(op)
    check("POST /login (sessao)", True)

    # 4) dashboard
    op2 = _opener()
    # re-login no opener que segue redirects
    _login(op2)
    status, _, body = _request(op2, "GET", "/dashboard")
    ok_total &= check("GET /dashboard", status == 200 and b"Relat" in body, f"status={status}")

    # 5) paginas autenticadas basicas
    for path in ("/usuarios", "/governanca-relatorio", "/mapa-aplicacao"):
        status, _, _ = _request(op2, "GET", path, timeout=60)
        ok_total &= check(f"GET {path}", status in (200, 204), f"status={status}")

    # 6) rotas legadas de PDF -> 307
    rel_id = _first_rel_id(op2)
    if rel_id is None:
        check("descobrir rel_id", False, "nenhum relatorio encontrado em /relatorios")
    else:
        check("descobrir rel_id", True, f"rel_id={rel_id}")

        op_nr = _opener(follow_redirects=False)
        _login(op_nr)

        # 6a) GET /relatorios/{id}/pdf  -> 307 -> /relatorios/{id}/preview
        status, hdrs, _ = _request(op_nr, "GET", f"/relatorios/{rel_id}/pdf")
        loc = hdrs.get("Location") or hdrs.get("location") or ""
        ok_total &= check(
            f"GET /relatorios/{rel_id}/pdf -> 307",
            status == 307 and f"/relatorios/{rel_id}/preview" in loc,
            f"status={status} loc={loc}",
        )

        # 6b) GET /relatorios/{id}/exportar?formato=pdf -> 307 -> formato=docx
        status, hdrs, _ = _request(
            op_nr, "GET", f"/relatorios/{rel_id}/exportar?formato=pdf&escopo=inteiro"
        )
        loc = hdrs.get("Location") or hdrs.get("location") or ""
        ok_total &= check(
            f"GET /relatorios/{rel_id}/exportar?formato=pdf -> 307",
            status == 307 and "formato=docx" in loc,
            f"status={status} loc={loc}",
        )

        # 6c) GET /relatorios/{id}/exportar-assinatura -> 307
        status, hdrs, _ = _request(op_nr, "GET", f"/relatorios/{rel_id}/exportar-assinatura")
        loc = hdrs.get("Location") or hdrs.get("location") or ""
        ok_total &= check(
            f"GET /relatorios/{rel_id}/exportar-assinatura -> 307",
            status == 307 and "formato=docx" in loc,
            f"status={status} loc={loc}",
        )

        # 7) preview A4 (HTML)
        status, hdrs, body = _request(
            op2, "GET", f"/relatorios/{rel_id}/preview", timeout=60
        )
        ctype = (hdrs.get("content-type") or hdrs.get("Content-Type") or "").lower()
        ok_total &= check(
            f"GET /relatorios/{rel_id}/preview",
            status == 200 and "text/html" in ctype,
            f"status={status} ctype={ctype}",
        )

        # 8) export DOCX (pode levar ate ~2min em relatorios grandes)
        status, hdrs, body = _request(
            op2, "GET", f"/relatorios/{rel_id}/exportar?formato=docx&escopo=inteiro",
            timeout=180,
        )
        ctype = (hdrs.get("content-type") or hdrs.get("Content-Type") or "").lower()
        is_docx = (
            status == 200
            and (
                "officedocument.wordprocessingml" in ctype
                or "application/octet-stream" in ctype
            )
            and body[:2] == b"PK"
        )
        ok_total &= check(
            f"GET /relatorios/{rel_id}/exportar?formato=docx",
            is_docx,
            f"status={status} ctype={ctype} bytes={len(body)}",
        )

    # 9) logout (POST)
    status, _hdrs, _ = _request(op2, "POST", "/logout")
    ok_total &= check("POST /logout", status in (200, 302, 303, 307), f"status={status}")

    print()
    print("RESULTADO:", "PASS" if ok_total else "FAIL")
    return 0 if ok_total else 1


if __name__ == "__main__":
    sys.exit(main())
