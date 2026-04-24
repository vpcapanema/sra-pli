from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from ..db import get_db
from ..models import User
from ..auth import verify_password, hash_password, current_user, formatar_nome_pessoa

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.strip().lower()).one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "E-mail ou senha inválidos."},
            status_code=401,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/usuarios")
def usuarios_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    usuarios = db.query(User).order_by(User.nome).all()
    return templates.TemplateResponse(
        request, "usuarios.html", {"user": user, "usuarios": usuarios, "error": None}
    )


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
        return RedirectResponse("/login", status_code=303)
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
    return RedirectResponse("/usuarios", status_code=303)


def _pode_editar(viewer: User, alvo: User) -> bool:
    return viewer.role == "admin" or viewer.id == alvo.id


@router.get("/usuarios/{user_id}/editar")
def usuario_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    viewer = current_user(request, db)
    if not viewer:
        return RedirectResponse("/login", status_code=303)
    alvo = db.get(User, user_id)
    if not alvo:
        return RedirectResponse("/usuarios", status_code=303)
    if not _pode_editar(viewer, alvo):
        return RedirectResponse("/usuarios", status_code=303)
    return templates.TemplateResponse(
        request,
        "usuario_edit.html",
        {"user": viewer, "alvo": alvo, "error": None, "ok": request.query_params.get("ok")},
    )


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
        return RedirectResponse("/login", status_code=303)
    alvo = db.get(User, user_id)
    if not alvo:
        return RedirectResponse("/usuarios", status_code=303)
    if not _pode_editar(viewer, alvo):
        return RedirectResponse("/usuarios", status_code=303)

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
    return RedirectResponse(f"/usuarios/{alvo.id}/editar?ok=1", status_code=303)
