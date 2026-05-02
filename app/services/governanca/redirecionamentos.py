"""Redirecionamentos padronizados da governança."""
from __future__ import annotations

from urllib.parse import quote

from starlette.responses import RedirectResponse


def redirect_governanca(ok: str, relatorio_id: str | int | None = None) -> RedirectResponse:
    rid = str(relatorio_id or "").strip()
    suffix = f"?ok={ok}"
    if rid:
        suffix += f"&relatorio_id={quote(rid)}"
    return RedirectResponse(url=f"/governanca-relatorio{suffix}", status_code=303)
