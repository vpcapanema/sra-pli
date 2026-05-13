"""Executor de alertas configuráveis com envio real via SendGrid.

Este módulo implementa a camada de execução do Sistema de Alertas:
- Resolve destinatários por perfil ou usuários específicos
- Executa fluxos de mensagens de acordo com timing configurado
- Integra com email_sender.py para envio via SendGrid
- Cria registros de AlertaExecucao e logs de auditoria
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ...models import (
    Alerta,
    AlertaExecucao,
    AlertaFluxo,
    AlertaLog,
    User,
)
from ...notificacoes.email_sender import (
    ResultadoEnvio,
    enviar_notificacao,
)

log = logging.getLogger(__name__)


def _resolver_destinatarios_fluxo(
    db: Session,
    fluxo: AlertaFluxo,
) -> list[tuple[str, str]]:
    """Resolve lista de (email, nome) para um fluxo.

    Prioridade:
    1. Se `usuarios_destinatarios_json` tem IDs, usa esses usuários
    2. Senão, se `perfis_destinatarios_json` tem perfis, filtra
    3. Se ambos vazios, retorna lista vazia
    """
    destinatarios: list[tuple[str, str]] = []

    # 1. Usuários específicos (prioridade)
    if fluxo.usuarios_destinatarios_json:
        try:
            user_ids = json.loads(fluxo.usuarios_destinatarios_json)
            if user_ids:
                usuarios = db.query(User).filter(User.id.in_(user_ids)).all()
                for u in usuarios:
                    if u.email:
                        destinatarios.append((u.email, u.nome))
                log.info(
                    "[custom_sender] Fluxo %d: %d destinatários por usuário específico",
                    fluxo.id,
                    len(destinatarios),
                )
                return destinatarios
        except json.JSONDecodeError as e:
            log.error(
                "[custom_sender] Erro ao parse usuarios_destinatarios_json: %s",
                e,
            )

    # 2. Perfis
    if fluxo.perfis_destinatarios_json:
        try:
            perfis = json.loads(fluxo.perfis_destinatarios_json)
            if perfis:
                usuarios = db.query(User).filter(User.role.in_(perfis)).all()
                for u in usuarios:
                    if u.email:
                        destinatarios.append((u.email, u.nome))
                log.info(
                    "[custom_sender] Fluxo %d: %d destinatários por perfil %s",
                    fluxo.id,
                    len(destinatarios),
                    perfis,
                )
                return destinatarios
        except json.JSONDecodeError as e:
            log.error(
                "[custom_sender] Erro ao parse perfis_destinatarios_json: %s",
                e,
            )

    log.warning(
        "[custom_sender] Fluxo %d: nenhum destinatário configurado",
        fluxo.id,
    )
    return destinatarios


def _montar_contexto_email(
    alerta: Alerta,
    fluxo: AlertaFluxo,
) -> dict[str, Any]:
    """Monta contexto Jinja para o template de email."""
    contexto = {
        "alerta_nome": alerta.nome,
        "alerta_descricao": alerta.descricao or "",
        "tipo_mensagem": fluxo.tipo_mensagem,
        "fluxo_ordem": fluxo.ordem,
        "dia_no_ciclo": fluxo.dia_no_ciclo,
        "hora_disparo": fluxo.hora_disparo,
        "evento_inicio": (alerta.inicio_evento.strftime("%d/%m/%Y %H:%M") if alerta.inicio_evento else ""),
        "evento_fim": (alerta.fim_evento.strftime("%d/%m/%Y %H:%M") if alerta.fim_evento else ""),
        "alerta_inicio": (alerta.inicio_alerta.strftime("%d/%m/%Y %H:%M") if alerta.inicio_alerta else ""),
        "alerta_fim": (alerta.fim_alerta.strftime("%d/%m/%Y %H:%M") if alerta.fim_alerta else ""),
    }

    return contexto


def _criar_execucao(
    db: Session,
    alerta: Alerta,
    fluxo: AlertaFluxo,
    agendamento_id: int | None = None,
) -> AlertaExecucao:
    """Cria registro de AlertaExecucao."""
    execucao = AlertaExecucao(
        alerta_id=alerta.id,
        fluxo_id=fluxo.id,
        agendamento_id=agendamento_id,
        origem_execucao="scheduler",
        horario_programado=datetime.now(timezone.utc),
        status="pendente",
        tentativa=1,
    )
    db.add(execucao)
    db.flush()
    return execucao


def _registrar_log(
    db: Session,
    alerta_id: int,
    execucao_id: int | None,
    tipo_evento: str,
    descricao: str,
    detalhes: dict[str, Any] | None = None,
) -> None:
    """Registra log de auditoria."""
    log_entry = AlertaLog(
        alerta_id=alerta_id,
        execucao_id=execucao_id,
        tipo_evento=tipo_evento,
        descricao=descricao,
        detalhes_json=json.dumps(detalhes) if detalhes else None,
    )
    db.add(log_entry)
    db.flush()


def executar_fluxo_alerta(
    db: Session,
    alerta_id: int,
    fluxo_id: int,
    agendamento_id: int | None = None,
) -> AlertaExecucao:
    """Executa um fluxo de alerta completo.

    Fluxo:
    1. Carrega alerta e fluxo do banco
    2. Resolve destinatários (perfil ou usuários específicos)
    3. Cria AlertaExecucao com status=pendente
    4. Para cada destinatário: envia email via email_sender.py
    5. Atualiza AlertaExecucao com resultado final
    6. Registra logs de auditoria

    Args:
        db: Sessão do banco de dados
        alerta_id: ID do alerta
        fluxo_id: ID do fluxo a executar
        agendamento_id: ID do agendamento (opcional)

    Returns:
        AlertaExecucao criada/atualizada
    """
    # 1. Carregar alerta e fluxo
    alerta = db.get(Alerta, alerta_id)
    if not alerta:
        raise ValueError(f"Alerta {alerta_id} não encontrado")

    fluxo = db.get(AlertaFluxo, fluxo_id)
    if not fluxo:
        raise ValueError(f"Fluxo {fluxo_id} não encontrado")

    if not fluxo.ativo:
        log.warning(
            "[custom_sender] Fluxo %d está inativo, pulando execução",
            fluxo_id,
        )
        raise ValueError(f"Fluxo {fluxo_id} está inativo")

    # 2. Criar execução
    execucao = _criar_execucao(db, alerta, fluxo, agendamento_id)
    execucao.horario_inicio_real = datetime.now(timezone.utc)
    execucao.status = "em_execucao"
    db.flush()

    _registrar_log(
        db,
        alerta_id,
        execucao.id,
        "execucao_inicio",
        f"Início da execução do fluxo {fluxo.ordem} do alerta '{alerta.nome}'",
        {"fluxo_id": fluxo_id, "tipo_mensagem": fluxo.tipo_mensagem},
    )

    # 3. Resolver destinatários
    destinatarios = _resolver_destinatarios_fluxo(db, fluxo)

    if not destinatarios:
        execucao.status = "falha"
        execucao.erro = "nenhum_destinatario"
        execucao.horario_fim_real = datetime.now(timezone.utc)
        execucao.sucesso = False
        db.commit()

        _registrar_log(
            db,
            alerta_id,
            execucao.id,
            "execucao_falha",
            "Falha: nenhum destinatário configurado",
        )

        log.warning(
            "[custom_sender] Execução %d abortada: nenhum destinatário",
            execucao.id,
        )
        return execucao

    # 4. Enviar emails
    contexto = _montar_contexto_email(alerta, fluxo)
    resultados: list[ResultadoEnvio] = []
    destinatarios_processados: dict[str, Any] = {}

    for email, nome in destinatarios:
        resultado = enviar_notificacao(
            destinatario_email=email,
            destinatario_nome=nome,
            tipo=fluxo.tipo_mensagem,
            contexto={**contexto, "destinatario_nome": nome},
        )
        resultados.append(resultado)
        destinatarios_processados[email] = {
            "sucesso": resultado.sucesso,
            "erro": resultado.erro,
            "message_id": resultado.message_id,
            "modo": resultado.modo,
        }

    # 5. Atualizar execução com resultado
    todos_sucesso = all(r.sucesso for r in resultados)
    execucao.sucesso = todos_sucesso
    execucao.status = "concluida" if todos_sucesso else "parcial"
    execucao.horario_fim_real = datetime.now(timezone.utc)
    execucao.destinatarios_processados_json = json.dumps(destinatarios_processados)

    # Pega message_id do primeiro sucesso (se houver)
    primeiro_sucesso = next((r for r in resultados if r.sucesso), None)
    if primeiro_sucesso:
        execucao.message_id_provedor = primeiro_sucesso.message_id
        execucao.provedor_status = primeiro_sucesso.modo

    # Se todos falharam, registra erro geral
    if not todos_sucesso:
        erros = [r.erro for r in resultados if r.erro]
        execucao.erro = "; ".join(erros) if erros else "falha_envio"

    db.commit()

    # 6. Log final
    _registrar_log(
        db,
        alerta_id,
        execucao.id,
        "execucao_conclusao",
        f"Execução concluída: {len(resultados)} emails, {len([r for r in resultados if r.sucesso])} sucesso",
        {
            "total_envios": len(resultados),
            "sucessos": len([r for r in resultados if r.sucesso]),
            "falhas": len([r for r in resultados if not r.sucesso]),
            "modo_envio": resultados[0].modo if resultados else "desconhecido",
        },
    )

    log.info(
        "[custom_sender] Execução %d concluída: sucesso=%s, %d/%d emails enviados",
        execucao.id,
        execucao.sucesso,
        len([r for r in resultados if r.sucesso]),
        len(resultados),
    )

    return execucao


def executar_alerta_completo(
    db: Session,
    alerta_id: int,
    agendamento_id: int | None = None,
) -> list[AlertaExecucao]:
    """Executa todos os fluxos ativos de um alerta.

    Útil para execução manual ou quando o scheduler determina que
    todos os fluxos devem ser disparados (ex.: alerta único).

    Args:
        db: Sessão do banco de dados
        alerta_id: ID do alerta
        agendamento_id: ID do agendamento (opcional)

    Returns:
        Lista de AlertaExecucao criadas
    """
    alerta = db.get(Alerta, alerta_id)
    if not alerta:
        raise ValueError(f"Alerta {alerta_id} não encontrado")

    if alerta.status != "ativo":
        log.warning(
            "[custom_sender] Alerta %d não está ativo (status=%s), pulando execução",
            alerta_id,
            alerta.status,
        )
        return []

    fluxos_ativos = [f for f in alerta.fluxos if f.ativo]
    if not fluxos_ativos:
        log.warning(
            "[custom_sender] Alerta %d não possui fluxos ativos",
            alerta_id,
        )
        return []

    log.info(
        "[custom_sender] Executando alerta %d (%s): %d fluxos ativos",
        alerta_id,
        alerta.nome,
        len(fluxos_ativos),
    )

    execucoes: list[AlertaExecucao] = []
    for fluxo in fluxos_ativos:
        try:
            execucao = executar_fluxo_alerta(
                db,
                alerta_id,
                fluxo.id,
                agendamento_id,
            )
            execucoes.append(execucao)
        except Exception as e:
            log.error(
                "[custom_sender] Erro ao executar fluxo %d do alerta %d: %s",
                fluxo.id,
                alerta_id,
                e,
                exc_info=True,
            )
            # Continua com próximos fluxos mesmo se um falhar

    _registrar_log(
        db,
        alerta_id,
        None,
        "alerta_execucao_batch",
        f"Execução em lote do alerta '{alerta.nome}': {len(execucoes)} fluxos processados",
        {
            "total_fluxos": len(fluxos_ativos),
            "execucoes_criadas": len(execucoes),
            "execucoes_sucesso": len([e for e in execucoes if e.sucesso]),
        },
    )
    db.commit()

    return execucoes
