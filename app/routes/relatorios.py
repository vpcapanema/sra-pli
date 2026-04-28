import re
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from starlette.responses import Response
from sqlalchemy.orm import Session, selectinload
from dateutil import parser as dateparser

from ..db import get_db, tx_session
from ..models import Relatorio, Secao, Bloco, User
from .blocos import _hook_recompute_entrega, _impacta_numeracao, _pode_editar_status
from ..bootstrap import criar_secoes_padrao
from ..numeracao import consolidar_referencias, renumerar_relatorio
from ..sumario_extractor import (
    extrair_sumario,
    extrair_sumario_pdf_disponivel,
)
from ..process_events import process_done, process_log, process_start
from ..sra_process_modal import montar_data_modal_fim
from .pages import (
    response_conteudo_upload,
    response_dashboard,
    response_relatorio_detail,
    response_secao_edit,
    user_or_login_page,
)

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


def _exigir_relatorio_editavel(db: Session, rel_id: int) -> Relatorio:
    """Carrega o relatorio garantindo status mutavel.

    Bloqueia mutacoes estruturais (criar/excluir/mover secao) em relatorios
    finalizados: a numeracao do PDF entregue e contratual e nao pode mudar
    sem reverter o status. Coordenador/admin tem ``/reverter`` se precisar.
    """
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if rel.status == "finalizado":
        raise HTTPException(
            400,
            detail=(
                "Relatorio finalizado: reverta o status antes de alterar a estrutura."
            ),
        )
    return rel


def _u_or_login(
    request: Request, db: Session
) -> tuple[User, None] | tuple[None, Response]:
    u, p = user_or_login_page(request, db)
    if p is not None:
        return None, p
    assert u is not None
    return u, None


