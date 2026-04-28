"""Rotas POST de exclusão de relatório inteiro ou de subseção (SSE + sessão modal)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db, tx_session
from ..models import Bloco, EntregaRelatorio, Figura, Relatorio, Secao
from ..numeracao import consolidar_referencias, renumerar_relatorio
from ..process_events import process_done, process_log, process_start
from ..sra_process_modal import montar_data_modal_fim
from .pages import response_dashboard, response_relatorio_detail
from .relatorios import (
    _exigir_relatorio_editavel,
    _u_or_login,
)

router = APIRouter()


def _mensagem_mapa_exclusao_relatorio(db: Session, rel_id: int, codigo: str) -> str:
    """Resumo textual do escopo FK para o modal SSE (inventário do fluxo)."""
    n_sec = db.query(Secao).filter(Secao.relatorio_id == rel_id).count()
    n_blocos = (
        db.query(Bloco).join(Secao).filter(Secao.relatorio_id == rel_id).count()
    )
    n_figuras = db.query(Figura).filter(Figura.relatorio_id == rel_id).count()
    n_entregas = (
        db.query(EntregaRelatorio)
        .filter(EntregaRelatorio.relatorio_id == rel_id)
        .count()
    )
    return (
        f"Mapeamento: «{codigo}» — {n_sec} secção(ões), {n_blocos} bloco(s), "
        f"{n_figuras} figura(s), {n_entregas} registro(s) em entrega_relatorio "
        "(cascata até notificações)."
    )


@router.post("/{rel_id}/excluir")
def excluir_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    codigo = rel.codigo
    msg_mapa = _mensagem_mapa_exclusao_relatorio(db, rel_id, codigo)
    process_id = process_start(
        request,
        "Exclusão de relatório",
        f"Início da exclusão definitiva do relatório «{codigo}».",
        data={
            "process_key": "relatorio_excluir",
            "tarefa": "Exclusão de relatório",
        },
    )
    process_log(
        request,
        process_id,
        msg_mapa,
        etapa="Inventário (tabelas mapeadas)",
        tarefa="Exclusão de relatório",
        progresso_geral=18,
        progresso_tarefa=22,
    )
    process_log(
        request,
        process_id,
        "Eliminação em cascata: relatorio → secao → bloco; figuras; "
        "entrega_relatorio → notificacao_envio.",
        etapa="Transação e FK CASCADE",
        tarefa="Exclusão de relatório",
        progresso_geral=52,
        progresso_tarefa=58,
    )
    with tx_session() as txdb:
        rel_tx = txdb.get(Relatorio, rel_id)
        if rel_tx is not None:
            txdb.delete(rel_tx)
    process_log(
        request,
        process_id,
        "Linha principal e dependentes eliminadas na mesma transação.",
        etapa="Consolidação",
        tarefa="Exclusão de relatório",
        progresso_geral=88,
        progresso_tarefa=92,
    )
    msg_ok = f"O relatório «{codigo}» foi excluído do sistema."
    process_done(
        request,
        process_id,
        "Relatório excluído",
        msg_ok,
        process_key="relatorio_excluir",
    )
    fin_data = montar_data_modal_fim(
        process_key="relatorio_excluir",
        titulo="Relatório excluído",
        mensagem=msg_ok,
        outcome="success",
    )
    request.session["sra_fim_pendente"] = {"process_id": process_id, "data": fin_data}
    return response_dashboard(request, db)


@router.post("/{rel_id}/secoes/{sec_id}/excluir")
def excluir_subsecao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if "." not in (sec.numero or ""):
        raise HTTPException(400, detail="Não é possível excluir seções de primeiro nível")
    num_rotulo = (sec.numero or "").strip()
    tit_rotulo = (sec.titulo or "").strip()
    proc_label = "Exclusão de subseção"
    process_id = process_start(
        request,
        proc_label,
        f"Início da remoção da secção {num_rotulo} — {tit_rotulo} (blocos em cascata).",
        data={"process_key": "secao_excluir", "tarefa": proc_label},
    )
    process_log(
        request,
        process_id,
        "A consolidar marcadores FIGURA/TABELA e referências no texto…",
        etapa="Pré-remoção (consolidar)",
        tarefa=proc_label,
        progresso_geral=22,
        progresso_tarefa=28,
    )
    process_log(
        request,
        process_id,
        "A remover linha «secoes» (e «blocos» em cascata) e a renumerar o sumário…",
        etapa="Exclusão e renumeração",
        tarefa=proc_label,
        progresso_geral=58,
        progresso_tarefa=62,
    )
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        sec_tx = txdb.get(Secao, sec_id)
        if sec_tx is not None:
            txdb.delete(sec_tx)
            txdb.flush()
        renumerar_relatorio(txdb, rel_id)
    msg_ok = f"A secção {num_rotulo} foi removida e os números do sumário reajustados."
    process_done(
        request,
        process_id,
        "Subseção excluída",
        msg_ok,
        process_key="secao_excluir",
    )
    fin_data = montar_data_modal_fim(
        process_key="secao_excluir",
        titulo="Subseção excluída",
        mensagem=msg_ok,
        outcome="success",
    )
    request.session["sra_fim_pendente"] = {"process_id": process_id, "data": fin_data}
    return response_relatorio_detail(request, db, rel_id)
