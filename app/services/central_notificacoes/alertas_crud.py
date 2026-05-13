"""CRUD e regras de negócio para o Sistema de Alertas Configuráveis."""

import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from fastapi import HTTPException

from ...models import (
    Alerta,
    AlertaFluxo,
    AlertaAgendamento,
    AlertaExecucao,
    AlertaLog,
    AlertaUnico,
    User,
)

# ---------- Validações ----------


def _validar_fluxo_cobre_janela(alerta: Alerta) -> None:
    """Verifica se itens do fluxo não caem fora da janela do alerta."""
    if alerta.status in ("rascunho", "encerrado"):
        return
    fluxos = [f for f in alerta.fluxos if f.ativo]
    if not fluxos and alerta.status != "rascunho":
        raise HTTPException(422, "Alerta finalizado deve ter pelo menos um fluxo ativo.")
    if alerta.fim_alerta:
        for f in fluxos:
            if f.dia_no_ciclo < 0:
                raise HTTPException(
                    422,
                    f"Fluxo {f.ordem}: dia_no_ciclo não pode ser negativo.",
                )


def _validar_agendamento_passado(data_inicio: Optional[datetime]) -> None:
    if data_inicio and data_inicio < datetime.now(timezone.utc):
        raise HTTPException(422, "data_inicio_disparos não pode estar no passado.")


def _validar_conflito_regras(alerta: Alerta) -> None:
    if alerta.frequencia == "unico" and alerta.subtipo_recorrencia:
        raise HTTPException(422, "Frequência única não permite recorrência.")
    if alerta.frequencia == "recorrente" and alerta.subtipo_recorrencia == "customizada":
        if not alerta.regras_customizadas_json:
            raise HTTPException(422, "Recorrência customizada exige regras_customizadas.")


def _log(
    db: Session,
    alerta_id: int,
    tipo_evento: str,
    descricao: str,
    usuario_id: Optional[int] = None,
    execucao_id: Optional[int] = None,
    detalhes: Optional[dict] = None,
) -> None:
    db.add(
        AlertaLog(
            alerta_id=alerta_id,
            execucao_id=execucao_id,
            tipo_evento=tipo_evento,
            descricao=descricao,
            usuario_acao_id=usuario_id,
            detalhes_json=json.dumps(detalhes) if detalhes else None,
        )
    )
    db.commit()


# ---------- CRUD Alerta ----------


def criar_alerta(db: Session, dados: dict, criado_por: User) -> Alerta:
    fluxos_dados = dados.pop("fluxos", None)
    dados.pop("status", None)
    alerta = Alerta(
        **dados,
        criado_por_id=criado_por.id,
        status="rascunho",
    )
    db.add(alerta)
    db.flush()
    if fluxos_dados:
        for i, f in enumerate(fluxos_dados):
            db.add(
                AlertaFluxo(
                    alerta_id=alerta.id,
                    ordem=i,
                    tipo_mensagem=f["tipo_mensagem"],
                    perfis_destinatarios_json=json.dumps(f.get("perfis_destinatarios") or []),
                    usuarios_destinatarios_json=json.dumps(f.get("usuarios_destinatarios") or []),
                    dia_no_ciclo=f.get("dia_no_ciclo", 1),
                    hora_disparo=f.get("hora_disparo", "09:00"),
                    regra_disparo_json=(json.dumps(f.get("regra_disparo")) if f.get("regra_disparo") else None),
                    ativo=f.get("ativo", True),
                )
            )
    db.commit()
    db.refresh(alerta)
    _log(
        db,
        alerta.id,
        "criacao",
        f"Alerta '{alerta.nome}' criado por {criado_por.nome}",
        criado_por.id,
    )
    return alerta


