"""Lógica da página de Revisão e Edição (rotas em ``routes/revisao_edicao.py``).

Workspace único do coordenador sobre o relatório completo:

- Árvore de navegação à esquerda (todo o relatório + por seção) com
  agregação de erros/avisos vindos das checagens globais.
- Painel à direita com pré-visualização paginada (mesmo pipeline do PDF)
  e edição inline de blocos (auto-save), revisão linguística sob demanda,
  gestão de vocabulário do projeto e nota interna por seção.

Restrito a admin/coordenador.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload
from starlette.responses import RedirectResponse

from ..models import Bloco, Relatorio, Secao
from ..numeracao import chave_numero
from ..pdf_render import _montar_contexto as _montar_contexto_pdf
from .pages import templates, user_or_login_page
from .validacao.checagens_globais import (
    autor_rotulo_secao,
    montar_checagens_globais,
)
from .validacao.revisao_linguistica import (
    adicionar_termo_vocabulario,
    analisar_relatorio,
    resultado_para_dict,
)

_MAX_OBSERVACAO_VALIDACAO = 8000
_SEC_LINK_RE = re.compile(r"/secoes/(\d+)/")


# ---------------------------------------------------------------------------
# Árvores de navegação e mapas de propagação
# ---------------------------------------------------------------------------


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
    """Cor da linha na árvore: erro > aviso > ok (conforme blocos e checagens)."""
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
    blocos_txt = (
        "sem blocos" if n_b == 0 else f"{n_c}/{n_b} blocos confirmados"
    )
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
    """Árvore plana para o painel de Revisão e Edição."""
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


def _mapa_checagens_por_secao(checagens) -> dict[int, tuple[bool, bool]]:
    m: dict[int, tuple[bool, bool]] = {}
    for c in checagens:
        for s in c.secoes:
            err, av = m.get(s.secao_id, (False, False))
            m[s.secao_id] = (err or s.tem_erro, av or s.tem_aviso)
    return m


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


# pylint: disable=too-many-arguments,too-many-positional-arguments
def salvar_observacao_validacao_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    observacao: str,
    redirect_to: str,
    db: Session,
):
    """Nota interna do coordenador por seção (não entra no PDF)."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(
            403, detail="Acesso restrito a coordenador/admin."
        )
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
        f"/relatorios/{rel_id}/revisao-edicao"
    )
    return RedirectResponse(url=dest, status_code=303)