@router.get("/{rel_id}/blocos-confirmados.json")
def listar_blocos_confirmados_json(  # pylint: disable=too-many-locals
    rel_id: int, request: Request, db: Session = Depends(get_db)
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    assert u is not None
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    pode_status, motivo_status = _pode_editar_status(user, rel)
    blocos = (
        db.query(Bloco)
        .join(Secao, Secao.id == Bloco.secao_id)
        .options(selectinload(Bloco.autor))
        .filter(Secao.relatorio_id == rel_id, Bloco.bloqueado.is_(True))
        .order_by(Secao.ordem, Bloco.ordem)
        .all()
    )
    sec_por_id = {
        s.id: s for s in db.query(Secao).filter(Secao.relatorio_id == rel_id).all()
    }
    payload_blocos = []
    for b in blocos:
        sec_row = sec_por_id.get(b.secao_id)
        payload_blocos.append(
            {
                "id": b.id,
                "secao_id": b.secao_id,
                "secao_numero": sec_row.numero if sec_row else "",
                "secao_titulo": sec_row.titulo if sec_row else "",
                "tipo": b.tipo,
                "ordem": b.ordem,
                "titulo": b.titulo or "",
                "conteudo": b.conteudo or "",
                "legenda": b.legenda or "",
                "fonte": b.fonte or "",
                "figura_id": b.figura_id,
                "bloqueado": True,
                "pode_editar": False,
                "autor_nome": b.autor.nome if b.autor else None,
                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            }
        )
    return JSONResponse(
        {
            "modo": "todas_confirmadas",
            "relatorio": {"status": rel.status},
            "pode_editar_secao": pode_status,
            "motivo_bloqueio": motivo_status,
            "secao": None,
            "blocos": payload_blocos,
        }
    )


@router.post("/{rel_id}/blocos/excluir-todos-confirmados")
def excluir_todos_blocos_confirmados(  # pylint: disable=too-many-locals
    rel_id: int, request: Request, db: Session = Depends(get_db)
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    assert u is not None
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = _exigir_relatorio_editavel(db, rel_id)
    ok_ed, motivo = _pode_editar_status(user, rel)
    if not ok_ed:
        raise HTTPException(403, detail=motivo)
    blocos = (
        db.query(Bloco)
        .join(Secao, Secao.id == Bloco.secao_id)
        .filter(Secao.relatorio_id == rel_id, Bloco.bloqueado.is_(True))
        .all()
    )
    if not blocos:
        return JSONResponse({"ok": True, "removidos": 0})
    sec_ids = {b.secao_id for b in blocos}
    process_id = process_start(
        request,
        "Exclusão em lote (confirmados)",
        f"Removendo {len(blocos)} bloco(s) confirmado(s) do relatório.",
    )
    ids = [b.id for b in blocos]
    afeta = any(_impacta_numeracao(b.tipo, b.conteudo) for b in blocos)
    with tx_session() as txdb:
        if afeta:
            consolidar_referencias(txdb, rel_id)
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).delete(synchronize_session=False)
    for sid in sec_ids:
        _hook_recompute_entrega(db, rel_id, sid)
    process_done(
        request,
        process_id,
        "Blocos excluídos",
        f"{len(blocos)} bloco(s) confirmado(s) removido(s).",
    )
    return JSONResponse({"ok": True, "removidos": len(blocos)})


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
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    if db.query(Relatorio).filter(Relatorio.codigo == codigo.strip()).first():
        raise HTTPException(400, detail="Código já existe")
    process_id = process_start(
        request,
        "Criação de relatório",
        f"Configuração inicial do código {codigo.strip()} e da estrutura de seções.",
        data={"process_key": "relatorio_criar"},
    )

    # 1) Decide a fonte das seções ANTES de gravar (para falhar cedo).
    secoes_explicitas: "list[tuple[str, str]] | None" = None
    fonte = (fonte_secoes or "pdf_disponivel").strip().lower()
    if fonte == "pdf_disponivel":
        nome = (pdf_disponivel or "").strip()
        if not nome:
            process_done(
                request, process_id, "Criação interrompida", "PDF disponível não selecionado.", ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail="Selecione o PDF disponível.")
        try:
            process_log(
                request,
                process_id,
                f"Lê-se o sumário no PDF de referência “{nome}” e extrai-se a hierarquia prevista para o relatório.",
                etapa="Obtenção do sumário",
                tarefa="Criação de relatório",
                progresso_tarefa=35,
                progresso_geral=28,
            )
            secoes_explicitas = extrair_sumario_pdf_disponivel(nome)
        except ValueError as exc:
            process_done(
                request, process_id, "Falha no sumário", str(exc), ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail=str(exc))
        if not secoes_explicitas:
            process_done(
                request,
                process_id,
                "Falha no sumário",
                f"Não foi possível extrair o sumário de {nome}.",
                ok=False,
                process_key="relatorio_criar",
            )
            raise HTTPException(400, detail=f"Não foi possível extrair o sumário de {nome}.")
    elif fonte == "upload":
        if pdf_upload is None or not pdf_upload.filename:
            process_done(
                request, process_id, "Criação interrompida", "PDF não enviado.", ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail="Envie um arquivo PDF.")
        if not pdf_upload.filename.lower().endswith(".pdf"):
            process_done(
                request, process_id, "Arquivo recusado", "O arquivo enviado não é um PDF.", ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail="O arquivo enviado não é um PDF.")
        dados = await pdf_upload.read()
        if not dados:
            process_done(
                request, process_id, "Arquivo recusado", "Arquivo PDF vazio.", ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail="Arquivo PDF vazio.")
        try:
            process_log(
                request,
                process_id,
                f"Lê-se o ficheiro enviado ({pdf_upload.filename}) e extrai-se a hierarquia de secções para o novo relatório.",
                etapa="Obtenção do sumário",
                tarefa="Criação de relatório",
                progresso_tarefa=38,
                progresso_geral=30,
            )
            secoes_explicitas = extrair_sumario(dados)
        except Exception as exc:  # noqa: BLE001
            process_done(
                request, process_id, "Falha ao ler PDF", str(exc), ok=False, process_key="relatorio_criar"
            )
            raise HTTPException(400, detail=f"Falha ao ler o PDF: {exc}")
        if not secoes_explicitas:
            process_done(
                request,
                process_id,
                "Falha no sumário",
                "Não foi possível extrair o sumário do PDF enviado.",
                ok=False,
                process_key="relatorio_criar",
            )
            raise HTTPException(400, detail="Não foi possível extrair o sumário do PDF enviado.")
    else:
        process_done(
            request, process_id, "Criação interrompida", "Fonte de seções inválida.", ok=False, process_key="relatorio_criar"
        )
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
        process_log(
            request,
            process_id,
            f"Persistem-se o relatório e {len(secoes_explicitas or [])} secção(ões) em transação única, com renumeração consistente.",
            etapa="Persistência",
            tarefa="Criação de relatório",
            progresso_tarefa=85,
            progresso_geral=78,
        )
        txdb.add(rel)
        txdb.flush()
        rel_id_novo = rel.id
        criar_secoes_padrao(txdb, rel_id_novo, secoes_explicitas=secoes_explicitas)
    msg_ok = f"{codigo.strip()} disponível para edição."
    process_done(
        request,
        process_id,
        "Relatório criado",
        msg_ok,
        process_key="relatorio_criar",
    )
    # Permite exibir o modal de sucesso na resposta; em produção com vários
    # workers o SSE pode servir a outro processo e o evento não ser repetido.
    fin_data = montar_data_modal_fim(
        process_key="relatorio_criar",
        titulo="Relatório criado",
        mensagem=msg_ok,
        outcome="success",
    )
    request.session["sra_fim_pendente"] = {"process_id": process_id, "data": fin_data}
    return response_relatorio_detail(request, db, rel_id_novo)


@router.post("/{rel_id}/status")
def alterar_status(
    rel_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if status not in ("aberto", "em_revisao", "finalizado"):
        raise HTTPException(400)
    rel.status = status
    db.commit()
    return response_relatorio_detail(request, db, rel_id)


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
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
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
    return response_dashboard(request, db)


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
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    rel.versao = _proxima_versao(rel.versao)
    db.commit()
    return response_relatorio_detail(request, db, rel_id)


@router.post("/{rel_id}/duplicar")
def duplicar_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
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

    return response_dashboard(request, db)


@router.post("/{rel_id}/reverter")
def reverter_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    if rel.status != "finalizado":
        raise HTTPException(400, detail="Só é possível reverter relatórios finalizados.")
    rel.status = "aberto"
    db.commit()
    return response_dashboard(request, db)


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
    with tx_session() as txdb:
        rel_tx = txdb.get(Relatorio, rel_id)
        if rel_tx is not None:
            txdb.delete(rel_tx)
    return response_dashboard(request, db)


@router.post("/{rel_id}/secoes/{sec_id}/responsavel")
def atribuir_responsavel(  # pylint: disable=too-many-arguments
    rel_id: int,
    sec_id: int,
    request: Request,
    *,
    responsavel_id: str = Form(""),
    retorno: str = Form(""),
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if user.role == "autor":
        if not responsavel_id.strip():
            raise HTTPException(400, detail="Selecione-se como responsável e confirme.")
        rid = int(responsavel_id)
        if rid != user.id:
            raise HTTPException(403, detail="Autor só pode atribuir a si próprio.")
        sec.responsavel_id = rid
    else:
        if user.role not in ("admin", "coordenador"):
            raise HTTPException(403)
        sec.responsavel_id = int(responsavel_id) if responsavel_id else None
    db.commit()
    if retorno == "upload":
        return response_conteudo_upload(request, db, rel_id, sec_id)
    return response_secao_edit(request, db, rel_id, sec_id)


@router.post("/{rel_id}/secoes/{sec_id}/status")
def status_secao(  # pylint: disable=too-many-arguments
    rel_id: int,
    sec_id: int,
    request: Request,
    *,
    status: str = Form(...),
    retorno: str = Form(""),
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if u.role == "autor":
        if sec.responsavel_id is not None and sec.responsavel_id != u.id:
            raise HTTPException(403, detail="Sem permissão para alterar o status desta seção.")
    elif u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    if status not in ("pendente", "em_andamento", "aprovada"):
        raise HTTPException(400)
    sec.status = status
    db.commit()
    if retorno == "upload":
        return response_conteudo_upload(request, db, rel_id, sec_id)
    return response_secao_edit(request, db, rel_id, sec_id)


def _ordem_for_numero(numero: str) -> tuple:
    """Chave de ordenação tipo (1, 2, 3) para '4.4.6.1'."""
    parts = []
    for p in numero.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _numero_livre_no_nivel(
    secoes: list[Secao], nivel: int, prefixo: str
) -> str:
    """Devolve um numero livre no nivel/prefixo indicado.

    Varre TODAS as secoes (inclusive descendentes) sob ``prefixo`` e toma a
    K-esima parte (``K = nivel - 1``); o resultado e ``prefixo + (max + 1)``,
    garantindo zero colisao com numeros existentes ou com qualquer prefixo de
    descendente. Necessario para inserir com shift-on-insert sem violar
    ``UniqueConstraint(relatorio_id, numero)`` antes da renumeracao.
    """
    sufixos: list[int] = []
    for sec in secoes:
        num = sec.numero or ""
        partes = num.split(".")
        if len(partes) < nivel:
            continue
        if prefixo and not num.startswith(prefixo):
            continue
        try:
            sufixos.append(int(partes[nivel - 1]))
        except ValueError:
            continue
    proximo = (max(sufixos) + 1) if sufixos else 1
    return f"{prefixo}{proximo}"


def _inserir_secao_em_relatorio(
    db_session: Session, rel_id: int, numero: str, titulo: str
) -> None:
    """Insere uma secao na posicao indicada por ``numero`` e renumera a arvore.

    Comportamento:
    - ``numero`` e um HINT DE POSICAO. Se ja existir secao com esse numero,
      a inserida toma a posicao e a existente (e suas irmas posteriores) sao
      empurradas via ``ordem``. A renumeracao recalcula os numeros finais.
    - Para evitar ``IntegrityError`` no flush (UniqueConstraint), a nova
      secao entra com um numero TEMPORARIO LIVRE no mesmo nivel/prefixo
      (``_numero_livre_no_nivel``). O numero final sai do ``renumerar_relatorio``.
    - Limitacao contratual D20: ``renumerar_relatorio`` PRESERVA o numero das
      raizes (``numeracao.py``). Inserir entre raizes nao desloca; a nova fica
      no proximo slot livre. O frontend reflete isso oferecendo max+1 no nivel 1.

    Aplica em transacao explicita: consolida referencias textuais ANTES da
    mutacao (estabiliza alvos por id), desloca a ``ordem`` das irmas posteriores,
    persiste a nova secao e renumera por DFS.
    """
    todas = db_session.query(Secao).filter_by(relatorio_id=rel_id).all()
    partes_alvo = numero.split(".")
    nivel = len(partes_alvo)
    prefixo_alvo = ".".join(partes_alvo[:-1]) + "." if nivel > 1 else ""
    raiz_em_conflito = nivel == 1 and any(
        (s.numero or "") == numero for s in todas
    )
    if raiz_em_conflito:
        # Renumerar preserva numeros de raiz; deslocamento entre raizes nao e
        # suportado. Append: ordem maxima + 1, sem mexer nos existentes.
        nova_ordem = len(todas)
        ids_deslocar: list[int] = []
    else:
        chave_alvo = _ordem_for_numero(numero)
        nova_ordem = sum(
            1 for s in todas if _ordem_for_numero(s.numero) < chave_alvo
        )
        ids_deslocar = [
            s.id for s in todas if _ordem_for_numero(s.numero) >= chave_alvo
        ]
    numero_temp = _numero_livre_no_nivel(todas, nivel, prefixo_alvo)
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        if ids_deslocar:
            txdb.query(Secao).filter(Secao.id.in_(ids_deslocar)).update(
                {Secao.ordem: Secao.ordem + 1}, synchronize_session=False
            )
        txdb.add(
            Secao(
                relatorio_id=rel_id,
                numero=numero_temp,
                titulo=titulo,
                ordem=nova_ordem,
            )
        )
        txdb.flush()
        renumerar_relatorio(txdb, rel_id)


def _proximo_numero_filho(
    db_session: Session, rel_id: int, pai_numero: str
) -> str:
    """Calcula o proximo numero de filha direta de ``pai_numero``.

    Retorna ``{pai_numero}.{max_filha_direta + 1}``, ou ``{pai_numero}.1``
    quando ainda nao ha filhas diretas. Considera apenas filhas no nivel
    imediatamente abaixo (ignora netos).
    """
    nivel_pai = pai_numero.count(".")
    prefixo = pai_numero + "."
    sufixos: list[int] = []
    for sec in db_session.query(Secao).filter_by(relatorio_id=rel_id).all():
        num = sec.numero or ""
        if not num.startswith(prefixo) or num.count(".") != nivel_pai + 1:
            continue
        try:
            sufixos.append(int(num[len(prefixo):]))
        except ValueError:
            continue
    proximo = (max(sufixos) + 1) if sufixos else 1
    return f"{prefixo}{proximo}"


_RE_NUMERO_SECAO = re.compile(r"^\d+(?:\.\d+)*$")


@router.post("/{rel_id}/secoes")
def criar_subsecao(
    rel_id: int,
    request: Request,
    numero: str = Form(...),
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    """Cria uma secao no relatorio na posicao indicada por ``numero``.

    ``numero`` e o INDICE DESEJADO da nova secao (ex.: ``4.4`` insere antes
    do atual ``4.4``, deslocando os irmaos posteriores). Para niveis >= 2 o
    deslocamento e efetivo via ``_inserir_secao_em_relatorio``; para nivel 1
    (raizes), ``renumerar_relatorio`` preserva os numeros existentes por
    contrato D20 e a nova secao toma o proximo slot livre quando o indice
    pedido ja esta ocupado.
    """
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    numero = numero.strip()
    titulo = titulo.strip()
    if not numero or not titulo:
        raise HTTPException(400, detail="Informe número e título")
    if not _RE_NUMERO_SECAO.match(numero):
        raise HTTPException(
            400, detail="Número de seção inválido (use apenas dígitos e pontos)"
        )
    _inserir_secao_em_relatorio(db, rel_id, numero, titulo)
    return response_relatorio_detail(request, db, rel_id)


@router.post("/{rel_id}/secoes/{sec_id}/subsecao")
def criar_subsecao_filha(
    rel_id: int,
    sec_id: int,
    request: Request,
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    """Cria uma subsecao como ultima filha direta da secao indicada.

    O numero da nova subsecao e calculado pelo servidor a partir do pai
    via ``_proximo_numero_filho``. Apos a insercao, ``renumerar_relatorio``
    recompoe a arvore inteira para fechar buracos e propagar deslocamentos.
    """
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    pai = db.get(Secao, sec_id)
    if not pai or pai.relatorio_id != rel_id:
        raise HTTPException(404)
    titulo = titulo.strip()
    if not titulo:
        raise HTTPException(400, detail="Informe o título da subseção")
    pai_numero = (pai.numero or "").strip()
    if not pai_numero:
        raise HTTPException(400, detail="Seção pai sem número definido")
    novo_numero = _proximo_numero_filho(db, rel_id, pai_numero)
    if db.query(Secao).filter_by(relatorio_id=rel_id, numero=novo_numero).first():
        raise HTTPException(409, detail="Conflito de numeração; tente novamente.")
    _inserir_secao_em_relatorio(db, rel_id, novo_numero, titulo)
    return response_relatorio_detail(request, db, rel_id)


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
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if "." not in (sec.numero or ""):
        raise HTTPException(400, detail="Não é possível excluir seções de primeiro nível")
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        sec_tx = txdb.get(Secao, sec_id)
        if sec_tx is not None:
            txdb.delete(sec_tx)
            txdb.flush()
        renumerar_relatorio(txdb, rel_id)
    return response_relatorio_detail(request, db, rel_id)


def _achar_par_swap(
    db: Session, rel_id: int, sec: Secao, direcao: str
) -> tuple[Secao, Secao] | None:
    """Localiza o par (atual, vizinho) para swap entre irmaos diretos.

    Retorna ``None`` se a secao ja esta na borda (mover para cima do primeiro
    ou para baixo do ultimo). Top-level deve ter sido bloqueado antes.
    """
    numero_sec = sec.numero or ""
    nivel = numero_sec.count(".")
    prefixo_pai = ".".join(numero_sec.split(".")[:-1]) + "."
    irmaos = (
        db.query(Secao)
        .filter(
            Secao.relatorio_id == rel_id,
            Secao.numero.like(f"{prefixo_pai}%"),
        )
        .all()
    )
    diretos = sorted(
        (s for s in irmaos if (s.numero or "").count(".") == nivel),
        key=lambda s: (s.ordem or 0, _ordem_for_numero(s.numero or "")),
    )
    pos = next((i for i, s in enumerate(diretos) if s.id == sec.id), -1)
    if pos < 0:
        return None
    alvo = pos - 1 if direcao == "cima" else pos + 1
    if alvo < 0 or alvo >= len(diretos):
        return None
    return diretos[pos], diretos[alvo]


@router.post("/{rel_id}/secoes/{sec_id}/mover")
def mover_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    direcao: str = Form(...),
    db: Session = Depends(get_db),
):
    """Move uma subsecao para cima ou para baixo entre os irmaos diretos.

    Apenas troca a ``ordem`` dos dois nos diretos. ``renumerar_relatorio``
    refaz numeros e ordem global; subsecoes filhas seguem o pai
    automaticamente porque a hierarquia e inferida do numero.

    Top-level nao se move: a estrutura "4 / 5 / 6 ..." do contrato D20 e fixa.
    """
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
    if user.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    _exigir_relatorio_editavel(db, rel_id)
    direcao = (direcao or "").strip().lower()
    if direcao not in ("cima", "baixo"):
        raise HTTPException(400, detail="Direcao invalida; use 'cima' ou 'baixo'.")
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if "." not in (sec.numero or ""):
        raise HTTPException(400, detail="Secoes de primeiro nivel nao podem ser movidas.")
    par = _achar_par_swap(db, rel_id, sec, direcao)
    if par is None:
        return response_relatorio_detail(request, db, rel_id)

    par_a, par_b = par
    with tx_session() as txdb:
        consolidar_referencias(txdb, rel_id)
        # ``ordem`` nao tem unique constraint: swap direto e seguro.
        # ``renumerar_relatorio`` normaliza ordem em sequencia DFS depois.
        sec_a = txdb.get(Secao, par_a.id)
        sec_b = txdb.get(Secao, par_b.id)
        if sec_a is not None and sec_b is not None:
            sec_a.ordem, sec_b.ordem = sec_b.ordem, sec_a.ordem
            txdb.flush()
        renumerar_relatorio(txdb, rel_id)
    return response_relatorio_detail(request, db, rel_id)


@router.post("/{rel_id}/secoes/{sec_id}/renomear")
def renomear_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    user = u
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
    return response_secao_edit(request, db, rel_id, sec_id)
