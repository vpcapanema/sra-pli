"""Orquestrador do ciclo de notificações mensais.

Pontos de entrada principais:

- :func:`abrir_periodo` — esperado no **dia** configurado (BRT) em
  ``parametros_ciclo_notificacao`` — cria o relatório do mês clonando **seções e
  conteúdos** do relatório-base (último ``finalizado``, fallback: mais recente).
  Responsáveis das seções ficam ``NULL``. Em seguida envia Mensagem 1 a **todos**
  os utilizadores com ``role=autor`` e coluna Relatório (``notificacoes_ativas``)
  ativa — não exige secção atribuída; a lista de secções no e-mail pode estar
  vazia até o coordenador atribuir.
- :func:`notificar_autores_abertura` — reenvia Mensagem 1 aos endereços do
  utilizador (``email`` e ``email2``) que ainda não tiveram ``abertura`` com
  sucesso (critério de destinatários: autor + ``notificacoes_ativas``).
- :func:`enviar_lembretes` — respeita **dias** configurados por tipo
  (`lembrete` vs ``ultima_chamada``).
- :func:`retry_falhas` — retenta falhas recentes de envio.
- :func:`recompute_status_enviado` — hook quando blocos são confirmados.

Idempotência: relatório por ``mes_referencia``; abertura/lembrete por entrega e
por endereço (principal e secundário). A evolução de ``EntregaRelatorio.status``
continua baseada só em envios com sucesso para o **e-mail principal**.

Datas de período/prazos e calendário de disparos ficam persistidos (:mod:`.ciclo_params`).
"""
# Domínio extenso: aberturas, clones, refs, retries e ganchos PDF num único lugar.
# pylint: disable=too-many-lines

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..models import (
    Bloco,
    EntregaRelatorio,
    Figura,
    NotificacaoEnvio,
    Relatorio,
    Secao,
    User,
)
from . import destinatarios as destinatarios_ciclo
from .email_context_arvore import (
    arvore_secoes_com_links,
    format_arvore_secoes_email_plaintext,
    link_dotx_secao,
    link_upload_secao,
)
from .ciclo_params import (
    ParametrosCicloDTO,
    dia_util_no_mes,
    obter_parametros_ciclo,
    periodo_referente_para_data,
)
from .email_sender import ResultadoEnvio, enviar_notificacao, modo_atual

log = logging.getLogger(__name__)

# Janelas mínimas entre envios para o mesmo destinatário (evita burst em
# retry/cron paralelos). 22h cobre os horários humanos sem cair na mesma
# janela do dia seguinte.
_INTERVALO_MIN_ENTRE_ENVIOS = timedelta(hours=22)
_MAX_RETRIES_POR_SLOT = 3
_RETRY_JANELA = timedelta(days=7)

NUMERO_MEDICAO_BASE = 14


