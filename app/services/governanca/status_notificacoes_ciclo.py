"""Status consolidado do ciclo mensal e das notificações por autor."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ...models import EntregaRelatorio, NotificacaoEnvio, Relatorio, User
from ...notificacoes import destinatarios as destinatarios_ciclo
from .status_jobs_cron import proxima_execucao


def _quando_notificacao(row: NotificacaoEnvio) -> datetime:
    return row.aberto_em or row.provedor_status_em or row.enviada_em


def _status_email(email: str, eventos: list[NotificacaoEnvio]) -> dict[str, Any]:
    eventos_email = [
        n for n in eventos if (n.destinatario_email or "").strip().lower() == email
    ]
    confirmados = [
        n
        for n in eventos_email
        if n.provedor_status in ("delivered", "open") or n.aberto_em is not None
    ]
    if confirmados:
        ultimo = max(confirmados, key=_quando_notificacao)
        aberto = ultimo.aberto_em is not None or ultimo.provedor_status == "open"
        return {
            "email": email,
            "estado": "Visualização detectada" if aberto else "Entregue",
            "tag": "tag-ok",
            "quando": _quando_notificacao(ultimo),
            "mensagem": (
                "visualização técnica detectada"
                if aberto
                else "entrega confirmada pelo provedor"
            ),
            "enviado": True,
            "entregue": True,
            "falhou": False,
        }
    falhas = [n for n in eventos_email if not n.sucesso]
    if falhas:
        ultimo = max(falhas, key=_quando_notificacao)
        return {
            "email": email,
            "estado": "Falhou",
            "tag": "tag-err",
            "quando": _quando_notificacao(ultimo),
            "mensagem": ultimo.provedor_motivo or ultimo.erro or "falha informada pelo envio",
            "enviado": False,
            "entregue": False,
            "falhou": True,
        }
    solicitados = [n for n in eventos_email if n.sucesso]
    if solicitados:
        ultimo = max(solicitados, key=_quando_notificacao)
        return {
            "email": email,
            "estado": "Envio solicitado",
            "tag": "tag-warn",
            "quando": _quando_notificacao(ultimo),
            "mensagem": "SendGrid aceitou; entrega ainda não confirmada",
            "enviado": True,
            "entregue": False,
            "falhou": False,
        }
    return {
        "email": email,
        "estado": "Ainda não enviado",
        "tag": "tag-warn",
        "quando": None,
        "mensagem": "sem tentativa registrada para este endereço",
        "enviado": False,
        "entregue": False,
        "falhou": False,
    }


def _status_autor_notificacao(
    autor: User,
    entrega: EntregaRelatorio | None,
    tipo: str,
) -> dict[str, Any]:
    if not autor.notificacoes_ativas:
        return {
            "nome": autor.nome,
            "email": autor.email,
            "email2": autor.email2,
            "emails_status": [],
            "estado": "Pausado",
            "tag": "tag-neutral",
            "quando": None,
            "motivo": "Este autor está fora do ciclo de notificações.",
            "enviado": False,
            "entregue": False,
            "contabilizar": False,
        }
    eventos = [n for n in (entrega.notificacoes if entrega else []) if n.tipo == tipo]
    emails_status = [
        _status_email(email, eventos)
        for email in destinatarios_ciclo.emails_destino_notificacao(autor)
    ]
    return _resumir_status_autor(autor, emails_status)


def _resumir_status_autor(autor: User, emails_status: list[dict[str, Any]]) -> dict[str, Any]:
    quando = max(
        (item["quando"] for item in emails_status if item["quando"] is not None),
        default=None,
    )
    base = {
        "nome": autor.nome,
        "email": autor.email,
        "email2": autor.email2,
        "emails_status": emails_status,
        "quando": quando,
        "contabilizar": True,
    }
    if emails_status and all(item["entregue"] for item in emails_status):
        aberto = any(item["estado"] == "Visualização detectada" for item in emails_status)
        motivo = (
            "Todos os e-mails cadastrados tiveram visualização técnica detectada."
            if aberto
            else "Todos os e-mails cadastrados tiveram entrega confirmada pelo provedor."
        )
        return {**base, "estado": "Visualização detectada" if aberto else "Entregue", "tag": "tag-ok", "motivo": motivo, "enviado": True, "entregue": True}
    if any(item["falhou"] for item in emails_status):
        return {**base, "estado": "Falhou", "tag": "tag-err", "motivo": "Pelo menos um dos e-mails cadastrados falhou.", "enviado": False, "entregue": False}
    entregues = sum(1 for item in emails_status if item["entregue"])
    if entregues:
        motivo = f"{entregues}/{len(emails_status)} e-mail(s) com entrega confirmada."
        return {**base, "estado": "Entrega parcial", "tag": "tag-warn", "motivo": motivo, "enviado": True, "entregue": False}
    if any(item["enviado"] for item in emails_status):
        motivo = (
            "O SendGrid aceitou pelo menos um envio, mas ainda falta confirmação "
            "de entrega para todos os e-mails cadastrados."
        )
        return {**base, "estado": "Envio solicitado", "tag": "tag-warn", "motivo": motivo, "enviado": True, "entregue": False}
    return {**base, "estado": "Ainda não enviado", "tag": "tag-warn", "motivo": "Aguardando a rotina de envio ou execução manual.", "enviado": False, "entregue": False}


def _linha_notificacao(
    relatorio: Relatorio | None,
    autores: list[User],
    entregas_por_user: dict[int, EntregaRelatorio],
    spec: dict[str, Any],
) -> dict[str, Any]:
    detalhes = [
        _status_autor_notificacao(autor, entregas_por_user.get(autor.id), spec["tipo"])
        for autor in autores
    ]
    total = sum(1 for item in detalhes if item["contabilizar"])
    solicitados = sum(1 for item in detalhes if item["contabilizar"] and item["enviado"])
    entregues = sum(1 for item in detalhes if item["contabilizar"] and item["entregue"])
    falhas = [item for item in detalhes if item["estado"] == "Falhou"]
    quando = max((item["quando"] for item in detalhes if item["quando"] is not None), default=None)
    estado, tag, mensagem = _resumo_linha_notificacao(relatorio, total, solicitados, entregues, falhas)
    return {
        "tipo": "notificacao",
        "titulo": spec["titulo"],
        "estado": estado,
        "tag": tag,
        "quando": quando,
        "autores_texto": f"{entregues}/{total} entregues",
        "modal_id": spec["modal_id"],
        "detalhes": detalhes,
        "proxima_execucao": spec["proxima_execucao"],
        "mensagem": mensagem,
    }


def _resumo_linha_notificacao(
    relatorio: Relatorio | None,
    total: int,
    solicitados: int,
    entregues: int,
    falhas: list[dict[str, Any]],
) -> tuple[str, str, str]:
    if relatorio is None:
        estado = "Sem relatório"
        tag = "tag-neutral"
        mensagem = "Crie ou abra um relatório antes de enviar notificações."
    elif total == 0:
        estado = "Sem autores ativos"
        tag = "tag-neutral"
        mensagem = "Nenhum autor está marcado para receber notificações."
    elif entregues == total:
        estado = "Entrega confirmada"
        tag = "tag-ok"
        mensagem = "O SendGrid confirmou entrega para todos os autores ativos."
    elif falhas:
        estado = "Atenção"
        tag = "tag-err"
        mensagem = "Há envio com falha. Abra a lista de autores para ver o motivo."
    elif entregues:
        estado = "Entrega parcial"
        tag = "tag-warn"
        mensagem = f"{total - entregues} autor(es) ainda não têm entrega confirmada."
    elif solicitados:
        estado = "Envio solicitado"
        tag = "tag-warn"
        mensagem = (
            "O SendGrid aceitou a mensagem, mas ainda não confirmou entrega. "
            "Isto não prova recebimento na caixa."
        )
    else:
        estado = "Aguardando envio"
        tag = "tag-warn"
        mensagem = "Nenhum envio solicitado para esta etapa até agora."
    return estado, tag, mensagem


def _linha_relatorio(
    relatorio: Relatorio | None,
    prox_execucao: datetime | None,
) -> dict[str, Any]:
    if relatorio is None:
        return {
            "tipo": "relatorio",
            "titulo": "Relatório do mês",
            "estado": "Ainda não gerado",
            "tag": "tag-warn",
            "quando": None,
            "autores_texto": "—",
            "modal_id": "",
            "detalhes": [],
            "proxima_execucao": prox_execucao,
            "mensagem": "O próximo relatório será criado pela rotina de abertura ou pela execução manual.",
        }
    aberto = relatorio.status in ("aberto", "em_revisao")
    return {
        "tipo": "relatorio",
        "titulo": "Relatório do mês",
        "estado": "Aberto" if aberto else relatorio.status.replace("_", " "),
        "tag": "tag-ok" if aberto else "tag-neutral",
        "quando": relatorio.created_at,
        "autores_texto": "—",
        "modal_id": "",
        "detalhes": [],
        "proxima_execucao": prox_execucao,
        "mensagem": (
            f"{relatorio.codigo} está disponível para preenchimento."
            if aberto
            else f"{relatorio.codigo} não está aberto para novos envios."
        ),
    }


def ciclo_execucao_rows(
    cron_status: list[dict[str, Any]],
    relatorio: Relatorio | None,
    autores: list[User],
    entregas: list[EntregaRelatorio],
) -> list[dict[str, Any]]:
    entregas_por_user = {ent.user_id: ent for ent in entregas}
    return [
        _linha_relatorio(relatorio, proxima_execucao(cron_status, {"Abrir período"})),
        _linha_notificacao(relatorio, autores, entregas_por_user, {
            "titulo": "Aviso de abertura",
            "tipo": "abertura",
            "proxima_execucao": proxima_execucao(cron_status, {"Abrir período"}),
            "modal_id": "gov-modal-abertura",
        }),
        _linha_notificacao(relatorio, autores, entregas_por_user, {
            "titulo": "Lembretes aos autores",
            "tipo": "lembrete",
            "proxima_execucao": proxima_execucao(cron_status, {"Lembrete dia 5", "Lembrete dia 8"}),
            "modal_id": "gov-modal-lembrete",
        }),
        _linha_notificacao(relatorio, autores, entregas_por_user, {
            "titulo": "Última chamada",
            "tipo": "ultima_chamada",
            "proxima_execucao": proxima_execucao(cron_status, {"Última chamada"}),
            "modal_id": "gov-modal-ultima-chamada",
        }),
    ]
