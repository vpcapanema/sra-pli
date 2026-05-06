from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..rate_limit import limiter
from ..services import auth as auth_service

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return auth_service.login_page(request)


@router.post("/login")
@limiter.limit("10/minute")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    return auth_service.login_submit(request, email, password, role, db)


@router.post("/logout")
def logout(request: Request):
    return auth_service.logout(request)


@router.get("/recuperar-senha")
def recuperar_senha_page(request: Request):
    return auth_service.recuperar_senha_page(request)


@router.post("/recuperar-senha")
@limiter.limit("5/minute")
def recuperar_senha_submit(
    request: Request,
    email: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    return auth_service.recuperar_senha_submit(request, email, role, db)


@router.get("/recuperar-senha/definir")
def recuperar_senha_definir_page(request: Request):
    return auth_service.recuperar_senha_definir_page(request)


@router.post("/recuperar-senha/definir")
@limiter.limit("5/minute")
def recuperar_senha_definir_submit(
    request: Request,
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    return auth_service.recuperar_senha_definir_submit(
        request, password, password2, db
    )


@router.get("/usuarios")
def usuarios_page(request: Request, db: Session = Depends(get_db)):
    return auth_service.usuarios_page(request, db)


@router.post("/usuarios")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def usuarios_create(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(""),
    password: str = Form(...),
    role: str = Form("autor"),
    db: Session = Depends(get_db),
):
    return auth_service.usuarios_create(
        request,
        nome=nome,
        email=email,
        email2=email2,
        password=password,
        role=role,
        db=db,
    )


@router.get("/usuarios/{user_id}/editar")
def usuario_edit_page(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return auth_service.usuario_edit_page(user_id, request, db)


@router.post("/usuarios/{user_id}/editar")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def usuario_edit_submit(
    user_id: int,
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(""),
    role: str | None = Form(None),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    return auth_service.usuario_edit_submit(
        user_id,
        request,
        nome=nome,
        email=email,
        email2=email2,
        role=role,
        password=password,
        db=db,
    )
