"""Permissões da área de governança."""
from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ...models import User
from ..pages import user_or_login_page


def coordenador_admin_ou_login(
    request: Request, db: Session
) -> tuple[User, None] | tuple[None, object]:
    user, login_page = user_or_login_page(request, db)
    if login_page is not None:
        return None, login_page
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador ou administrador.")
    return user, None


def pode_editar_usuario_governanca(viewer: User, alvo: User) -> bool:
    if viewer.role == "admin":
        return True
    if viewer.role == "coordenador":
        return alvo.role == "autor" or alvo.id == viewer.id
    return False
