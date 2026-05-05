import re
import threading
from pathlib import Path
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from sqlalchemy.exc import IntegrityError, DataError
from fastapi.responses import JSONResponse

from starlette.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload
from dateutil import parser as dateparser

from ..db import get_db, tx_session, SessionLocal
from ..models import Bloco, Relatorio, Secao, User
from .blocos import _hook_recompute_entrega, _impacta_numeracao, _pode_editar_status, campos_json_bloco_transversal
from ..bootstrap import criar_secoes_padrao
from ..modo_edicao_blocos import definir_modo_edicao_coordenador
from ..numeracao import consolidar_referencias, renumerar_relatorio, secao_ids_na_subarvore
from .. import ref_resolve
from ..sumario_extractor import (
    extrair_completo_pdf_disponivel,
    extrair_sumario,
    extrair_sumario_pdf_disponivel,
)
from ..docx_clone_extractor import (
    PASTA_RELATORIOS,
    extrair_relatorio_docx,
    extrair_relatorio_docx_disponivel,
)
from .. import progress_jobs

from .pages import (
    response_conteudo_upload,
    response_dashboard,
    response_relatorio_detail,
    user_or_login_page,
)

from .relatorios_secao_numeracao import (
    RE_NUMERO_SECAO,
    _achar_par_swap,
    _inserir_secao_em_relatorio,
    _proximo_numero_filho,
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
            detail=("Relatorio finalizado: reverta o status antes de alterar a estrutura."),
        )
    return rel


def _u_or_login(request: Request, db: Session) -> tuple[User, None] | tuple[None, Response]:
    u, p = user_or_login_page(request, db)
    if p is not None:
        return None, p
    assert u is not None
    return u, None


def _admin_coord_ou_login(
    request: Request,
    db: Session,
) -> tuple[User, None] | tuple[None, Response]:
    u, p = _u_or_login(request, db)
    if p is not None:
        return None, p
    assert u is not None
    if u.role not in ("admin", "coordenador"):
        raise HTTPException(403)
    return u, None


