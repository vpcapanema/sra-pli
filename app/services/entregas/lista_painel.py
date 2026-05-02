"""Fonte única da 'Lista de entregas' usada por /relatorios/{rel_id}/entregas
e pelo painel de governança. As duas telas renderizam o mesmo partial Jinja
`complementos/_lista_entregas_partial.html` consumindo as `linhas` produzidas
aqui — assim, qualquer mudança em estrutura/regra reflete em ambas.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ...models import EntregaRelatorio, Relatorio, Secao, User


def _achatar_linha(entrega: EntregaRelatorio, sec_counts: dict[int, int]) -> dict[str, Any]:
    """Achata ``EntregaRelatorio`` para o template, derivando notif1/2/3/última
    da relação 1:N ``notificacoes`` (já ordenada por ``enviada_em``)."""
    enviadas = [n for n in entrega.notificacoes if n.sucesso]
    notif1 = enviadas[0].enviada_em if len(enviadas) >= 1 else None
    notif2 = enviadas[1].enviada_em if len(enviadas) >= 2 else None
    notif3 = enviadas[2].enviada_em if len(enviadas) >= 3 else None
    ultima = enviadas[-1].enviada_em if enviadas else None
    u = entrega.user
    return {
        "entrega_id": entrega.id,
        "user_id": u.id if u else None,
        "nome": u.nome if u else "—",
        "email": u.email if u else "—",
        "perfil": u.role if u else "—",
        "secoes_count": sec_counts.get(u.id, 0) if u else 0,
        "notif1": notif1,
        "notif2": notif2,
        "notif3": notif3,
        "ultima": ultima,
        "data_envio": entrega.data_envio,
        "status": entrega.status,
    }


def montar_lista_entregas(
    db: Session,
    rel: Relatorio,
    viewer: User,
) -> tuple[list[dict[str, Any]], bool]:
    """Carrega entregas + contagem de seções e devolve linhas achatadas + flag
    de permissão para ações. Coord/admin veem todas as linhas; autores veem
    apenas a sua. A agregação dos timestamps de notificação é feita em Python:
    ≤ ~30 linhas por relatório torna SQL agregado sobre-engenharia.
    """
    q = (
        db.query(EntregaRelatorio)
        .options(
            selectinload(EntregaRelatorio.user),
            selectinload(EntregaRelatorio.notificacoes),
        )
        .filter(EntregaRelatorio.relatorio_id == rel.id)
    )
    if viewer.role not in ("admin", "coordenador"):
        q = q.filter(EntregaRelatorio.user_id == viewer.id)
    entregas = q.all()
    entregas.sort(key=lambda e: (e.user.nome if e.user else ""))

    sec_counts: dict[int, int] = dict(
        db.query(
            Secao.responsavel_id,
            func.count(Secao.id),  # pylint: disable=not-callable
        )
        .filter(Secao.relatorio_id == rel.id, Secao.responsavel_id.isnot(None))
        .group_by(Secao.responsavel_id)
        .all()
    )

    linhas = [_achatar_linha(e, sec_counts) for e in entregas]
    pode_acoes = viewer.role in ("admin", "coordenador")
    return linhas, pode_acoes
