import re
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from dateutil import parser as dateparser

from ..db import get_db, tx_session
from ..models import Relatorio, Secao, Bloco, User
from ..auth import current_user
from ..bootstrap import criar_secoes_padrao
from ..sumario_extractor import (
    extrair_sumario,
    extrair_sumario_pdf_disponivel,
)
from ..process_events import process_done, process_log, process_start

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _require(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


@router.post("")
async def criar_relatorio(
    request: Request,
    codigo: str = Form(...),
    titulo: str = Form(...),
    mes_referencia: str = Form(...),
    periodo_inicio: str = Form(...),
    periodo_fim: str = Form(...),
    numero_medicao: str = Form(""),
    fonte_secoes: str = Form("pdf_disponivel"),
    pdf_disponivel: str = Form(""),
    pdf_upload: "UploadFile | None" = File(None),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    if db.query(Relatorio).filter(Relatorio.codigo == codigo.strip()).first():
        raise HTTPException(400, detail="Código já existe")
    process_id = process_start(request, "Criação de relatório", f"Preparando {codigo.strip()}.")

    # 1) Decide a fonte das seções ANTES de gravar (para falhar cedo).
    secoes_explicitas: "list[tuple[str, str]] | None" = None
    fonte = (fonte_secoes or "pdf_disponivel").strip().lower()
    if fonte == "pdf_disponivel":
        nome = (pdf_disponivel or "").strip()
        if not nome:
            process_done(request, process_id, "Criação interrompida", "PDF disponível não selecionado.", ok=False)
            raise HTTPException(400, detail="Selecione o PDF disponível.")
        try:
            process_log(request, process_id, f"Extraindo sumário de {nome}.")
            secoes_explicitas = extrair_sumario_pdf_disponivel(nome)
        except ValueError as exc:
            process_done(request, process_id, "Falha no sumário", str(exc), ok=False)
            raise HTTPException(400, detail=str(exc))
        if not secoes_explicitas:
            process_done(request, process_id, "Falha no sumário", f"Não foi possível extrair o sumário de {nome}.", ok=False)
            raise HTTPException(400, detail=f"Não foi possível extrair o sumário de {nome}.")
    elif fonte == "upload":
        if pdf_upload is None or not pdf_upload.filename:
            process_done(request, process_id, "Criação interrompida", "PDF não enviado.", ok=False)
            raise HTTPException(400, detail="Envie um arquivo PDF.")
        if not pdf_upload.filename.lower().endswith(".pdf"):
            process_done(request, process_id, "Arquivo recusado", "O arquivo enviado não é um PDF.", ok=False)
            raise HTTPException(400, detail="O arquivo enviado não é um PDF.")
        dados = await pdf_upload.read()
        if not dados:
            process_done(request, process_id, "Arquivo recusado", "Arquivo PDF vazio.", ok=False)
            raise HTTPException(400, detail="Arquivo PDF vazio.")
        try:
            process_log(request, process_id, f"Extraindo sumário do upload {pdf_upload.filename}.")
            secoes_explicitas = extrair_sumario(dados)
        except Exception as exc:  # noqa: BLE001
            process_done(request, process_id, "Falha ao ler PDF", str(exc), ok=False)
            raise HTTPException(400, detail=f"Falha ao ler o PDF: {exc}")
        if not secoes_explicitas:
            process_done(request, process_id, "Falha no sumário", "Não foi possível extrair o sumário do PDF enviado.", ok=False)
            raise HTTPException(400, detail="Não foi possível extrair o sumário do PDF enviado.")
    else:
        process_done(request, process_id, "Criação interrompida", "Fonte de seções inválida.", ok=False)
        raise HTTPException(400, detail="Selecione um relatório entregue ou envie um PDF.")

    rel = Relatorio(
        codigo=codigo.strip(),
        titulo=titulo.strip(),
        mes_referencia=mes_referencia.strip(),
        periodo_inicio=dateparser.parse(periodo_inicio).date(),
        periodo_fim=dateparser.parse(periodo_fim).date(),
        numero_medicao=int(numero_medicao) if numero_medicao.strip() else None,
    )
    # Criar relatório + seções padrão em uma única transação (multi-statement).
    with tx_session() as txdb:
        process_log(request, process_id, f"Gravando relatório e {len(secoes_explicitas or [])} seção(ões).")
        txdb.add(rel)
        txdb.flush()
        rel_id_novo = rel.id
        criar_secoes_padrao(txdb, rel_id_novo, secoes_explicitas=secoes_explicitas)
    process_done(request, process_id, "Relatório criado", f"{codigo.strip()} disponível para edição.")
    return RedirectResponse(f"/relatorios/{rel_id_novo}", status_code=303)


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


@router.post("/{rel_id}/editar")
def editar_relatorio(
    rel_id: int,
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
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)

    codigo_limpo = codigo.strip()
    if not codigo_limpo:
        raise HTTPException(400, detail="Informe o código do relatório.")
    existente = db.query(Relatorio).filter(Relatorio.codigo == codigo_limpo, Relatorio.id != rel_id).first()
    if existente:
        raise HTTPException(400, detail="Código já existe")

    titulo_limpo = titulo.strip()
    mes_limpo = mes_referencia.strip()
    if not titulo_limpo or not mes_limpo:
        raise HTTPException(400, detail="Informe título e mês de referência.")

    rel.codigo = codigo_limpo
    rel.titulo = titulo_limpo
    rel.mes_referencia = mes_limpo
    rel.periodo_inicio = dateparser.parse(periodo_inicio).date()
    rel.periodo_fim = dateparser.parse(periodo_fim).date()
    rel.numero_medicao = int(numero_medicao) if numero_medicao.strip() else None
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


_RE_VERSAO_NUM = re.compile(r"(\d+)")


def _proxima_versao(versao_atual: str | None) -> str:
    """Incrementa a versão preservando o prefixo. Aceita 'R00', 'R0A1', 'V3'…
    Se não houver número, começa em R01.
    """
    raw = (versao_atual or "").strip()
    match = _RE_VERSAO_NUM.search(raw)
    if not match:
        return "R01"
    numero = int(match.group(1)) + 1
    prefixo = raw[: match.start()] or "R"
    sufixo = raw[match.end():]
    return f"{prefixo}{numero:02d}{sufixo}"


@router.post("/{rel_id}/versao")
def nova_versao(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    rel.versao = _proxima_versao(rel.versao)
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)


@router.post("/{rel_id}/duplicar")
def duplicar_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)

    base_codigo = f"{rel.codigo}_copia"
    novo_codigo = base_codigo
    i = 2
    while db.query(Relatorio).filter(Relatorio.codigo == novo_codigo).first():
        novo_codigo = f"{base_codigo}{i}"
        i += 1

    secoes_orig = db.query(Secao).filter(Secao.relatorio_id == rel.id).order_by(Secao.ordem).all()
    sec_ids_orig = [s.id for s in secoes_orig]
    blocos_orig = (
        db.query(Bloco).filter(Bloco.secao_id.in_(sec_ids_orig)).order_by(Bloco.ordem).all()
        if sec_ids_orig else []
    )

    # Multi-statement: usa transação explícita para garantir atomicidade
    # (engine padrão roda em AUTOCOMMIT por performance).
    with tx_session() as txdb:
        novo = Relatorio(
            codigo=novo_codigo,
            titulo=f"{rel.titulo}_copia",
            mes_referencia=rel.mes_referencia,
            periodo_inicio=rel.periodo_inicio,
            periodo_fim=rel.periodo_fim,
            numero_medicao=rel.numero_medicao,
            versao="R00",
            status="aberto",
        )
        txdb.add(novo)
        txdb.flush()

        sec_map: dict[int, int] = {}
        for s in secoes_orig:
            nova_sec = Secao(
                relatorio_id=novo.id,
                numero=s.numero,
                titulo=s.titulo,
                ordem=s.ordem,
                responsavel_id=s.responsavel_id,
                status="pendente",
            )
            txdb.add(nova_sec)
            txdb.flush()
            sec_map[s.id] = nova_sec.id

        for b in blocos_orig:
            txdb.add(
                Bloco(
                    secao_id=sec_map[b.secao_id],
                    tipo=b.tipo,
                    ordem=b.ordem,
                    titulo=b.titulo,
                    conteudo=b.conteudo,
                    legenda=b.legenda,
                    fonte=b.fonte,
                    figura_id=b.figura_id,
                    autor_id=b.autor_id,
                )
            )

    return RedirectResponse("/dashboard", status_code=303)


@router.post("/{rel_id}/reverter")
def reverter_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if rel.status != "finalizado":
        raise HTTPException(400, detail="Só é possível reverter relatórios finalizados.")
    rel.status = "aberto"
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/{rel_id}/excluir")
def excluir_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    with tx_session() as txdb:
        rel_tx = txdb.get(Relatorio, rel_id)
        if rel_tx is not None:
            txdb.delete(rel_tx)
    return RedirectResponse("/dashboard", status_code=303)


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
    _require(request, db)
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
    todas = db.query(Secao).filter_by(relatorio_id=rel_id).all()
    chave_nova = _ordem_for_numero(numero)
    chaves = sorted(
        [(_ordem_for_numero(s.numero), s.id) for s in todas] + [(chave_nova, None)]
    )
    nova_ordem = next(i for i, (_, sid) in enumerate(chaves) if sid is None)
    ids_para_deslocar = [s.id for s in todas if _ordem_for_numero(s.numero) >= chave_nova]
    with tx_session() as txdb:
        if ids_para_deslocar:
            txdb.query(Secao).filter(Secao.id.in_(ids_para_deslocar)).update(
                {Secao.ordem: Secao.ordem + 1}, synchronize_session=False
            )
        txdb.add(Secao(relatorio_id=rel_id, numero=numero, titulo=titulo, ordem=nova_ordem))
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
    if "." not in sec.numero:
        raise HTTPException(400, detail="Não é possível excluir seções de primeiro nível")
    with tx_session() as txdb:
        sec_tx = txdb.get(Secao, sec_id)
        if sec_tx is not None:
            txdb.delete(sec_tx)
    return RedirectResponse(f"/relatorios/{rel_id}", status_code=303)


@router.post("/{rel_id}/secoes/{sec_id}/renomear")
def renomear_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require(request, db)
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    titulo = titulo.strip()
    if not titulo:
        raise HTTPException(400, detail="Título não pode ser vazio")
    sec.titulo = titulo
    db.commit()
    return RedirectResponse(f"/relatorios/{rel_id}/secoes/{sec_id}", status_code=303)
