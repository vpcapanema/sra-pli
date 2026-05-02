"""Regras para edição de usuários pela governança."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy.orm import Session

from ...auth import formatar_nome_pessoa
from ...models import User
from ...routes.auth import normalizar_email_secundario_obrigatorio
from .acesso_permissoes import pode_editar_usuario_governanca


@dataclass(frozen=True)
class DadosEdicaoUsuario:
    """Campos editáveis de usuário recebidos pelo formulário de governança."""

    nome: str
    email: str
    email2: str
    role: str
    notificacoes_ativas: str


def _novo_role_permitido(viewer: User, alvo: User, role: str) -> tuple[str, str | None]:
    novo_role = alvo.role
    if viewer.role == "admin" and role and role in ("admin", "coordenador", "autor"):
        return role, None
    if viewer.role == "coordenador" and role and role != alvo.role:
        return novo_role, "apenas+admin+altera+perfil"
    return novo_role, None


def _email_ja_usado(
    db: Session,
    email_norm: str,
    role: str,
    exceto_id: int,
) -> bool:
    duplicado = (
        db.query(User)
        .filter(User.email == email_norm, User.role == role, User.id != exceto_id)
        .first()
    )
    return duplicado is not None


def salvar_usuario_governanca(
    request,
    db: Session,
    viewer: User,
    alvo: User,
    dados: DadosEdicaoUsuario,
) -> str | None:
    if not pode_editar_usuario_governanca(viewer, alvo):
        return "sem+permissao+para+este+utilizador"
    try:
        nome_fmt = formatar_nome_pessoa(dados.nome)
    except ValueError as exc:
        return quote(str(exc))
    email_norm = dados.email.strip().lower()
    email2_norm, err_email2 = normalizar_email_secundario_obrigatorio(dados.email2)
    if err_email2:
        return quote(err_email2)
    novo_role, err_role = _novo_role_permitido(viewer, alvo, dados.role)
    if err_role:
        return err_role
    if _email_ja_usado(db, email_norm, novo_role, alvo.id):
        return "email+e+perfil+ja+existentes"
    alvo.nome = nome_fmt
    alvo.email = email_norm
    alvo.email2 = email2_norm
    alvo.role = novo_role
    alvo.notificacoes_ativas = dados.notificacoes_ativas in ("1", "on", "true", "sim")
    if alvo.id == viewer.id:
        request.session["user_role"] = novo_role
    db.commit()
    return None


def alternar_notificacoes_relatorio(alvo: User) -> None:
    alvo.notificacoes_ativas = not bool(alvo.notificacoes_ativas)