def _admin_coord_relatorio_mutavel(
    request: Request,
    db: Session,
    rel_id: int,
) -> Response | None:
    """Admin/coordenador e relatório editável, ou redirect login."""
    u, p = _admin_coord_ou_login(request, db)
    if p is not None:
        return p
    assert u is not None
    _exigir_relatorio_editavel(db, rel_id)
    return None


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
    rel = ref_resolve.carregar_relatorio_com_secoes_e_blocos(db, rel_id)
    if not rel:
        raise HTTPException(404)
    pode_status, motivo_status = _pode_editar_status(user, rel)
    mapas_ref = ref_resolve.calcular_mapas_referencia(rel.secoes)
    blocos = (
        db.query(Bloco)
        .join(Secao, Secao.id == Bloco.secao_id)
        .options(selectinload(Bloco.autor))
        .filter(Secao.relatorio_id == rel_id, Bloco.bloqueado.is_(True))
        .order_by(Secao.ordem, Bloco.ordem)
        .all()
    )
    sec_por_id = {s.id: s for s in db.query(Secao).filter(Secao.relatorio_id == rel_id).all()}
    payload_blocos = []
    for b in blocos:
        sec_row = sec_por_id.get(b.secao_id)
        payload_blocos.append(
            {
                **campos_json_bloco_transversal(b),
                "secao_id": b.secao_id,
                "secao_numero": sec_row.numero if sec_row else "",
                "secao_titulo": sec_row.titulo if sec_row else "",
                "bloqueado": True,
                "pode_editar": False,
            }
        )
    return JSONResponse(
        {
            "modo": "todas_confirmadas",
            "relatorio": {"status": rel.status},
            "pode_editar_secao": pode_status,
            "motivo_bloqueio": motivo_status,
            "ref_mapas": ref_resolve.mapas_para_json(mapas_ref),
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
    ids = [b.id for b in blocos]
    afeta = any(_impacta_numeracao(b.tipo, b.conteudo) for b in blocos)
    with tx_session() as txdb:
        if afeta:
            consolidar_referencias(txdb, rel_id)
        txdb.query(Bloco).filter(Bloco.id.in_(ids)).delete(synchronize_session=False)
    for sid in sec_ids:
        _hook_recompute_entrega(db, rel_id, sid)
    return JSONResponse({"ok": True, "removidos": len(blocos)})


@router.post("/{rel_id}/modo-edicao-blocos")
def post_modo_edicao_blocos(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    ativo: str = Form("0"),
):
    """Coordenador alterna modo em que pode editar/excluir/mover blocos já bloqueados."""
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    assert u is not None
    if u.role != "coordenador":
        raise HTTPException(403, detail="Somente o coordenador pode ativar o modo edição.")
    rel = db.get(Relatorio, rel_id)
    if not rel:
        raise HTTPException(404)
    ok_ed, motivo_ed = _pode_editar_status(u, rel)
    if not ok_ed:
        raise HTTPException(403, detail=motivo_ed)
    ligado = str(ativo).strip().lower() in ("1", "on", "true", "sim", "yes")
    if ligado:
        definir_modo_edicao_coordenador(request, rel_id)
    else:
        definir_modo_edicao_coordenador(request, None)
    alvo = (request.headers.get("referer") or "").strip() or f"/relatorios/{rel_id}"
    return RedirectResponse(url=alvo, status_code=303)


@router.get("/novo/progresso/{token}")
async def progresso_criar_relatorio(token: str) -> JSONResponse:
    """Consulta o progresso de uma criação assíncrona de relatório."""
    estado = progress_jobs.get_job(token)
    if not estado:
        return JSONResponse({"erro": "token_desconhecido"}, status_code=404)
    return JSONResponse(estado)


def _criar_relatorio_core(
    token: str | None,
    codigo: str,
    titulo: str,
    mes_referencia: str,
    periodo_inicio: str,
    periodo_fim: str,
    numero_medicao: str,
    fonte: str,
    pdf_disponivel: str,
    docx_disponivel: str,
    pdf_bytes: bytes | None,
    pdf_filename: str | None,
    docx_bytes: bytes | None,
    docx_filename: str | None,
    base_relatorio_id: str,
) -> int:
    """Cria o relatório (com seções/blocos) reportando progresso ao token.

    Retorna o ID do relatório criado. Levanta ``HTTPException`` em caso de
    validação falha. Usa sua própria ``Session`` do ``SessionLocal`` (não
    depende de request scope) para poder rodar em background.
    """

    def _p(pct: int, etapa: str) -> None:
        if token:
            progress_jobs.set_progress(token, pct, etapa)

    _p(2, "Validando parâmetros")
    secoes_explicitas: "list[tuple[str, str]] | None" = None
    secoes_com_conteudo: "list[dict] | None" = None
    origem_blocos: str = "pdf_import"
    base_rel_id: int | None = None

    db_check = SessionLocal()
    try:
        if db_check.query(Relatorio).filter(Relatorio.codigo == codigo.strip()).first():
            raise HTTPException(400, detail="Código já existe")
    finally:
        db_check.close()

    if fonte == "clone_relatorio":
        base_id_str = (base_relatorio_id or "").strip()
        if not base_id_str:
            raise HTTPException(400, detail="Selecione o relatório base para clonagem.")
        try:
            base_rel_id = int(base_id_str)
        except ValueError:
            raise HTTPException(400, detail="ID do relatório base inválido.")
        db_check = SessionLocal()
        try:
            base = db_check.get(Relatorio, base_rel_id)
            if not base:
                raise HTTPException(400, detail="Relatório base não encontrado.")
        finally:
            db_check.close()
        _p(20, "Preparando clonagem")
    elif fonte == "docx_disponivel":
        nome = (docx_disponivel or "").strip()
        if not nome:
            raise HTTPException(400, detail="Selecione o DOCX disponível.")
        _p(15, "Lendo DOCX do acervo")
        try:
            secoes_com_conteudo = extrair_relatorio_docx_disponivel(nome)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, detail=f"Erro ao processar DOCX: {exc}")
        if not secoes_com_conteudo:
            raise HTTPException(400, detail=f"Não foi possível extrair o conteúdo de {nome}.")
        origem_blocos = "docx_import"
        _p(45, "DOCX processado; gravando seções")
    elif fonte == "pdf_disponivel":
        nome = (pdf_disponivel or "").strip()
        if not nome:
            raise HTTPException(400, detail="Selecione o PDF disponível.")
        _p(15, "Lendo PDF do acervo")
        try:
            secoes_com_conteudo = extrair_completo_pdf_disponivel(nome)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, detail=f"Erro ao processar PDF: {exc}")
        if not secoes_com_conteudo:
            raise HTTPException(400, detail=f"Não foi possível extrair o conteúdo de {nome}.")
        _p(45, "PDF processado; gravando seções")
    elif fonte == "docx_upload":
        if not docx_bytes or not docx_filename:
            raise HTTPException(400, detail="Envie um arquivo DOCX.")
        nome_arquivo = Path(docx_filename).name.strip()
        if not nome_arquivo.lower().endswith(".docx"):
            raise HTTPException(400, detail="O arquivo enviado não é um DOCX.")
        if nome_arquivo.startswith("~$"):
            raise HTTPException(400, detail="Arquivo temporário do Word não é aceito.")
        if not docx_bytes:
            raise HTTPException(400, detail="Arquivo DOCX vazio.")
        _p(10, "Salvando DOCX enviado")
        try:
            PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
            destino = PASTA_RELATORIOS / nome_arquivo
            destino.write_bytes(docx_bytes)
        except OSError as exc:
            raise HTTPException(500, detail=f"Falha ao salvar DOCX: {exc}")
        _p(20, "Extraindo seções do DOCX")
        try:
            secoes_com_conteudo = extrair_relatorio_docx(docx_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, detail=f"Falha ao ler o DOCX: {exc}")
        if not secoes_com_conteudo:
            raise HTTPException(400, detail="Não foi possível extrair conteúdo do DOCX enviado.")
        origem_blocos = "docx_import"
        _p(55, "DOCX processado; gravando seções")
    elif fonte == "upload":
        if not pdf_bytes or not pdf_filename:
            raise HTTPException(400, detail="Envie um arquivo PDF.")
        if not pdf_filename.lower().endswith(".pdf"):
            raise HTTPException(400, detail="O arquivo enviado não é um PDF.")
        if not pdf_bytes:
            raise HTTPException(400, detail="Arquivo PDF vazio.")
        _p(20, "Extraindo sumário do PDF")
        try:
            secoes_explicitas = extrair_sumario(pdf_bytes)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, detail=f"Falha ao ler o PDF: {exc}")
        if not secoes_explicitas:
            raise HTTPException(400, detail="Não foi possível extrair o sumário do PDF enviado.")
        _p(50, "PDF processado; gravando seções")
    else:
        raise HTTPException(400, detail="Selecione um relatório base, um relatório entregue ou envie um arquivo.")

    rel = Relatorio(
        codigo=codigo.strip(),
        titulo=titulo.strip(),
        mes_referencia=mes_referencia.strip(),
        periodo_inicio=dateparser.parse(periodo_inicio).date(),
        periodo_fim=dateparser.parse(periodo_fim).date(),
        numero_medicao=int(numero_medicao) if numero_medicao.strip() else None,
    )
    try:
        with tx_session() as txdb:
            txdb.add(rel)
            txdb.flush()
            rel_id_novo = rel.id
            if base_rel_id:
                from app.notificacoes.service import (
                    _clonar_estrutura_e_conteudo,
                    _substituir_referencias_periodo,
                )

                base = txdb.get(Relatorio, base_rel_id)
                if base:
                    _p(55, "Clonando seções e blocos")
                    _clonar_estrutura_e_conteudo(txdb, base, rel)
                    secoes = txdb.query(Secao).filter(Secao.relatorio_id == rel.id).all()
                    for sec in secoes:
                        sec.titulo = _substituir_referencias_periodo(sec.titulo, base, rel) or sec.titulo
                    txdb.commit()
                    _p(90, "Clonagem concluída")
            elif secoes_com_conteudo:
                from ..models import Figura

                _vistos_nums: set[str] = set()
                _secoes_unicas: list[dict] = []
                for _sd in secoes_com_conteudo:
                    _num = (_sd.get("secao_numero") or "").strip()
                    if not _num or _num in _vistos_nums or len(_num) > 16:
                        continue
                    _vistos_nums.add(_num)
                    _secoes_unicas.append(_sd)

                total = max(1, len(_secoes_unicas))
                pct_inicio = 60
                pct_fim = 92
                for ordem, sec_data in enumerate(_secoes_unicas, start=1):
                    nova_sec = Secao(
                        relatorio_id=rel_id_novo,
                        numero=sec_data["secao_numero"],
                        titulo=sec_data["secao_titulo"],
                        ordem=ordem,
                        responsavel_id=None,
                        status="pendente",
                    )
                    txdb.add(nova_sec)
                    txdb.flush()
                    for bloco_ordem, bloco_data in enumerate(sec_data.get("blocos", [])):
                        tipo = bloco_data.get("tipo", "texto")
                        fig_id = None
                        if tipo == "figura" and bloco_data.get("dados_imagem"):
                            fig = Figura(
                                relatorio_id=rel_id_novo,
                                nome=f"fig_{nova_sec.numero}_{bloco_ordem}",
                                mime=bloco_data.get("mime", "image/png"),
                                dados=bloco_data["dados_imagem"],
                            )
                            txdb.add(fig)
                            txdb.flush()
                            fig_id = fig.id
                        txdb.add(
                            Bloco(
                                secao_id=nova_sec.id,
                                tipo=tipo,
                                ordem=bloco_ordem,
                                conteudo=bloco_data.get("conteudo", ""),
                                figura_id=fig_id,
                                origem=origem_blocos,
                            )
                        )
                    pct = pct_inicio + int((pct_fim - pct_inicio) * ordem / total)
                    _p(pct, f"Gravando seção {ordem}/{total}")
            else:
                _p(70, "Criando seções padrão")
                criar_secoes_padrao(txdb, rel_id_novo, secoes_explicitas=secoes_explicitas)
    except (IntegrityError, DataError) as exc:
        raise HTTPException(400, detail=f"Erro ao gravar seções: {exc.orig}")

    _p(98, "Finalizando")
    return rel_id_novo


