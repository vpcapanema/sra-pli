"""Parâmetros persistidos do ciclo mensal (período, prazos, calendário de lembretes).

Valores ficam na tabela :class:`ParametrosCicloNotificacao` (linha ``id=1``).
Cron externo não lê esta tabela diretamente: ela orienta horários esperados na
documentação da UI **e** aplica regras no backend (:func:`~.service.abrir_periodo`,
:func:`~.service.enviar_lembretes`, prazos nos e-mails e sugestões de período).

``MESES_PT`` é duplicado de ``service.py``/adjacentes só para evitar importação circular.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TypedDict, Unpack

from sqlalchemy.orm import Session

from ..models import ParametrosCicloNotificacao

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_HH_MM = re.compile(r"^\d{2}:\d{2}$")
_ID_LINHA_UNICA = 1


class CamposCicloFormulario(TypedDict):
    """Payload bruto vindo do POST do formulário (campos em texto)."""

    ciclo_dia_prev: str
    ciclo_dia_atual: str
    prazo_autor: str
    prazo_coord: str
    dias_lembrete_csv: str
    dia_ultima: str
    dia_abertura: str
    hora_aber: str
    hora_lem: str
    hora_ret: str
    observacoes: str


def salvar_parametros_ciclo_form_post_campos(
    db: Session,
    **campos: Unpack[CamposCicloFormulario],
) -> None:
    """Persiste a linha única a partir dos nomes de campos do formulário POST."""
    salvar_parametros_ciclo_form(db, campos)


def try_salvar_parametros_ciclo_form_post_campos(
    db: Session,
    **campos: Unpack[CamposCicloFormulario],
) -> str | None:
    """Como :func:`salvar_parametros_ciclo_form_post_campos`; devolve texto de erro ou ``None``."""
    try:
        salvar_parametros_ciclo_form_post_campos(db, **campos)
    except ValueError as err:
        return str(err)
    return None


def dia_util_no_mes(ano: int, mes: int, dia_escolha: int) -> int:
    """Garante ``dia_escolha`` dentro do mês ``ano/mes`` (ex.: não 31 em fevereiro)."""
    ultimo = calendar.monthrange(ano, mes)[1]
    if dia_escolha < 1:
        return 1
    return min(dia_escolha, ultimo)


@dataclass(frozen=True)
class ParametrosCicloDTO:  # pylint: disable=too-many-instance-attributes
    """Snapshot imutável usado pela lógica de negócio (sem objeto ORM vivo)."""

    ciclo_dia_mes_anterior: int = 11
    ciclo_dia_mes_atual: int = 11
    prazo_autor_dia: int = 8
    prazo_coordenacao_dia: int = 10
    dias_lembrete: tuple[int, ...] = (5, 8)
    dia_ultima_chamada: int = 10
    dia_abertura_novo_ciclo: int = 1
    hora_abertura_brt_hhmm: str = "03:00"
    hora_lembretes_brt_hhmm: str = "09:00"
    hora_retry_brt_hhmm: str = "12:00"
    observacoes_internas: str = ""

    @classmethod
    def padrao(cls) -> ParametrosCicloDTO:
        return cls()


def _validar_hhmm(val: str) -> str:
    s = val.strip()
    if not _HH_MM.match(s):
        raise ValueError("Horário deve ser HH:MM (00–23:00–59).")
    hora_txt, min_txt = s.split(":")
    hora_i = int(hora_txt)
    min_i = int(min_txt)
    if hora_i < 0 or hora_i > 23 or min_i < 0 or min_i > 59:
        raise ValueError("Horário fora dos limites válidos.")
    return f"{hora_i:02d}:{min_i:02d}"


def _normalizar_csv_dias(csv: str) -> tuple[int, ...]:
    out: list[int] = []
    for parte in csv.split(","):
        tok = parte.strip()
        if not tok:
            continue
        dia = int(tok)
        if dia < 1 or dia > 31:
            raise ValueError("Dias devem estar entre 1 e 31.")
        out.append(dia)
    if not out:
        raise ValueError("Informe pelo menos um dia para lembretes (ex.: 5, 8).")
    return tuple(sorted(dict.fromkeys(out)))


def _parcelas_formulario(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    ciclo_dia_prev: str,
    ciclo_dia_atual: str,
    prazo_autor: str,
    prazo_coord: str,
    dias_lembrete_csv: str,
    dia_ultima: str,
    dia_abertura: str,
    hora_aber: str,
    hora_lem: str,
    hora_ret: str,
    observacoes: str | None,
) -> dict:
    errors: list[str] = []

    def _int_or_err(chave_val: tuple[str, str], min_v: int, max_v: int) -> int | None:
        label, raw = chave_val
        try:
            n = int((raw or "").strip())
        except ValueError:
            errors.append(f"{label}: inteiro obrigatório.")
            return None
        if n < min_v or n > max_v:
            errors.append(f"{label}: usar entre {min_v} e {max_v}.")
            return None
        return n

    d_prev = _int_or_err(("Dia início período (mês anterior)", ciclo_dia_prev), 1, 31)
    d_cur = _int_or_err(("Dia fim período (mês referência)", ciclo_dia_atual), 1, 31)
    pa = _int_or_err(("Prazo conteúdo autor no mês-ref.", prazo_autor), 1, 31)
    pc = _int_or_err(("Prazo coordenação no mês-ref.", prazo_coord), 1, 31)
    duc = _int_or_err(("Dia da última chamada", dia_ultima), 1, 31)
    dab = _int_or_err(("Dia útil de abrir novo relatório", dia_abertura), 1, 31)
    if errors:
        raise ValueError(" ".join(errors))

    dias_tup = _normalizar_csv_dias(dias_lembrete_csv)
    hh_a = _validar_hhmm(hora_aber)
    hh_l = _validar_hhmm(hora_lem)
    hh_r = _validar_hhmm(hora_ret)

    obs = (observacoes or "").strip()[:2048]

    assert d_prev is not None and d_cur is not None and pa is not None
    assert pc is not None and duc is not None and dab is not None

    if pa >= pc:
        raise ValueError("O prazo do autor deve correr antes do da coordenação.")

    return {
        "ciclo_dia_mes_anterior": d_prev,
        "ciclo_dia_mes_atual": d_cur,
        "prazo_autor_dia": pa,
        "prazo_coordenacao_dia": pc,
        "dias_lembrete_csv": ",".join(str(x) for x in dias_tup),
        "dia_ultima_chamada": duc,
        "dia_abertura_novo_ciclo": dab,
        "hora_abertura_brt_hhmm": hh_a,
        "hora_lembretes_brt_hhmm": hh_l,
        "hora_retry_brt_hhmm": hh_r,
        "observacoes_internas": obs or None,
        "atualizado_em": datetime.utcnow(),
    }


def parametros_para_dto(row: ParametrosCicloNotificacao | None) -> ParametrosCicloDTO:
    """Converte ORM (:mod:`models`) em DTO; ``None`` => defaults."""
    if row is None:
        return ParametrosCicloDTO.padrao()
    dias = tuple(
        int(x.strip())
        for x in row.dias_lembrete_csv.split(",")
        if x.strip().isdigit()
    )
    if not dias:
        dias = ParametrosCicloDTO.padrao().dias_lembrete
    return ParametrosCicloDTO(
        ciclo_dia_mes_anterior=max(1, min(31, int(row.ciclo_dia_mes_anterior))),
        ciclo_dia_mes_atual=max(1, min(31, int(row.ciclo_dia_mes_atual))),
        prazo_autor_dia=max(1, min(31, int(row.prazo_autor_dia))),
        prazo_coordenacao_dia=max(1, min(31, int(row.prazo_coordenacao_dia))),
        dias_lembrete=dias,
        dia_ultima_chamada=max(1, min(31, int(row.dia_ultima_chamada))),
        dia_abertura_novo_ciclo=max(1, min(31, int(row.dia_abertura_novo_ciclo))),
        hora_abertura_brt_hhmm=(row.hora_abertura_brt_hhmm or "03:00").strip(),
        hora_lembretes_brt_hhmm=(row.hora_lembretes_brt_hhmm or "09:00").strip(),
        hora_retry_brt_hhmm=(row.hora_retry_brt_hhmm or "12:00").strip(),
        observacoes_internas=(row.observacoes_internas or ""),
    )


def obter_parametros_ciclo(db: Session) -> ParametrosCicloDTO:
    """Carrega persistido ou valores padrão (sem criar linha)."""
    linha = db.get(ParametrosCicloNotificacao, _ID_LINHA_UNICA)
    return parametros_para_dto(linha)


def periodo_referente_para_data(hoje: date, parametros: ParametrosCicloDTO | None = None) -> dict:
    """Mesma forma que o antigo ``_periodo_atual``: chaves ``periodo_inicio``,
    ``periodo_fim``, ``mes_referencia``."""
    parametros = parametros or ParametrosCicloDTO.padrao()
    ano, mes_atual = hoje.year, hoje.month
    if mes_atual == 1:
        ano_prev, mes_prev = ano - 1, 12
    else:
        ano_prev, mes_prev = ano, mes_atual - 1

    dia_start = parametros.ciclo_dia_mes_anterior
    dia_end = parametros.ciclo_dia_mes_atual
    ini = date(
        ano_prev,
        mes_prev,
        dia_util_no_mes(ano_prev, mes_prev, dia_start),
    )
    fim = date(
        ano,
        mes_atual,
        dia_util_no_mes(ano, mes_atual, dia_end),
    )
    mes_ref_txt = f"{MESES_PT[fim.month - 1]}/{fim.year}"
    return {
        "periodo_inicio": ini,
        "periodo_fim": fim,
        "mes_referencia": mes_ref_txt,
    }


def salvar_parametros_ciclo_form(db: Session, pack: CamposCicloFormulario) -> None:
    """Atualiza a linha ``id=1`` (criando se não existir). Erro só ValueError."""
    valores = _parcelas_formulario(
        ciclo_dia_prev=pack["ciclo_dia_prev"],
        ciclo_dia_atual=pack["ciclo_dia_atual"],
        prazo_autor=pack["prazo_autor"],
        prazo_coord=pack["prazo_coord"],
        dias_lembrete_csv=pack["dias_lembrete_csv"],
        dia_ultima=pack["dia_ultima"],
        dia_abertura=pack["dia_abertura"],
        hora_aber=pack["hora_aber"],
        hora_lem=pack["hora_lem"],
        hora_ret=pack["hora_ret"],
        observacoes=pack["observacoes"],
    )
    linha = db.get(ParametrosCicloNotificacao, _ID_LINHA_UNICA)
    if linha is None:
        linha = ParametrosCicloNotificacao(id=_ID_LINHA_UNICA)
        db.add(linha)
    for chave, v in valores.items():
        setattr(linha, chave, v)
    db.commit()