def listar_alertas(
    db: Session,
    status: Optional[str] = None,
    frequencia: Optional[str] = None,
    busca: Optional[str] = None,
) -> list:
    q = db.query(Alerta)
    if status:
        q = q.filter(Alerta.status == status)
    if frequencia:
        q = q.filter(Alerta.frequencia == frequencia)
    if busca:
        q = q.filter(Alerta.nome.ilike(f"%{busca}%"))
    return q.order_by(desc(Alerta.atualizado_em)).all()


def obter_alerta(db: Session, alerta_id: int) -> Alerta:
    alerta = db.get(Alerta, alerta_id)
    if not alerta:
        raise HTTPException(404, "Alerta não encontrado.")
    return alerta


def atualizar_alerta(db: Session, alerta_id: int, dados: dict, usuario: User) -> Alerta:
    alerta = obter_alerta(db, alerta_id)
    if alerta.status == "encerrado":
        raise HTTPException(422, "Alerta encerrado não pode ser editado. Reative-o primeiro.")
    for campo, valor in dados.items():
        if campo in (
            "regras_customizadas",
            "dias_semana",
            "intervalo_horario_inicio",
            "intervalo_horario_fim",
        ):
            if campo == "regras_customizadas" and valor is not None:
                setattr(alerta, "regras_customizadas_json", json.dumps(valor))
            elif campo == "dias_semana" and valor is not None:
                setattr(alerta, "dias_semana", ",".join(str(d) for d in valor))
            elif campo == "intervalo_horario_inicio" and valor is not None:
                setattr(alerta, "intervalo_horario_inicio", valor)
            elif campo == "intervalo_horario_fim" and valor is not None:
                setattr(alerta, "intervalo_horario_fim", valor)
        else:
            if hasattr(alerta, campo):
                setattr(alerta, campo, valor)
    alerta.atualizado_em = datetime.now(timezone.utc)
    _validar_conflito_regras(alerta)
    _validar_fluxo_cobre_janela(alerta)
    db.commit()
    db.refresh(alerta)
    _log(
        db,
        alerta.id,
        "edicao",
        f"Alerta '{alerta.nome}' atualizado por {usuario.nome}",
        usuario.id,
    )
    return alerta


def deletar_alerta(db: Session, alerta_id: int, usuario: User) -> None:
    alerta = obter_alerta(db, alerta_id)
    db.delete(alerta)
    db.commit()
    _log(
        db,
        alerta_id,
        "exclusao",
        f"Alerta excluído por {usuario.nome}",
        usuario.id,
    )


def duplicar_alerta(db: Session, alerta_id: int, novo_nome: Optional[str], usuario: User) -> Alerta:
    original = obter_alerta(db, alerta_id)
    alerta = Alerta(
        nome=novo_nome or f"Cópia de {original.nome}",
        descricao=original.descricao,
        status="rascunho",
        frequencia=original.frequencia,
        subtipo_recorrencia=original.subtipo_recorrencia,
        timezone=original.timezone,
        inicio_evento=original.inicio_evento,
        fim_evento=original.fim_evento,
        inicio_alerta=original.inicio_alerta,
        fim_alerta=original.fim_alerta,
        condicao_encerramento=original.condicao_encerramento,
        regras_customizadas_json=original.regras_customizadas_json,
        data_inicio_disparos=None,
        dias_semana=original.dias_semana,
        intervalo_horario_inicio=original.intervalo_horario_inicio,
        intervalo_horario_fim=original.intervalo_horario_fim,
        criado_por_id=usuario.id,
    )
    db.add(alerta)
    db.flush()
    for f in original.fluxos:
        db.add(
            AlertaFluxo(
                alerta_id=alerta.id,
                ordem=f.ordem,
                tipo_mensagem=f.tipo_mensagem,
                perfis_destinatarios_json=f.perfis_destinatarios_json,
                usuarios_destinatarios_json=f.usuarios_destinatarios_json,
                dia_no_ciclo=f.dia_no_ciclo,
                hora_disparo=f.hora_disparo,
                regra_disparo_json=f.regra_disparo_json,
                ativo=f.ativo,
            )
        )
    db.commit()
    db.refresh(alerta)
    _log(
        db,
        alerta.id,
        "duplicacao",
        f"Duplicado de alerta {original.id} por {usuario.nome}",
        usuario.id,
    )
    return alerta