def _job_criar_relatorio(token: str, **kwargs: object) -> None:
    """Executa ``_criar_relatorio_core`` em thread, atualizando o job."""
    try:
        rel_id_novo = _criar_relatorio_core(token=token, **kwargs)  # type: ignore[arg-type]
        progress_jobs.set_done(token, f"/relatorios/{rel_id_novo}")
    except HTTPException as exc:
        progress_jobs.set_error(token, str(exc.detail))
    except Exception as exc:  # noqa: BLE001
        progress_jobs.set_error(token, f"Erro inesperado: {exc}")


@router.post("")
async def criar_relatorio(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
    request: Request,
    codigo: str = Form(...),
    titulo: str = Form(...),
    mes_referencia: str = Form(...),
    periodo_inicio: str = Form(...),
    periodo_fim: str = Form(...),
    numero_medicao: str = Form(""),
    fonte_secoes: str = Form("clone_relatorio"),
    pdf_disponivel: str = Form(""),
    docx_disponivel: str = Form(""),
    pdf_upload: "UploadFile | None" = File(None),
    docx_upload: "UploadFile | None" = File(None),
    base_relatorio_id: str = Form(""),
    db: Session = Depends(get_db),
):
    u, p = _admin_coord_ou_login(request, db)
    if p is not None:
        return p
    assert u is not None

    fonte = (fonte_secoes or "clone_relatorio").strip().lower()
    pdf_bytes: bytes | None = None
    pdf_filename: str | None = None
    if pdf_upload is not None and pdf_upload.filename:
        pdf_bytes = await pdf_upload.read()
        pdf_filename = pdf_upload.filename
    docx_bytes: bytes | None = None
    docx_filename: str | None = None
    if docx_upload is not None and docx_upload.filename:
        docx_bytes = await docx_upload.read()
        docx_filename = docx_upload.filename

    kwargs = dict(
        codigo=codigo,
        titulo=titulo,
        mes_referencia=mes_referencia,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        numero_medicao=numero_medicao,
        fonte=fonte,
        pdf_disponivel=pdf_disponivel,
        docx_disponivel=docx_disponivel,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
        docx_bytes=docx_bytes,
        docx_filename=docx_filename,
        base_relatorio_id=base_relatorio_id,
    )

    accept = (request.headers.get("accept") or "").lower()
    wants_json = "application/json" in accept
    if wants_json:
        token = progress_jobs.criar_job()
        progress_jobs.set_progress(token, 1, "Recebido")
        t = threading.Thread(
            target=_job_criar_relatorio,
            args=(token,),
            kwargs=kwargs,
            daemon=True,
        )
        t.start()
        return JSONResponse({"token": token}, status_code=202)

    try:
        rel_id_novo = _criar_relatorio_core(token=None, **kwargs)  # type: ignore[arg-type]
    except HTTPException:
        raise
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
def editar_relatorio(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
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
    sufixo = raw[match.end() :]
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
def duplicar_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):  # pylint: disable=too-many-locals
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
        db.query(Bloco).filter(Bloco.secao_id.in_(sec_ids_orig)).order_by(Bloco.ordem).all() if sec_ids_orig else []
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
    # Regra: Responsável só é obrigatório quando a seção (subárvore) já tem
    # algum bloco inserido/upado pelo autor — ou seja, algo cuja origem não
    # seja o clone/importação (DOCX/PDF).
    sec_ids_escopo = secao_ids_na_subarvore(sec.relatorio.secoes, sec.numero or "") if sec.relatorio else {sec.id}
    if not sec_ids_escopo:
        sec_ids_escopo = {sec.id}
    origens_clonadas = {"clonado", "docx_import", "pdf_import"}
    sec_tem_upload = (
        db.query(Bloco)
        .join(Secao, Secao.id == Bloco.secao_id)
        .filter(Secao.id.in_(sec_ids_escopo))
        .filter(~Bloco.origem.in_(origens_clonadas))
        .first()
        is not None
    )
    if not responsavel_id.strip():
        if sec_tem_upload:
            raise HTTPException(
                400,
                detail=(
                    "Selecione um responsável: esta seção já tem conteúdo "
                    "inserido pelo autor."
                ),
            )
        if user.role == "autor":
            raise HTTPException(403, detail="Autor só pode atribuir a si próprio.")
        # Admin/coord podem limpar o responsável enquanto a seção só tiver
        # conteúdo clonado.
        sec.responsavel_id = None
    else:
        try:
            rid = int(responsavel_id)
        except ValueError:
            raise HTTPException(400, detail="Responsável inválido.")
        if user.role == "autor":
            if rid != user.id:
                raise HTTPException(403, detail="Autor só pode atribuir a si próprio.")
            sec.responsavel_id = rid
        else:
            if user.role not in ("admin", "coordenador"):
                raise HTTPException(403)
            sec.responsavel_id = rid
    db.commit()
    if retorno == "upload":
        return response_conteudo_upload(request, db, rel_id, sec_id)
    return response_conteudo_upload(request, db, rel_id, sec_id)


