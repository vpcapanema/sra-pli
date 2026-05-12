"""Schemas Pydantic para o Sistema de Alertas Configuráveis."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator

# ---------- Fluxo ----------


class AlertaFluxoBase(BaseModel):
    ordem: int = 0
    tipo_mensagem: str = Field(..., min_length=1, max_length=32)
    perfis_destinatarios: Optional[List[str]] = None
    usuarios_destinatarios: Optional[List[int]] = None
    dia_no_ciclo: int = 1
    hora_disparo: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    regra_disparo: Optional[dict] = None
    ativo: bool = True


class AlertaFluxoCreate(AlertaFluxoBase):
    pass


class AlertaFluxoUpdate(AlertaFluxoBase):
    ordem: Optional[int] = None
    tipo_mensagem: Optional[str] = None
    dia_no_ciclo: Optional[int] = None
    hora_disparo: Optional[str] = None
    ativo: Optional[bool] = None


class AlertaFluxoOut(AlertaFluxoBase):
    id: int
    alerta_id: int

    class Config:
        from_attributes = True


# ---------- Alerta ----------


class AlertaBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=255)
    descricao: Optional[str] = None
    status: str = Field(
        default="rascunho",
        pattern=r"^(rascunho|agendado|ativo|pausado|encerrado)$",
    )
    frequencia: str = Field(default="unico", pattern=r"^(unico|recorrente)$")
    subtipo_recorrencia: Optional[str] = None
    timezone: str = Field(default="America/Sao_Paulo", max_length=64)
    inicio_evento: Optional[datetime] = None
    fim_evento: Optional[datetime] = None
    inicio_alerta: Optional[datetime] = None
    fim_alerta: Optional[datetime] = None
    condicao_encerramento: str = Field(
        default="manual",
        pattern=(r"^(fim_ciclo|todos_concluiram|item_validado|manual|ultima_mensagem)$"),
    )
    regras_customizadas: Optional[dict] = None
    data_inicio_disparos: Optional[datetime] = None
    dias_semana: Optional[List[int]] = None
    intervalo_horario_inicio: Optional[str] = None
    intervalo_horario_fim: Optional[str] = None

    @model_validator(mode="after")
    def validar_datas(self):
        if self.fim_evento and self.inicio_evento and self.fim_evento < self.inicio_evento:
            raise ValueError("fim_evento não pode ser anterior a inicio_evento")
        if self.fim_alerta and self.inicio_alerta and self.fim_alerta < self.inicio_alerta:
            raise ValueError("fim_alerta não pode ser anterior a inicio_alerta")
        if self.frequencia == "unico" and self.subtipo_recorrencia:
            raise ValueError("frequência única não pode ter subtipo_recorrencia")
        if (
            self.frequencia == "recorrente"
            and self.status not in ("rascunho", "encerrado")
            and not self.subtipo_recorrencia
        ):
            raise ValueError("frequência recorrente exige subtipo_recorrencia")
        return self


class AlertaCreate(AlertaBase):
    fluxos: Optional[List[AlertaFluxoCreate]] = None


class AlertaUpdate(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    descricao: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern=r"^(rascunho|agendado|ativo|pausado|encerrado)$")
    frequencia: Optional[str] = None
    subtipo_recorrencia: Optional[str] = None
    timezone: Optional[str] = None
    inicio_evento: Optional[datetime] = None
    fim_evento: Optional[datetime] = None
    inicio_alerta: Optional[datetime] = None
    fim_alerta: Optional[datetime] = None
    condicao_encerramento: Optional[str] = None
    regras_customizadas: Optional[dict] = None
    data_inicio_disparos: Optional[datetime] = None
    dias_semana: Optional[List[int]] = None
    intervalo_horario_inicio: Optional[str] = None
    intervalo_horario_fim: Optional[str] = None

    @model_validator(mode="after")
    def validar_datas(self):
        if self.fim_evento and self.inicio_evento and self.fim_evento < self.inicio_evento:
            raise ValueError("fim_evento não pode ser anterior a inicio_evento")
        if self.fim_alerta and self.inicio_alerta and self.fim_alerta < self.inicio_alerta:
            raise ValueError("fim_alerta não pode ser anterior a inicio_alerta")
        return self


class AlertaOut(AlertaBase):
    id: int
    criado_por_id: int
    criado_em: datetime
    atualizado_em: datetime
    fluxos: List[AlertaFluxoOut] = []

    class Config:
        from_attributes = True


class AlertaResumoOut(BaseModel):
    id: int
    nome: str
    descricao: Optional[str]
    status: str
    frequencia: str
    subtipo_recorrencia: Optional[str]
    inicio_alerta: Optional[datetime]
    fim_alerta: Optional[datetime]
    condicao_encerramento: str
    criado_em: datetime
    atualizado_em: datetime
    total_fluxos: int = 0

    class Config:
        from_attributes = True


# ---------- Agendamento ----------


class AlertaAgendamentoBase(BaseModel):
    status_scheduler: str = Field(default="pendente", max_length=32)
    data_inicio_disparos: Optional[datetime] = None
    proxima_execucao: Optional[datetime] = None
    ultima_execucao: Optional[datetime] = None
    timezone: str = Field(default="America/Sao_Paulo", max_length=64)
    cron_expression: Optional[str] = None
    bloqueado_ate: Optional[datetime] = None
    ativo: bool = True


class AlertaAgendamentoOut(AlertaAgendamentoBase):
    id: int
    alerta_id: int
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


# ---------- Execução ----------


class AlertaExecucaoBase(BaseModel):
    origem_execucao: str = Field(default="cron", max_length=32)
    horario_programado: datetime
    horario_inicio_real: Optional[datetime] = None
    horario_fim_real: Optional[datetime] = None
    status: str = Field(default="pendente", max_length=32)
    sucesso: Optional[bool] = None
    erro: Optional[str] = None
    tentativa: int = 1
    payload_execucao: Optional[dict] = None
    message_id_provedor: Optional[str] = None
    provedor_status: Optional[str] = None
    aberto_em: Optional[datetime] = None
    entregue_em: Optional[datetime] = None
    destinatarios_processados: Optional[dict] = None


class AlertaExecucaoOut(AlertaExecucaoBase):
    id: int
    alerta_id: int
    fluxo_id: Optional[int]
    agendamento_id: Optional[int]

    class Config:
        from_attributes = True


# ---------- Log / Auditoria ----------


class AlertaLogBase(BaseModel):
    tipo_evento: str = Field(..., max_length=64)
    descricao: Optional[str] = None
    detalhes: Optional[dict] = None


class AlertaLogOut(AlertaLogBase):
    id: int
    alerta_id: int
    execucao_id: Optional[int]
    usuario_acao_id: Optional[int]
    criado_em: datetime

    class Config:
        from_attributes = True


# ---------- Operações de estado ----------


class EstadoTransicao(BaseModel):
    acao: str = Field(
        ...,
        pattern=(
            r"^(ativar|pausar|reativar|encerrar|agendar|suspender|retomar"
            r"|cancelar|executar_agora|reagendar)$"
        ),
    )
    motivo: Optional[str] = None


class ReordenarFluxo(BaseModel):
    ordens: List[int] = Field(..., min_length=1)


class DuplicarAlerta(BaseModel):
    novo_nome: Optional[str] = None


class RetryExecucao(BaseModel):
    motivo: Optional[str] = None


# ---------- Filtros ----------


class AlertaFiltro(BaseModel):
    status: Optional[str] = None
    frequencia: Optional[str] = None
    busca: Optional[str] = None
