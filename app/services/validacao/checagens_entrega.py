"""Checagens estruturais da parcial de cada autor (página Validação e Revisão).

Não inventa novos conceitos: usa dados que já existem em ``Bloco``, ``Figura``,
``Secao`` e ``EntregaRelatorio``. Cada checagem devolve uma lista de
``Achado`` agrupados por seção; o template decide cor/severidade pela própria
chave do achado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy.orm import Session, selectinload

from ...models import Bloco, EntregaRelatorio, Figura, Relatorio, Secao, User


# Severidades: 'erro' bloqueia visualmente (vermelho), 'aviso' chama atenção
# (amarelo). 'info' é neutro (cinza, contagens).
SEVERIDADES = ("erro", "aviso", "info")

_REF_RE = re.compile(r"\[\[REF:(figura|tabela|secao)\|(\d+)\]\]")


@dataclass(frozen=True, slots=True)
class Achado:
    """Item produzido por uma checagem estrutural.

    ``chave`` permite ao template traduzir/agrupar; ``rotulo`` é o texto humano
    que aparece direto na UI; ``severidade`` rege a cor/ícone.
    """
    chave: str
    rotulo: str
    severidade: str  # 'erro' | 'aviso' | 'info'


@dataclass(slots=True)
class ChecagemSecao:
    secao_id: int
    secao_numero: str
    secao_titulo: str
    blocos_total: int
    blocos_bloqueados: int
    achados: list[Achado] = field(default_factory=list)
    link_upload: str = ""

    @property
    def tem_erro(self) -> bool:
        return any(a.severidade == "erro" for a in self.achados)

    @property
    def tem_aviso(self) -> bool:
        return any(a.severidade == "aviso" for a in self.achados)


@dataclass(slots=True)
# pylint: disable=too-many-instance-attributes
# Dataclass de transporte para o template Jinja: cada campo aparece direto na
# UI (8 dimensões: id, autor, status, seções e três da última reprovação).
# Aglutinar em sub-dataclass complica o template sem reduzir conceitos reais.
class ChecagemEntrega:
    """Resumo da parcial de um autor: secções + agregados por severidade."""
    entrega_id: int
    user_id: int | None
    user_nome: str
    user_email: str
    status: str
    secoes: list[ChecagemSecao] = field(default_factory=list)
    motivo_reprovacao: str | None = None
    data_reprovacao: Any = None  # datetime | None — Any evita import só para hint

    @property
    def total_erros(self) -> int:
        return sum(1 for s in self.secoes for a in s.achados if a.severidade == "erro")

    @property
    def total_avisos(self) -> int:
        return sum(1 for s in self.secoes for a in s.achados if a.severidade == "aviso")

    @property
    def total_blocos(self) -> int:
        return sum(s.blocos_total for s in self.secoes)

    @property
    def total_blocos_bloqueados(self) -> int:
        return sum(s.blocos_bloqueados for s in self.secoes)

    @property
    def pronta_para_aprovar(self) -> bool:
        """Só sugere aprovação quando não há erros estruturais E todas as
        seções têm pelo menos 1 bloco bloqueado. Avisos não bloqueiam."""
        if not self.secoes:
            return False
        if self.total_erros > 0:
            return False
        return all(s.blocos_bloqueados > 0 for s in self.secoes)


def _ids_validos_referencia(rel: Relatorio) -> tuple[set[int], set[int]]:
    """IDs de seções e blocos do relatório que podem ser alvo de [[REF:...]].

    Retorna ``(ids_secoes, ids_blocos_figura_tabela)``. Bloco texto/lista não
    é alvo válido de REF figura/tabela; só `figura` e `tabela` entram.
    """
    ids_secoes = {s.id for s in rel.secoes}
    ids_blocos_figtab: set[int] = set()
    for s in rel.secoes:
        for b in s.blocos:
            if b.tipo in ("figura", "tabela"):
                ids_blocos_figtab.add(b.id)
    return ids_secoes, ids_blocos_figtab


def _figuras_com_dados(db: Session, rel_id: int) -> set[int]:
    """IDs de Figura que existem E possuem binário não vazio. Bloco figura
    apontando para fora desse conjunto vira erro estrutural."""
    rows = (
        db.query(Figura.id)
        .filter(
            Figura.relatorio_id == rel_id,
            Figura.dados.isnot(None),
        )
        .all()
    )
    return {row[0] for row in rows}


def _checar_bloco_texto(b: Bloco) -> Iterable[Achado]:
    if not (b.conteudo or "").strip():
        yield Achado(
            chave="texto_vazio",
            rotulo=f"Bloco texto #{b.id} sem conteúdo.",
            severidade="erro",
        )


def _checar_bloco_figura(
    b: Bloco, figuras_validas: set[int]
) -> Iterable[Achado]:
    if not b.figura_id:
        yield Achado(
            chave="figura_sem_id",
            rotulo=f"Bloco figura #{b.id} sem imagem anexada.",
            severidade="erro",
        )
    elif b.figura_id not in figuras_validas:
        yield Achado(
            chave="figura_sem_binario",
            rotulo=(
                f"Bloco figura #{b.id} aponta para Figura {b.figura_id} "
                "ausente ou sem dados no banco."
            ),
            severidade="erro",
        )
    if not (b.fonte or "").strip():
        yield Achado(
            chave="figura_sem_fonte",
            rotulo=f"Bloco figura #{b.id} sem campo Fonte preenchido.",
            severidade="aviso",
        )
    if not (b.legenda or "").strip():
        yield Achado(
            chave="figura_sem_legenda",
            rotulo=f"Bloco figura #{b.id} sem legenda.",
            severidade="aviso",
        )


def _checar_bloco_tabela(b: Bloco) -> Iterable[Achado]:
    if not (b.conteudo or "").strip():
        yield Achado(
            chave="tabela_vazia",
            rotulo=f"Bloco tabela #{b.id} sem células.",
            severidade="erro",
        )
    if not (b.fonte or "").strip():
        yield Achado(
            chave="tabela_sem_fonte",
            rotulo=f"Bloco tabela #{b.id} sem campo Fonte preenchido.",
            severidade="aviso",
        )
    if not (b.legenda or "").strip():
        yield Achado(
            chave="tabela_sem_legenda",
            rotulo=f"Bloco tabela #{b.id} sem legenda.",
            severidade="aviso",
        )


def _checar_bloco_lista(b: Bloco) -> Iterable[Achado]:
    if not (b.conteudo or "").strip():
        yield Achado(
            chave="lista_vazia",
            rotulo=f"Bloco lista #{b.id} sem itens.",
            severidade="erro",
        )


def _checar_referencias(
    b: Bloco,
    ids_secoes: set[int],
    ids_blocos_figtab: set[int],
) -> Iterable[Achado]:
    """Detecta marcadores ``[[REF:tipo|id]]`` apontando para alvo inexistente.

    Varre ``conteudo`` e ``legenda``. Não tenta resolver o REF — só sinaliza.
    O renderizador final ignora marcadores quebrados; aqui o coord vê antes.
    """
    textos = (b.conteudo or "") + " " + (b.legenda or "")
    for tipo, alvo_str in _REF_RE.findall(textos):
        alvo_id = int(alvo_str)
        valido = (
            alvo_id in ids_secoes if tipo == "secao" else alvo_id in ids_blocos_figtab
        )
        if not valido:
            yield Achado(
                chave=f"ref_quebrada_{tipo}",
                rotulo=(
                    f"Bloco #{b.id}: referência [[REF:{tipo}|{alvo_id}]] "
                    "aponta para alvo inexistente no relatório."
                ),
                severidade="erro",
            )


def _checar_secao(
    sec: Secao,
    figuras_validas: set[int],
    ids_secoes: set[int],
    ids_blocos_figtab: set[int],
) -> ChecagemSecao:
    achados: list[Achado] = []
    blocos = list(sec.blocos)
    bloqueados = sum(1 for b in blocos if b.bloqueado)

    if not blocos:
        achados.append(
            Achado(
                chave="secao_sem_bloco",
                rotulo="Seção sem nenhum bloco enviado.",
                severidade="erro",
            )
        )
    elif bloqueados == 0:
        achados.append(
            Achado(
                chave="secao_sem_bloco_confirmado",
                rotulo=(
                    f"Seção tem {len(blocos)} bloco(s), mas nenhum foi "
                    "confirmado pelo autor."
                ),
                severidade="aviso",
            )
        )

    for b in blocos:
        if b.tipo == "texto":
            achados.extend(_checar_bloco_texto(b))
        elif b.tipo == "figura":
            achados.extend(_checar_bloco_figura(b, figuras_validas))
        elif b.tipo == "tabela":
            achados.extend(_checar_bloco_tabela(b))
        elif b.tipo == "lista":
            achados.extend(_checar_bloco_lista(b))
        achados.extend(_checar_referencias(b, ids_secoes, ids_blocos_figtab))

    return ChecagemSecao(
        secao_id=sec.id,
        secao_numero=sec.numero,
        secao_titulo=sec.titulo,
        blocos_total=len(blocos),
        blocos_bloqueados=bloqueados,
        achados=achados,
        link_upload=f"/relatorios/{sec.relatorio_id}/secoes/{sec.id}/upload-conteudo",
    )


def montar_checagens_validacao(
    db: Session,
    rel: Relatorio,
    entregas: list[EntregaRelatorio],
) -> list[ChecagemEntrega]:
    """Para cada entrega, devolve checagens estruturais agregadas por seção do
    autor responsável. Entregas sem usuário (caso de borda) são ignoradas.

    A consulta carrega seções com ``selectinload`` para evitar N+1 ao varrer
    blocos. Figuras com binário são pré-buscadas em uma única query.
    """
    figuras_validas = _figuras_com_dados(db, rel.id)
    rel_carregado = (
        db.query(Relatorio)
        .options(selectinload(Relatorio.secoes).selectinload(Secao.blocos))
        .filter(Relatorio.id == rel.id)
        .one()
    )
    ids_secoes, ids_blocos_figtab = _ids_validos_referencia(rel_carregado)
    secoes_por_responsavel: dict[int, list[Secao]] = {}
    for sec in rel_carregado.secoes:
        if sec.responsavel_id is None:
            continue
        secoes_por_responsavel.setdefault(sec.responsavel_id, []).append(sec)

    resultado: list[ChecagemEntrega] = []
    for entrega in entregas:
        u: User | None = entrega.user
        if u is None:
            continue
        secoes_user = sorted(
            secoes_por_responsavel.get(u.id, []),
            key=lambda s: (s.numero, s.ordem),
        )
        chk_secoes = [
            _checar_secao(s, figuras_validas, ids_secoes, ids_blocos_figtab)
            for s in secoes_user
        ]
        # chk_secoes vazia (autor sem nenhuma seção atribuída neste relatório)
        # é tratada no template com um banner amarelo dedicado, sem achados.
        resultado.append(
            ChecagemEntrega(
                entrega_id=entrega.id,
                user_id=u.id,
                user_nome=u.nome,
                user_email=u.email,
                status=entrega.status,
                secoes=chk_secoes,
                motivo_reprovacao=entrega.motivo_reprovacao,
                data_reprovacao=entrega.data_reprovacao,
            )
        )
    resultado.sort(key=lambda c: c.user_nome.lower())
    return resultado
