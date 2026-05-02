"""Página unificada de Validação e Revisão do relatório.

Seção 1 — Validação: parciais por autor com checagens estruturais por seção e
botões Aprovar/Reprovar (POST em ``routes.notificacoes`` reusando
`alterar_status_entrega` e `reprovar_entrega`).

Seção 2 — Revisão: checagens estruturais agregadas globais
(`services.validacao.checagens_globais`), painel de revisão linguística sob
demanda (`POST /relatorios/{id}/revisao-linguistica` chamado por fetch()),
botão "Exportar para assinatura" (`GET /relatorios/{id}/exportar-assinatura`,
em `routes.pdf`) e botão "Aprovar e finalizar" (POST `/relatorios/{id}/status`
existente, com `status=finalizado`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import EntregaRelatorio, Relatorio
from ..services.entregas.lista_painel import montar_lista_entregas
from ..services.validacao.checagens_entrega import montar_checagens_validacao
from ..services.validacao.checagens_globais import montar_checagens_globais
from ..services.validacao.revisao_linguistica import (
    analisar_relatorio,
    resultado_para_dict,
)
from .pages import templates, user_or_login_page

router = APIRouter()


@router.get("/relatorios/{rel_id}/validacao-revisao")
# pylint: disable=too-many-locals
# A rota agrega 7 famílias de dados independentes que precisam ir ao template
# (entregas, checagens por entrega, lista canônica, resumo global, categorias
# globais, contadores, flag de finalização). Quebrar em sub-funções iria só
# embolar o fluxo já linear do handler.
def validacao_revisao_page(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Página única com as duas seções. Exclusiva de admin/coordenador."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")

    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")

    entregas = (
        db.query(EntregaRelatorio)
        .options(
            selectinload(EntregaRelatorio.user),
            selectinload(EntregaRelatorio.notificacoes),
            selectinload(EntregaRelatorio.reprovado_por),
            selectinload(EntregaRelatorio.validado_por),
        )
        .filter(EntregaRelatorio.relatorio_id == rel_id)
        .all()
    )
    checagens = montar_checagens_validacao(db, rel, entregas)

    # Resumo do progresso para o cabeçalho da página: quantos autores prontos
    # vs. com erros vs. ainda em aberto. Decisão de exibição fica no template.
    total_entregas = len(checagens)
    aprovadas = sum(1 for c in checagens if c.status == "validado")
    com_erros = sum(1 for c in checagens if c.total_erros > 0)
    prontas_para_aprovar = sum(
        1
        for c in checagens
        if c.status != "validado" and c.pronta_para_aprovar
    )

    # Lista de entregas (mesma fonte da governança): usada na Seção 1 para
    # mostrar a tabela canônica dos autores em paralelo às checagens. Mantém
    # a ideia de "tudo orbita a Lista de entregas".
    linhas_lista, pode_acoes = montar_lista_entregas(db, rel, user)

    # Seção 2: checagens estruturais agregadas do relatório inteiro.
    resumo_global, categorias_globais = montar_checagens_globais(db, rel)
    erros_globais = sum(
        c.total for c in categorias_globais if c.severidade == "erro"
    )
    avisos_globais = sum(
        c.total for c in categorias_globais if c.severidade == "aviso"
    )
    pode_finalizar = (
        rel.status != "finalizado"
        and erros_globais == 0
        and resumo_global.todas_validadas
    )

    contexto = {
        "user": user,
        "rel": rel,
        "checagens": checagens,
        "lista_entregas_linhas": linhas_lista,
        "lista_entregas_pode_acoes": pode_acoes,
        "total_entregas": total_entregas,
        "aprovadas": aprovadas,
        "com_erros": com_erros,
        "prontas_para_aprovar": prontas_para_aprovar,
        "resumo_global": resumo_global,
        "categorias_globais": categorias_globais,
        "erros_globais": erros_globais,
        "avisos_globais": avisos_globais,
        "pode_finalizar": pode_finalizar,
    }
    return templates.TemplateResponse(
        request,
        "complementos/validacao_revisao.html",
        contexto,
    )


@router.post("/relatorios/{rel_id}/revisao-linguistica")
def revisao_linguistica_rodar(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Análise sob demanda — devolve JSON consumido por fetch() na Seção 2.

    Resposta sempre 200 mesmo quando o motor está desligado: o frontend lida
    com `aviso_motor`. Erros 500 só para situação realmente excepcional
    (404 do relatório, falta de sessão).
    """
    user, p = user_or_login_page(request, db)
    if p is not None:
        # Sem sessão: devolve 401 para o fetch() poder tratar com clareza, em
        # vez do HTML de login (que confunde o cliente JSON).
        return JSONResponse({"detail": "Sessão expirada."}, status_code=401)
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")
    resultado = analisar_relatorio(db, rel)
    return JSONResponse(resultado_para_dict(resultado))
