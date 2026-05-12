"""Endpoints REST para o Sistema de Alertas Configuráveis."""

from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..auth import require_user_api, require_admin
from ..schemas.alertas import (
    AlertaCreate,
    AlertaUpdate,
    AlertaOut,
    AlertaResumoOut,
    AlertaFluxoCreate,
    AlertaFluxoUpdate,
    AlertaFluxoOut,
    AlertaAgendamentoOut,
    AlertaExecucaoOut,
    AlertaLogOut,
    ReordenarFluxo,
    DuplicarAlerta,
)
from ..services.central_notificacoes.alertas_crud import (
    criar_alerta,
    listar_alertas,
    obter_alerta,
    atualizar_alerta,
    deletar_alerta,
    duplicar_alerta,
    transicionar_estado,
    criar_fluxo,
    atualizar_fluxo,
    deletar_fluxo,
    reordenar_fluxos,
    criar_ou_atualizar_agendamento,
    suspender_agendamento,
    retomar_agendamento,
    cancelar_agendamento,
    listar_execucoes,
    obter_execucao,
    retry_execucao,
    listar_logs,
)

router = APIRouter(prefix="/api", tags=["alertas"])


# ---------- Apoio à UI ----------


@router.get("/tipos-mensagem")
def tipos_mensagem():
    return [
        {"id": "abertura", "nome": "Abertura"},
        {"id": "lembrete", "nome": "Lembrete"},
        {"id": "ultima_chamada", "nome": "Última Chamada"},
        {"id": "customizado", "nome": "Customizado"},
        {"id": "boas_vindas", "nome": "Boas-vindas"},
    ]


@router.get("/perfis-usuario")
def perfis_usuario():
    return [
        {"id": "autor", "nome": "Autor"},
        {"id": "coordenador", "nome": "Coordenador"},
        {"id": "admin", "nome": "Administrador"},
    ]


@router.get("/usuarios")
def usuarios_lista(
    db: Session = Depends(get_db),
    perfil: Optional[str] = Query(None),
    _=Depends(require_user_api),
):
    from ..models import User

    q = db.query(User)
    if perfil:
        q = q.filter(User.role == perfil)
    return [
        {"id": u.id, "nome": u.nome, "email": u.email, "role": u.role}
        for u in q.all()
    ]


@router.get("/frequencias-alerta")
def frequencias_alerta():
    return [
        {"id": "unico", "nome": "Único"},
        {"id": "recorrente", "nome": "Recorrente"},
    ]


@router.get("/subtipos-recorrencia")
def subtipos_recorrencia():
    return [
        {"id": "horaria", "nome": "Horária"},
        {"id": "diaria", "nome": "Diária"},
        {"id": "semanal", "nome": "Semanal"},
        {"id": "quinzenal", "nome": "Quinzenal"},
        {"id": "mensal", "nome": "Mensal"},
        {"id": "anual", "nome": "Anual"},
        {"id": "customizada", "nome": "Customizada"},
    ]


@router.get("/condicoes-encerramento")
def condicoes_encerramento():
    return [
        {"id": "fim_ciclo", "nome": "Encerrar no fim do ciclo"},
        {
            "id": "todos_concluiram",
            "nome": "Todos os destinatários concluíram",
        },
        {"id": "item_validado", "nome": "Item validado/aprovado"},
        {"id": "manual", "nome": "Encerramento manual"},
        {"id": "ultima_mensagem", "nome": "Ao atingir última mensagem"},
    ]


# ---------- Alertas ----------


