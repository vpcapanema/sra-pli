"""Governança técnica: parâmetros do ciclo, entregas, notificações e utilizadores."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import quote, unquote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session, joinedload
from starlette.responses import RedirectResponse

from ..auth import current_user, formatar_nome_pessoa
from ..config import settings
from ..db import get_db
from ..models import (
    ENTREGA_STATUS_VALIDOS,
    EntregaRelatorio,
    NotificacaoEnvio,
    ParametrosCicloNotificacao,
    Relatorio,
    User,
)
from ..notificacoes.ciclo_params import try_salvar_parametros_ciclo_form_post_campos
from ..notificacoes.email_sender import modo_atual
from ..notificacoes.service import (
    abrir_periodo,
    enviar_lembretes,
    notificar_autores_abertura,
    retry_falhas,
)
from ..routes.auth import normalizar_email_secundario_obrigatorio
from .pages import templates, user_or_login_page

router = APIRouter(tags=["governanca"])

_GOV_LIMIT_ENTREGAS = 250
_GOV_LIMIT_NOTIFS = 300
_GOV_TESTE_SESS_KEY = "gov_teste_resultado"
_CRONJOB_API_ENDPOINT = "https://api.cron-job.org"


def _coord_admin_or_login(
    request: Request, db: Session
) -> tuple[User, None] | tuple[None, object]:
    u, p = user_or_login_page(request, db)
    if p is not None:
        return None, p
    assert u is not None
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador ou administrador.")
    return u, None


def _pode_editar_user_governanca(viewer: User, alvo: User) -> bool:
    if viewer.role == "admin":
        return True
    if viewer.role == "coordenador":
        return alvo.role == "autor" or alvo.id == viewer.id
    return False


def _parse_dt_opt(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError("Data ou hora inválida (use AAAA-MM-DDTHH:MM ou DD/MM/AAAA HH:MM).")


def _gov_entrega_erro_antes_commit(  # pylint: disable=too-many-arguments
    db: Session,
    ent: EntregaRelatorio,
    *,
    status: str,
    data_envio: str,
    data_validacao: str,
    validado_por_id: str,
) -> str | None:
    st = (status or "").strip()
    if st not in ENTREGA_STATUS_VALIDOS:
        return "status+invalido"
    try:
        ent.data_envio = _parse_dt_opt(data_envio)
        ent.data_validacao = _parse_dt_opt(data_validacao)
    except ValueError:
        return "data+invalida"
    vp_raw = (validado_por_id or "").strip()
    if not vp_raw:
        ent.validado_por_id = None
    else:
        try:
            vid = int(vp_raw)
        except ValueError:
            return "validado_por+invalido"
        if db.get(User, vid) is None:
            return "utilizador+validador+inexistente"
        ent.validado_por_id = vid
    ent.status = st
    return None


def _gov_resolve_novo_role(viewer: User, alvo: User, role: str) -> tuple[str, str | None]:
    novo_role = alvo.role
    if viewer.role == "admin" and role and role in ("admin", "coordenador", "autor"):
        return role, None
    if viewer.role == "coordenador" and role and role != alvo.role:
        return novo_role, "apenas+admin+altera+perfil"
    return novo_role, None


def _gov_email_ja_usado(
    db: Session,
    email_norm: str,
    role: str,
    exceto_id: int,
) -> bool:
    duplicado = (
        db.query(User)
        .filter(User.email == email_norm, User.role == role, User.id != exceto_id)
        .first()
    )
    return duplicado is not None


def _ultimo_relatorio_id(db: Session) -> int | None:
    row = db.query(Relatorio.id).order_by(Relatorio.created_at.desc()).first()
    return int(row[0]) if row else None


def _relatorio_filtro_id(request: Request, db: Session) -> int | None:
    raw = (request.query_params.get("relatorio_id") or "").strip()
    if raw:
        try:
            rel_id = int(raw)
        except ValueError:
            rel_id = None
        else:
            if db.get(Relatorio, rel_id) is not None:
                return rel_id
    return _ultimo_relatorio_id(db)


def _governanca_carregar_listas(
    db: Session,
    relatorio_id: int | None,
) -> tuple[
    ParametrosCicloNotificacao | None,
    list[EntregaRelatorio],
    list[NotificacaoEnvio],
    list[User],
    list[User],
    list[Relatorio],
    list[Relatorio],
]:
    c_row = db.get(ParametrosCicloNotificacao, 1)
    entregas_q = (
        db.query(EntregaRelatorio)
        .options(
            joinedload(EntregaRelatorio.relatorio),
            joinedload(EntregaRelatorio.user),
            joinedload(EntregaRelatorio.validado_por),
            joinedload(EntregaRelatorio.atualizado_por),
        )
    )
    if relatorio_id is not None:
        entregas_q = entregas_q.filter(EntregaRelatorio.relatorio_id == relatorio_id)
    entregas = entregas_q.order_by(EntregaRelatorio.id.desc()).limit(_GOV_LIMIT_ENTREGAS).all()

    notifs_q = (
        db.query(NotificacaoEnvio)
        .options(
            joinedload(NotificacaoEnvio.entrega).joinedload(EntregaRelatorio.relatorio),
            joinedload(NotificacaoEnvio.entrega).joinedload(EntregaRelatorio.user),
        )
    )
    if relatorio_id is not None:
        notifs_q = notifs_q.join(EntregaRelatorio).filter(
            EntregaRelatorio.relatorio_id == relatorio_id
        )
    notifs = notifs_q.order_by(NotificacaoEnvio.id.desc()).limit(_GOV_LIMIT_NOTIFS).all()
    usuarios = db.query(User).order_by(User.nome).all()
    autores = [u for u in usuarios if u.role == "autor"]
    relatorios = db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    relatorios_abertos = (
        db.query(Relatorio)
        .filter(Relatorio.status.in_(("aberto", "em_revisao")))
        .order_by(Relatorio.created_at.desc())
        .all()
    )
    return c_row, entregas, notifs, usuarios, autores, relatorios, relatorios_abertos


def _dt_utc_from_unix(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc)


def _cronjob_api_get(path: str) -> dict[str, Any]:
    req = urllib.request.Request(
        _CRONJOB_API_ENDPOINT + path,
        headers={
            "Authorization": f"Bearer {settings.CRONJOB_ORG_API_KEY}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _cronjob_status_item(job_id: int, label: str) -> dict[str, Any]:
    details = _cronjob_api_get(f"/jobs/{job_id}")["jobDetails"]
    history = _cronjob_api_get(f"/jobs/{job_id}/history")
    last = (history.get("history") or [None])[0]
    return {
        "job_id": job_id,
        "label": label,
        "available": True,
        "enabled": bool(details.get("enabled")),
        "url": details.get("url") or "",
        "next_execution": _dt_utc_from_unix(details.get("nextExecution")),
        "last_execution": _dt_utc_from_unix(last.get("date") if last else None),
        "last_http_status": last.get("httpStatus") if last else None,
        "last_status": last.get("status") if last else None,
        "last_status_text": (last.get("statusText") if last else None) or "",
        "last_duration_ms": last.get("duration") if last else None,
    }


def _cron_status_real() -> list[dict[str, Any]]:
    specs = [
        (settings.CRONJOB_ORG_JOB_ABRIR_PERIODO, "Abrir período"),
        (settings.CRONJOB_ORG_JOB_LEMBRETE_D5, "Lembrete dia 5"),
        (settings.CRONJOB_ORG_JOB_LEMBRETE_D8, "Lembrete dia 8"),
        (settings.CRONJOB_ORG_JOB_ULTIMA_CHAMADA, "Última chamada"),
        (settings.CRONJOB_ORG_JOB_RETRY_FALHAS, "Retry falhas"),
    ]
    if not settings.CRONJOB_ORG_API_KEY:
        return [
            {
                "job_id": job_id,
                "label": label,
                "available": False,
                "error": "CRONJOB_ORG_API_KEY não configurada.",
            }
            for job_id, label in specs
        ]
    out: list[dict[str, Any]] = []
    for job_id, label in specs:
        try:
            out.append(_cronjob_status_item(job_id, label))
        except (KeyError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            out.append(
                {
                    "job_id": job_id,
                    "label": label,
                    "available": False,
                    "error": str(exc),
                }
            )
    return out


def _redirect_gov(ok: str, relatorio_id: str | int | None = None) -> RedirectResponse:
    rid = str(relatorio_id or "").strip()
    suffix = f"?ok={ok}"
    if rid:
        suffix += f"&relatorio_id={quote(rid)}"
    return RedirectResponse(url=f"/governanca-relatorio{suffix}", status_code=303)


def _gov_usuario_erro_ou_none(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    request: Request,
    db: Session,
    viewer: User,
    alvo: User,
    *,
    nome: str,
    email: str,
    email2: str,
    role: str,
    notificacoes_ativas: str,
) -> str | None:
    if not _pode_editar_user_governanca(viewer, alvo):
        return "sem+permissao+para+este+utilizador"
    try:
        nome_fmt = formatar_nome_pessoa(nome)
    except ValueError as e:
        return quote(str(e))
    email_norm = email.strip().lower()
    email2_norm, err_email2 = normalizar_email_secundario_obrigatorio(email2)
    if err_email2:
        return quote(err_email2)
    novo_role, err_role = _gov_resolve_novo_role(viewer, alvo, role)
    if err_role:
        return err_role
    if _gov_email_ja_usado(db, email_norm, novo_role, alvo.id):
        return "email+e+perfil+ja+existentes"
    alvo.nome = nome_fmt
    alvo.email = email_norm
    alvo.email2 = email2_norm
    alvo.role = novo_role
    alvo.notificacoes_ativas = notificacoes_ativas in ("1", "on", "true", "sim")
    if alvo.id == viewer.id:
        request.session["user_role"] = novo_role
    db.commit()
    return None


def _governanca_template_context(request: Request, db: Session, user: User) -> dict[str, Any]:
    erro_raw = request.query_params.get("erro")
    relatorio_id = _relatorio_filtro_id(request, db)
    listas = _governanca_carregar_listas(db, relatorio_id=relatorio_id)
    resultado_teste = request.session.pop(_GOV_TESTE_SESS_KEY, None)

    return {
        "user": user,
        "ciclo_row": listas[0],
        "entregas": listas[1],
        "notificacoes": listas[2],
        "usuarios_gov": listas[3],
        "autores_lista": listas[4],
        "relatorios_filtro": listas[5],
        "relatorio_filtro_id": relatorio_id,
        "relatorios_abertos": listas[6],
        "cron_status": _cron_status_real(),
        "entrega_status_ops": ENTREGA_STATUS_VALIDOS,
        "modo_envio": modo_atual(),
        "resultado_teste": resultado_teste,
        "ok": request.query_params.get("ok"),
        "erro": unquote_plus(erro_raw) if erro_raw else None,
        "limite_entregas": _GOV_LIMIT_ENTREGAS,
        "limite_notifs": _GOV_LIMIT_NOTIFS,
    }


@router.get("/governanca-relatorio")
def governanca_relatorio_page(request: Request, db: Session = Depends(get_db)):
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    user = pre[0]
    assert user is not None
    return templates.TemplateResponse(
        request,
        "complementos/governanca_relatorio.html",
        _governanca_template_context(request, db, user),
    )


@router.post("/governanca-relatorio/parametros-ciclo")
def governanca_salvar_parametros_ciclo(  # pylint: disable=duplicate-code,too-many-arguments,too-many-locals,too-many-positional-arguments
    request: Request,
    db: Session = Depends(get_db),
    ciclo_dia_prev: str = Form(""),
    ciclo_dia_atual: str = Form(""),
    prazo_autor: str = Form(""),
    prazo_coord: str = Form(""),
    dias_lembrete_csv: str = Form(""),
    dia_ultima: str = Form(""),
    dia_abertura: str = Form(""),
    hora_aber: str = Form(""),
    hora_lem: str = Form(""),
    hora_ret: str = Form(""),
    observacoes: str = Form(""),
):
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    err_txt = try_salvar_parametros_ciclo_form_post_campos(
        db,
        ciclo_dia_prev=ciclo_dia_prev,
        ciclo_dia_atual=ciclo_dia_atual,
        prazo_autor=prazo_autor,
        prazo_coord=prazo_coord,
        dias_lembrete_csv=dias_lembrete_csv,
        dia_ultima=dia_ultima,
        dia_abertura=dia_abertura,
        hora_aber=hora_aber,
        hora_lem=hora_lem,
        hora_ret=hora_ret,
        observacoes=observacoes,
    )
    if err_txt:
        q = f"?erro={quote(err_txt)}"
        return RedirectResponse(url=f"/governanca-relatorio{q}", status_code=303)
    return _redirect_gov("ciclo")


@router.post("/governanca-relatorio/entrega/{entrega_id}")
def governanca_entrega_salvar(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    entrega_id: int,
    request: Request,
    db: Session = Depends(get_db),
    status: str = Form(...),
    data_envio: str = Form(""),
    data_validacao: str = Form(""),
    validado_por_id: str = Form(""),
    relatorio_filtro_id: str = Form(""),
):
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    ent = db.get(EntregaRelatorio, entrega_id)
    if not ent:
        raise HTTPException(404, detail="Entrega não encontrada.")
    err_slug = _gov_entrega_erro_antes_commit(
        db,
        ent,
        status=status,
        data_envio=data_envio,
        data_validacao=data_validacao,
        validado_por_id=validado_por_id,
    )
    if err_slug:
        return RedirectResponse(
            url=f"/governanca-relatorio?erro={err_slug}&relatorio_id={quote(relatorio_filtro_id)}",
            status_code=303,
        )
    ent.atualizado_em = datetime.utcnow()
    viewer = current_user(request, db)
    if viewer:
        ent.atualizado_por_id = viewer.id
    db.commit()
    return _redirect_gov("entrega", relatorio_filtro_id)


@router.post("/governanca-relatorio/notificacao/{notif_id}")
def governanca_notificacao_salvar(
    notif_id: int,
    request: Request,
    db: Session = Depends(get_db),
    sucesso: str = Form("0"),
    erro_txt: str = Form(""),
):
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    row = db.get(NotificacaoEnvio, notif_id)
    if not row:
        raise HTTPException(404, detail="Notificação não encontrada.")
    row.sucesso = sucesso in ("1", "on", "true", "sim")
    row.erro = (erro_txt or "").strip() or None
    db.commit()
    return _redirect_gov("notif", request.query_params.get("relatorio_id"))


@router.post("/governanca-relatorio/usuario/{user_id}")
def governanca_usuario_salvar(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    nome: str = Form(...),
    email: str = Form(...),
    email2: str = Form(...),
    role: str = Form(""),
    notificacoes_ativas: str = Form("1"),
):
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    viewer = pre[0]
    assert viewer is not None
    alvo = db.get(User, user_id)
    if not alvo:
        raise HTTPException(404, detail="Utilizador não encontrado.")
    slug = _gov_usuario_erro_ou_none(
        request,
        db,
        viewer,
        alvo,
        nome=nome,
        email=email,
        email2=email2,
        role=role,
        notificacoes_ativas=notificacoes_ativas,
    )
    if slug:
        return RedirectResponse(url=f"/governanca-relatorio?erro={slug}", status_code=303)
    return RedirectResponse(url="/governanca-relatorio?ok=usuario", status_code=303)


@router.post("/governanca-relatorio/usuario/{user_id}/toggle-relatorio")
def governanca_toggle_relatorio_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Liga/desliga `notificacoes_ativas` (campo Relatório do usuário)."""
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    viewer = pre[0]
    assert viewer is not None
    alvo = db.get(User, user_id)
    if not alvo:
        raise HTTPException(404, detail="Usuário não encontrado.")
    if not _pode_editar_user_governanca(viewer, alvo):
        return RedirectResponse(
            url="/governanca-relatorio?erro=sem+permissao+para+este+utilizador#ss-usuarios-notificados",
            status_code=303,
        )
    alvo.notificacoes_ativas = not bool(alvo.notificacoes_ativas)
    db.commit()
    return RedirectResponse(
        url="/governanca-relatorio?ok=toggle#ss-usuarios-notificados",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Testes reais do sistema (chamadas autenticadas dos jobs reais)
# ---------------------------------------------------------------------------
def _guardar_resultado_teste(
    request: Request,
    rotulo: str,
    dados: dict,
) -> None:
    """Persiste o resumo do último teste na sessão para a próxima renderização."""
    request.session[_GOV_TESTE_SESS_KEY] = {
        "rotulo": rotulo,
        "modo_envio": modo_atual(),
        "executado_em": datetime.utcnow().isoformat(timespec="seconds"),
        "dados": dados,
    }


@router.post("/governanca-relatorio/testar/abrir-periodo")
def governanca_testar_abrir_periodo(
    request: Request,
    db: Session = Depends(get_db),
    force: str = Form("1"),
    base_relatorio_id: str = Form(""),
):
    """Executa `abrir_periodo` real (idempotente sem force)."""
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    base_id: int | None = None
    base_raw = (base_relatorio_id or "").strip()
    if base_raw:
        try:
            base_id = int(base_raw)
        except ValueError:
            base_id = None
    resumo = abrir_periodo(
        db,
        force=force in ("1", "on", "true", "sim"),
        base_relatorio_id=base_id,
    )
    _guardar_resultado_teste(request, "Abrir período", asdict(resumo))
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )


