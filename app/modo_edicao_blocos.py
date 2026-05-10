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


def pode_mutar_apesar_de_bloqueado(
    request: Request,
    user: User,
    rel_id: int,
    rel_status: str | None = None,
) -> bool:
    """Decide se um bloco com ``bloqueado=True`` ainda pode ser mutado.

    Matriz por status do relatório (consulte ``project-instructions.md``):

    - ``rel_status == "aberto"``: ``bloqueado`` é trava **cooperativa** entre
      autores; admin sempre passa, coordenador sempre passa (pode excluir com qualquer status).
    - ``rel_status == "em_revisao"``: a coleta encerrou e o coord é dono do
      conteúdo — coordenador e admin passam **sem** modo edição.
    - ``rel_status`` ``None`` (legado): mantém comportamento conservador
      (apenas admin + modo edição coord), idêntico à versão anterior.
    """
    if user.role == "admin":
        return True
    if user.role == "coordenador":
        # Coordenador pode sempre mutar blocos bloqueados (pode excluir com qualquer status)
        return True
    return False


def definir_modo_edicao_coordenador(request: Request, rel_id: int | None) -> None:
    """Define ou remove (None) qual relatório está em modo edição para coordenador."""
    if rel_id is None:
        request.session.pop(SESSION_KEY_MODO_EDICAO_REL, None)
        return
    request.session[SESSION_KEY_MODO_EDICAO_REL] = int(rel_id)
