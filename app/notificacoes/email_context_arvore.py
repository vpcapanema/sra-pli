"""Arvore de secoes com URLs para corpo HTML/texto dos e-mails de notificacao."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Protocol

from ..config import settings
from ..models import SECOES_PADRAO


class _SecaoArvoreLike(Protocol):
    """Objeto com os atributos lidos por ``arvore_secoes_com_links``."""

    id: int
    ordem: int
    numero: Any
    titulo: Any


def _partes_numero_secao(numero: object) -> tuple[int, ...] | None:
    """Partes inteiras de ``numero`` (ex.: ``4.4.6`` → ``(4, 4, 6)``); inválido/vazio → ``None``."""
    raw = str(numero or "").strip()
    if not raw:
        return None
    partes: list[int] = []
    for p in raw.split("."):
        try:
            partes.append(int(p, 10))
        except ValueError:
            return None
    return tuple(partes)


def _chave_ordenacao_arvore(sec: _SecaoArvoreLike) -> tuple:
    """Ordena por hierarquia do número (pai antes do filho), depois ``ordem``.

    Só ``ordem`` bastava se a lista já viesse em pré-ordem; quando não vem,
    o algoritmo por pilha colocava filhos na raiz ou perdia níveis.
    """
    partes = _partes_numero_secao(sec.numero)
    if partes is None:
        return ((99_999,), sec.ordem)
    return (partes, sec.ordem)


def link_upload_secao(rel_id: int, sec_id: int) -> str:
    return (
        f"{settings.APP_BASE_URL.rstrip('/')}"
        f"/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo"
    )


def link_dotx_secao(rel_id: int, sec_id: int) -> str:
    return (
        f"{settings.APP_BASE_URL.rstrip('/')}"
        f"/relatorios/{rel_id}/secoes/{sec_id}/modelo.dotx"
    )


def arvore_secoes_com_links(rel_id: int, secoes_flat: list[_SecaoArvoreLike]) -> list[dict]:
    """Arvore aninhada com links de upload e modelo ``.dotx`` por secao."""
    raiz: list[dict] = []
    pilha: list[tuple[int, dict]] = []
    for sec in sorted(secoes_flat, key=_chave_ordenacao_arvore):
        numero = str(sec.numero or "")
        nivel = numero.count(".") + 1 if numero else 1
        node: dict = {
            "numero": numero,
            "titulo": sec.titulo,
            "link_upload": link_upload_secao(rel_id, sec.id),
            "link_dotx": link_dotx_secao(rel_id, sec.id),
            "filhos": [],
        }
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        if pilha:
            pilha[-1][1]["filhos"].append(node)
        else:
            raiz.append(node)
        pilha.append((nivel, node))
    return raiz


def arvore_secoes_padrao_para_preview(rel_id: int) -> list[dict]:
    """Árvore completa do sumário canônico (``SECOES_PADRAO``) com IDs sintéticos.

    Usada no preview sem base de dados e na exportação estática em ``tmp/``.
    Os links apontam para ``/relatorios/{rel_id}/secoes/{id}/…`` como no envio real.
    """
    fake: list[_SecaoArvoreLike] = [
        SimpleNamespace(ordem=i, numero=num, titulo=tit, id=10_000 + i)
        for i, (num, tit) in enumerate(SECOES_PADRAO)
    ]
    return arvore_secoes_com_links(rel_id, fake)


def format_arvore_secoes_email_plaintext(nodes: list[dict], *, apenas_dotx: bool) -> str:
    """Texto indentado por nivel (corpo plano do e-mail e previews)."""
    linhas: list[str] = []

    def walk(ns: list[dict], depth: int) -> None:
        prefixo = "  " * depth
        for no in ns:
            linhas.append(f"{prefixo}{no['numero']} {no['titulo']}")
            if apenas_dotx:
                linhas.append(f"{prefixo}  → modelo .dotx: {no['link_dotx']}")
            else:
                linhas.append(f"{prefixo}  → enviar conteudo: {no['link_upload']}")
                linhas.append(f"{prefixo}  → modelo .dotx: {no['link_dotx']}")
            walk(no["filhos"], depth + 1)

    walk(nodes, 0)
    return "\n".join(linhas)
