import logging
import time
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..auth import (
    verify_password,
    hash_password,
    current_user,
    formatar_nome_pessoa,
    pode_editar_perfil_usuario,
)
from .pages import (
    response_client_goto,
    response_login,
    response_usuario_edit,
    response_usuarios,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
_log = logging.getLogger(__name__)

_ROLES_LOGIN = frozenset({"admin", "coordenador", "autor"})
_PWD_RESET_MAX_SEC = 3600
_SRA_PWD_RESET_UID = "sra_pwd_reset_uid"
_SRA_PWD_RESET_AT = "sra_pwd_reset_at"


def _normalizar_email_secundario_obrigatorio(raw: str) -> tuple[str | None, str | None]:
    s = (raw or "").strip().lower()
    if not s:
        return None, "E-mail secundário é obrigatório."
    if "@" not in s or len(s) < 5:
        return None, "E-mail secundário inválido."
    return s, None


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


@router.get("/login")
def login_page(request: Request):
    return response_login(request)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    perfil = (role or "").strip().lower()
    if perfil not in _ROLES_LOGIN:
        return response_login(
            request,
            error="Selecione um perfil válido.",
            status_code=400,
        )
    email_norm = email.strip().lower()
    user = (
        db.query(User)
        .filter(User.email == email_norm, User.role == perfil)
        .one_or_none()
    )
    if not user or not verify_password(password, user.password_hash):
        return response_login(
            request,
            error="E-mail, perfil ou senha inválidos.",
            status_code=401,
        )
    _clear_pwd_reset_session(request)
    request.session["user_id"] = user.id
    request.session["user_role"] = user.role
    destino = "/painel-upload" if user.role == "autor" else "/dashboard"
    return response_client_goto(destino)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return response_client_goto("/login")


@router.get("/recuperar-senha")
def recuperar_senha_page(request: Request):
    return templates.TemplateResponse(
        request,
        "recuperar_senha.html",
        {"error": None},
    )


@router.post("/recuperar-senha")
def recuperar_senha_submit(
    request: Request,
    email: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    perfil = (role or "").strip().lower()
    if perfil not in _ROLES_LOGIN:
        return templates.TemplateResponse(
            request,
            "recuperar_senha.html",
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
            "recuperar_senha.html",
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


@router.get("/recuperar-senha/definir")
def recuperar_senha_definir_page(request: Request):
    if not _pwd_reset_session_ok(request):
        return templates.TemplateResponse(
            request,
            "recuperar_senha.html",
            {
                "error": "Sessão de recuperação expirada ou inválida. "
                "Comece novamente por e-mail e perfil.",
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "recuperar_senha_definir.html",
        {"error": None},
    )


@router.post("/recuperar-senha/definir")
def recuperar_senha_definir_submit(
    request: Request,
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    if not _pwd_reset_session_ok(request):
        return templates.TemplateResponse(
            request,
            "recuperar_senha.html",
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
            "recuperar_senha_definir.html",
            {"error": "A senha deve ter ao menos 6 caracteres."},
            status_code=400,
        )
    if pw != (password2 or "").strip():
        return templates.TemplateResponse(
            request,
            "recuperar_senha_definir.html",
            {"error": "As senhas não coincidem."},
            status_code=400,
        )
    uid = request.session.get(_SRA_PWD_RESET_UID)
    user = db.get(User, uid) if uid is not None else None
    if not user:
        _clear_pwd_reset_session(request)
        return templates.TemplateResponse(
            request,
            "recuperar_senha.html",
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


@router.get("/usuarios")
def usuarios_page(request: Request, db: Session = Depends(get_db)):
    return response_usuarios(request, db)


@router.get("/usuarios/registro-atividade")
def usuarios_registro_atividade(request: Request, db: Session = Depends(get_db)):
    """Página dedicada ao painel de registro em tempo real (SSE + logging)."""
    user = current_user(request, db)
    if not user:
        return response_login(request)
    if user.role not in ("admin", "coordenador"):
        return RedirectResponse(url="/painel-upload", status_code=303)
    return templates.TemplateResponse(
        request,
        "registro_servidor.html",
        {"user": user, "sra_logs_altura": "alta"},
    )


@router.post("/usuarios")
def usuarios_create(  # pylint: disable=too-many-arguments
    request: Request,
    *,
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(...),
    password: str = Form(...),
    role: str = Form("autor"),
    db: Session = Depends(get_db),
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
    email2_norm, err_email2 = _normalizar_email_secundario_obrigatorio(email2)
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
            "usuarios.html",
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
            "usuarios.html",
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
            "usuarios.html",
            {"user": user, "usuarios": usuarios, "error": "Perfil inválido."},
            status_code=400,
        )
    if db.query(User).filter(User.email == email_norm, User.role == role).first():
        _log.warning(
            "Cadastro utilizador: rejeitado duplicado email=%s role=%s operador_id=%s",
            email_norm,
            role,
            user.id,
        )
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "usuarios.html",
            {"user": user, "usuarios": usuarios, "error": "Já existe utilizador com este e-mail e perfil."},
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


@router.get("/usuarios/{user_id}/editar")
def usuario_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    return response_usuario_edit(request, db, user_id)


@router.post("/usuarios/{user_id}/editar")
def usuario_edit_submit(  # pylint: disable=too-many-arguments,too-many-return-statements,too-many-locals
    user_id: int,
    request: Request,
    *,
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(...),
    role: str = Form(None),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    viewer = current_user(request, db)
    if not viewer:
        return response_login(request)
    alvo = db.get(User, user_id)
    if not alvo:
        return response_usuarios(request, db)
    if not pode_editar_perfil_usuario(viewer, alvo):
        return response_usuarios(request, db)

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
            "usuario_edit.html",
            {"user": viewer, "alvo": alvo, "error": msg, "ok": None},
            status_code=400,
        )

    try:
        nome_fmt = formatar_nome_pessoa(nome)
    except ValueError as e:
        return _err(str(e))

    email_norm = email.strip().lower()
    email2_norm, err_email2 = _normalizar_email_secundario_obrigatorio(email2)
    if err_email2:
        return _err(err_email2)

    novo_role = alvo.role
    if viewer.role == "admin" and role and role in ("admin", "coordenador", "autor"):
        novo_role = role

    duplicado = (
        db.query(User)
        .filter(User.email == email_norm, User.role == novo_role, User.id != alvo.id)
        .first()
    )
    if duplicado:
        return _err("Já existe utilizador com este e-mail e perfil.")

    alvo.email = email_norm
    alvo.email2 = email2_norm
    alvo.nome = nome_fmt

    if viewer.role == "admin" and role and role in ("admin", "coordenador", "autor"):
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
