"""Registro em memória de jobs de progresso para operações longas.

Mantém um dicionário simples por token UUID com {pct, etapa, pronto, erro,
redirect_url, ts}. Usado para criação assíncrona de relatórios (POST
``/relatorios``) quando o frontend precisa exibir barra de progresso real.

Thread-safe via ``threading.Lock``. Limpeza preguiçosa: jobs concluídos ou
em erro com ``ts`` maior que ``JOB_TTL_SECONDS`` são removidos em qualquer
chamada a ``get`` / ``set_progress``.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

JOB_TTL_SECONDS = 600  # 10 minutos

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _agora() -> float:
    return time.time()


def _gc_locked() -> None:
    agora = _agora()
    expirados = [
        tok
        for tok, j in _jobs.items()
        if (j.get("pronto") or j.get("erro"))
        and (agora - j.get("ts", agora)) > JOB_TTL_SECONDS
    ]
    for tok in expirados:
        _jobs.pop(tok, None)


def criar_job() -> str:
    token = uuid.uuid4().hex
    with _lock:
        _gc_locked()
        _jobs[token] = {
            "pct": 0,
            "etapa": "Aguardando…",
            "pronto": False,
            "erro": None,
            "redirect_url": None,
            "ts": _agora(),
        }
    return token


def set_progress(token: str, pct: int, etapa: str) -> None:
    with _lock:
        j = _jobs.get(token)
        if not j:
            return
        j["pct"] = max(0, min(100, int(pct)))
        j["etapa"] = etapa
        j["ts"] = _agora()


def set_done(token: str, redirect_url: str) -> None:
    with _lock:
        j = _jobs.get(token)
        if not j:
            return
        j["pct"] = 100
        j["etapa"] = "Concluído"
        j["pronto"] = True
        j["redirect_url"] = redirect_url
        j["ts"] = _agora()


def set_error(token: str, mensagem: str) -> None:
    with _lock:
        j = _jobs.get(token)
        if not j:
            return
        j["erro"] = mensagem
        j["etapa"] = "Erro"
        j["ts"] = _agora()


def get_job(token: str) -> dict[str, Any] | None:
    with _lock:
        _gc_locked()
        j = _jobs.get(token)
        if not j:
            return None
        return {
            "pct": j.get("pct", 0),
            "etapa": j.get("etapa", ""),
            "pronto": bool(j.get("pronto")),
            "erro": j.get("erro"),
            "redirect_url": j.get("redirect_url"),
        }


def descartar(token: str) -> None:
    with _lock:
        _jobs.pop(token, None)
