"""Resolução de marcadores estáveis ``[[REF:tipo|id]]`` para texto legível.

Usado pelo PDF/HTML do relatório e pela API/UI para pré-visualização do mesmo
formato de exibição: Figura ou Tabela ``{capítulo}.{sequência}`` (ex.: ``4.1``, ``3.2``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, selectinload

from .models import Relatorio, Secao

_RE_REF = re.compile(r"\[\[REF:(figura|tabela|secao)\|(\d+)\]\]")


@dataclass(frozen=True)
class MapasRef:
    """IDs estáveis → rótulos numéricos atuais (string já sem prefixo Figura/Tabela)."""

    figuras: dict[int, str] = field(default_factory=dict)
    tabelas: dict[int, str] = field(default_factory=dict)
    secoes: dict[int, str] = field(default_factory=dict)

    def vazio(self) -> bool:
        return not (self.figuras or self.tabelas or self.secoes)


def label_numero_pli(sec_top: str, n: int) -> str:
    """Rótulo por capítulo: ``capítulo.sequência`` (ex.: ``4.1``)."""
    return f"{sec_top}.{n}" if sec_top else str(n)


def idx_efetivo_marcador(idx_raw: str, derivado: str) -> str:
    """Resolve ``idx`` em ``[[FIGURA:idx|…]]`` / ``[[TABELA:idx|…]]``.

    - Só dígitos: sequência global explícita (ex.: ``12``).
    - Qualquer outro valor (vazio, ``4.1``, ``4-1``, legado): usa ``derivado``
      (``label_numero_pli`` por secção).
    """
    raw = (idx_raw or "").strip()
    if raw.isdigit():
        return raw
    return derivado


def calcular_mapas_referencia(secoes_relatorio) -> MapasRef:
    """Replica a contagem do ``pdf_render`` para mapear IDs de bloco/seção.

    Apenas blocos ``tipo=figura``/``tipo=tabela`` geram entrada nos mapas de
    bloco. Marcadores ``[[FIGURA:`` / ``[[TABELA`` inline em texto contam para o
    contador mas não criam entrada nos mapas.
    """
    mapas = MapasRef()
    fig_by_top: dict[str, int] = {}
    tab_by_top: dict[str, int] = {}
    for sec in secoes_relatorio:
        if sec.numero:
            mapas.secoes[sec.id] = sec.numero
        sec_top = (sec.numero or "").split(".")[0]
        fig_counter = fig_by_top.get(sec_top, 0)
        tab_counter = tab_by_top.get(sec_top, 0)
        for bloco in sec.blocos:
            if bloco.tipo == "figura":
                fig_counter += 1
                mapas.figuras[bloco.id] = label_numero_pli(sec_top, fig_counter)
            elif bloco.tipo == "tabela":
                tab_counter += 1
                mapas.tabelas[bloco.id] = label_numero_pli(sec_top, tab_counter)
            elif bloco.conteudo:
                fig_counter += len(re.findall(r"\[\[FIGURA:", bloco.conteudo))
                tab_counter += len(re.findall(r"\[\[TABELA(?::|\||\]\])", bloco.conteudo))
        fig_by_top[sec_top] = fig_counter
        tab_by_top[sec_top] = tab_counter
    return mapas


def resolver_referencias(texto: str | None, mapas: MapasRef) -> str:
    """Substitui ``[[REF:..]]`` por texto humano (Figura/Tabela/Seção …)."""
    if not texto or "[[REF:" not in texto:
        return texto or ""

    def _sub(match: re.Match) -> str:
        tipo = match.group(1)
        alvo = int(match.group(2))
        if tipo == "figura":
            numero = mapas.figuras.get(alvo)
            if numero:
                return f"Figura {numero}"
        elif tipo == "tabela":
            numero = mapas.tabelas.get(alvo)
            if numero:
                return f"Tabela {numero}"
        elif tipo == "secao":
            numero = mapas.secoes.get(alvo)
            if numero:
                return f"Se\u00e7\u00e3o {numero}"
        return match.group(0)

    return _RE_REF.sub(_sub, texto)


def mapas_para_json(mapas: MapasRef) -> dict[str, dict[str, str]]:
    """Serialização para JSON (chaves inteiras como string)."""
    return {
        "figuras": {str(k): v for k, v in mapas.figuras.items()},
        "tabelas": {str(k): v for k, v in mapas.tabelas.items()},
        "secoes": {str(k): v for k, v in mapas.secoes.items()},
    }


def carregar_relatorio_com_secoes_e_blocos(db: Session, rel_id: int) -> Relatorio | None:
    """Carrega relatório com ``secoes`` e ``blocos`` (``order_by`` do modelo)."""
    return (
        db.query(Relatorio)
        .options(selectinload(Relatorio.secoes).selectinload(Secao.blocos))
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
