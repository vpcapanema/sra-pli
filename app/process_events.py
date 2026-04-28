import asyncio
import json
import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from fastapi import Request

from . import sra_process_modal


SESSION_KEY = "process_session_id"
MAX_RECENT_EVENTS = 80
_subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]]] = defaultdict(list)
_recent_events: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=MAX_RECENT_EVENTS))
_broadcast_recent: deque[dict[str, Any]] = deque(maxlen=MAX_RECENT_EVENTS)
_state = {"logger_bridge_configured": False}


def process_session_id(request: Request) -> str:
    sid = request.session.get(SESSION_KEY)
    if not sid:
        sid = uuid.uuid4().hex
        request.session[SESSION_KEY] = sid
    return sid


def _event(
    kind: str,
    level: str,
    title: str,
    message: str = "",
    *,
    status: str = "info",
    process_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "kind": kind,
        "level": level,
        "status": status,
        "title": title,
        "message": message,
        "process_id": process_id or uuid.uuid4().hex,
        "data": data or {},
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _deliver(session_id: str, event: dict[str, Any]) -> None:
    def enqueue(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    alive = []
    for loop, queue in _subscribers.get(session_id, []):
        if loop.is_closed():
            continue
        loop.call_soon_threadsafe(enqueue, queue, event)
        alive.append((loop, queue))
    _subscribers[session_id] = alive


def subscribe(session_id: str) -> asyncio.Queue[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    _subscribers[session_id].append((loop, queue))
    for event in list(_broadcast_recent)[-20:] + list(_recent_events.get(session_id, []))[-20:]:
        queue.put_nowait(event)
    return queue


def unsubscribe(session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
    _subscribers[session_id] = [(loop, item) for loop, item in _subscribers.get(session_id, []) if item is not queue]


def publish(
    session_id: str,
    kind: str,
    level: str,
    title: str,
    message: str = "",
    *,
    status: str = "info",
    process_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    event = _event(kind, level, title, message, status=status, process_id=process_id, data=data)
    _recent_events[session_id].append(event)
    _deliver(session_id, event)
    return event["process_id"]


def publish_all(
    kind: str,
    level: str,
    title: str,
    message: str = "",
    *,
    status: str = "info",
    process_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    event = _event(kind, level, title, message, status=status, process_id=process_id, data=data)
    _broadcast_recent.append(event)
    for session_id in list(_subscribers):
        _deliver(session_id, event)
    return event["process_id"]


def _pct_0_100(value: int | float | None) -> int | None:
    if value is None:
        return None
    v = int(round(float(value)))
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


def process_start(request: Request, title: str, message: str = "", data: dict[str, Any] | None = None) -> str:
    merged: dict[str, Any] = {
        "channel": "process",
        "tarefa": title,
        "texto_tratado": True,
        "subtarefa": "Início do fluxo",
        "progresso_geral": 1,
        "progresso_tarefa": 1,
    }
    if data:
        merged.update(data)
    if "tarefa" not in merged or not merged.get("tarefa"):
        merged["tarefa"] = title
    return publish(process_session_id(request), "process", "info", title, message, status="working", data=merged)


def process_log(  # pylint: disable=too-many-arguments
    request: Request,
    process_id: str,
    message: str,
    *,
    level: str = "info",
    etapa: str = "Etapa do processo",
    tarefa: str = "",
    progresso_tarefa: int | None = None,
    progresso_geral: int | None = None,
) -> None:
    status = "danger" if level in {"error", "critical"} else "working"
    data: dict[str, Any] = {
        "channel": "process",
        "texto_tratado": True,
        "subtarefa": etapa,
    }
    if tarefa:
        data["tarefa"] = tarefa
    p_t = _pct_0_100(progresso_tarefa)
    p_g = _pct_0_100(progresso_geral)
    if p_t is not None:
        data["progresso_tarefa"] = p_t
    if p_g is not None:
        data["progresso_geral"] = p_g
    publish(
        process_session_id(request),
        "log",
        level,
        etapa,
        message,
        status=status,
        process_id=process_id,
        data=data,
    )


def process_done(  # pylint: disable=too-many-arguments
    request: Request,
    process_id: str,
    title: str,
    message: str = "",
    *,
    ok: bool = True,
    process_key: str = "",
    outcome: str | None = None,
    detalhe: str = "",
    recomendacao: str = "",
) -> None:
    res = sra_process_modal.outcome_resolvido(ok=ok, outcome=outcome)
    level, ev_status = sra_process_modal.nivel_e_status_por_outcome(res)
    data = sra_process_modal.montar_data_modal_fim(
        process_key=process_key,
        titulo=title,
        mensagem=message,
        outcome=res,
        detalhe=detalhe,
        recomendacao=recomendacao,
    )
    data["tarefa"] = title
    data["texto_tratado"] = True
    data["subtarefa"] = "Conclusão"
    data["progresso_geral"] = 100
    data["progresso_tarefa"] = 100
    publish(
        process_session_id(request),
        "process",
        level,
        title,
        message,
        status=ev_status,
        process_id=process_id,
        data=data,
    )


class ProcessLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = record.levelname.lower()
            status = "danger" if record.levelno >= logging.ERROR else "warning" if record.levelno >= logging.WARNING else "info"
            publish_all("server_log", level, record.name, self.format(record), status=status, process_id="fastapi-log")
        except Exception:
            pass


def configure_logging_bridge() -> None:
    if _state["logger_bridge_configured"]:
        return
    handler = ProcessLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    for logger_name in ("uvicorn.error", "fastapi", "app"):
        logging.getLogger(logger_name).addHandler(handler)
    _state["logger_bridge_configured"] = True


def sse_payload(event: dict[str, Any]) -> str:
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
