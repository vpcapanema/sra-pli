"""Numeracao hierarquica e insercao de secoes (logica usada por rotas de relatorios)."""

import re
from sqlalchemy.orm import Session

from ..db import tx_session
from ..models import Secao
from ..numeracao import consolidar_referencias, renumerar_relatorio


def _ordem_for_numero(numero: str) -> tuple:
    """Chave de ordenação tipo (1, 2, 3) para '4.4.6.1'."""
    parts = []
    for p in numero.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _numero_livre_no_nivel(secoes: list[Secao], nivel: int, prefixo: str) -> str:
    """Devolve um numero livre no nivel/prefixo indicado.

    Varre TODAS as secoes (inclusive descendentes) sob ``prefixo`` e toma a
    K-esima parte (``K = nivel - 1``); o resultado e ``prefixo + (max + 1)``,
    garantindo zero colisao com numeros existentes ou com qualquer prefixo de
    descendente. Necessario para inserir com shift-on-insert sem violar
    ``UniqueConstraint(relatorio_id, numero)`` antes da renumeracao.
    """
    sufixos: list[int] = []
    for sec in secoes:
        num = sec.numero or ""
        partes = num.split(".")
        if len(partes) < nivel:
            continue
        if prefixo and not num.startswith(prefixo):
            continue
        try:
            sufixos.append(int(partes[nivel - 1]))
        except ValueError:
            continue
    proximo = (max(sufixos) + 1) if sufixos else 1
    return f"{prefixo}{proximo}"


def _inserir_secao_em_relatorio(
    db_session: Session, rel_id: int, numero: str, titulo: str
) -> None:
    """Insere uma secao na posicao indicada por ``numero`` e renumera a arvore.

    Comportamento:
    - ``numero`` e um HINT DE POSICAO. Se ja existir secao com esse numero,
      a inserida toma a posicao e a existente (e suas irmas posteriores) sao
      empurradas via ``ordem``. A renumeracao recalcula os numeros finais.
    - Para evitar ``IntegrityError`` no flush (UniqueConstraint), a nova
      secao entra com um numero TEMPORARIO LIVRE no mesmo nivel/prefixo
      (``_numero_livre_no_nivel``). O numero final sai do ``renumerar_relatorio``.
    - Limitacao contratual D20: ``renumerar_relatorio`` PRESERVA o numero das
      raizes (``numeracao.py``). Inserir entre raizes nao desloca; a nova fica
      no proximo slot livre. O frontend reflete isso oferecendo max+1 no nivel 1.

    Aplica em transacao explicita: consolida referencias textuais ANTES da
    mutacao (estabiliza alvos por id), desloca a ``ordem`` das irmas posteriores,
    persiste a nova secao e renumera por DFS.
    """
    todas = db_session.query(Secao).filter_by(relatorio_id=rel_id).all()
    partes_alvo = numero.split(".")
    nivel = len(partes_alvo)
    prefixo_alvo = ".".join(partes_alvo[:-1]) + "." if nivel > 1 else ""
    raiz_em_conflito = nivel == 1 and any((s.numero or "") == numero for s in todas)
    if raiz_em_conflito:
        nova_ordem = len(todas)
        ids_deslocar: list[int] = []
    else:
        chave_alvo = _ordem_for_numero(numero)
        nova_ordem = sum(
            1 for s in todas if _ordem_for_numero(s.numero) < chave_alvo
        )
        ids_deslocar = [
            s.id for s in todas if _ordem_for_numero(s.numero) >= chave_alvo
        ]
    numero_temp = _numero_livre_no_nivel(todas, nivel, prefixo_alvo)
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        if ids_deslocar:
            txdb.query(Secao).filter(Secao.id.in_(ids_deslocar)).update(
                {Secao.ordem: Secao.ordem + 1}, synchronize_session=False
            )
        txdb.add(
            Secao(
                relatorio_id=rel_id,
                numero=numero_temp,
                titulo=titulo,
                ordem=nova_ordem,
            )
        )
        txdb.flush()
        renumerar_relatorio(txdb, rel_id)


def _proximo_numero_filho(
    db_session: Session,
    rel_id: int,
    pai_numero: str,
) -> str:
    """Calcula o proximo numero de filha direta de ``pai_numero``.

    Retorna ``{pai_numero}.{max_filha_direta + 1}``, ou ``{pai_numero}.1``
    quando ainda nao ha filhas diretas. Considera apenas filhas no nivel
    imediatamente abaixo (ignora netos).
    """
    nivel_pai = pai_numero.count(".")
    prefixo = pai_numero + "."
    sufixos: list[int] = []
    for sec in db_session.query(Secao).filter_by(relatorio_id=rel_id).all():
        num = sec.numero or ""
        if not num.startswith(prefixo) or num.count(".") != nivel_pai + 1:
            continue
        try:
            sufixos.append(int(num[len(prefixo):]))
        except ValueError:
            continue
    proximo = (max(sufixos) + 1) if sufixos else 1
    return f"{prefixo}{proximo}"


RE_NUMERO_SECAO = re.compile(r"^\d+(?:\.\d+)*$")


def _achar_par_swap(
    db: Session, rel_id: int, sec: Secao, direcao: str
) -> tuple[Secao, Secao] | None:
    """Localiza o par (atual, vizinho) para swap entre irmaos diretos.

    Retorna ``None`` se a secao ja esta na borda (mover para cima do primeiro
    ou para baixo do ultimo). Top-level deve ter sido bloqueado antes.
    """
    numero_sec = sec.numero or ""
    nivel = numero_sec.count(".")
    prefixo_pai = ".".join(numero_sec.split(".")[:-1]) + "."
    irmaos = (
        db.query(Secao)
        .filter(
            Secao.relatorio_id == rel_id,
            Secao.numero.like(f"{prefixo_pai}%"),
        )
        .all()
    )
    diretos = sorted(
        (s for s in irmaos if (s.numero or "").count(".") == nivel),
        key=lambda s: (s.ordem or 0, _ordem_for_numero(s.numero or "")),
    )
    pos = next((i for i, s in enumerate(diretos) if s.id == sec.id), -1)
    if pos < 0:
        return None
    alvo = pos - 1 if direcao == "cima" else pos + 1
    if alvo < 0 or alvo >= len(diretos):
        return None
    return diretos[pos], diretos[alvo]
