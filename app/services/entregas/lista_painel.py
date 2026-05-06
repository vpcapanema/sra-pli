"""Fonte única da 'Lista de entregas' usada por /relatorios/{rel_id}/entregas
e pelo painel de governança. As duas telas renderizam o mesmo partial Jinja
`complementos/_lista_entregas_partial.html` consumindo as `linhas` produzidas
aqui — assim, qualquer mudança em estrutura/regra reflete em ambas.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ...models import EntregaRelatorio, Relatorio, Secao, User
from ...notificacoes.ciclo_params import (
    obter_parametros_ciclo,
    periodo_referente_para_data,
)

DIA_LIMITE_PARTICIPA_MES_CORRENTE = 10


def _hoje_brt() -> date:
    """Data 'hoje' em America/Sao_Paulo (fallback UTC). Duplica a lógica
    de ``app.notificacoes.service.agora_brt`` para manter este módulo
    livre de ciclos de import com o pacote ``notificacoes``.
    """
    try:
        from zoneinfo import ZoneInfo  # pylint: disable=import-outside-toplevel
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:  # pylint: disable=broad-except
        return datetime.now(timezone.utc).date()


def garantir_entregas_relatorio(db: Session, rel: Relatorio) -> int:
    """Garante que exista 1 ``EntregaRelatorio`` por autor com notificações
    ativas para o relatório dado. Cria as faltantes com ``status='pendente'``.

    Idempotente: reexecutar não duplica (``uq_entrega_rel_user`` + filtro
    existente). Chamado em dois pontos: (a) no ``abrir_periodo`` (cria junto
    com o relatório); (b) no início de ``montar_lista_entregas`` (reconcilia
    relatórios antigos e autores criados após a abertura). Retorna a
    quantidade de linhas inseridas.
    """
    existentes: set[int] = {
        uid
        for (uid,) in db.query(EntregaRelatorio.user_id).filter(
            EntregaRelatorio.relatorio_id == rel.id
        )
    }
    autores_ativos = (
        db.query(User)
        .filter(User.role == "autor", User.notificacoes_ativas.is_(True))
        .all()
    )
    criadas = 0
    for u in autores_ativos:
        if u.id in existentes:
            continue
        db.add(
            EntregaRelatorio(
                relatorio_id=rel.id,
                user_id=u.id,
                status="pendente",
            )
        )
        criadas += 1
    if criadas:
        db.flush()
    return criadas


def garantir_entregas_para_autor(db: Session, user: User) -> int:
    """Garante que ``user`` tenha 1 ``EntregaRelatorio`` (status='pendente')
    em todos os relatórios ainda não finalizados. Usada quando um autor é
    cadastrado ou promovido ao papel 'autor' — o FK ``user_id`` da entrega
    já aponta para ``users`` e este hook mantém a tabela persistente em
    sincronia com as dimensões.

    Regra de entrada: se o cadastro ocorre entre os dias 1 e
    ``DIA_LIMITE_PARTICIPA_MES_CORRENTE`` (inclusive) em Brasília, o autor
    **não** é vinculado ao relatório do mês corrente (cujo período está a
    fechar); só passa a responder a partir do relatório do mês seguinte.

    Idempotente: respeita ``uq_entrega_rel_user`` e só insere onde falta.
    Retorna a quantidade inserida. Ignora users que não sejam autores ou
    estejam com ``notificacoes_ativas=False``.
    """
    if user.role != "autor" or not user.notificacoes_ativas:
        return 0

    hoje_brt = _hoje_brt()
    mes_ref_a_pular: str | None = None
    if hoje_brt.day <= DIA_LIMITE_PARTICIPA_MES_CORRENTE:
        parametros = obter_parametros_ciclo(db)
        periodo = periodo_referente_para_data(hoje_brt, parametros)
        mes_ref_a_pular = periodo["mes_referencia"]

    relatorios_abertos = (
        db.query(Relatorio).filter(Relatorio.status != "finalizado").all()
    )
    existentes: set[int] = {
        rid
        for (rid,) in db.query(EntregaRelatorio.relatorio_id).filter(
            EntregaRelatorio.user_id == user.id
        )
    }
    criadas = 0
    for rel in relatorios_abertos:
        if rel.id in existentes:
            continue
        if mes_ref_a_pular is not None and rel.mes_referencia == mes_ref_a_pular:
            continue
        db.add(
            EntregaRelatorio(
                relatorio_id=rel.id,
                user_id=user.id,
                status="pendente",
            )
        )
        criadas += 1
    if criadas:
        db.flush()
    return criadas


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

    Antes de consultar, chama ``garantir_entregas_relatorio`` para reconciliar
    o modelo: todo autor ativo tem sempre uma linha, mesmo que o
    ``abrir_periodo`` ainda não tenha rodado para o relatório.
    """
    criadas = garantir_entregas_relatorio(db, rel)
    if criadas:
        db.commit()

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