# ---------- Estado ----------


def _transicao_permitida(status_atual: str, acao: str) -> bool:
    maquina = {
        "rascunho": {"ativar", "agendar"},
        "agendado": {"ativar", "pausar", "cancelar"},
        "ativo": {"pausar", "encerrar", "executar_agora"},
        "pausado": {"reativar", "encerrar"},
        "encerrado": {"reativar"},
    }
    return acao in maquina.get(status_atual, set())


def transicionar_estado(db: Session, alerta_id: int, acao: str, usuario: User) -> Alerta:
    alerta = obter_alerta(db, alerta_id)
    if not _transicao_permitida(alerta.status, acao):
        raise HTTPException(422, f"Ação '{acao}' não permitida para status '{alerta.status}'.")
    if acao == "ativar":
        alerta.status = "ativo"
    elif acao == "pausar":
        alerta.status = "pausado"
    elif acao == "reativar":
        alerta.status = "ativo"
    elif acao == "encerrar":
        alerta.status = "encerrado"
    elif acao == "agendar":
        alerta.status = "agendado"
    alerta.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alerta)
    _log(
        db,
        alerta.id,
        "transicao_estado",
        f"Status alterado para {alerta.status} por {usuario.nome}",
        usuario.id,
        detalhes={"acao": acao},
    )
    return alerta


# ---------- CRUD Fluxo ----------


def criar_fluxo(db: Session, alerta_id: int, dados: dict, usuario: User) -> AlertaFluxo:
    alerta = obter_alerta(db, alerta_id)
    if alerta.status == "encerrado":
        raise HTTPException(422, "Alerta encerrado não pode receber novos fluxos.")
    max_ordem = db.query(func.max(AlertaFluxo.ordem)).filter(AlertaFluxo.alerta_id == alerta_id).scalar() or -1
    fluxo = AlertaFluxo(
        alerta_id=alerta_id,
        ordem=max_ordem + 1,
        tipo_mensagem=dados["tipo_mensagem"],
        perfis_destinatarios_json=json.dumps(dados.get("perfis_destinatarios") or []),
        usuarios_destinatarios_json=json.dumps(dados.get("usuarios_destinatarios") or []),
        dia_no_ciclo=dados.get("dia_no_ciclo", 1),
        hora_disparo=dados.get("hora_disparo", "09:00"),
        regra_disparo_json=(json.dumps(dados.get("regra_disparo")) if dados.get("regra_disparo") else None),
        ativo=dados.get("ativo", True),
    )
    db.add(fluxo)
    db.commit()
    db.refresh(fluxo)
    _log(
        db,
        alerta_id,
        "fluxo_criacao",
        f"Fluxo {fluxo.ordem} adicionado por {usuario.nome}",
        usuario.id,
    )
    return fluxo


def atualizar_fluxo(db: Session, alerta_id: int, fluxo_id: int, dados: dict, usuario: User) -> AlertaFluxo:
    fluxo = db.query(AlertaFluxo).filter(AlertaFluxo.id == fluxo_id, AlertaFluxo.alerta_id == alerta_id).first()
    if not fluxo:
        raise HTTPException(404, "Fluxo não encontrado.")
    for campo, valor in dados.items():
        if campo in ("perfis_destinatarios", "usuarios_destinatarios"):
            setattr(fluxo, f"{campo}_json", json.dumps(valor or []))
        elif campo == "regra_disparo" and valor is not None:
            setattr(fluxo, "regra_disparo_json", json.dumps(valor))
        else:
            if hasattr(fluxo, campo):
                setattr(fluxo, campo, valor)
    db.commit()
    db.refresh(fluxo)
    _log(
        db,
        alerta_id,
        "fluxo_edicao",
        f"Fluxo {fluxo_id} atualizado por {usuario.nome}",
        usuario.id,
    )
    return fluxo