@router.post("/governanca-relatorio/testar/notificar-autores")
def governanca_testar_notificar_autores(
    request: Request,
    db: Session = Depends(get_db),
    relatorio_id: int = Form(...),
):
    """Reenvia Mensagem 1 (abertura) para autores que ainda não receberam."""
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    resumo = notificar_autores_abertura(db, relatorio_id)
    _guardar_resultado_teste(request, "Notificar autores · abertura", asdict(resumo))
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )


@router.post("/governanca-relatorio/testar/lembretes")
def governanca_testar_lembretes(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str = Form("lembrete"),
    relatorio_id: str = Form(""),
    ignorar_calendario: str = Form("1"),
):
    """Dispara lembrete ou última chamada (ignorar_calendario padrão = sim)."""
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    rid: int | None = None
    rid_raw = (relatorio_id or "").strip()
    if rid_raw:
        try:
            rid = int(rid_raw)
        except ValueError:
            rid = None
    resumo = enviar_lembretes(
        db,
        tipo=tipo,
        relatorio_id=rid,
        ignorar_calendario=ignorar_calendario in ("1", "on", "true", "sim"),
    )
    _guardar_resultado_teste(request, f"Lembretes · {tipo}", asdict(resumo))
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )


@router.post("/governanca-relatorio/testar/retry")
def governanca_testar_retry(
    request: Request,
    db: Session = Depends(get_db),
):
    """Retenta envios falhados nos últimos 7 dias."""
    pre = _coord_admin_or_login(request, db)
    if pre[1] is not None:
        return pre[1]
    resumo = retry_falhas(db)
    _guardar_resultado_teste(request, "Retry · falhas recentes", asdict(resumo))
    return RedirectResponse(
        url="/governanca-relatorio#ss-testar-sistema",
        status_code=303,
    )
