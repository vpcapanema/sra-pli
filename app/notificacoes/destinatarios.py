"""Quem recebe mensagens do ciclo mensal (abertura, lembrete, última chamada)."""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from ..models import NotificacaoEnvio, Relatorio, Secao, User


def emails_destino_notificacao(user: User) -> list[str]:
    """Principal primeiro, depois ``email2``; sem duplicar (case-insensitive)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (user.email, user.email2):
        e = (raw or "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def email_primario_norm(user: User) -> str:
    return (user.email or "").strip().lower()


def destinos_pendentes_tipo(
    db: Session,
    entrega_id: int,
    tipo: str,
    destinos_completos: list[str],
) -> list[str]:
    """Endereços ainda sem ``NotificacaoEnvio`` com sucesso para este ``tipo``."""
    if not destinos_completos:
        return []
    ok_norm = {
        (row[0] or "").strip().lower()
        for row in db.query(NotificacaoEnvio.destinatario_email)
        .filter(
            NotificacaoEnvio.entrega_id == entrega_id,
            NotificacaoEnvio.tipo == tipo,
            NotificacaoEnvio.sucesso.is_(True),
        )
        .all()
    }
    return [d for d in destinos_completos if d.strip().lower() not in ok_norm]


def destinatarios_mensagem_abertura(
    db: Session, rel: Relatorio
) -> list[tuple[User, list[Secao]]]:
    """Destinatários do ciclo (abertura, lembretes, última chamada): todos ``autor``
    com Relatório ativo (``notificacoes_ativas``). Secções por utilizador = onde é
    ``responsavel`` neste relatório (pode ser vazia).
    """
    autores = (
        db.query(User)
        .filter(User.role == "autor", User.notificacoes_ativas.is_(True))
        .order_by(User.nome)
        .all()
    )
    secoes_com_resp = (
        db.query(Secao)
        .options(selectinload(Secao.responsavel))
        .filter(Secao.relatorio_id == rel.id, Secao.responsavel_id.isnot(None))
        .all()
    )
    por_user: dict[int, list[Secao]] = {u.id: [] for u in autores}
    for s in secoes_com_resp:
        if s.responsavel_id and s.responsavel_id in por_user:
            por_user[s.responsavel_id].append(s)
    return [(u, sorted(por_user[u.id], key=lambda x: x.ordem)) for u in autores]