@router.get("/{rel_id}/secoes/{sec_id}/status")
def status_secao_get(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Abrir ``/status`` no navegador não deve devolver 405; redireciona à página com o formulário."""
    u, p = _u_or_login(request, db)
    if p is not None:
        return p
    sec = db.get(Secao, sec_id)
    if not sec or sec.relatorio_id != rel_id:
        raise HTTPException(404)
    if u.role == "autor":
        if sec.responsavel_id is not None and sec.responsavel_id != u.id:
            raise HTTPException(403, detail="Sem permissão para alterar o status desta seção.")
        url = f"/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo"
    elif u.role in ("admin", "coordenador"):
        url = f"/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo"
    else:
        raise HTTPException(403)
    return RedirectResponse(url=url, status_code=303)


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
    return response_conteudo_upload(request, db, rel_id, sec_id)


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
    redir = _admin_coord_relatorio_mutavel(request, db, rel_id)
    if redir is not None:
        return redir
    numero = numero.strip()
    titulo = titulo.strip()
    if not numero or not titulo:
        raise HTTPException(400, detail="Informe número e título")
    if not RE_NUMERO_SECAO.match(numero):
        raise HTTPException(400, detail="Número de seção inválido (use apenas dígitos e pontos)")
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
    return response_conteudo_upload(request, db, rel_id, sec_id)
