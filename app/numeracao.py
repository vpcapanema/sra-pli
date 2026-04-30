"""Numeracao hierarquica consolidada de secoes, figuras e tabelas.

Este modulo concentra as duas operacoes que mantem a integridade dos indices
do relatorio quando o usuario insere, exclui ou move secoes/blocos:

- ``renumerar_relatorio`` recalcula ``Secao.numero`` e ``Secao.ordem`` em
  varredura DFS sobre a arvore inferida pelo prefixo do numero atual e pela
  ordem dos irmaos. Aplica em duas fases para nao colidir com o
  ``UniqueConstraint(relatorio_id, numero)``.
- ``consolidar_referencias`` varre o conteudo dos blocos antes da renumeracao,
  detecta referencias textuais a "Figura X.Y", "Tabela X.Y" e "Secao X.Y" e
  troca por marcadores ``[[REF:tipo|alvo_id]]`` baseados em IDs estaveis
  (``Bloco.id`` para figuras/tabelas, ``Secao.id`` para secoes). Os marcadores
  sao resolvidos no momento do render, sempre exibindo o numero atual.

A numeracao de figuras e tabelas ja e derivada em ``app/pdf_render.py``
(contador por primeiro nivel da secao). Aqui cuidamos apenas da numeracao das
secoes e da consolidacao das referencias textuais que ficariam obsoletas.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import case, text, update
from sqlalchemy.orm import Session

from .models import Bloco, Secao


# Prefixo temporario usado na fase 1 da renumeracao para evitar colisao com o
# UniqueConstraint(relatorio_id, numero). Curto o suficiente para caber em
# ``String(16)`` mesmo para ids longos.
_TMP_PREFIX = "__t"

# Regex para deteccao de referencias textuais. Aceita tanto "4.1" quanto "4-1"
# (separador comum em legendas oficiais do contrato).
# Referências textuais: aceita ``4.1``, ``4-1``, ``4 - 1`` etc.
_RE_FIGURA_TXT = re.compile(r"\bFigura\s+(\d+(?:\s*[.\-]\s*\d+)+)\b", re.IGNORECASE)
_RE_TABELA_TXT = re.compile(r"\bTabela\s+(\d+(?:\s*[.\-]\s*\d+)+)\b", re.IGNORECASE)
_RE_SECAO_TXT = re.compile(r"\b(?:Se(?:c|\u00e7)(?:a|\u00e3)o)\s+(\d+(?:\.\d+)*)\b")

# Regex para evitar reprocessar texto ja convertido (idempotencia).
_RE_REF_EXISTENTE = re.compile(r"\[\[REF:(figura|tabela|secao)\|\d+\]\]")


def chave_numero(numero: str) -> tuple:
    """Chave de ordenacao tipo (1, 4, 7) para '1.4.7'.

    Mantem strings nao-numericas em uma classe separada para evitar TypeError
    em comparacoes mistas. Identica em espirito a ``_secao_sort_key`` de
    ``app/routes/importacao.py``; centralizar aqui evita drift.
    """
    partes: list[tuple[int, int | str]] = []
    for parte in (numero or "").split("."):
        if parte.isdigit():
            partes.append((0, int(parte)))
        else:
            partes.append((1, parte.lower()))
    return tuple(partes)


def secao_ids_na_subarvore(secoes: Iterable[Secao], anc_numero: str) -> set[int]:
    """IDs das seções cujo número é ``anc_numero`` ou é descendente na hierarquia PLI.

    Descendência: prefixo ``anc_numero + '.'`` (ex.: âncora ``4.3`` inclui ``4.3.1``,
    ``4.3.10``; não inclui ``4.31`` nem ``4``).
    """
    base = (anc_numero or "").strip()
    if not base:
        return set()
    pref = base + "."
    out: set[int] = set()
    for sec in secoes:
        n = (sec.numero or "").strip()
        if n == base or n.startswith(pref):
            out.add(sec.id)
    return out


def _construir_arvore(secoes: list[Secao]) -> dict[str, list[Secao]]:
    """Agrupa filhos por pai usando o prefixo do numero atual.

    Raizes ficam em ``children[""]``. Secoes com pai ausente sao tratadas como
    raizes (caso patologico) para nao perder a secao na renumeracao.
    """
    by_num = {(s.numero or ""): s for s in secoes}
    children: dict[str, list[Secao]] = defaultdict(list)
    for sec in secoes:
        partes = (sec.numero or "").split(".")
        if len(partes) <= 1:
            children[""].append(sec)
            continue
        pai = ".".join(partes[:-1])
        if pai in by_num:
            children[pai].append(sec)
        else:
            children[""].append(sec)
    for filhos in children.values():
        filhos.sort(key=lambda s: (s.ordem or 0, chave_numero(s.numero or "")))
    return children


def _renumerar_arvore(
    children: dict[str, list[Secao]],
) -> tuple[dict[int, str], dict[int, int]]:
    """DFS pelas raizes; retorna ({secao_id: numero_novo}, {secao_id: ordem_nova}).

    Top-level (raizes) tem o ``numero`` preservado: a estrutura do contrato
    D20 fixa "4. Atividades", "5. Consideracoes finais" etc., e renumerar
    raizes destruiria essa convencao. Apenas subniveis sao renumerados em
    sequencia (1, 2, 3...) a partir do numero da raiz, garantindo a remocao
    de buracos e propagacao de insercoes/exclusoes ao longo da hierarquia.

    A ``ordem`` e reescrita em sequencia DFS global para que iteracoes
    lineares (sumario, exportacao por ordem) reflitam a hierarquia visivel.
    """
    novo_numero: dict[int, str] = {}
    nova_ordem: dict[int, int] = {}
    contador_ordem = [0]

    def _dfs(prefixo: str, irmaos: list[Secao]) -> None:
        for indice, sec in enumerate(irmaos, start=1):
            if not prefixo:
                numero = sec.numero or str(indice)
            else:
                numero = f"{prefixo}.{indice}"
            novo_numero[sec.id] = numero
            nova_ordem[sec.id] = contador_ordem[0]
            contador_ordem[0] += 1
            filhos = children.get(sec.numero or "", [])
            if filhos:
                _dfs(numero, filhos)

    _dfs("", children.get("", []))
    return novo_numero, nova_ordem


def renumerar_relatorio(db: Session, rel_id: int) -> dict[int, str]:
    """Reaplica numeracao hierarquica a todas as secoes do relatorio.

    Deve rodar dentro de uma transacao explicita (``tx_session`` ou
    ``with db.begin():``) porque executa duas etapas de UPDATE em massa que
    precisam ser atomicas.

    Retorna ``{secao_id: numero_final}`` para todas as secoes do relatorio.
    """
    secoes = db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    if not secoes:
        return {}

    arvore = _construir_arvore(secoes)
    novo_numero, nova_ordem = _renumerar_arvore(arvore)

    sec_atual = {s.id: s for s in secoes}
    diff_numero = {
        sid: num
        for sid, num in novo_numero.items()
        if sid in sec_atual and sec_atual[sid].numero != num
    }
    diff_ordem = {
        sid: ordem
        for sid, ordem in nova_ordem.items()
        if sid in sec_atual and (sec_atual[sid].ordem or 0) != ordem
    }

    if diff_numero:
        # Fase 1: prefixo temporario para soltar UniqueConstraint nas linhas que mudam.
        db.execute(
            text(
                "UPDATE secoes SET numero = :tmp || id::text "
                "WHERE relatorio_id = :rel_id AND id = ANY(:ids)"
            ),
            {"tmp": _TMP_PREFIX, "rel_id": rel_id, "ids": list(diff_numero.keys())},
        )
        # Fase 2: aplica o numero final em UPDATE unico via CASE.
        case_numero = case(*[(Secao.id == sid, num) for sid, num in diff_numero.items()])
        db.execute(
            update(Secao)
            .where(Secao.relatorio_id == rel_id, Secao.id.in_(diff_numero.keys()))
            .values(numero=case_numero)
        )

    if diff_ordem:
        case_ordem = case(*[(Secao.id == sid, ordem) for sid, ordem in diff_ordem.items()])
        db.execute(
            update(Secao)
            .where(Secao.relatorio_id == rel_id, Secao.id.in_(diff_ordem.keys()))
            .values(ordem=case_ordem)
        )

    return novo_numero


def _mapear_blocos_alvo(
    secoes: list[Secao], blocos_por_secao: dict[int, list[Bloco]]
) -> tuple[dict[str, int], dict[str, int]]:
    """Calcula os numeros derivados atuais para blocos ``figura``/``tabela``.

    Retorna ``(figuras_por_numero, tabelas_por_numero)`` mapeando "X.Y"
    (numero exibido) para ``Bloco.id``. Reproduz a contagem por primeiro nivel
    da secao usada em ``app/pdf_render.py`` para que as referencias textuais
    possam ser resolvidas pelo numero exibido hoje.

    Markers ``[[FIGURA:..]]`` inline em blocos de texto contam para o contador,
    mas nao geram entradas no mapa (nao tem ``Bloco.id`` proprio estavel).
    """
    fig_por_top: dict[str, int] = {}
    tab_por_top: dict[str, int] = {}
    figuras: dict[str, int] = {}
    tabelas: dict[str, int] = {}

    for sec in secoes:
        sec_top = (sec.numero or "").split(".")[0]
        for bloco in blocos_por_secao.get(sec.id, []):
            if bloco.tipo == "figura":
                fig_por_top[sec_top] = fig_por_top.get(sec_top, 0) + 1
                rotulo = f"{sec_top}.{fig_por_top[sec_top]}" if sec_top else str(fig_por_top[sec_top])
                figuras.setdefault(rotulo, bloco.id)
            elif bloco.tipo == "tabela":
                tab_por_top[sec_top] = tab_por_top.get(sec_top, 0) + 1
                rotulo = f"{sec_top}.{tab_por_top[sec_top]}" if sec_top else str(tab_por_top[sec_top])
                tabelas.setdefault(rotulo, bloco.id)
            elif bloco.tipo == "texto" and bloco.conteudo:
                # Markers inline contam mas nao mapeiam para id.
                fig_por_top[sec_top] = fig_por_top.get(sec_top, 0) + len(
                    re.findall(r"\[\[FIGURA:", bloco.conteudo)
                )
                tab_por_top[sec_top] = tab_por_top.get(sec_top, 0) + len(
                    re.findall(r"\[\[TABELA(?::|\||\]\])", bloco.conteudo)
                )

    return figuras, tabelas


def _normalizar_numero_legenda(raw: str) -> str:
    """Normaliza para chave ``X.Y`` (remove espaços; ``-`` → ``.``)."""
    s = "".join((raw or "").split())
    return s.replace("-", ".")


def _substituir_referencias(
    texto_in: str,
    figuras: dict[str, int],
    tabelas: dict[str, int],
    secoes_por_numero: dict[str, int],
) -> tuple[str, int]:
    """Substitui referencias textuais por marcadores estaveis. Retorna
    ``(texto_novo, contagem_substituicoes)``."""
    if not texto_in:
        return texto_in, 0
    contagem = 0

    def _sub_figura(match: re.Match) -> str:
        nonlocal contagem
        numero = _normalizar_numero_legenda(match.group(1))
        bloco_id = figuras.get(numero)
        if not bloco_id:
            return match.group(0)
        contagem += 1
        return f"[[REF:figura|{bloco_id}]]"

    def _sub_tabela(match: re.Match) -> str:
        nonlocal contagem
        numero = _normalizar_numero_legenda(match.group(1))
        bloco_id = tabelas.get(numero)
        if not bloco_id:
            return match.group(0)
        contagem += 1
        return f"[[REF:tabela|{bloco_id}]]"

    def _sub_secao(match: re.Match) -> str:
        nonlocal contagem
        numero = match.group(1)
        secao_id = secoes_por_numero.get(numero)
        if not secao_id:
            return match.group(0)
        contagem += 1
        return f"[[REF:secao|{secao_id}]]"

    saida = _RE_FIGURA_TXT.sub(_sub_figura, texto_in)
    saida = _RE_TABELA_TXT.sub(_sub_tabela, saida)
    saida = _RE_SECAO_TXT.sub(_sub_secao, saida)
    return saida, contagem


def consolidar_referencias(db: Session, rel_id: int) -> int:
    """Varre o conteudo dos blocos do relatorio e troca referencias textuais
    de Figura/Tabela/Secao por marcadores estaveis ``[[REF:..]]``.

    Idempotente: marcadores ja existentes nao sao alterados, e re-executar
    sobre o mesmo relatorio nao produz efeito.

    Deve rodar **antes** de ``renumerar_relatorio`` para que os numeros usados
    na resolucao dos alvos correspondam ao estado atual exibido.

    Retorna o numero total de substituicoes aplicadas.
    """
    secoes = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id)
        .order_by(Secao.ordem)
        .all()
    )
    if not secoes:
        return 0
    secoes_por_numero = {s.numero: s.id for s in secoes if s.numero}

    blocos = (
        db.query(Bloco)
        .filter(Bloco.secao_id.in_([s.id for s in secoes]))
        .order_by(Bloco.secao_id, Bloco.ordem)
        .all()
    )
    blocos_por_secao: dict[int, list[Bloco]] = defaultdict(list)
    for bloco in blocos:
        blocos_por_secao[bloco.secao_id].append(bloco)

    figuras, tabelas = _mapear_blocos_alvo(secoes, blocos_por_secao)

    total = 0
    for bloco in blocos:
        mudou = False
        if bloco.conteudo:
            novo, contagem = _substituir_referencias(
                bloco.conteudo, figuras, tabelas, secoes_por_numero
            )
            if contagem:
                bloco.conteudo = novo
                total += contagem
                mudou = True
        if bloco.legenda:
            novo, contagem = _substituir_referencias(
                bloco.legenda, figuras, tabelas, secoes_por_numero
            )
            if contagem:
                bloco.legenda = novo
                total += contagem
                mudou = True
        if mudou:
            # Forca flush para que SQLAlchemy persista a alteracao na transacao.
            db.add(bloco)
    return total


def consolidar_e_renumerar(db: Session, rel_id: int) -> tuple[int, dict[int, str]]:
    """Atalho seguro: consolida referencias textuais (preserva alvo atual) e
    em seguida renumera o relatorio. Os marcadores estaveis sobrevivem a
    renumeracao porque guardam ID, nao numero.

    Deve rodar dentro de transacao.
    """
    refs = consolidar_referencias(db, rel_id)
    mapa = renumerar_relatorio(db, rel_id)
    return refs, mapa


__all__ = [
    "chave_numero",
    "consolidar_e_renumerar",
    "consolidar_referencias",
    "renumerar_relatorio",
]
