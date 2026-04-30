"""Coordenador pode ativar 'modo edição' por relatório para mutar blocos já bloqueados."""
from __future__ import annotations

from starlette.requests import Request

from .models import User

SESSION_KEY_MODO_EDICAO_REL = "sra_modo_edicao_rel_id"


def modo_edicao_coordenador_rel(request: Request, user: User, rel_id: int) -> bool:
    """True se coordenador ativou o modo edição nesta sessão para este relatório."""
    if user.role != "coordenador":
        return False
    raw = request.session.get(SESSION_KEY_MODO_EDICAO_REL)
    if raw is None:
        return False
    try:
        return int(raw) == int(rel_id)
    except (TypeError, ValueError):
        return False


def pode_mutar_apesar_de_bloqueado(request: Request, user: User, rel_id: int) -> bool:
    """Administrador sempre; coordenador só com modo edição ligado neste relatório."""
    if user.role == "admin":
        return True
    return modo_edicao_coordenador_rel(request, user, rel_id)


def definir_modo_edicao_coordenador(request: Request, rel_id: int | None) -> None:
    """Define ou remove (None) qual relatório está em modo edição para coordenador."""
    if rel_id is None:
        request.session.pop(SESSION_KEY_MODO_EDICAO_REL, None)
        return
    request.session[SESSION_KEY_MODO_EDICAO_REL] = int(rel_id)
