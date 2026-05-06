"""Filtros e globais Jinja específicos do SRA.

Registrados nos `Jinja2Templates` das páginas HTML (ver callers em
`app/services/{auth,pages,dev_ui}.py`).
"""
from __future__ import annotations


def registrar_globais(env) -> None:
    """Globais Jinja (todas as páginas que usam este `Environment`).

    `sra_console_verbose`: com ``APP_ENV=development``, o `base.html` define
    `window.__SRA_CONSOLE_VERBOSE__` para `sra_log.js` emitir `debug`/`info`
    no console do browser mesmo quando o hostname não é loopback (ex.: Linux
    em LAN a apontar para o servidor de desenvolvimento).
    """
    from .config import settings

    env.globals["sra_console_verbose"] = (getattr(settings, "APP_ENV", "") or "").lower() == "development"
