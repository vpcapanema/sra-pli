import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..process_events import process_session_id, sse_payload, subscribe, unsubscribe
from ..sra_fluxo_confirmacao import resposta_fluxo_confirmacao


router = APIRouter(prefix="/processos", tags=["processos"])


@router.get("/fluxo-confirmacao/{chave}")
def fluxo_confirmacao(chave: str, request: Request):
    """Textos para o modal de confirmação (chave estável por fluxo). Requer sessão autenticada."""
    if not request.session.get("user_id"):
        raise HTTPException(403, detail="Sessão expirada")
    body = resposta_fluxo_confirmacao(chave.strip())
    if not body:
        raise HTTPException(404, detail="Fluxo desconhecido")
    return body


@router.get("/eventos")
async def eventos_processos(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(403, detail="Sessão expirada")
    session_id = process_session_id(request)
    queue = subscribe(session_id)

    async def stream():
        try:
            yield sse_payload(
                {
                    "id": "connected",
                    "kind": "connection",
                    "level": "info",
                    "status": "success",
                    "title": "Canal de processos conectado",
                    "message": "",
                    "process_id": "connection",
                    "data": {},
                    "ts": "",
                }
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield sse_payload(event)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe(session_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
