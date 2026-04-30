import re
from fastapi import APIRouter, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from starlette.responses import RedirectResponse, Response
from sqlalchemy.orm import Session, selectinload
from dateutil import parser as dateparser

from ..db import get_db, tx_session
from ..models import Bloco, Relatorio, Secao, User
from .blocos import _hook_recompute_entrega, _impacta_numeracao, _pode_editar_status, campos_json_bloco_transversal
from ..bootstrap import criar_secoes_padrao
from ..modo_edicao_blocos import definir_modo_edicao_coordenador
from ..numeracao import consolidar_referencias, renumerar_relatorio
from .. import ref_resolve
from ..sumario_extractor import (
    extrair_sumario,
    extrair_sumario_pdf_disponivel,
)

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


@router.post("")
async def criar_relatorio(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
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

    # 1) Decide a fonte das seções ANTES de gravar (para falhar cedo).
    secoes_explicitas: "list[tuple[str, str]] | None" = None
    fonte = (fonte_secoes or "pdf_disponivel").strip().lower()
    if fonte == "pdf_disponivel":
        nome = (pdf_disponivel or "").strip()
        if not nome:
            raise HTTPException(400, detail="Selecione o PDF disponível.")
        try:
            secoes_explicitas = extrair_sumario_pdf_disponivel(nome)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc))
        if not secoes_explicitas:
            raise HTTPException(400, detail=f"Não foi possível extrair o sumário de {nome}.")
    elif fonte == "upload":
        if pdf_upload is None or not pdf_upload.filename:
            raise HTTPException(400, detail="Envie um arquivo PDF.")
        if not pdf_upload.filename.lower().endswith(".pdf"):
            raise HTTPException(400, detail="O arquivo enviado não é um PDF.")
        dados = await pdf_upload.read()
        if not dados:
            raise HTTPException(400, detail="Arquivo PDF vazio.")
        try:
            secoes_explicitas = extrair_sumario(dados)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, detail=f"Falha ao ler o PDF: {exc}")
        if not secoes_explicitas:
            raise HTTPException(400, detail="Não foi possível extrair o sumário do PDF enviado.")
    else:
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
        txdb.add(rel)
        txdb.flush()
        rel_id_novo = rel.id
        criar_secoes_padrao(txdb, rel_id_novo, secoes_explicitas=secoes_explicitas)
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
            raise HTTPException(
                403, detail="Sem permissão para alterar o status desta seção."
            )
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
