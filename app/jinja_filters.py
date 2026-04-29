"""Filtros Jinja específicos do SRA.

Registrados nos `Jinja2Templates` que renderizam páginas com `rel` em contexto
(atualmente `app.routes.pages.templates`).
"""
from __future__ import annotations

from typing import Iterable, Mapping


def _numero_ordem_tuple(numero: str) -> tuple:
    """Chave de ordenação para hierarquia 1 < 1.2 < 1.10 < 2 (segmentos numéricos)."""
    partes = str(numero or "").strip().split(".")
    saida: list[int] = []
    for p in partes:
        p = p.strip()
        if not p:
            continue
        try:
            saida.append(int(p, 10))
        except ValueError:
            saida.append(-1)
    return tuple(saida) if saida else (999999,)


def secoes_arvore(
    secoes: Iterable,
    sec_numero: str | None = None,
    abrir_caminho: bool = True,
) -> list[dict]:
    """Constrói árvore aninhada a partir da lista flat de seções ordenadas.

    Retorna lista de raízes; cada nó tem `sec`, `filhos`, `nivel`, `aberta`
    e `ativa`. Com `abrir_caminho=True`, `aberta=True` nos ancestrais de
    `sec_numero` (atributo open nos details). Com `False`, tudo recolhido no HTML
    mas `ativa` continua a marcar a secção corrente.
    """
    raiz: list[dict] = []
    pilha: list[dict] = []
    ancestrais: set[str] = set()
    if sec_numero and abrir_caminho:
        partes = str(sec_numero).split(".")
        for i in range(1, len(partes) + 1):
            ancestrais.add(".".join(partes[:i]))
    lista = list(secoes or [])
    lista.sort(
        key=lambda s: (
            _numero_ordem_tuple(getattr(s, "numero", "") or ""),
            getattr(s, "ordem", 0) or 0,
            getattr(s, "id", 0) or 0,
        )
    )
    for s in lista:
        numero = str(getattr(s, "numero", "") or "")
        nivel = numero.count(".") + 1 if numero else 1
        node: dict = {
            "sec": s,
            "filhos": [],
            "nivel": nivel,
            "aberta": bool(ancestrais) and numero in ancestrais,
            "ativa": bool(sec_numero) and numero == str(sec_numero),
        }
        while pilha and pilha[-1]["nivel"] >= nivel:
            pilha.pop()
        (pilha[-1]["filhos"] if pilha else raiz).append(node)
        pilha.append(node)
    return raiz


def registrar(env_filters: Mapping) -> None:
    """Registra os filtros do SRA em `Jinja2Templates(...).env.filters`."""
    env_filters["secoes_arvore"] = secoes_arvore


def registrar_globais(env) -> None:
    """Globais Jinja (todas as páginas que usam este `Environment`).

    `sra_console_verbose`: com ``APP_ENV=development``, o `base.html` define
    `window.__SRA_CONSOLE_VERBOSE__` para `sra_log.js` emitir `debug`/`info`
    no console do browser mesmo quando o hostname não é loopback (ex.: Linux
    em LAN a apontar para o servidor de desenvolvimento).
    """
    from .config import settings

    env.globals["sra_console_verbose"] = (getattr(settings, "APP_ENV", "") or "").lower() == "development"
