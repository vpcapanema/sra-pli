"""Página unificada de Validação e Revisão do relatório.

Seção 1 — Validação: árvore (filtro/navegação) sobre o relatório completo no iframe
(mesmo HTML do PDF); dock no painel com Aprovar/Reprovar da parcial do responsável
pela seção escolhida; notas internas (`observacao_validacao`, POST dedicado).

Seção 2 — Revisão: mesmo **workspace** que a Validação (árvore à esquerda, painel à
direita com pré-visualização ou editor de blocos por iframe); checagens globais,
revisão linguística no painel, exportar e finalizar.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload
from starlette.responses import RedirectResponse

from ..db import get_db
from ..models import EntregaRelatorio, Relatorio, Secao
from ..numeracao import chave_numero
from ..services.entregas.lista_painel import montar_lista_entregas
from ..services.validacao.checagens_entrega import montar_checagens_validacao
from ..services.validacao.checagens_globais import autor_rotulo_secao, montar_checagens_globais
from ..services.validacao.revisao_linguistica import (
    analisar_relatorio,
    resultado_para_dict,
)
from .pages import templates, user_or_login_page

router = APIRouter()

_MAX_OBSERVACAO_VALIDACAO = 8000
_SEC_LINK_RE = re.compile(r"/secoes/(\d+)/")


def _mapa_categorias_globais_por_secao(categorias) -> dict[int, tuple[bool, bool]]:
    """Propaga achados globais com link de seção para (tem_erro, tem_aviso)."""
    m: dict[int, tuple[bool, bool]] = {}
    for cat in categorias:
        for it in cat.itens:
            match = _SEC_LINK_RE.search(it.link or "")
            if not match:
                continue
            sid = int(match.group(1))
            te, ta = m.get(sid, (False, False))
            if cat.severidade == "erro":
                m[sid] = (True, ta)
            elif cat.severidade in ("aviso", "info"):
                m[sid] = (te, True)
    return m


def _merge_mapas_erro_aviso(
    a: dict[int, tuple[bool, bool]],
    b: dict[int, tuple[bool, bool]],
) -> dict[int, tuple[bool, bool]]:
    out: dict[int, tuple[bool, bool]] = {}
    for k in set(a) | set(b):
        te_a, ta_a = a.get(k, (False, False))
        te_b, ta_b = b.get(k, (False, False))
        out[k] = (te_a or te_b, ta_a or ta_b)
    return out


def _situacao_secao_revisao(
    sec: Secao,
    tem_erro: bool,
    tem_aviso: bool,
) -> str:
    """Cor da linha na árvore 2.1: erro > aviso > ok (conforme blocos e checagens)."""
    if sec.responsavel_id is None or tem_erro:
        return "erro"
    n_b = len(sec.blocos)
    if n_b == 0:
        return "aviso"
    if any(not b.bloqueado for b in sec.blocos) or tem_aviso:
        return "aviso"
    return "ok"


def _dict_navegacao_revisao_secao(
    sec: Secao,
    rid: int,
    preview_url: str,
    situ: str,
) -> dict:
    num = sec.numero or ""
    anchor = ("sec-" + num.replace(".", "-")) if num else ""
    sem = sec.responsavel_id is None
    rotulo = "" if sem else autor_rotulo_secao(sec)
    n_b = len(sec.blocos)
    n_c = sum(1 for b in sec.blocos if b.bloqueado)
    blocos_txt = "sem blocos" if n_b == 0 else f"{n_c}/{n_b} blocos confirmados"
    return {
        "secao_id": sec.id,
        "numero": num,
        "titulo": sec.titulo or "",
        "nivel": num.count(".") + 1 if num else 1,
        "sem_responsavel": sem,
        "responsavel_rotulo": rotulo,
        "preview_url": preview_url,
        "anchor_id": anchor,
        "responsavel_user_id": sec.responsavel_id,
        "editor_url": f"/relatorios/{rid}/secoes/{sec.id}/upload-conteudo",
        "tem_erro": situ == "erro",
        "tem_aviso": situ == "aviso",
        "observacao": sec.observacao_validacao or "",
        "blocos_txt": blocos_txt,
    }


def _arvore_revisao_navegacao(
    rel: Relatorio,
    categorias_globais,
    checagens,
) -> list[dict]:
    """Árvore plana para o painel Revisão (mesmo contrato que `arvore_validacao`)."""
    mp = _merge_mapas_erro_aviso(
        _mapa_checagens_por_secao(checagens),
        _mapa_categorias_globais_por_secao(categorias_globais),
    )
    rid = rel.id
    preview_url = f"/relatorios/{rid}/preview"
    secoes_ord = sorted(
        rel.secoes,
        key=lambda s: (chave_numero(s.numero or ""), s.ordem or 0),
    )
    pares: list[tuple[Secao, str]] = [
        (
            sec,
            _situacao_secao_revisao(sec, *mp.get(sec.id, (False, False))),
        )
        for sec in secoes_ord
    ]
    ag_erro = any(situ == "erro" for _, situ in pares)
    ag_aviso = any(situ == "aviso" for _, situ in pares)
    root = {
        "secao_id": None,
        "numero": "",
        "titulo": "Todo o relatório",
        "nivel": 0,
        "preview_url": preview_url,
        "anchor_id": "",
        "responsavel_user_id": None,
        "sem_responsavel": False,
        "responsavel_rotulo": "",
        "editor_url": f"/relatorios/{rid}",
        "tem_erro": ag_erro,
        "tem_aviso": ag_aviso,
        "observacao": "",
        "blocos_txt": "",
    }
    nos: list[dict] = [root]
    for sec, situ in pares:
        nos.append(_dict_navegacao_revisao_secao(sec, rid, preview_url, situ))
    return nos


def _mapa_secao_autores(rel: Relatorio) -> list[dict]:
    """Linhas para tabela seção ↔ responsável (Revisão — transparência obrigatória)."""
    rows: list[dict] = []
    for sec in sorted(
        rel.secoes,
        key=lambda s: (chave_numero(s.numero or ""), s.ordem or 0),
    ):
        user = sec.responsavel
        rows.append(
            {
                "numero": sec.numero or "",
                "titulo": sec.titulo or "",
                "autor_nome": (user.nome or "").strip() if user else "",
                "autor_email": (user.email or "").strip() if user else "",
                "sem_responsavel": sec.responsavel_id is None,
                "link_upload": f"/relatorios/{rel.id}/secoes/{sec.id}/upload-conteudo",
                "link_sumario": f"/relatorios/{rel.id}#sec-{sec.id}",
            }
        )
    return rows


def _mapa_checagens_por_secao(checagens) -> dict[int, tuple[bool, bool]]:
    m: dict[int, tuple[bool, bool]] = {}
    for c in checagens:
        for s in c.secoes:
            err, av = m.get(s.secao_id, (False, False))
            m[s.secao_id] = (err or s.tem_erro, av or s.tem_aviso)
    return m


def _arvore_node_secao(
    rid: int,
    preview_url: str,
    sec: Secao,
    mp: dict[int, tuple[bool, bool]],
) -> dict:
    num = sec.numero or ""
    anchor = ("sec-" + num.replace(".", "-")) if num else ""
    te, ta = mp.get(sec.id, (False, False))
    sem = sec.responsavel_id is None
    rotulo_resp = "" if sem else autor_rotulo_secao(sec)
    return {
        "secao_id": sec.id,
        "numero": num,
        "titulo": sec.titulo or "",
        "nivel": num.count(".") + 1,
        "sem_responsavel": sem,
        "responsavel_rotulo": rotulo_resp,
        "preview_url": preview_url,
        "anchor_id": anchor,
        "responsavel_user_id": sec.responsavel_id,
        "editor_url": f"/relatorios/{rid}/secoes/{sec.id}/upload-conteudo",
        "tem_erro": te,
        "tem_aviso": ta,
        "observacao": sec.observacao_validacao or "",
        "blocos_txt": (
            "sem blocos"
            if not sec.blocos
            else (
                f"{sum(1 for b in sec.blocos if b.bloqueado)}/"
                f"{len(sec.blocos)} blocos confirmados"
            )
        ),
    }


def _arvore_validacao(rel: Relatorio, checagens) -> list[dict]:
    mp = _mapa_checagens_por_secao(checagens)
    rid = rel.id
    ag_erro = any(t[0] for t in mp.values())
    ag_aviso = any(t[1] for t in mp.values())
    preview_url = f"/relatorios/{rid}/preview"
    root = {
        "secao_id": None,
        "numero": "",
        "titulo": "Todo o relatório",
        "nivel": 0,
        "preview_url": preview_url,
        "anchor_id": "",
        "responsavel_user_id": None,
        "sem_responsavel": False,
        "responsavel_rotulo": "",
        "editor_url": f"/relatorios/{rid}",
        "tem_erro": ag_erro,
        "tem_aviso": ag_aviso,
        "observacao": "",
        "blocos_txt": "",
    }
    nos: list[dict] = [root]
    secoes_ord = sorted(
        rel.secoes,
        key=lambda s: (chave_numero(s.numero or ""), s.ordem or 0),
    )
    for s in secoes_ord:
        nos.append(_arvore_node_secao(rid, preview_url, s, mp))
    return nos


@router.get("/relatorios/{rel_id}/validacao-revisao")
# pylint: disable=too-many-locals
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

    rel = (
        db.query(Relatorio)
        .options(
            selectinload(Relatorio.secoes).options(
                selectinload(Secao.responsavel),
                selectinload(Secao.blocos),
            ),
        )
        .filter(Relatorio.id == rel_id)
        .one_or_none()
    )
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")

    relatorios_opcao = (
        db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    )

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

    total_entregas = len(checagens)
    aprovadas = sum(1 for c in checagens if c.status == "validado")
    com_erros = sum(1 for c in checagens if c.total_erros > 0)
    prontas_para_aprovar = sum(
        1
        for c in checagens
        if c.status != "validado" and c.pronta_para_aprovar
    )

    linhas_lista, pode_acoes = montar_lista_entregas(db, rel, user)

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

    arvore_validacao = _arvore_validacao(rel, checagens)
    arvore_revisao_navegacao = _arvore_revisao_navegacao(
        rel, categorias_globais, checagens
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
        "relatorios_opcao": relatorios_opcao,
        "arvore_validacao": arvore_validacao,
        "arvore_revisao_navegacao": arvore_revisao_navegacao,
        "mapa_secao_autores": _mapa_secao_autores(rel),
    }
    return templates.TemplateResponse(
        request,
        "complementos/validacao_revisao.html",
        contexto,
    )


@router.post("/relatorios/{rel_id}/secoes/{sec_id}/observacao-validacao")
# Cinco argumentos de rota/corpo além do path violariam R0917; Form+Depends
# contam como parâmetros reais — padrão já usado nas rotas POST do projeto.
# pylint: disable=too-many-arguments,too-many-positional-arguments
def salvar_observacao_validacao_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    observacao: str = Form(""),
    redirect_to: str = Form(""),
    db: Session = Depends(get_db),
):
    """Nota interna do coordenador na Validação (não entra no PDF)."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404, detail="Seção não encontrada.")
    body = (observacao or "").strip()
    if len(body) > _MAX_OBSERVACAO_VALIDACAO:
        raise HTTPException(400, detail="Texto excede o limite permitido.")
    sec.observacao_validacao = body or None
    db.add(sec)
    db.commit()
    dest = (redirect_to or "").strip() or (
        f"/relatorios/{rel_id}/validacao-revisao#ss-validacao"
    )
    return RedirectResponse(url=dest, status_code=303)


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
        return JSONResponse({"detail": "Sessão expirada."}, status_code=401)
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403, detail="Acesso restrito a coordenador/admin.")
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")
    resultado = analisar_relatorio(db, rel)
    return JSONResponse(resultado_para_dict(resultado))