def deletar_fluxo(db: Session, alerta_id: int, fluxo_id: int, usuario: User) -> None:
    fluxo = db.query(AlertaFluxo).filter(AlertaFluxo.id == fluxo_id, AlertaFluxo.alerta_id == alerta_id).first()
    if not fluxo:
        raise HTTPException(404, "Fluxo não encontrado.")
    db.delete(fluxo)
    db.commit()
    _log(
        db,
        alerta_id,
        "fluxo_exclusao",
        f"Fluxo {fluxo_id} removido por {usuario.nome}",
        usuario.id,
    )


def reordenar_fluxos(db: Session, alerta_id: int, ordens: list, usuario: User) -> list:
    fluxos = db.query(AlertaFluxo).filter(AlertaFluxo.alerta_id == alerta_id).all()
    if len(fluxos) != len(ordens):
        raise HTTPException(422, "Número de ordens não corresponde ao número de fluxos.")
    id_map = {f.id: f for f in fluxos}
    for i, fid in enumerate(ordens):
        if fid not in id_map:
            raise HTTPException(422, f"Fluxo id={fid} não encontrado.")
        id_map[fid].ordem = i
    db.commit()
    _log(
        db,
        alerta_id,
        "fluxo_reordenacao",
        f"Fluxos reordenados por {usuario.nome}",
        usuario.id,
    )
    return fluxos


# ---------- CRUD Alerta Único ----------


def criar_alerta_unico(db: Session, dados: dict) -> AlertaUnico:
    alerta_unico = AlertaUnico(
        alerta_id=dados["alerta_id"],
        tipo_mensagem=dados["tipo_mensagem"],
        perfis_destinatarios_json=json.dumps(dados.get("perfis_destinatarios") or []),
        usuarios_destinatarios_json=json.dumps(dados.get("usuarios_destinatarios") or []),
        data_evento=dados.get("data_evento"),
        data_alerta=dados.get("data_alerta"),
        data_inicio_disparos=dados.get("data_inicio_disparos"),
    )
    db.add(alerta_unico)
    db.commit()
    db.refresh(alerta_unico)
    return alerta_unico


def obter_alerta_unico(db: Session, alerta_unico_id: int) -> Optional[AlertaUnico]:
    return db.query(AlertaUnico).filter(AlertaUnico.id == alerta_unico_id).first()


def obter_alerta_unico_por_alerta(db: Session, alerta_id: int) -> Optional[AlertaUnico]:
    return db.query(AlertaUnico).filter(AlertaUnico.alerta_id == alerta_id).first()


def atualizar_alerta_unico(
    db: Session, alerta_unico_id: int, dados: dict
) -> AlertaUnico:
    alerta_unico = obter_alerta_unico(db, alerta_unico_id)
    if not alerta_unico:
        raise HTTPException(404, "Alerta único não encontrado")
    for key, value in dados.items():
        if key in ("perfis_destinatarios", "usuarios_destinatarios"):
            value = json.dumps(value or [])
        if hasattr(alerta_unico, key):
            setattr(alerta_unico, key, value)
    alerta_unico.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alerta_unico)
    return alerta_unico


def deletar_alerta_unico(db: Session, alerta_unico_id: int) -> None:
    alerta_unico = obter_alerta_unico(db, alerta_unico_id)
    if not alerta_unico:
        raise HTTPException(404, "Alerta único não encontrado")
    db.delete(alerta_unico)
    db.commit()


# ---------- Agendamento ----------


