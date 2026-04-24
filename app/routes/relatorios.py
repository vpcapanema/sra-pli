from datetime import date
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from dateutil import parser as dateparser

from ..db import get_db
from ..models import Relatorio, Secao, User
from ..auth import current_user
from ..bootstrap import criar_secoes_padrao

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _require(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


@router.post("")
def criar_relatorio(
    request: Request,
    codigo: str = Form(...),
    titulo: str = Form(...),
    mes_referencia: str = Form(...),
    periodo_inicio: str = Form(...),
    periodo_fim: str = Form(...),
    numero_medicao: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    if db.query(Relatorio).filter(Relatorio.codigo == codigo.strip()).first():
        raise HTTPException(400, detail="Código já existe")
    rel = Relatorio(
        codigo=codigo.strip(),
        titulo=titulo.strip(),
        mes_referencia=mes_referencia.strip(),
        periodo_inicio=dateparser.parse(periodo_inicio).date(),
        periodo_fim=dateparser.parse(periodo_fim).date(),
        numero_medicao=int(numero_medicao) if numero_medicao.strip() else None,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    criar_secoes_padrao(db, rel.id)
    return RedirectResponse(f"/relatorios/{rel.id}", status_code=303)


@router.post("/{rel_id}/status")
def alterar_status(
    rel_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if status not in ("aberto", "em_revisao", "finalizado"):
        raise HTTPException(400)
    rel.status = status
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)


@router.post("/{rel_id}/versao")
def nova_versao(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    n = int(rel.versao.replace("R", "")) + 1
    rel.versao = f"R{n:02d}"
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)


@router.post("/{rel_id}/secoes/{sec_id}/responsavel")
def atribuir_responsavel(
    rel_id: int,
    sec_id: int,
    request: Request,
    responsavel_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    sec.responsavel_id = int(responsavel_id) if responsavel_id else None
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


@router.post("/{rel_id}/secoes/{sec_id}/status")
def status_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if status not in ("pendente", "em_andamento", "aprovada"):
        raise HTTPException(400)
    sec.status = status
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)


def _ordem_for_numero(numero: str) -> tuple:
    """Chave de ordenação tipo (1, 2, 3) para '4.4.6.1'."""
    parts = []
    for p in numero.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


@router.post("/{rel_id}/secoes")
def criar_subsecao(
    rel_id: int,
    request: Request,
    numero: str = Form(...),
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    numero = numero.strip()
    titulo = titulo.strip()
    if not numero or not titulo:
        raise HTTPException(400, detail="Informe número e título")
    if db.query(Secao).filter_by(relatorio_id=rel_id, numero=numero).first():
        raise HTTPException(400, detail="Número de seção já existe neste relatório")
    # ordem = posição na sequência ordenada de todas as seções
    todas = db.query(Secao).filter_by(relatorio_id=rel_id).all()
    chaves = sorted(
        [(_ordem_for_numero(s.numero), s.id) for s in todas] + [(_ordem_for_numero(numero), None)]
    )
    nova_ordem = next(i for i, (_, sid) in enumerate(chaves) if sid is None)
    # reindexa ordens
    db.add(Secao(relatorio_id=rel_id, numero=numero, titulo=titulo, ordem=nova_ordem))
    # incrementa ordem das seções abaixo
    for sec in todas:
        if _ordem_for_numero(sec.numero) >= _ordem_for_numero(numero):
            sec.ordem = sec.ordem + 1
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)


@router.post("/{rel_id}/secoes/{sec_id}/excluir")
def excluir_subsecao(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    # Só permite excluir subseções com mais de um nível (ex.: 4.3.1, 10.1)
    if "." not in sec.numero:
        raise HTTPException(400, detail="Não é possível excluir seções de primeiro nível")
    db.delete(sec)
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)
