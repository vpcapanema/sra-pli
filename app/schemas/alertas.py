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
    data_base_inicio_evento: Optional[datetime] = None
    regra_disparo: Optional[dict] = None
    ativo: bool = True


class AlertaFluxoCreate(AlertaFluxoBase):
    pass


class AlertaFluxoUpdate(AlertaFluxoBase):
    ordem: Optional[int] = None
    tipo_mensagem: Optional[str] = None
    dia_no_ciclo: Optional[int] = None
    hora_disparo: Optional[str] = None
    data_base_inicio_evento: Optional[datetime] = None
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
    inicio_ciclo_evento_posicao: Optional[int] = None
    fim_ciclo_evento_posicao: Optional[int] = None
    inicio_ciclo_alerta_posicao: Optional[int] = None
    fim_ciclo_alerta_posicao: Optional[int] = None
    condicao_encerramento: str = Field(
        default="manual",
        pattern=(r"^(fim_ciclo|todos_concluiram|item_validado|manual|ultima_mensagem)$"),
    )
    regras_customizadas: Optional[dict] = None

    @model_validator(mode="after")
    def validar_posicoes(self):
        if self.fim_ciclo_evento_posicao and self.inicio_ciclo_evento_posicao:
            # Se fim < inicio, indica ciclo cruzando período (ex: dia 11 ao dia 10 do mês seguinte)
            pass
        if self.fim_ciclo_alerta_posicao and self.inicio_ciclo_alerta_posicao:
            # Se fim < inicio, indica ciclo cruzando período
            pass
        if self.frequencia == "unico" and self.subtipo_recorrencia:
            raise ValueError("frequência única não pode ter subtipo_recorrencia")
        if (self.frequencia == "recorrente"
                and self.status not in ("rascunho", "encerrado")
                and not self.subtipo_recorrencia):
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
    inicio_ciclo_evento_posicao: Optional[int] = None
    fim_ciclo_evento_posicao: Optional[int] = None
    inicio_ciclo_alerta_posicao: Optional[int] = None
    fim_ciclo_alerta_posicao: Optional[int] = None
    condicao_encerramento: Optional[str] = None
    regras_customizadas: Optional[dict] = None

    @model_validator(mode="after")
    def validar_posicoes(self):
        if self.fim_ciclo_evento_posicao and self.inicio_ciclo_evento_posicao:
            pass
        if self.fim_ciclo_alerta_posicao and self.inicio_ciclo_alerta_posicao:
            pass
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
    inicio_ciclo_alerta_posicao: Optional[int]
    fim_ciclo_alerta_posicao: Optional[int]
    condicao_encerramento: str
    criado_em: datetime
    atualizado_em: datetime
    total_fluxos: int = 0

    class Config:
        from_attributes = True


# ---------- Alerta Único ----------


class AlertaUnicoBase(BaseModel):
    tipo_mensagem: str = Field(..., min_length=1, max_length=32)
    perfis_destinatarios: Optional[List[str]] = None
    usuarios_destinatarios: Optional[List[int]] = None
    data_evento: Optional[datetime] = None
    data_alerta: Optional[datetime] = None
    data_inicio_disparos: Optional[datetime] = None


class AlertaUnicoCreate(AlertaUnicoBase):
    alerta_id: int


class AlertaUnicoUpdate(AlertaUnicoBase):
    pass


class AlertaUnicoOut(AlertaUnicoBase):
    id: int
    alerta_id: int
    criado_em: datetime
    atualizado_em: datetime

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
