from __future__ import annotations

import re
from unicodedata import normalize

from sqlalchemy.orm import Session

from ..models import Secao, User

_AUTO_RESPONSAVEL_POR_SECAO: dict[str, str] = {
    "3": "raquel",
    "4.1": "luciana",
    "4.2": "raquel",
    "4.3": "cris",
    "4.5": "raquel",
    "10": "raquel",
}

_SECOES_ESTATICAS_SISTEMA: frozenset[str] = frozenset(
    {
        "1",
        "2",
        "5",
        "6",
        "8",
        "11",
        "ap. 1",
    }
)


def normalizar_numero_secao(numero: str | None) -> str:
    texto = (numero or "").strip().lower()
    texto = re.sub(r"\s+", " ", texto)
    return texto.rstrip(".")


def secao_estatica_sistema(numero: str | None) -> bool:
    return normalizar_numero_secao(numero) in _SECOES_ESTATICAS_SISTEMA


def _normalizar_nome(nome: str | None) -> str:
    texto = normalize("NFKD", nome or "")
    texto = "".join(ch for ch in texto if ch.isascii())
    return texto.casefold()


def _autor_por_apelido(db: Session, apelido: str) -> User | None:
    alvo = _normalizar_nome(apelido)
    autores = db.query(User).filter(User.role == "autor").all()
    for autor in autores:
        nome = _normalizar_nome(autor.nome)
        email = _normalizar_nome(autor.email)
        if alvo in nome or alvo in email:
            return autor
    return None


def aplicar_responsaveis_padrao(db: Session, relatorio_id: int) -> None:
    cache: dict[str, User | None] = {}
    secoes = db.query(Secao).filter(Secao.relatorio_id == relatorio_id).all()
    for secao in secoes:
        numero = normalizar_numero_secao(secao.numero)
        apelido = _AUTO_RESPONSAVEL_POR_SECAO.get(numero)
        if not apelido:
            secao.responsavel_id = None
            continue
        if apelido not in cache:
            cache[apelido] = _autor_por_apelido(db, apelido)
        autor = cache[apelido]
        secao.responsavel_id = autor.id if autor is not None else None
