"""Autenticação, recuperação de senha e CRUD de usuários (lógica).

Lógica das rotas em ``app/routes/auth.py``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import Response

from ..auth import (
    current_user,
    formatar_nome_pessoa,
    hash_password,
    verify_password,
)
from ..jinja_filters import registrar_globais as _registrar_globais_jinja
from ..models import User
from .pages import (
    response_client_goto,
    response_login,
    response_usuario_edit,
    response_usuarios,
    usuario_edit_precheck,
)

templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)
_registrar_globais_jinja(templates.env)
_log = logging.getLogger(__name__)

_ROLES_LOGIN = frozenset({"admin", "coordenador", "autor"})
_PWD_RESET_MAX_SEC = 3600
_SRA_PWD_RESET_UID = "sra_pwd_reset_uid"
_SRA_PWD_RESET_AT = "sra_pwd_reset_at"


# ---------------------------------------------------------------------------
# Helpers públicos (reutilizados por outros services, ex.: governanca)
# ---------------------------------------------------------------------------


def normalizar_email_secundario_obrigatorio(
    raw: str,
) -> tuple[str | None, str | None]:
    s = (raw or "").strip().lower()
    if not s:
        return None, "E-mail secundário é obrigatório."
    if "@" not in s or len(s) < 5:
        return None, "E-mail secundário inválido."
    return s, None


# Alias interno mantido p/ minimizar diff. Novos códigos devem usar o público.
_normalizar_email_secundario_obrigatorio = normalizar_email_secundario_obrigatorio


def _clear_pwd_reset_session(request: Request) -> None:
    request.session.pop(_SRA_PWD_RESET_UID, None)
    request.session.pop(_SRA_PWD_RESET_AT, None)


def _pwd_reset_session_ok(request: Request) -> bool:
    uid = request.session.get(_SRA_PWD_RESET_UID)
    started = request.session.get(_SRA_PWD_RESET_AT)
    if uid is None or started is None:
        return False
    if time.time() - float(started) > _PWD_RESET_MAX_SEC:
        _clear_pwd_reset_session(request)
        return False
    return True


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def login_page(request: Request):
    return response_login(request)


def login_submit(
    request: Request,
    email: str,
    password: str,
    role: str,
    db: Session,
):
    perfil = (role or "").strip().lower()
    if perfil not in _ROLES_LOGIN:
        return response_login(
            request,
            error="Selecione um perfil válido.",
            role=perfil,
            status_code=400,
        )
    email_norm = email.strip().lower()
    t0 = time.perf_counter()
    _log.info("login_submit inicio role=%s email=%s", perfil, email_norm)
    try:
        user = (
            db.query(User)
            .filter(User.email == email_norm, User.role == perfil)
            .one_or_none()
        )
        t_user = time.perf_counter()
        _log.info(
            "login_submit consulta_usuario_ms=%.1f encontrado=%s role=%s",
            (t_user - t0) * 1000,
            bool(user),
            perfil,
        )
        senha_ok = bool(user) and verify_password(password, user.password_hash)
        t_pwd = time.perf_counter()
        _log.info(
            "login_submit verifica_senha_ms=%.1f ok=%s role=%s",
            (t_pwd - t_user) * 1000,
            senha_ok,
            perfil,
        )
        if not senha_ok:
            return response_login(
                request,
                error="E-mail, perfil ou senha inválidos.",
                role=perfil,
                status_code=401,
            )
        _clear_pwd_reset_session(request)
        request.session["user_id"] = user.id
        request.session["user_role"] = user.role
        destino = "/dashboard"
        if user.role == "autor":
            destino = "/painel-upload"
        t_destino = time.perf_counter()
        _log.info(
            "login_submit destino_ms=%.1f total_ms=%.1f user_id=%s role=%s destino=%s",
            (t_destino - t_pwd) * 1000,
            (t_destino - t0) * 1000,
            user.id,
            user.role,
            destino,
        )
        return response_client_goto(destino)
    except Exception:  # noqa: BLE001
        _log.exception(
            "login_submit erro inesperado role=%s email=%s", perfil, email_norm
        )
        return response_login(
            request,
            error="Falha temporária no login. Tente novamente em instantes.",
            role=perfil,
            status_code=500,
        )


def logout(request: Request):
    request.session.clear()
    return response_client_goto("/login")


def recuperar_senha_page(request: Request):
    return templates.TemplateResponse(
        request,
        "complementos/recuperar_senha.html",
        {"error": None},
    )


def recuperar_senha_submit(
    request: Request, email: str, role: str, db: Session
):
    perfil = (role or "").strip().lower()
    if perfil not in _ROLES_LOGIN:
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha.html",
            {"error": "Selecione um perfil válido."},
            status_code=400,
        )
    email_norm = email.strip().lower()
    user = (
        db.query(User)
        .filter(User.email == email_norm, User.role == perfil)
        .one_or_none()
    )
    if not user:
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha.html",
            {
                "error": "Não encontramos conta com este e-mail e perfil. "
                "Confirme os dados ou contacte um administrador.",
            },
            status_code=400,
        )
    _clear_pwd_reset_session(request)
    request.session[_SRA_PWD_RESET_UID] = user.id
    request.session[_SRA_PWD_RESET_AT] = time.time()
    return response_client_goto("/recuperar-senha/definir")


def recuperar_senha_definir_page(request: Request):
    if not _pwd_reset_session_ok(request):
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha.html",
            {
                "error": "Sessão de recuperação expirada ou inválida. "
                "Comece novamente por e-mail e perfil.",
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "complementos/recuperar_senha_definir.html",
        {"error": None},
    )


def recuperar_senha_definir_submit(
    request: Request, password: str, password2: str, db: Session
):
    if not _pwd_reset_session_ok(request):
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha.html",
            {
                "error": "Sessão de recuperação expirada ou inválida. "
                "Comece novamente por e-mail e perfil.",
            },
            status_code=400,
        )
    pw = (password or "").strip()
    if len(pw) < 6:
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha_definir.html",
            {"error": "A senha deve ter ao menos 6 caracteres."},
            status_code=400,
        )
    if pw != (password2 or "").strip():
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha_definir.html",
            {"error": "As senhas não coincidem."},
            status_code=400,
        )
    uid = request.session.get(_SRA_PWD_RESET_UID)
    user = db.get(User, uid) if uid is not None else None
    if not user:
        _clear_pwd_reset_session(request)
        return templates.TemplateResponse(
            request,
            "complementos/recuperar_senha.html",
            {"error": "Conta não encontrada. Solicite recuperação outra vez."},
            status_code=400,
        )
    user.password_hash = hash_password(pw)
    db.commit()
    _clear_pwd_reset_session(request)
    return response_login(
        request,
        notice="Senha atualizada. Entre com e-mail, perfil e nova senha.",
    )


def usuarios_page(request: Request, db: Session):
    return response_usuarios(request, db)


def usuarios_create(  # pylint: disable=too-many-arguments
    request: Request,
    *,
    nome: str,
    email: str,
    email2: str,
    password: str,
    role: str,
    db: Session,
):
    user = current_user(request, db)
    if not user or user.role not in ("admin", "coordenador"):
        return response_login(request)
    email_norm = email.strip().lower()
    _log.info(
        "Cadastro utilizador: início email=%s role_pedido=%s operador_id=%s",
        email_norm,
        (role or "").strip().lower(),
        user.id,
    )
    email2_norm, err_email2 = normalizar_email_secundario_obrigatorio(email2)
    if err_email2:
        _log.warning(
            "Cadastro utilizador: rejeitado email2 inválido email=%s operador_id=%s detalhe=%s",
            email_norm,
            user.id,
            err_email2,
        )
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "complementos/usuarios.html",
            {"user": user, "usuarios": usuarios, "error": err_email2},
            status_code=400,
        )
    try:
        nome_fmt = formatar_nome_pessoa(nome)
    except ValueError as e:
        _log.warning(
            "Cadastro utilizador: rejeitado nome inválido email=%s operador_id=%s detalhe=%s",
            email_norm,
            user.id,
            str(e),
        )
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "complementos/usuarios.html",
            {"user": user, "usuarios": usuarios, "error": str(e)},
            status_code=400,
        )
    if role not in ("admin", "coordenador", "autor"):
        _log.warning(
            "Cadastro utilizador: rejeitado perfil inválido email=%s role=%s operador_id=%s",
            email_norm,
            role,
            user.id,
        )
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "complementos/usuarios.html",
            {"user": user, "usuarios": usuarios, "error": "Perfil inválido."},
            status_code=400,
        )
    if (
        db.query(User)
        .filter(User.email == email_norm, User.role == role)
        .first()
    ):
        _log.warning(
            "Cadastro utilizador: rejeitado duplicado email=%s role=%s operador_id=%s",
            email_norm,
            role,
            user.id,
        )
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "complementos/usuarios.html",
            {
                "user": user,
                "usuarios": usuarios,
                "error": "Já existe utilizador com este e-mail e perfil.",
            },
            status_code=400,
        )
    novo = User(
        nome=nome_fmt,
        email=email_norm,
        email2=email2_norm,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(novo)
    db.commit()
    _log.info(
        "Cadastro utilizador: concluído id=%s email=%s role=%s operador_id=%s",
        novo.id,
        email_norm,
        role,
        user.id,
    )
    return response_usuarios(request, db)


def usuario_edit_page(user_id: int, request: Request, db: Session):
    return response_usuario_edit(request, db, user_id)


def usuario_edit_submit(  # pylint: disable=too-many-arguments,too-many-return-statements,too-many-locals
    user_id: int,
    request: Request,
    *,
    nome: str,
    email: str,
    email2: str,
    role: str | None,
    password: str,
    db: Session,
):
    pre = usuario_edit_precheck(request, db, user_id)
    if isinstance(pre, Response):
        return pre
    viewer, alvo = pre

    _log.info(
        "Edição utilizador: início id=%s operador_id=%s",
        alvo.id,
        viewer.id,
    )

    def _err(msg: str):
        _log.warning(
            "Edição utilizador: rejeitado id=%s operador_id=%s detalhe=%s",
            alvo.id,
            viewer.id,
            msg,
        )
        return templates.TemplateResponse(
            request,
            "complementos/usuario_edit.html",
            {"user": viewer, "alvo": alvo, "error": msg, "ok": None},
            status_code=400,
        )

    try:
        nome_fmt = formatar_nome_pessoa(nome)
    except ValueError as e:
        return _err(str(e))

    email_norm = email.strip().lower()
    email2_norm, err_email2 = normalizar_email_secundario_obrigatorio(email2)
    if err_email2:
        return _err(err_email2)

    novo_role = alvo.role
    if (
        viewer.role == "admin"
        and role
        and role in ("admin", "coordenador", "autor")
    ):
        novo_role = role

    duplicado = (
        db.query(User)
        .filter(
            User.email == email_norm,
            User.role == novo_role,
            User.id != alvo.id,
        )
        .first()
    )
    if duplicado:
        return _err("Já existe utilizador com este e-mail e perfil.")

    alvo.email = email_norm
    alvo.email2 = email2_norm
    alvo.nome = nome_fmt

    if (
        viewer.role == "admin"
        and role
        and role in ("admin", "coordenador", "autor")
    ):
        alvo.role = role

    if password:
        if len(password) < 6:
            return _err("Senha deve ter ao menos 6 caracteres.")
        alvo.password_hash = hash_password(password)

    db.commit()
    if alvo.id == request.session.get("user_id"):
        request.session["user_role"] = alvo.role
    _log.info(
        "Edição utilizador: gravado id=%s email=%s operador_id=%s",
        alvo.id,
        email_norm,
        viewer.id,
    )
    return response_usuario_edit(request, db, alvo.id, ok="1")