def revisao_linguistica_rodar(
    rel_id: int,
    request: Request,
    db: Session,
):
    """Análise sob demanda — devolve JSON consumido por fetch() no painel."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return JSONResponse(
            {"detail": "Sessão expirada."}, status_code=401
        )
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(
            403, detail="Acesso restrito a coordenador/admin."
        )
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404, detail="Relatório não encontrado.")
    resultado = analisar_relatorio(db, rel)
    return JSONResponse(resultado_para_dict(resultado))


# pylint: disable=too-many-locals
def revisao_edicao_page(
    rel_id: int,
    request: Request,
    db: Session,
):
    """Workspace de revisão editorial. Reusa o pipeline do PDF para paginar o
    relatório por folhas A4 e expõe ``bloco_id`` em cada bloco para edição
    inline. Restrito a admin/coordenador.
    """
    user, p = user_or_login_page(request, db)
    if p is not None:
        return p
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(
            403, detail="Acesso restrito a coordenador/admin."
        )

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

    contexto_pdf = _montar_contexto_pdf(db, rel)
    resumo_global, categorias_globais = montar_checagens_globais(db, rel)
    arvore_revisao = _arvore_revisao_navegacao(rel, categorias_globais, [])
    relatorios_opcao = (
        db.query(Relatorio).order_by(Relatorio.created_at.desc()).all()
    )

    contexto = {
        "user": user,
        "rel": rel,
        "secoes_preview_grupos": contexto_pdf["secoes_preview_grupos"],
        "sumario_html": contexto_pdf["sumario_html"],
        "medicao": contexto_pdf["medicao"],
        "cover_bg_src": contexto_pdf["cover_bg_src"],
        "cover_produto": contexto_pdf["cover_produto"],
        "header_logos_src": contexto_pdf["header_logos_src"],
        "pli_line_src": contexto_pdf["pli_line_src"],
        "arvore_revisao": arvore_revisao,
        "resumo_global": resumo_global,
        "relatorio_editavel": rel.status != "finalizado",
        "hoje": date.today(),
        # O cadeado por bloco só faz sentido enquanto a coleta está aberta —
        # ali ele protege contra outros autores. Em ``em_revisao`` o
        # coordenador é dono do conteúdo e a trava some da UI (o campo
        # ``bloqueado`` permanece intacto no DB).
        "bloqueio_visivel": rel.status == "aberto",
        "relatorios_opcao": relatorios_opcao,
    }
    return templates.TemplateResponse(
        request,
        "complementos/revisao_edicao.html",
        contexto,
    )


# pylint: disable=too-many-return-statements
async def revisao_salvar_bloco(
    rel_id: int,
    bloco_id: int,
    request: Request,
    db: Session,
):
    """Auto-save de bloco a partir da página de revisão editorial.

    Recebe JSON com ``conteudo``, ``legenda``, ``fonte`` (todos opcionais).
    Preserva ``bloqueado`` (admin/coord pode editar mesmo confirmado, sem
    desbloquear). Recusa em relatórios ``finalizado``. Retorna JSON.
    """
    user, p = user_or_login_page(request, db)
    if p is not None:
        return JSONResponse(
            {"detail": "Sessão expirada."}, status_code=401
        )
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        return JSONResponse(
            {"detail": "Acesso restrito."}, status_code=403
        )

    rel = db.get(Relatorio, rel_id)
    if not rel:
        return JSONResponse(
            {"detail": "Relatório não encontrado."}, status_code=404
        )
    if rel.status == "finalizado":
        return JSONResponse(
            {
                "detail": (
                    "Relatório finalizado: reverta o status antes de editar."
                )
            },
            status_code=409,
        )

    bloco = db.get(Bloco, bloco_id)
    sec = db.get(Secao, bloco.secao_id) if bloco else None
    if not bloco or sec is None or sec.relatorio_id != rel_id:
        return JSONResponse(
            {"detail": "Bloco não encontrado."}, status_code=404
        )

    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            {"detail": "Payload inválido."}, status_code=400
        )

    # Defesa em profundidade: se o conteúdo bruto contém marcadores
    # estruturais ([[FIGURA:..]], [[TABELA..]], [[REF:..]]), a edição inline
    # destruiria a integridade. O frontend já bloqueia a UI, mas o backend
    # também recusa explicitamente.
    bruto_atual = bloco.conteudo or ""
    tem_marcador = (
        "[[FIGURA:" in bruto_atual
        or "[[TABELA" in bruto_atual
        or "[[REF:" in bruto_atual
    )
    if "conteudo" in payload and tem_marcador:
        return JSONResponse(
            {
                "detail": (
                    "Bloco contém marcadores de figura/tabela/referência. "
                    "Edite no Editor de Conteúdo da seção."
                ),
            },
            status_code=409,
        )

    # Edição parcial: só os campos presentes no JSON são atualizados. Isso
    # permite ao frontend salvar só legenda/fonte (figura/tabela) sem mexer
    # em ``conteudo``.
    if "conteudo" in payload:
        bloco.conteudo = payload.get("conteudo") or ""
    if "legenda" in payload:
        leg = (payload.get("legenda") or "").strip()
        bloco.legenda = leg or None
    if "fonte" in payload:
        fonte = (payload.get("fonte") or "").strip()
        bloco.fonte = fonte or None

    bloco.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse(
        {
            "ok": True,
            "bloco_id": bloco.id,
            "updated_at": bloco.updated_at.isoformat(),
            "bloqueado": bool(bloco.bloqueado),
        }
    )


# pylint: disable=too-many-return-statements
def revisao_desconfirmar_bloco(
    rel_id: int,
    bloco_id: int,
    request: Request,
    db: Session,
):
    """Reabre um bloco confirmado (``bloqueado=False``). Idempotente."""
    user, p = user_or_login_page(request, db)
    if p is not None:
        return JSONResponse(
            {"detail": "Sessão expirada."}, status_code=401
        )
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        return JSONResponse(
            {"detail": "Acesso restrito."}, status_code=403
        )

    rel = db.get(Relatorio, rel_id)
    if not rel:
        return JSONResponse(
            {"detail": "Relatório não encontrado."}, status_code=404
        )
    if rel.status == "finalizado":
        return JSONResponse(
            {"detail": "Relatório finalizado: reverta o status antes."},
            status_code=409,
        )

    bloco = db.get(Bloco, bloco_id)
    sec = db.get(Secao, bloco.secao_id) if bloco else None
    if not bloco or sec is None or sec.relatorio_id != rel_id:
        return JSONResponse(
            {"detail": "Bloco não encontrado."}, status_code=404
        )

    bloco.bloqueado = False
    bloco.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse(
        {"ok": True, "bloco_id": bloco.id, "bloqueado": False}
    )


# pylint: disable=too-many-return-statements,unused-argument
async def revisao_vocabulario_adicionar(
    rel_id: int,
    request: Request,
    db: Session,
):
    """Adiciona termo ao vocabulário do projeto (escopo global).

    ``rel_id`` só serve como contexto; termos são compartilhados. Body JSON:
    ``{"termo": "Concremat"}``. Idempotente — termo existente devolve 200 com
    ``criado=false``. Restrito a admin/coordenador.
    """
    user, p = user_or_login_page(request, db)
    if p is not None:
        return JSONResponse(
            {"detail": "Sessão expirada."}, status_code=401
        )
    assert user is not None
    if user.role not in ("admin", "coordenador"):
        return JSONResponse(
            {"detail": "Acesso restrito."}, status_code=403
        )

    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            {"detail": "Payload inválido."}, status_code=400
        )
    termo = (payload.get("termo") or "").strip()
    if not termo:
        return JSONResponse({"detail": "Termo vazio."}, status_code=400)

    try:
        registro, criado = adicionar_termo_vocabulario(db, termo, user.id)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "ok": True,
            "criado": criado,
            "termo": registro.termo,
            "id": registro.id,
        }
    )
