from datetime import datetime, timezone
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from ...auth import current_user
from ...models import DefconConfig, User, Alerta
from ...notificacoes import email_sender
from ...services.governanca_relatorio import governanca_salvar_parametros_ciclo
from ...services.governanca.contexto_pagina import montar_contexto_governanca


def central_notificacoes_page(request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        return HTMLResponse(
            "<script>window.location='/login'</script>",
            status_code=401,
        )
    contexto = montar_contexto_governanca(request, db, user)
    contexto["header"] = "Central de Notificações"
    contexto["title"] = "Central de Notificações"
    alertas = db.query(Alerta).order_by(Alerta.atualizado_em.desc()).all()
    contexto["alertas"] = alertas or []
    
    # Garantir que todas as variáveis necessárias existam
    contexto.setdefault("ciclo_execucao_rows", [])
    contexto.setdefault("notificacoes", [])
    contexto.setdefault("relatorios_filtro", [])
    contexto.setdefault("relatorios_abertos", [])
    contexto.setdefault("modo_envio", "desligado")
    
    return contexto


def central_salvar_parametros_ciclo(
    request: Request,
    db: Session,
    ciclo_dia_prev: str,
    ciclo_dia_atual: str,
    prazo_autor: str,
    prazo_coord: str,
    dias_lembrete_csv: str,
    dia_ultima: str,
    dia_abertura: str,
    hora_aber: str,
    hora_lem: str,
    hora_ret: str,
    observacoes: str,
):
    return governanca_salvar_parametros_ciclo(
        request,
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


def central_ativar_defcon(request: Request, db: Session):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Desativar configurações anteriores
    db.query(DefconConfig).filter(DefconConfig.ativo).update(
        {"ativo": False, "desativado_em": datetime.now(timezone.utc)}
    )

    # Criar nova configuração DEFCON
    defcon = DefconConfig(
        ativo=True,
        nivel=1,
        ativado_em=datetime.now(timezone.utc),
        ativado_por=user.id,
    )
    db.add(defcon)
    db.commit()

    return RedirectResponse(
        "/central-notificacoes?ok=defcon_ativado",
        status_code=303,
    )


def central_desativar_defcon(request: Request, db: Session):
    db.query(DefconConfig).filter(DefconConfig.ativo).update(
        {"ativo": False, "desativado_em": datetime.now(timezone.utc)}
    )
    db.commit()

    return RedirectResponse(
        "/central-notificacoes?ok=defcon_desativado",
        status_code=303,
    )


def central_enviar_email(
    request: Request,
    db: Session,
    tipo: str,
    assunto: str,
    corpo: str,
    relatorio_id: str,
    destinatarios: list,
    agendar: str,
    data_agendada: str,
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if agendar == "depois" and data_agendada:
        # TODO: Implementar agendamento de email
        return RedirectResponse(
            "/central-notificacoes?ok=email_agendado",
            status_code=303,
        )

    # Enviar imediatamente
    for user_id in destinatarios:
        usuario = db.query(User).filter(User.id == user_id).first()
        if not usuario:
            continue

        contexto = {
            "destinatario_nome": usuario.nome,
            "destinatario_email": usuario.email,
            "assunto": assunto,
            "corpo_mensagem": corpo,
            "link_relatorio_painel": (
                f"{email_sender.settings.APP_BASE_URL}"
                f"/relatorios/{relatorio_id}"
                if relatorio_id
                else email_sender.settings.APP_BASE_URL
            ),
        }

        if tipo == "boas_vindas":
            contexto["senha_inicial"] = "senha_temporaria"  # TODO: gerar senha
            contexto["link_login_sra"] = (
                f"{email_sender.settings.APP_BASE_URL}/login"
            )
            contexto["link_modelos_word_ajuda"] = (
                f"{email_sender.settings.APP_BASE_URL}"
                f"/modelos-word"
            )
            contexto["link_painel_upload"] = (
                f"{email_sender.settings.APP_BASE_URL}"
                f"/relatorios/{relatorio_id}/upload"
                if relatorio_id
                else email_sender.settings.APP_BASE_URL
            )
        elif tipo == "customizado":
            contexto["assunto"] = assunto or "Mensagem do coordenador"

        email_sender.enviar_notificacao(
            destinatario_email=usuario.email,
            destinatario_nome=usuario.nome,
            tipo=tipo,
            contexto=contexto,
        )

        # TODO: Salvar log de envio no banco

    return RedirectResponse(
        "/central-notificacoes?ok=email_enviado",
        status_code=303,
    )