@router.post("/alertas", response_model=AlertaOut)
def api_criar_alerta(
    payload: AlertaCreate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return criar_alerta(db, dados, user)


@router.get("/alertas", response_model=list[AlertaResumoOut])
def api_listar_alertas(
    status: Optional[str] = Query(None),
    frequencia: Optional[str] = Query(None),
    busca: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    return listar_alertas(
        db,
        status=status,
        frequencia=frequencia,
        busca=busca,
    )


@router.get("/alertas/{alerta_id}", response_model=AlertaOut)
def api_obter_alerta(
    alerta_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    return obter_alerta(db, alerta_id)


@router.put("/alertas/{alerta_id}", response_model=AlertaOut)
def api_atualizar_alerta(
    alerta_id: int,
    payload: AlertaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return atualizar_alerta(db, alerta_id, dados, user)


@router.patch("/alertas/{alerta_id}", response_model=AlertaOut)
def api_patch_alerta(
    alerta_id: int,
    payload: AlertaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return atualizar_alerta(db, alerta_id, dados, user)


@router.delete("/alertas/{alerta_id}")
def api_deletar_alerta(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    deletar_alerta(db, alerta_id, user)
    return {"ok": True}


@router.post("/alertas/{alerta_id}/duplicar", response_model=AlertaOut)
def api_duplicar_alerta(
    alerta_id: int,
    payload: DuplicarAlerta,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return duplicar_alerta(db, alerta_id, payload.novo_nome, user)


@router.post("/alertas/{alerta_id}/validar")
def api_validar_alerta(
    alerta_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    alerta = obter_alerta(db, alerta_id)
    return {"valido": True, "status": alerta.status}


# ---------- Estado ----------


@router.post("/alertas/{alerta_id}/ativar", response_model=AlertaOut)
def api_ativar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return transicionar_estado(db, alerta_id, "ativar", user)


@router.post("/alertas/{alerta_id}/pausar", response_model=AlertaOut)
def api_pausar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return transicionar_estado(db, alerta_id, "pausar", user)


@router.post("/alertas/{alerta_id}/reativar", response_model=AlertaOut)
def api_reativar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return transicionar_estado(db, alerta_id, "reativar", user)


@router.post("/alertas/{alerta_id}/encerrar", response_model=AlertaOut)
def api_encerrar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return transicionar_estado(db, alerta_id, "encerrar", user)


# ---------- Fluxos ----------


@router.post("/alertas/{alerta_id}/fluxos", response_model=AlertaFluxoOut)
def api_criar_fluxo(
    alerta_id: int,
    payload: AlertaFluxoCreate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return criar_fluxo(db, alerta_id, dados, user)


@router.put(
    "/alertas/{alerta_id}/fluxos/{fluxo_id}",
    response_model=AlertaFluxoOut,
)
def api_atualizar_fluxo(
    alerta_id: int,
    fluxo_id: int,
    payload: AlertaFluxoUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return atualizar_fluxo(db, alerta_id, fluxo_id, dados, user)


@router.patch(
    "/alertas/{alerta_id}/fluxos/{fluxo_id}",
    response_model=AlertaFluxoOut,
)
def api_patch_fluxo(
    alerta_id: int,
    fluxo_id: int,
    payload: AlertaFluxoUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    dados = payload.model_dump(exclude_unset=True)
    return atualizar_fluxo(db, alerta_id, fluxo_id, dados, user)


@router.delete("/alertas/{alerta_id}/fluxos/{fluxo_id}")
def api_deletar_fluxo(
    alerta_id: int,
    fluxo_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    deletar_fluxo(db, alerta_id, fluxo_id, user)
    return {"ok": True}


@router.post("/alertas/{alerta_id}/fluxos/reordenar")
def api_reordenar_fluxos(
    alerta_id: int,
    payload: ReordenarFluxo,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    reordenar_fluxos(db, alerta_id, payload.ordens, user)
    return {"ok": True}


# ---------- Agendamento ----------


@router.post(
    "/alertas/{alerta_id}/agendar",
    response_model=AlertaAgendamentoOut,
)
def api_agendar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return criar_ou_atualizar_agendamento(
        db,
        alerta_id,
        {"status_scheduler": "ativo", "ativo": True},
        user,
    )


@router.post(
    "/alertas/{alerta_id}/reagendar",
    response_model=AlertaAgendamentoOut,
)
def api_reagendar(
    alerta_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return criar_ou_atualizar_agendamento(db, alerta_id, payload, user)


@router.post(
    "/alertas/{alerta_id}/suspender",
    response_model=AlertaAgendamentoOut,
)
def api_suspender(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return suspender_agendamento(db, alerta_id, user)


@router.post(
    "/alertas/{alerta_id}/retomar",
    response_model=AlertaAgendamentoOut,
)
def api_retomar(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return retomar_agendamento(db, alerta_id, user)


@router.post("/alertas/{alerta_id}/cancelar-agendamento")
def api_cancelar_agendamento(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    cancelar_agendamento(db, alerta_id, user)
    return {"ok": True}


@router.post("/alertas/{alerta_id}/executar-agora")
def api_executar_agora(
    alerta_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    # TODO: acionar execução imediata via scheduler
    return {"ok": True, "message": "Execução imediata enfileirada."}


@router.get(
    "/alertas/{alerta_id}/agendamento",
    response_model=Optional[AlertaAgendamentoOut],
)
def api_obter_agendamento(
    alerta_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    from ..models import AlertaAgendamento

    return (
        db.query(AlertaAgendamento)
        .filter(AlertaAgendamento.alerta_id == alerta_id)
        .first()
    )


# ---------- Execução / Logs ----------


@router.get(
    "/alertas/{alerta_id}/execucoes",
    response_model=list[AlertaExecucaoOut],
)
def api_execucoes(
    alerta_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    return listar_execucoes(db, alerta_id, limit=limit)


@router.get("/alertas/{alerta_id}/logs", response_model=list[AlertaLogOut])
def api_logs(
    alerta_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    return listar_logs(db, alerta_id, limit=limit)


@router.get("/execucoes/{execucao_id}", response_model=AlertaExecucaoOut)
def api_obter_execucao(
    execucao_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_user_api),
):
    return obter_execucao(db, execucao_id)


@router.post(
    "/execucoes/{execucao_id}/retry",
    response_model=AlertaExecucaoOut,
)
def api_retry_execucao(
    execucao_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    return retry_execucao(db, execucao_id, user)
