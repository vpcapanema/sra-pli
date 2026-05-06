"""Rate-limit para endpoints sensiveis (login, recuperacao de senha).

Uso minimo:

    from .rate_limit import limiter, rate_limit_handler

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

Em rotas:

    @limiter.limit("5/minute")
    def login(request: Request, ...): ...

Chave: IP do cliente (X-Forwarded-For respeitado quando uvicorn roda com
--proxy-headers, o que e o caso em producao).
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        "<title>Muitas tentativas · SRA</title>"
        '<style>body{font-family:system-ui,Segoe UI,Arial,sans-serif;'
        "max-width:640px;margin:12vh auto;padding:0 24px;color:#1f2937}"
        "h1{font-size:1.5rem;margin-bottom:.5rem}"
        "p{color:#4b5563;line-height:1.5}"
        'a{color:#1d4ed8;text-decoration:none}</style></head><body>'
        "<h1>Muitas tentativas</h1>"
        "<p>Você atingiu o limite de tentativas para este recurso. "
        "Aguarde alguns instantes e tente novamente.</p>"
        '<p><a href="/login">Voltar ao login</a></p>'
        "</body></html>"
    )
    return HTMLResponse(html, status_code=429)
