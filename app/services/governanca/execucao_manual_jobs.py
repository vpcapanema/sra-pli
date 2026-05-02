"""Execução manual dos jobs reais pela tela de governança."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from ...notificacoes.email_sender import modo_atual
from ...notificacoes.service import (
    abrir_periodo,
    enviar_lembretes,
    notificar_autores_abertura,
    retry_falhas,
)

RESULTADO_TESTE_SESS_KEY = "gov_teste_resultado"


def guardar_resultado_teste(request: Request, rotulo: str, dados: dict) -> None:
    request.session[RESULTADO_TESTE_SESS_KEY] = {
        "rotulo": rotulo,
        "modo_envio": modo_atual(),
        "executado_em": datetime.utcnow().isoformat(timespec="seconds"),
        "dados": dados,
    }


def executar_abrir_periodo_manual(
    request: Request,
    db: Session,
    *,
    force: str,
    base_relatorio_id: str,
) -> None:
    base_id = _parse_int_optional(base_relatorio_id)
    resumo = abrir_periodo(db, force=force in ("1", "on", "true", "sim"), base_relatorio_id=base_id)
    guardar_resultado_teste(request, "Abrir período", asdict(resumo))


TIPOS_NOTIFICACAO_MANUAL: tuple[str, ...] = ("abertura", "lembrete", "ultima_chamada")

_ROTULOS_NOTIFICACAO_MANUAL: dict[str, str] = {
    "abertura": "Notificar usuário · abertura",
    "lembrete": "Notificar usuário · lembrete",
    "ultima_chamada": "Notificar usuário · última chamada",
}


def executar_notificacao_manual(
    request: Request,
    db: Session,
    *,
    tipo: str,
    relatorio_id: int,
) -> None:
    """Despacha o envio manual de notificação ao usuário no tipo escolhido.

    Manual sempre ignora a idempotência/calendário: o coord clicou de propósito.
    Para ``abertura`` passa ``force=True`` (não pula quem já recebeu, reenvia
    a principal **e** secundário). Para lembrete/última chamada, ignora o
    calendário. Centraliza para o card unificado da governança.
    """
    if tipo not in TIPOS_NOTIFICACAO_MANUAL:
        raise ValueError(f"tipo de notificação inválido: {tipo!r}")
    if tipo == "abertura":
        resumo = notificar_autores_abertura(db, relatorio_id, force=True)
    else:
        resumo = enviar_lembretes(
            db,
            tipo=tipo,
            relatorio_id=relatorio_id,
            ignorar_calendario=True,
        )
    guardar_resultado_teste(request, _ROTULOS_NOTIFICACAO_MANUAL[tipo], asdict(resumo))


def executar_retry_manual(request: Request, db: Session) -> None:
    resumo = retry_falhas(db)
    guardar_resultado_teste(request, "Retry · falhas recentes", asdict(resumo))


def _parse_int_optional(raw: str) -> int | None:
    texto = (raw or "").strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None