def criar_ou_atualizar_agendamento(db: Session, alerta_id: int, dados: dict, usuario: User) -> AlertaAgendamento:
    alerta = obter_alerta(db, alerta_id)
    _validar_fluxo_cobre_janela(alerta)
    _validar_agendamento_passado(dados.get("data_inicio_disparos"))
    ag = db.query(AlertaAgendamento).filter(AlertaAgendamento.alerta_id == alerta_id).first()
    if not ag:
        ag = AlertaAgendamento(alerta_id=alerta_id)
        db.add(ag)
    for campo in (
        "status_scheduler",
        "data_inicio_disparos",
        "proxima_execucao",
        "timezone",
        "cron_expression",
        "bloqueado_ate",
        "ativo",
    ):
        if campo in dados and dados[campo] is not None:
            setattr(ag, campo, dados[campo])
    ag.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ag)
    _log(
        db,
        alerta_id,
        "agendamento",
        f"Agendamento atualizado por {usuario.nome}",
        usuario.id,
    )
    return ag


def suspender_agendamento(db: Session, alerta_id: int, usuario: User) -> AlertaAgendamento:
    ag = db.query(AlertaAgendamento).filter(AlertaAgendamento.alerta_id == alerta_id).first()
    if not ag:
        raise HTTPException(404, "Agendamento não encontrado.")
    ag.ativo = False
    ag.status_scheduler = "suspenso"
    ag.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    _log(
        db,
        alerta_id,
        "agendamento_suspensao",
        f"Agendamento suspenso por {usuario.nome}",
        usuario.id,
    )
    return ag


def retomar_agendamento(db: Session, alerta_id: int, usuario: User) -> AlertaAgendamento:
    ag = db.query(AlertaAgendamento).filter(AlertaAgendamento.alerta_id == alerta_id).first()
    if not ag:
        raise HTTPException(404, "Agendamento não encontrado.")
    ag.ativo = True
    ag.status_scheduler = "ativo"
    ag.atualizado_em = datetime.now(timezone.utc)
    db.commit()
    _log(
        db,
        alerta_id,
        "agendamento_retomada",
        f"Agendamento retomado por {usuario.nome}",
        usuario.id,
    )
    return ag


def cancelar_agendamento(db: Session, alerta_id: int, usuario: User) -> None:
    ag = db.query(AlertaAgendamento).filter(AlertaAgendamento.alerta_id == alerta_id).first()
    if ag:
        ag.ativo = False
        ag.status_scheduler = "cancelado"
        ag.atualizado_em = datetime.now(timezone.utc)
        db.commit()
        _log(
            db,
            alerta_id,
            "agendamento_cancelamento",
            f"Agendamento cancelado por {usuario.nome}",
            usuario.id,
        )


# ---------- Execução ----------


def listar_execucoes(db: Session, alerta_id: int, limit: int = 50) -> list:
    return (
        db.query(AlertaExecucao)
        .filter(AlertaExecucao.alerta_id == alerta_id)
        .order_by(desc(AlertaExecucao.horario_programado))
        .limit(limit)
        .all()
    )


def obter_execucao(db: Session, execucao_id: int) -> AlertaExecucao:
    e = db.get(AlertaExecucao, execucao_id)
    if not e:
        raise HTTPException(404, "Execução não encontrada.")
    return e


def retry_execucao(db: Session, execucao_id: int, usuario: User) -> AlertaExecucao:
    original = obter_execucao(db, execucao_id)
    nova = AlertaExecucao(
        alerta_id=original.alerta_id,
        fluxo_id=original.fluxo_id,
        agendamento_id=original.agendamento_id,
        origem_execucao="retry",
        horario_programado=datetime.now(timezone.utc),
        status="pendente",
        tentativa=original.tentativa + 1,
    )
    db.add(nova)
    db.commit()
    db.refresh(nova)
    _log(
        db,
        original.alerta_id,
        "execucao_retry",
        f"Retry da execução {execucao_id} por {usuario.nome}",
        usuario.id,
        execucao_id=nova.id,
    )
    return nova


# ---------- Logs ----------


def listar_logs(db: Session, alerta_id: int, limit: int = 100) -> list:
    return (
        db.query(AlertaLog)
        .filter(AlertaLog.alerta_id == alerta_id)
        .order_by(desc(AlertaLog.criado_em))
        .limit(limit)
        .all()
    )
