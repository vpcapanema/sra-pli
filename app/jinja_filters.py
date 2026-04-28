"""Filtros Jinja específicos do SRA.

Registrados nos `Jinja2Templates` que renderizam páginas com `rel` em contexto
(atualmente `app.routes.pages.templates`).
"""
from __future__ import annotations

from typing import Iterable, Mapping


def secoes_arvore(secoes: Iterable, sec_numero: str | None = None) -> list[dict]:
    """Constrói árvore aninhada a partir da lista flat de seções ordenadas.

    Retorna lista de raízes; cada nó tem `sec`, `filhos`, `nivel`, `aberta`
    e `ativa`. `aberta=True` quando o nó é ancestral (ou igual) a `sec_numero`,
    para que a sidebar abra automaticamente o caminho até a seção corrente.
    """
    raiz: list[dict] = []
    pilha: list[dict] = []
    ancestrais: set[str] = set()
    if sec_numero:
        partes = str(sec_numero).split(".")
        for i in range(1, len(partes) + 1):
            ancestrais.add(".".join(partes[:i]))
    for s in secoes or []:
        numero = str(getattr(s, "numero", "") or "")
        nivel = numero.count(".") + 1 if numero else 1
        node: dict = {
            "sec": s,
            "filhos": [],
            "nivel": nivel,
            "aberta": numero in ancestrais,
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
