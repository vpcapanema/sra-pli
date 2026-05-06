from fastapi import APIRouter, Request, Form, Depends, UploadFile, File

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import relatorios as relatorios_service

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


@router.get("/{rel_id}/blocos-confirmados.json")
def listar_blocos_confirmados_json(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorios_service.listar_blocos_confirmados_json(rel_id, request, db)


@router.post("/{rel_id}/blocos/excluir-todos-confirmados")
def excluir_todos_blocos_confirmados(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorios_service.excluir_todos_blocos_confirmados(rel_id, request, db)


@router.post("/{rel_id}/modo-edicao-blocos")
def post_modo_edicao_blocos(
    rel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    ativo: str = Form("0"),
):
    return relatorios_service.post_modo_edicao_blocos(rel_id, request, db, ativo)


@router.get("/novo/progresso/{token}")
async def progresso_criar_relatorio(token: str) -> JSONResponse:
    return await relatorios_service.progresso_criar_relatorio(token)


@router.post("")
async def criar_relatorio(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    return await relatorios_service.criar_relatorio(
        request,
        codigo,
        titulo,
        mes_referencia,
        periodo_inicio,
        periodo_fim,
        numero_medicao,
        fonte_secoes,
        pdf_disponivel,
        docx_disponivel,
        pdf_upload,
        docx_upload,
        base_relatorio_id,
        db,
    )


@router.post("/{rel_id}/status")
def alterar_status(
    rel_id: int,
    request: Request,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    return relatorios_service.alterar_status(rel_id, request, status, db)


@router.post("/{rel_id}/editar")
def editar_relatorio(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
    return relatorios_service.editar_relatorio(
        rel_id, request, codigo, titulo, mes_referencia, periodo_inicio, periodo_fim, numero_medicao, db
    )


@router.post("/{rel_id}/versao")
def nova_versao(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorios_service.nova_versao(rel_id, request, db)


@router.post("/{rel_id}/duplicar")
def duplicar_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorios_service.duplicar_relatorio(rel_id, request, db)


@router.post("/{rel_id}/reverter")
def reverter_relatorio(rel_id: int, request: Request, db: Session = Depends(get_db)):
    return relatorios_service.reverter_relatorio(rel_id, request, db)


@router.post("/{rel_id}/secoes/{sec_id}/responsavel")
def atribuir_responsavel(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    sec_id: int,
    request: Request,
    *,
    responsavel_id: str = Form(""),
    retorno: str = Form(""),
    db: Session = Depends(get_db),
):
    return relatorios_service.atribuir_responsavel(rel_id, sec_id, request, responsavel_id, retorno, db)


@router.get("/{rel_id}/secoes/{sec_id}/status")
def status_secao_get(
    rel_id: int,
    sec_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    return relatorios_service.status_secao_get(rel_id, sec_id, request, db)


@router.post("/{rel_id}/secoes/{sec_id}/status")
def status_secao(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rel_id: int,
    sec_id: int,
    request: Request,
    *,
    status: str = Form(...),
    retorno: str = Form(""),
    db: Session = Depends(get_db),
):
    return relatorios_service.status_secao(rel_id, sec_id, request, status, retorno, db)


@router.post("/{rel_id}/secoes")
def criar_subsecao(
    rel_id: int,
    request: Request,
    numero: str = Form(...),
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    return relatorios_service.criar_subsecao(rel_id, request, numero, titulo, db)


@router.post("/{rel_id}/secoes/{sec_id}/subsecao")
def criar_subsecao_filha(
    rel_id: int,
    sec_id: int,
    request: Request,
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    return relatorios_service.criar_subsecao_filha(rel_id, sec_id, request, titulo, db)


@router.post("/{rel_id}/secoes/{sec_id}/mover")
def mover_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    direcao: str = Form(...),
    db: Session = Depends(get_db),
):
    return relatorios_service.mover_secao(rel_id, sec_id, request, direcao, db)


@router.post("/{rel_id}/secoes/{sec_id}/renomear")
def renomear_secao(
    rel_id: int,
    sec_id: int,
    request: Request,
    titulo: str = Form(...),
    db: Session = Depends(get_db),
):
    return relatorios_service.renomear_secao(rel_id, sec_id, request, titulo, db)
