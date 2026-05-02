"""Regras para edição manual de entregas na governança."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ...auth import current_user
from ...models import ENTREGA_STATUS_VALIDOS, EntregaRelatorio, User
from .datas_horarios import parse_datetime_local_para_utc


@dataclass(frozen=True)
class DadosEdicaoEntrega:
    """Campos editáveis da entrega recebidos pelo formulário de governança."""

    status: str
    data_envio: str
    data_validacao: str
    validado_por_id: str


def validar_e_aplicar_edicao_entrega(
    db: Session,
    entrega: EntregaRelatorio,
    dados: DadosEdicaoEntrega,
) -> str | None:
    st = (dados.status or "").strip()
    if st not in ENTREGA_STATUS_VALIDOS:
        return "status+invalido"
    try:
        entrega.data_envio = parse_datetime_local_para_utc(dados.data_envio)
        entrega.data_validacao = parse_datetime_local_para_utc(dados.data_validacao)
    except ValueError:
        return "data+invalida"
    validador_raw = (dados.validado_por_id or "").strip()
    if not validador_raw:
        entrega.validado_por_id = None
    else:
        try:
            validador_id = int(validador_raw)
        except ValueError:
            return "validado_por+invalido"
        if db.get(User, validador_id) is None:
            return "utilizador+validador+inexistente"
        entrega.validado_por_id = validador_id
    entrega.status = st
    return None


def salvar_entrega_governanca(
    db: Session,
    entrega: EntregaRelatorio,
    request,
    dados: DadosEdicaoEntrega,
) -> str | None:
    erro = validar_e_aplicar_edicao_entrega(db, entrega, dados)
    if erro:
        return erro
    entrega.atualizado_em = datetime.utcnow()
    viewer = current_user(request, db)
    if viewer:
        entrega.atualizado_por_id = viewer.id
    db.commit()
    return None