# Helper exportado: calendário/notificações usam data em Brasília.
def agora_brt() -> datetime:
    """Retorna ``datetime.now()`` no fuso ``America/Sao_Paulo`` (Brasília).

    Persistência continua em UTC ingênuo como o resto do projeto.
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        return datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tipos de retorno
# ---------------------------------------------------------------------------
@dataclass
class ResumoAbertura:  # pylint: disable=too-many-instance-attributes
    """Valor de retorno de :func:`abrir_periodo`. Atributos descritivos.
    Limite ``too-many-instance-attributes`` (7) é restritivo demais para
    classes-resumo de retorno; o ganho de juntar dois campos correlatos
    (ex.: ``emails_enviados`` + ``emails_falhados``) seria pior pra leitura.
    """
    relatorio_id: int | None = None
    relatorio_codigo: str = ""
    base_relatorio_id: int | None = None
    criou_relatorio: bool = False
    entregas_criadas: int = 0
    emails_enviados: int = 0
    emails_falhados: int = 0
    pulada_idempotencia: bool = False
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResumoLembretes:
    tipo: str = ""
    relatorios_processados: int = 0
    emails_enviados: int = 0
    emails_falhados: int = 0
    pulados_intervalo: int = 0
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResumoRetry:
    tentativas: int = 0
    sucessos: int = 0
    falhas: int = 0
    desistencias: int = 0


@dataclass
class ResumoNotificarAutores:
    """Retorno de :func:`notificar_autores_abertura`."""

    relatorio_id: int = 0
    emails_enviados: int = 0
    emails_falhados: int = 0
    pulados_ja_enviados: int = 0
    avisos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers de período / estrutura
# ---------------------------------------------------------------------------
def _dia_referencia_abertura(data_referencia: date | None) -> date:
    """Dia civil do ciclo: explícito (testes) ou hoje em Brasília."""
    if data_referencia is not None:
        return data_referencia
    return agora_brt().date()


def _proximo_numero_medicao(db: Session) -> int:
    max_num = db.query(func.max(Relatorio.numero_medicao)).scalar()  # pylint: disable=not-callable
    return (max_num or NUMERO_MEDICAO_BASE) + 1


def _ja_existe_relatorio_no_mes(db: Session, mes_referencia: str) -> Relatorio | None:
    return (
        db.query(Relatorio)
        .filter(Relatorio.mes_referencia == mes_referencia)
        .order_by(Relatorio.created_at.desc())
        .first()
    )


def _relatorio_base(db: Session, base_relatorio_id: int | None = None) -> Relatorio | None:
    """Último ``finalizado`` (preferido) ou mais recente em qualquer status."""
    if base_relatorio_id is not None:
        return db.get(Relatorio, base_relatorio_id)
    rel = (
        db.query(Relatorio)
        .filter(Relatorio.status == "finalizado")
        .order_by(Relatorio.created_at.desc())
        .first()
    )
    if rel:
        return rel
    return (
        db.query(Relatorio).order_by(Relatorio.created_at.desc()).first()
    )


def _substituir_referencias_periodo(
    texto: str | None, base: Relatorio, novo: Relatorio
) -> str | None:
    """Atualiza trechos que identificam o relatório/período anterior para o atual.

    Substituições por igualdade literal (o conteúdo clonado costuma repetir
    strings do modelo e do mês anterior). Não altera marcadores ``[[REF:]]``
    — estes são remapeados em :func:`_remap_refs_texto`."""
    if not texto:
        return texto
    out = texto
    if base.mes_referencia != novo.mes_referencia:
        out = out.replace(base.mes_referencia, novo.mes_referencia)
    if base.codigo != novo.codigo:
        out = out.replace(base.codigo, novo.codigo)
    if base.titulo != novo.titulo:
        out = out.replace(base.titulo, novo.titulo)
    if base.periodo_inicio and base.periodo_fim and novo.periodo_inicio and novo.periodo_fim:
        pi_o = base.periodo_inicio.strftime("%d/%m/%Y")
        pf_o = base.periodo_fim.strftime("%d/%m/%Y")
        pi_n = novo.periodo_inicio.strftime("%d/%m/%Y")
        pf_n = novo.periodo_fim.strftime("%d/%m/%Y")
        for antigo, subst in (
            (f"{pi_o} – {pf_o}", f"{pi_n} – {pf_n}"),
            (f"{pi_o} - {pf_o}", f"{pi_n} - {pf_n}"),
            (f"{pi_o} a {pf_o}", f"{pi_n} a {pf_n}"),
            (f"de {pi_o} a {pf_o}", f"de {pi_n} a {pf_n}"),
        ):
            out = out.replace(antigo, subst)
    if base.numero_medicao is not None and novo.numero_medicao is not None:
        out = out.replace(
            f"Medição nº {base.numero_medicao}",
            f"Medição nº {novo.numero_medicao}",
        )
        out = out.replace(
            f"medição nº {base.numero_medicao}",
            f"medição nº {novo.numero_medicao}",
        )
        out = out.replace(
            f"Medicao nº {base.numero_medicao}",
            f"Medicao nº {novo.numero_medicao}",
        )
    return out


_REF_MARKER = re.compile(r"\[\[REF:(figura|tabela|secao)\|(\d+)\]\]")


def _remap_refs_texto(
    texto: str | None,
    map_secao: dict[int, int],
    map_bloco: dict[int, int],
) -> str | None:
    """Substitui IDs antigos em marcadores ``[[REF:tipo|id]]`` pelos novos."""
    if not texto:
        return texto

    def _subst(match: re.Match) -> str:
        tipo = match.group(1)
        oid = int(match.group(2))
        if tipo == "secao":
            nid = map_secao.get(oid)
        else:
            nid = map_bloco.get(oid)
        if nid is None:
            return match.group(0)
        return f"[[REF:{tipo}|{nid}]]"

    return _REF_MARKER.sub(_subst, texto)


def _remap_refs_em_blocos_novo_relatorio(
    db: Session,
    novo_rel_id: int,
    map_secao: dict[int, int],
    map_bloco: dict[int, int],
) -> None:
    sec_ids = [
        sid for (sid,) in db.query(Secao.id).filter(Secao.relatorio_id == novo_rel_id).all()
    ]
    if not sec_ids:
        return
    blocos = (
        db.query(Bloco).filter(Bloco.secao_id.in_(sec_ids)).order_by(Bloco.secao_id, Bloco.ordem).all()
    )
    for bl in blocos:
        bl.conteudo = _remap_refs_texto(bl.conteudo, map_secao, map_bloco)
        bl.legenda = _remap_refs_texto(bl.legenda, map_secao, map_bloco)
        bl.fonte = _remap_refs_texto(bl.fonte, map_secao, map_bloco)


def _obter_ou_clonar_figura(
    db: Session,
    base: Relatorio,
    novo: Relatorio,
    fig_antigo_id: int | None,
    cache: dict[int, int],
) -> int | None:
    """Duplica ``Figura`` para ``novo`` ou devolve ID já cacheado."""
    if not fig_antigo_id:
        return None
    if fig_antigo_id in cache:
        return cache[fig_antigo_id]
    old_fig = db.get(Figura, fig_antigo_id)
    if not old_fig:
        return None
    nome_fig = old_fig.nome
    if nome_fig:
        nome_fig = _substituir_referencias_periodo(nome_fig, base, novo) or nome_fig
    nf = Figura(
        relatorio_id=novo.id,
        nome=nome_fig,
        mime=old_fig.mime,
        dados=old_fig.dados,
        legenda=_substituir_referencias_periodo(old_fig.legenda, base, novo),
        fonte=_substituir_referencias_periodo(old_fig.fonte, base, novo),
    )
    db.add(nf)
    db.flush()
    cache[fig_antigo_id] = nf.id
    return nf.id


def _clonar_estrutura_e_conteudo(db: Session, base: Relatorio, novo: Relatorio) -> int:
    """Clona seções e blocos de ``base`` para ``novo``.

    Responsáveis **não** são copiados — ficam ``NULL`` até coord/autor atribuírem
    na UI. Texto de blocos/figuras passa por :func:`_substituir_referencias_periodo`
    e depois marcadores ``[[REF:...|id]]`` são remapeados para IDs novos.
    Figuras binárias são duplicadas para ``novo``. Um DOCX importado depois na
    mesma seção remove os blocos clonados — ver ``confirmar_importacao``.
    """
    secoes_orig = (
        db.query(Secao)
        .filter(Secao.relatorio_id == base.id)
        .order_by(Secao.ordem)
        .all()
    )
    map_secao: dict[int, int] = {}
    map_bloco: dict[int, int] = {}
    map_figura_antigo_novo: dict[int, int] = {}

    for sold in secoes_orig:
        nova_sec = Secao(
            relatorio_id=novo.id,
            numero=sold.numero,
            titulo=sold.titulo,
            ordem=sold.ordem,
            responsavel_id=None,
            status="pendente",
        )
        db.add(nova_sec)
        db.flush()
        map_secao[sold.id] = nova_sec.id

    for sold in secoes_orig:
        sid_novo = map_secao[sold.id]
        blocos_velhos = (
            db.query(Bloco)
            .filter(Bloco.secao_id == sold.id)
            .order_by(Bloco.ordem)
            .all()
        )
        for ob in blocos_velhos:
            fid_novo = _obter_ou_clonar_figura(
                db, base, novo, ob.figura_id, map_figura_antigo_novo
            )

            nb = Bloco(
                secao_id=sid_novo,
                tipo=ob.tipo,
                ordem=ob.ordem,
                titulo=_substituir_referencias_periodo(ob.titulo, base, novo),
                conteudo=_substituir_referencias_periodo(ob.conteudo, base, novo),
                legenda=_substituir_referencias_periodo(ob.legenda, base, novo),
                fonte=_substituir_referencias_periodo(ob.fonte, base, novo),
                figura_id=fid_novo,
                autor_id=ob.autor_id,
                bloqueado=False,
                origem="clonado",
            )
            db.add(nb)
            db.flush()
            map_bloco[ob.id] = nb.id

    _remap_refs_em_blocos_novo_relatorio(db, novo.id, map_secao, map_bloco)
    db.flush()
    return len(secoes_orig)


def _construir_relatorio_aberto(
    db: Session, base: Relatorio, periodo: dict
) -> Relatorio:
    """Cria o ``Relatorio`` com o próximo número de medição, clona a estrutura
    do ``base`` e devolve já refrescado. Faz commit estrutural antes para
    que o envio dos emails opere sobre estado durável."""
    proximo = _proximo_numero_medicao(db)
    novo = Relatorio(
        codigo=f"D20-{proximo}",
        titulo=f"Relatório Mensal D20-{proximo}",
        mes_referencia=periodo["mes_referencia"],
        periodo_inicio=periodo["periodo_inicio"],
        periodo_fim=periodo["periodo_fim"],
        numero_medicao=proximo,
        versao="R00",
        status="aberto",
    )
    db.add(novo)
    db.flush()
    _clonar_estrutura_e_conteudo(db, base, novo)
    db.commit()
    db.refresh(novo)
    return novo


# ---------------------------------------------------------------------------
# Helpers de email / entrega
# ---------------------------------------------------------------------------
def _parent_secao_label(numero: str, todas: dict[str, Secao]) -> str:
    """Devolve "4.4 Atividades..." (parent) ou string vazia."""
    if "." not in numero:
        return ""
    parent_num = numero.rsplit(".", 1)[0]
    pai = todas.get(parent_num)
    if not pai:
        return ""
    return f"{pai.numero} {pai.titulo}"


def _link_painel(rel_id: int) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/relatorios/{rel_id}"


def _link_modelos_word_ajuda() -> str:
    """Página autenticada com tutorial e catálogo dos modelos ``.dotx``."""
    return f"{settings.APP_BASE_URL.rstrip('/')}/modelos-word-importacao"


def _link_login_sra() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/login"


def _link_painel_upload() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/painel-upload"


def prazos_mensagem_relatorio(
    rel: Relatorio,
    *,
    parametros: ParametrosCicloDTO | None = None,
) -> dict[str, str]:
    """Prazos no texto do email: dias no mês/ano de ``periodo_fim``."""
    parametros = parametros or ParametrosCicloDTO.padrao()
    if not rel.periodo_fim:
        dash = "—"
        return {"prazo_envio": dash, "prazo_limite_conteudo_autor": dash}
    fim = rel.periodo_fim
    ano, mes = fim.year, fim.month
    dia_autor = dia_util_no_mes(ano, mes, parametros.prazo_autor_dia)
    dia_coord = dia_util_no_mes(ano, mes, parametros.prazo_coordenacao_dia)
    lim_autor = date(ano, mes, dia_autor)
    lim_coord = date(ano, mes, dia_coord)
    return {
        "prazo_envio": lim_coord.strftime("%d/%m/%Y") + " 23:59",
        "prazo_limite_conteudo_autor": lim_autor.strftime("%d/%m/%Y") + " 23:59",
    }


def _montar_contexto_email(
    db: Session,
    rel: Relatorio,
    user: User,
    secoes_do_user: list[Secao],
    todas_secoes: dict[str, Secao],
) -> dict:
    minhas = [
        {
            "numero": s.numero,
            "titulo": s.titulo,
            "contexto": _parent_secao_label(s.numero, todas_secoes),
            "link_upload": link_upload_secao(rel.id, s.id),
            "link_dotx": link_dotx_secao(rel.id, s.id),
        }
        for s in secoes_do_user
    ]
    par_ciclo = obter_parametros_ciclo(db)
    prazos = prazos_mensagem_relatorio(rel, parametros=par_ciclo)
    todas_list = sorted(todas_secoes.values(), key=lambda x: x.ordem)
    arvore = arvore_secoes_com_links(rel.id, todas_list)
    arvore_modelos_txt = format_arvore_secoes_email_plaintext(arvore, apenas_dotx=True)
    return {
        "destinatario_nome": user.nome,
        "relatorio_codigo": rel.codigo,
        "relatorio_titulo": rel.titulo,
        "mes_referencia": rel.mes_referencia,
        "prazo_envio": prazos["prazo_envio"],
        "prazo_limite_conteudo_autor": prazos["prazo_limite_conteudo_autor"],
        "minhas_secoes": minhas,
        "arvore_secoes_links": arvore,
        "arvore_modelos_dotx_texto": arvore_modelos_txt,
        "link_relatorio_painel": _link_painel(rel.id),
        "link_modelos_word_ajuda": _link_modelos_word_ajuda(),
        "link_login_sra": _link_login_sra(),
        "link_painel_upload": _link_painel_upload(),
    }


def _entrega_para(
    db: Session, rel_id: int, user_id: int
) -> EntregaRelatorio:
    """Pega ou cria a EntregaRelatorio (rel, user). UNIQUE garante não duplicar."""
    e = (
        db.query(EntregaRelatorio)
        .filter(
            EntregaRelatorio.relatorio_id == rel_id,
            EntregaRelatorio.user_id == user_id,
        )
        .one_or_none()
    )
    if e:
        return e
    e = EntregaRelatorio(relatorio_id=rel_id, user_id=user_id, status="notificado")
    db.add(e)
    db.flush()
    return e


def _ultimo_envio_sucesso(entrega: EntregaRelatorio) -> NotificacaoEnvio | None:
    bem = [n for n in entrega.notificacoes if n.sucesso]
    return bem[-1] if bem else None


def _registrar_envio(
    db: Session,
    entrega: EntregaRelatorio,
    tipo: str,
    destinatario_email: str,
    resultado: ResultadoEnvio,
) -> NotificacaoEnvio:
    n = NotificacaoEnvio(
        entrega_id=entrega.id,
        tipo=tipo,
        sucesso=resultado.sucesso,
        erro=resultado.erro,
        destinatario_email=destinatario_email,
        sendgrid_message_id=resultado.message_id,
    )
    db.add(n)
    db.flush()
    return n


@dataclass(frozen=True)
class _Envio:
    """Pacote de dados imutável para um envio: a quem, qual relatório, quais
    seções, e o mapa de seções para resolver parents no template."""
    rel: Relatorio
    user: User
    secoes_user: list[Secao]
    todas_map: dict[str, Secao]


def _processar_destinatario(  # pylint: disable=too-many-branches,too-many-locals
    db: Session,
    env: _Envio,
    tipo: str,
    *,
    enviar_para: str = "faltam",
) -> ResultadoEnvio:
    """Render → envia para ``email`` e ``email2`` (quando distintos) → regista.

    ``enviar_para``: ``faltam`` só endereços sem sucesso neste ``tipo``;
    ``todos`` força todos (ex.: reenvio manual do coordenador).

    O retorno é sucesso só se **todos** os envios da chamada tiverem sucesso.
    ``EntregaRelatorio.status`` avança a cada envio bem-sucedido em **qualquer
    um** dos endereços do autor (principal ou secundário); ver
    :func:`_avancar_status_apos_envio`.
    """
    entrega = _entrega_para(db, env.rel.id, env.user.id)
    contexto = _montar_contexto_email(
        db, env.rel, env.user, env.secoes_user, env.todas_map,
    )
    destinos_completos = destinatarios_ciclo.emails_destino_notificacao(env.user)
    if enviar_para == "todos":
        destinos = list(destinos_completos)
    else:
        destinos = destinatarios_ciclo.destinos_pendentes_tipo(
            db, entrega.id, tipo, destinos_completos
        )
    if not destinos:
        return ResultadoEnvio(True, None, None, modo_atual())

    resultados: list[ResultadoEnvio] = []
    erros: list[str] = []
    for dest_email in destinos:
        resultado = enviar_notificacao(
            destinatario_email=dest_email,
            destinatario_nome=env.user.nome,
            tipo=tipo,
            contexto=contexto,
        )
        _registrar_envio(db, entrega, tipo, dest_email, resultado)
        if resultado.sucesso:
            _avancar_status_apos_envio(entrega, tipo)
        resultados.append(resultado)
        if resultado.erro:
            erros.append(f"{dest_email}: {resultado.erro}")

    todos_ok = all(r.sucesso for r in resultados)
    primeiro_id = next((r.message_id for r in resultados if r.message_id), None)
    modo = resultados[-1].modo if resultados else modo_atual()
    if todos_ok:
        return ResultadoEnvio(True, primeiro_id, None, modo)
    return ResultadoEnvio(
        False,
        primeiro_id,
        "; ".join(erros) if erros else "falha_envio",
        modo,
    )


def _avancar_status_apos_envio(
    entrega: EntregaRelatorio, tipo: str
) -> None:
    """Avança o status da entrega a partir de um envio bem-sucedido.

    Regra (decisão por tipo, não por contagem):
    - ``abertura`` → ``notificado`` (se ainda em ``pendente``).
    - ``lembrete`` / ``ultima_chamada`` / ``manual`` → ``aguardando_envio``
      (se ainda em ``pendente``/``notificado``).

    **Qualquer** endereço bem-sucedido do autor (principal ou secundário)
    conta; o status reflete "autor foi avisado com sucesso", não um canal
    privilegiado. Nunca regride ``enviado``/``validado``.
    """
    if entrega.status in ("enviado", "validado"):
        return
    if tipo == "abertura":
        if entrega.status == "pendente":
            entrega.status = "notificado"
        return
    if tipo in ("lembrete", "ultima_chamada", "manual"):
        if entrega.status in ("pendente", "notificado"):
            entrega.status = "aguardando_envio"


def notificar_autores_abertura(
    db: Session, rel_id: int, *, force: bool = False
) -> ResumoNotificarAutores:
    """Envia Mensagem 1 (abertura) para cada autor com notificações ativas.

    Por padrão é idempotente: usuários que já receberam ``abertura`` com
    ``sucesso`` (em todos os endereços) são contados em ``pulados_ja_enviados``
    e não recebem novo e-mail. Esta forma é usada pelo cron e por scripts de
    correção de gaps.

    Com ``force=True``, **força o reenvio** a todos os autores ativos
    independentemente de tentativas anteriores e em todos os endereços
    (principal e secundário): é o caminho do botão *Notificar autores
    (abertura)* no sumário do relatório e da execução manual da governança.
    Cada chamada cria nova linha em ``notificacao_envio`` (audit trail) e o
    status da entrega não regride (``_avancar_status_apos_envio``).
    """
    resumo = ResumoNotificarAutores(relatorio_id=rel_id)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        resumo.avisos.append("Relatório não encontrado.")
        return resumo
    if rel.status == "finalizado":
        resumo.avisos.append("Relatório finalizado; não envie abertura.")
        return resumo
    pares = destinatarios_ciclo.destinatarios_mensagem_abertura(db, rel)
    if not pares:
        resumo.avisos.append(
            "Nenhum utilizador com perfil autor e notificações do relatório ativas."
        )
        return resumo
    todas_map = {
        s.numero: s
        for s in db.query(Secao)
        .options(selectinload(Secao.responsavel))
        .filter(Secao.relatorio_id == rel.id)
        .all()
    }
    log.info(
        "[notif/notificar_autores_abertura] relatorio=%s destinatarios=%d force=%s",
        rel.codigo,
        len(pares),
        force,
    )
    enviar_para_modo = "todos" if force else "faltam"
    for user_obj, secoes_user in pares:
        if not force:
            entrega_ex = (
                db.query(EntregaRelatorio)
                .filter(
                    EntregaRelatorio.relatorio_id == rel.id,
                    EntregaRelatorio.user_id == user_obj.id,
                )
                .one_or_none()
            )
            destinos_full = destinatarios_ciclo.emails_destino_notificacao(user_obj)
            pendentes = (
                destinatarios_ciclo.destinos_pendentes_tipo(
                    db, entrega_ex.id, "abertura", destinos_full
                )
                if entrega_ex
                else destinos_full
            )
            if entrega_ex and not pendentes:
                resumo.pulados_ja_enviados += 1
                continue
        env = _Envio(rel, user_obj, secoes_user, todas_map)
        resultado = _processar_destinatario(
            db, env, "abertura", enviar_para=enviar_para_modo
        )
        if resultado.sucesso:
            resumo.emails_enviados += 1
        else:
            resumo.emails_falhados += 1
    db.commit()
    return resumo


# ---------------------------------------------------------------------------
# 1) abrir_periodo
# ---------------------------------------------------------------------------
def abrir_periodo(  # pylint: disable=too-many-locals
    db: Session,
    *,
    force: bool = False,
    data_referencia: date | None = None,
    base_relatorio_id: int | None = None,
) -> ResumoAbertura:
    """Cria o relatório do mês, suas entregas e dispara Mensagem 1.

    Idempotente: se já existe relatório com o mesmo ``mes_referencia``, não
    cria de novo (a menos que ``force=True``).

    ``data_referencia`` permite simular a data corrente — útil para o coord
    reabrir um mês passado por engano e para o E2E de teste.

    ``base_relatorio_id`` permite à governança escolher explicitamente o
    relatório-modelo da clonagem manual. Sem valor, mantém a escolha automática.
    """
    resumo = ResumoAbertura()
    parametros = obter_parametros_ciclo(db)
    dia_ref = _dia_referencia_abertura(data_referencia)
    periodo = periodo_referente_para_data(dia_ref, parametros)

    existente = _ja_existe_relatorio_no_mes(db, periodo["mes_referencia"])
    if existente and not force:
        resumo.relatorio_id = existente.id
        resumo.relatorio_codigo = existente.codigo
        resumo.pulada_idempotencia = True
        resumo.avisos.append(
            f"Já existe relatório para {periodo['mes_referencia']} "
            f"(id={existente.id}). Use force=True para reabrir."
        )
        return resumo

    if not force and dia_ref.day != parametros.dia_abertura_novo_ciclo:
        resumo.avisos.append(
            f"Abertura automática configurada para o dia {parametros.dia_abertura_novo_ciclo}; "
            f"data de referência BRT = {dia_ref.isoformat()} (dia {dia_ref.day}). "
            "Use POST com force=true no cron para abrir fora do dia."
        )
        return resumo

    base = _relatorio_base(db, base_relatorio_id)
    if base is None:
        if base_relatorio_id is None:
            resumo.avisos.append(
                "Nenhum relatório anterior encontrado. A criação automática "
                "exige pelo menos um Relatorio existente como base de seções."
            )
        else:
            resumo.avisos.append(
                f"Relatório base id={base_relatorio_id} não encontrado."
            )
        return resumo
    resumo.base_relatorio_id = base.id
    if base.status != "finalizado":
        resumo.avisos.append(
            f"Base é o relatório {base.codigo} (status={base.status}). "
            f"Idealmente seria 'finalizado'."
        )

    novo = _construir_relatorio_aberto(db, base, periodo)
    resumo.relatorio_id = novo.id
    resumo.relatorio_codigo = novo.codigo
    resumo.criou_relatorio = True

    # Materializa 1 EntregaRelatorio (status='pendente') por autor ativo
    # imediatamente após a criação do relatório. Assim, a lista de entregas
    # fica persistente desde o minuto zero e o envio de e-mail a seguir só
    # atualiza colunas (evita janela em que a UI exibe 'tabela vazia').
    # pylint: disable=import-outside-toplevel
    from ..services.entregas.lista_painel import garantir_entregas_relatorio
    garantir_entregas_relatorio(db, novo)

    todas_map = {s.numero: s for s in db.query(Secao)
                 .options(selectinload(Secao.responsavel))
                 .filter(Secao.relatorio_id == novo.id).all()}
    pares = destinatarios_ciclo.destinatarios_mensagem_abertura(db, novo)
    log.info(
        "[notif/abrir_periodo] relatorio=%s destinatarios=%d modo_email=%s",
        novo.codigo, len(pares), modo_atual(),
    )
    for user_obj, secoes_user in pares:
        env = _Envio(novo, user_obj, secoes_user, todas_map)
        resultado = _processar_destinatario(db, env, "abertura")
        if resultado.sucesso:
            resumo.emails_enviados += 1
        else:
            resumo.emails_falhados += 1
        resumo.entregas_criadas += 1
    if resumo.criou_relatorio and not pares:
        resumo.avisos.append(
            "Relatório criado com conteúdo clonado; nenhum autor com "
            "notificações do relatório ativas — nada a enviar."
        )
    db.commit()
    return resumo


# ---------------------------------------------------------------------------
# 2) enviar_lembretes
# ---------------------------------------------------------------------------
def enviar_lembretes(  # pylint: disable=too-many-locals
    db: Session,
    *,
    tipo: str = "lembrete",
    relatorio_id: int | None = None,
    ignorar_calendario: bool = False,
) -> ResumoLembretes:
    """Manda Mensagem 2 para entregas pendentes em relatórios em aberto.

    Destinatários: mesmos de Mensagem 1 (``destinatarios_mensagem_abertura``).

    ``tipo`` ∈ {'lembrete', 'ultima_chamada'}.
    ``relatorio_id`` restringe a um relatório específico (útil para reenviar
    em batch ou para o E2E não tocar relatórios reais).

    Por defeito o envio **só corre** no dia civil de Brasília acordado na
    configuração persistida (lembretes: lista de dias; última chamada: um dia).
    ``ignorar_calendario=True`` contorna (testes e POST com query explícito).
    """
    resumo = ResumoLembretes(tipo=tipo)
    if tipo not in ("lembrete", "ultima_chamada"):
        resumo.avisos.append(f"tipo inválido: {tipo}")
        return resumo

    parametros_cal = obter_parametros_ciclo(db)
    hoje_brt = agora_brt().date()
    if not ignorar_calendario:
        if tipo == "lembrete" and hoje_brt.day not in parametros_cal.dias_lembrete:
            resumo.avisos.append(
                f"Hoje é dia {hoje_brt.day} BRT; só serão enviados lembretes "
                f"nos dias configurados ({parametros_cal.dias_lembrete}). "
                "Pode usar POST /admin/cron/lembretes?ignorar_calendario=true em urgentes."
            )
            return resumo
        if (
            tipo == "ultima_chamada"
            and hoje_brt.day != parametros_cal.dia_ultima_chamada
        ):
            resumo.avisos.append(
                "Hoje BRT não coincide com o dia da última chamada "
                f"({parametros_cal.dia_ultima_chamada}) na configuração do ciclo."
            )
            return resumo

    q = db.query(Relatorio).filter(
        Relatorio.status.in_(("aberto", "em_revisao"))
    )
    if relatorio_id is not None:
        q = q.filter(Relatorio.id == relatorio_id)
    relatorios = q.all()
    agora = datetime.utcnow()
    for rel in relatorios:
        resumo.relatorios_processados += 1
        todas_map = {s.numero: s for s in db.query(Secao)
                     .options(selectinload(Secao.responsavel))
                     .filter(Secao.relatorio_id == rel.id).all()}
        for user_obj, secoes_user in destinatarios_ciclo.destinatarios_mensagem_abertura(db, rel):
            entrega = _entrega_para(db, rel.id, user_obj.id)
            if entrega.status in ("enviado", "validado"):
                continue
            ultimo = _ultimo_envio_sucesso(entrega)
            if ultimo and (agora - ultimo.enviada_em) < _INTERVALO_MIN_ENTRE_ENVIOS:
                resumo.pulados_intervalo += 1
                continue
            env = _Envio(rel, user_obj, secoes_user, todas_map)
            resultado = _processar_destinatario(db, env, tipo)
            if resultado.sucesso:
                resumo.emails_enviados += 1
            else:
                resumo.emails_falhados += 1
    db.commit()
    return resumo


# ---------------------------------------------------------------------------
# 3) retry_falhas
# ---------------------------------------------------------------------------
def _deve_tentar_de_novo(
    entrega: EntregaRelatorio, tipo: str, limite_tempo: datetime
) -> tuple[bool, bool]:
    """(deve_processar, conta_como_desistencia). Decisão sem efeito colateral."""
    if not entrega or not entrega.user:
        return False, True
    if entrega.status in ("enviado", "validado"):
        return False, False
    primary = (entrega.user.email or "").strip().lower()
    eventos = [
        ev for ev in entrega.notificacoes
        if ev.tipo == tipo and ev.enviada_em >= limite_tempo
    ]
    if any(
        ev.sucesso
        for ev in eventos
        if (ev.destinatario_email or "").strip().lower() == primary
    ):
        return False, False
    if len(eventos) >= _MAX_RETRIES_POR_SLOT:
        return False, True
    return True, False


def retry_falhas(db: Session) -> ResumoRetry:
    """Reenvia notificações que falharam nos últimos 7 dias, até 3 tentativas
    por (entrega, tipo). Cria uma nova linha por tentativa para audit trail."""
    resumo = ResumoRetry()
    limite_tempo = datetime.utcnow() - _RETRY_JANELA

    falhas: Iterable[NotificacaoEnvio] = (
        db.query(NotificacaoEnvio)
        .options(selectinload(NotificacaoEnvio.entrega).selectinload(EntregaRelatorio.user))
        .filter(
            NotificacaoEnvio.sucesso.is_(False),
            NotificacaoEnvio.enviada_em >= limite_tempo,
        )
        .all()
    )
    chaves: set[tuple[int, str]] = set()
    for n in falhas:
        chave = (n.entrega_id, n.tipo)
        if chave in chaves:
            continue
        chaves.add(chave)
        resumo.tentativas += 1
        deve, desiste = _deve_tentar_de_novo(n.entrega, n.tipo, limite_tempo)
        if not deve:
            if desiste:
                resumo.desistencias += 1
            continue
        rel = db.get(Relatorio, n.entrega.relatorio_id)
        if not rel:
            resumo.desistencias += 1
            continue
        secoes_rel = (
            db.query(Secao)
            .options(selectinload(Secao.responsavel))
            .filter(Secao.relatorio_id == rel.id)
            .all()
        )
        env = _Envio(
            rel, n.entrega.user,
            [s for s in secoes_rel if s.responsavel_id == n.entrega.user_id],
            {s.numero: s for s in secoes_rel},
        )
        resultado = _processar_destinatario(db, env, n.tipo)
        if resultado.sucesso:
            resumo.sucessos += 1
        else:
            resumo.falhas += 1
    db.commit()
    return resumo


# ---------------------------------------------------------------------------
# 4) recompute_status_enviado
# ---------------------------------------------------------------------------
def _pode_promover_para_enviado(
    entrega: EntregaRelatorio | None,
    secoes_user: list[Secao],
    blocos: list[Bloco],
) -> bool:
    """Predicado puro. Verdadeiro se a entrega ainda não está em ``enviado``
    nem ``validado``, tem seções e blocos, e *todos* os blocos estão
    ``bloqueado=true``."""
    if not entrega or entrega.status in ("enviado", "validado"):
        return False
    if not secoes_user or not blocos:
        return False
    return all(b.bloqueado for b in blocos)


def recompute_status_enviado(
    db: Session, user_id: int, rel_id: int
) -> bool:
    """Promove a entrega para ``enviado`` se todas as seções do user no rel
    têm pelo menos 1 bloco e todos estão ``bloqueado=true``. Retorna
    ``True`` se mudou.
    """
    entrega = (
        db.query(EntregaRelatorio)
        .filter(
            EntregaRelatorio.relatorio_id == rel_id,
            EntregaRelatorio.user_id == user_id,
        )
        .one_or_none()
    )
    secoes_user = (
        db.query(Secao)
        .filter(Secao.relatorio_id == rel_id, Secao.responsavel_id == user_id)
        .all()
    )
    sec_ids = [s.id for s in secoes_user]
    blocos = (
        db.query(Bloco).filter(Bloco.secao_id.in_(sec_ids)).all()
        if sec_ids else []
    )
    if not _pode_promover_para_enviado(entrega, secoes_user, blocos):
        return False
    assert entrega is not None  # garantido pela função predicate
    entrega.status = "enviado"
    entrega.data_envio = datetime.utcnow()
    db.commit()
    log.info(
        "[notif/recompute] entrega=%s user=%d rel=%d -> enviado",
        entrega.id, user_id, rel_id,
    )
    return True


# ---------------------------------------------------------------------------
# Ações manuais do coordenador
# ---------------------------------------------------------------------------
_STATUS_ESCOLHIVEIS_PELO_COORD = ("notificado", "aguardando_envio", "enviado", "validado")


def alterar_status_entrega(
    db: Session,
    entrega: EntregaRelatorio,
    novo_status: str,
    *,
    coord: User,
) -> None:
    """Coord/admin troca status manualmente. Registra audit (atualizado_por,
    atualizado_em). ``validado`` carimba ``validado_por_id`` e ``data_validacao``.
    """
    if novo_status not in _STATUS_ESCOLHIVEIS_PELO_COORD:
        raise ValueError(f"Status inválido: {novo_status}")
    entrega.status = novo_status
    entrega.atualizado_por_id = coord.id
    entrega.atualizado_em = datetime.utcnow()
    if novo_status == "enviado" and not entrega.data_envio:
        entrega.data_envio = entrega.atualizado_em
    if novo_status == "validado":
        entrega.validado_por_id = coord.id
        entrega.data_validacao = entrega.atualizado_em
    db.commit()


def reprovar_entrega(
    db: Session,
    entrega: EntregaRelatorio,
    motivo: str,
    *,
    coord: User,
) -> None:
    """Devolve a parcial ao autor com justificativa obrigatória.

    Volta ``status`` para ``aguardando_envio`` (autor passa a receber lembretes
    do ciclo de novo) e carimba ``motivo_reprovacao``/``data_reprovacao``/
    ``reprovado_por_id``. O autor verá o motivo na sua próxima visita à página
    de upload da seção ou ao receber o próximo e-mail manual do coord.
    """
    motivo_limpo = (motivo or "").strip()
    if not motivo_limpo:
        raise ValueError("Justificativa obrigatória para reprovar a entrega.")
    agora = datetime.utcnow()
    entrega.status = "aguardando_envio"
    entrega.motivo_reprovacao = motivo_limpo
    entrega.data_reprovacao = agora
    entrega.reprovado_por_id = coord.id
    entrega.atualizado_por_id = coord.id
    entrega.atualizado_em = agora
    db.commit()


def reenviar_manual(db: Session, entrega: EntregaRelatorio) -> bool:
    """Reenvia Mensagem 2 (manual) para uma entrega específica. Retorna
    ``True`` se sucesso. Não respeita a janela de 22h: é ato deliberado do
    coord."""
    rel = db.get(Relatorio, entrega.relatorio_id)
    user_obj = db.get(User, entrega.user_id) if entrega.user_id else None
    if not rel or not user_obj:
        return False
    secoes_rel = (
        db.query(Secao)
        .options(selectinload(Secao.responsavel))
        .filter(Secao.relatorio_id == rel.id)
        .all()
    )
    env = _Envio(
        rel, user_obj,
        [s for s in secoes_rel if s.responsavel_id == user_obj.id],
        {s.numero: s for s in secoes_rel},
    )
    resultado = _processar_destinatario(db, env, "manual", enviar_para="todos")
    db.commit()
    return resultado.sucesso
