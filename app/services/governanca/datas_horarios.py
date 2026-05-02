"""Conversões de data/hora da governança, sempre exibindo São Paulo."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def parse_datetime_local_para_utc(raw: str) -> datetime | None:
    """Interpreta entrada humana em São Paulo e persiste como UTC ingênuo."""
    texto = (raw or "").strip()
    if not texto:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            local = datetime.strptime(texto, fmt).replace(tzinfo=_SAO_PAULO_TZ)
            return local.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError("Data ou hora inválida (use AAAA-MM-DDTHH:MM ou DD/MM/AAAA HH:MM).")


def datetime_sao_paulo(val: datetime | None) -> datetime | None:
    if val is None:
        return None
    base = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    return base.astimezone(_SAO_PAULO_TZ)


def formatar_datetime_sao_paulo(val: datetime | None) -> str:
    local = datetime_sao_paulo(val)
    return local.strftime("%d/%m/%Y %H:%M") if local else "—"


def formatar_datetime_input_sao_paulo(val: datetime | None) -> str:
    local = datetime_sao_paulo(val)
    return local.strftime("%Y-%m-%dT%H:%M") if local else ""
