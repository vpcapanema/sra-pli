"""Consulta e normalização do status dos jobs externos de cron."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import urllib.error
import urllib.request

from ...config import settings

_CRONJOB_API_ENDPOINT = "https://api.cron-job.org"


def datetime_utc_de_unix(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc)


def _cronjob_api_get(path: str) -> dict[str, Any]:
    req = urllib.request.Request(
        _CRONJOB_API_ENDPOINT + path,
        headers={
            "Authorization": f"Bearer {settings.CRONJOB_ORG_API_KEY}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cronjob_status_item(job_id: int, label: str) -> dict[str, Any]:
    details = _cronjob_api_get(f"/jobs/{job_id}")["jobDetails"]
    history = _cronjob_api_get(f"/jobs/{job_id}/history")
    last = (history.get("history") or [None])[0]
    return {
        "job_id": job_id,
        "label": label,
        "available": True,
        "enabled": bool(details.get("enabled")),
        "url": details.get("url") or "",
        "next_execution": datetime_utc_de_unix(details.get("nextExecution")),
        "last_execution": datetime_utc_de_unix(last.get("date") if last else None),
        "last_http_status": last.get("httpStatus") if last else None,
        "last_status": last.get("status") if last else None,
        "last_status_text": (last.get("statusText") if last else None) or "",
        "last_duration_ms": last.get("duration") if last else None,
    }


def cron_status_real() -> list[dict[str, Any]]:
    specs = [
        (settings.CRONJOB_ORG_JOB_ABRIR_PERIODO, "Abrir período"),
        (settings.CRONJOB_ORG_JOB_LEMBRETE_D5, "Lembrete dia 5"),
        (settings.CRONJOB_ORG_JOB_LEMBRETE_D8, "Lembrete dia 8"),
        (settings.CRONJOB_ORG_JOB_ULTIMA_CHAMADA, "Última chamada"),
        (settings.CRONJOB_ORG_JOB_RETRY_FALHAS, "Retry falhas"),
    ]
    if not settings.CRONJOB_ORG_API_KEY:
        return [
            {"job_id": job_id, "label": label, "available": False, "error": "CRONJOB_ORG_API_KEY não configurada."}
            for job_id, label in specs
        ]
    out: list[dict[str, Any]] = []
    for job_id, label in specs:
        try:
            out.append(_cronjob_status_item(job_id, label))
        except (KeyError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            out.append({"job_id": job_id, "label": label, "available": False, "error": str(exc)})
    return out


def proxima_execucao(cron_status: list[dict[str, Any]], labels: set[str]) -> datetime | None:
    datas = [
        row["next_execution"]
        for row in cron_status
        if row.get("label") in labels and row.get("next_execution") is not None
    ]
    return min(datas) if datas else None
