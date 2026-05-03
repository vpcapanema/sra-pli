"""Checagens estruturais agregadas do relatório inteiro (Seção 2 — Revisão).

Consome os mesmos modelos das checagens por entrega (`checagens_entrega.py`)
e devolve um único bloco por categoria com lista de itens problemáticos.
Uso típico: o coord percorre as categorias antes de finalizar o relatório.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, selectinload

from ...models import EntregaRelatorio, Figura, Relatorio, Secao
from .relatorio_secoes_load import load_relatorio_secoes_blocos_responsavel


_REF_RE = re.compile(r"\[\[REF:(figura|tabela|secao)\|(\d+)\]\]")


@dataclass(slots=True)
class ItemGlobal:
    """Um item problemático específico (uma seção, um bloco, um autor)."""
    rotulo: str
    link: str = ""
    autor_rotulo: str = ""


@dataclass(slots=True)
class CategoriaGlobal:
    """Uma categoria de checagem com sua lista de itens problemáticos."""
    chave: str
    titulo: str
    descricao: str
    severidade: str  # 'erro' | 'aviso' | 'info'
    itens: list[ItemGlobal] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.itens)


@dataclass(slots=True)
# pylint: disable=too-many-instance-attributes
# Dataclass de transporte para o template Jinja: 8 dimensões pequenas que
# aparecem cada uma como célula no resumo. Subdividir em sub-dataclass apenas
# infla acessos no template sem ganho semântico real.
class ResumoGlobal:
    """Agregação para o cabeçalho da Seção 2."""
    secoes: int
    secoes_sem_responsavel: int
    secoes_sem_blocos: int
    blocos_total: int
    blocos_confirmados: int
    figuras_total: int
    entregas_total: int
    entregas_validadas: int

    @property
    def todas_validadas(self) -> bool:
        return self.entregas_total > 0 and self.entregas_validadas == self.entregas_total

    @property
    def percent_confirmacao(self) -> int:
        if self.blocos_total == 0:
            return 0
        return round(100 * self.blocos_confirmados / self.blocos_total)


def _link_secao_upload(rel_id: int, sec: Secao) -> str:
    return f"/relatorios/{rel_id}/secoes/{sec.id}/upload-conteudo"


def _link_secao_no_sumario(rel_id: int, sec: Secao) -> str:
    return f"/relatorios/{rel_id}#sec-{sec.id}"


def autor_rotulo_secao(sec: Secao) -> str:
    """Rótulo explícito do responsável pela seção (para UI de validação/revisão)."""
    if sec.responsavel_id is None:
        return "Sem responsável atribuído"
    user = sec.responsavel
    if user is None:
        return f"Responsável ID {sec.responsavel_id} (detalhe não carregado)"
    nome = (user.nome or "").strip()
    if nome:
        return nome
    email = (user.email or "").strip()
    if email:
        return email
    return f"Usuário #{user.id}"


def _categoria_secoes_sem_responsavel(rel: Relatorio) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="secoes_sem_responsavel",
        titulo="Seções sem responsável atribuído",
        descricao=(
            "Seção sem responsável não recebe notificações no ciclo nem é "
            "monitorada na Validação. Atribua antes de finalizar."
        ),
        severidade="erro",
    )
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        if sec.responsavel_id is None:
            cat.itens.append(
                ItemGlobal(
                    rotulo=f"{sec.numero} — {sec.titulo}",
                    link=_link_secao_no_sumario(rel.id, sec),
                    autor_rotulo=autor_rotulo_secao(sec),
                )
            )
    return cat


def _categoria_secoes_sem_blocos(rel: Relatorio) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="secoes_sem_blocos",
        titulo="Seções sem blocos enviados",
        descricao=(
            "Seção sem nenhum bloco aparecerá vazia no PDF/DOCX final. "
            "Pode ser intencional (ex.: Assinaturas), mas vale conferir."
        ),
        severidade="aviso",
    )
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        if not sec.blocos:
            cat.itens.append(
                ItemGlobal(
                    rotulo=f"{sec.numero} — {sec.titulo}",
                    link=_link_secao_upload(rel.id, sec),
                    autor_rotulo=autor_rotulo_secao(sec),
                )
            )
    return cat


def _categoria_blocos_nao_confirmados(rel: Relatorio) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="blocos_nao_confirmados",
        titulo="Blocos enviados mas não confirmados pelo autor",
        descricao=(
            "Blocos não confirmados ainda podem ser editados/excluídos pelo "
            "autor. Considere bloqueá-los antes de finalizar para congelar."
        ),
        severidade="aviso",
    )
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        nao_conf = [b for b in sec.blocos if not b.bloqueado]
        if nao_conf:
            cat.itens.append(
                ItemGlobal(
                    rotulo=(
                        f"{sec.numero} — {sec.titulo}: "
                        f"{len(nao_conf)} bloco(s) não confirmado(s)"
                    ),
                    link=_link_secao_upload(rel.id, sec),
                    autor_rotulo=autor_rotulo_secao(sec),
                )
            )
    return cat


def _categoria_textos_vazios(rel: Relatorio) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="textos_vazios",
        titulo="Blocos texto/lista sem conteúdo",
        descricao=(
            "Bloco sem texto vai aparecer como espaço em branco no PDF. "
            "Apague ou preencha."
        ),
        severidade="erro",
    )
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        for b in sec.blocos:
            if b.tipo in ("texto", "lista") and not (b.conteudo or "").strip():
                cat.itens.append(
                    ItemGlobal(
                        rotulo=f"{sec.numero} — bloco #{b.id} ({b.tipo})",
                        link=_link_secao_upload(rel.id, sec),
                        autor_rotulo=autor_rotulo_secao(sec),
                    )
                )
    return cat


def _categoria_figuras_quebradas(rel: Relatorio, figs_validas: set[int]) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="figuras_quebradas",
        titulo="Blocos figura sem imagem ou apontando para figura ausente",
        descricao=(
            "Figura sem dados no banco quebra o PDF e o DOCX. Reenvie a "
            "imagem ou apague o bloco."
        ),
        severidade="erro",
    )
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        for b in sec.blocos:
            if b.tipo != "figura":
                continue
            if not b.figura_id:
                cat.itens.append(
                    ItemGlobal(
                        rotulo=f"{sec.numero} — bloco #{b.id} sem imagem anexada",
                        link=_link_secao_upload(rel.id, sec),
                        autor_rotulo=autor_rotulo_secao(sec),
                    )
                )
            elif b.figura_id not in figs_validas:
                cat.itens.append(
                    ItemGlobal(
                        rotulo=(
                            f"{sec.numero} — bloco #{b.id} aponta para "
                            f"Figura {b.figura_id} ausente"
                        ),
                        link=_link_secao_upload(rel.id, sec),
                        autor_rotulo=autor_rotulo_secao(sec),
                    )
                )
    return cat


def _categoria_refs_quebradas(rel: Relatorio) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="refs_quebradas",
        titulo="Referências cruzadas [[REF:...]] apontando para alvo inexistente",
        descricao=(
            "REF quebrado some ou aparece literal no PDF. Verifique se a "
            "seção/figura/tabela alvo ainda existe."
        ),
        severidade="erro",
    )
    ids_secoes = {s.id for s in rel.secoes}
    ids_figtab = {b.id for s in rel.secoes for b in s.blocos if b.tipo in ("figura", "tabela")}
    for sec in sorted(rel.secoes, key=lambda s: s.ordem):
        for b in sec.blocos:
            texto = (b.conteudo or "") + " " + (b.legenda or "")
            for tipo, alvo_str in _REF_RE.findall(texto):
                alvo = int(alvo_str)
                ok = alvo in ids_secoes if tipo == "secao" else alvo in ids_figtab
                if not ok:
                    cat.itens.append(
                        ItemGlobal(
                            rotulo=(
                                f"{sec.numero} — bloco #{b.id}: "
                                f"[[REF:{tipo}|{alvo}]]"
                            ),
                            link=_link_secao_upload(rel.id, sec),
                            autor_rotulo=autor_rotulo_secao(sec),
                        )
                    )
    return cat


def _categoria_entregas_pendentes(entregas: list[EntregaRelatorio]) -> CategoriaGlobal:
    cat = CategoriaGlobal(
        chave="entregas_pendentes",
        titulo="Entregas ainda não validadas pelo coordenador",
        descricao=(
            "Finalizar com entregas pendentes mantém o autor sem confirmação "
            "formal. Recomenda-se validar todas na Seção 1 antes."
        ),
        severidade="aviso",
    )
    for e in sorted(entregas, key=lambda x: (x.user.nome if x.user else "")):
        if e.status != "validado":
            nome = e.user.nome if e.user else "(sem usuário)"
            email = (e.user.email or "").strip() if e.user else ""
            cat.itens.append(
                ItemGlobal(
                    rotulo=f"{nome} — status: {e.status.replace('_', ' ')}",
                    link=f"/relatorios/{e.relatorio_id}/validacao-revisao#ss-validacao",
                    autor_rotulo=(
                        f"E-mail: {email}" if email else "(sem e-mail no cadastro do usuário)"
                    ),
                )
            )
    return cat


def _figuras_com_dados(db: Session, rel_id: int) -> set[int]:
    rows = (
        db.query(Figura.id)
        .filter(Figura.relatorio_id == rel_id, Figura.dados.isnot(None))
        .all()
    )
    return {row[0] for row in rows}


def montar_checagens_globais(
    db: Session,
    rel: Relatorio,
) -> tuple[ResumoGlobal, list[CategoriaGlobal]]:
    """Devolve (resumo, categorias). Categorias com 0 itens permanecem na lista
    para que o template renderize um '✓ ok' ao lado do título — facilita ler
    em uma passada o que já está limpo.
    """
    rel_full = load_relatorio_secoes_blocos_responsavel(db, rel.id)
    entregas = (
        db.query(EntregaRelatorio)
        .options(selectinload(EntregaRelatorio.user))
        .filter(EntregaRelatorio.relatorio_id == rel.id)
        .all()
    )
    figs_validas = _figuras_com_dados(db, rel.id)

    blocos_total = sum(len(s.blocos) for s in rel_full.secoes)
    blocos_confirmados = sum(
        1 for s in rel_full.secoes for b in s.blocos if b.bloqueado
    )
    figuras_total = (
        db.query(Figura).filter(Figura.relatorio_id == rel.id).count()
    )

    resumo = ResumoGlobal(
        secoes=len(rel_full.secoes),
        secoes_sem_responsavel=sum(
            1 for s in rel_full.secoes if s.responsavel_id is None
        ),
        secoes_sem_blocos=sum(1 for s in rel_full.secoes if not s.blocos),
        blocos_total=blocos_total,
        blocos_confirmados=blocos_confirmados,
        figuras_total=figuras_total,
        entregas_total=len(entregas),
        entregas_validadas=sum(1 for e in entregas if e.status == "validado"),
    )

    categorias = [
        _categoria_secoes_sem_responsavel(rel_full),
        _categoria_secoes_sem_blocos(rel_full),
        _categoria_blocos_nao_confirmados(rel_full),
        _categoria_textos_vazios(rel_full),
        _categoria_figuras_quebradas(rel_full, figs_validas),
        _categoria_refs_quebradas(rel_full),
        _categoria_entregas_pendentes(entregas),
    ]
    return resumo, categorias
