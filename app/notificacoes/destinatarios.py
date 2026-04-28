"""Quem recebe mensagens do ciclo mensal (abertura, lembrete, última chamada)."""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from ..models import Relatorio, Secao, User


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
