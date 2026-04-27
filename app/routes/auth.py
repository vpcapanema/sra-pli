from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

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


@router.get("/login")
def login_page(request: Request):
    return response_login(request)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.strip().lower()).one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return response_login(
            request,
            error="E-mail ou senha inválidos.",
            status_code=401,
        )
    request.session["user_id"] = user.id
    return response_client_goto("/dashboard")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return response_client_goto("/login")


@router.get("/usuarios")
def usuarios_page(request: Request, db: Session = Depends(get_db)):
    return response_usuarios(request, db)


@router.post("/usuarios")
def usuarios_create(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("autor"),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user or user.role not in ("admin", "coordenador"):
        return response_login(request)
    email_norm = email.strip().lower()
    try:
        nome_fmt = formatar_nome_pessoa(nome)
    except ValueError as e:
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "usuarios.html",
            {"user": user, "usuarios": usuarios, "error": str(e)},
            status_code=400,
        )
    if db.query(User).filter(User.email == email_norm).first():
        usuarios = db.query(User).order_by(User.nome).all()
        return templates.TemplateResponse(
            request,
            "usuarios.html",
            {"user": user, "usuarios": usuarios, "error": "E-mail já cadastrado."},
            status_code=400,
        )
    novo = User(nome=nome_fmt, email=email_norm, password_hash=hash_password(password), role=role)
    db.add(novo)
    db.commit()
    return response_usuarios(request, db)


@router.get("/usuarios/{user_id}/editar")
def usuario_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    return response_usuario_edit(request, db, user_id)


@router.post("/usuarios/{user_id}/editar")
def usuario_edit_submit(
    user_id: int,
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
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

    def _err(msg: str):
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
    if email_norm != alvo.email:
        if db.query(User).filter(User.email == email_norm, User.id != alvo.id).first():
            return _err("E-mail já cadastrado.")
        alvo.email = email_norm

    alvo.nome = nome_fmt

    if viewer.role == "admin" and role and role in ("admin", "coordenador", "autor"):
        alvo.role = role

    if password:
        if len(password) < 6:
            return _err("Senha deve ter ao menos 6 caracteres.")
        alvo.password_hash = hash_password(password)

    db.commit()
    return response_usuario_edit(request, db, alvo.id, ok="1")
