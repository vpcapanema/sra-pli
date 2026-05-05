from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import cron_admin as cron_admin_service
from ..services.cron_admin import check_token

router = APIRouter(prefix="/admin/cron")


@router.post("/abrir-periodo")
def http_abrir_periodo(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _t: None = Depends(check_token),
):
    return cron_admin_service.http_abrir_periodo(force, db)


@router.post("/abrir-periodo-background")
def http_abrir_periodo_background(
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
    _t: None = Depends(check_token),
):
    return cron_admin_service.http_abrir_periodo_background(
        background_tasks, force
    )


@router.post("/notificar-autores-abertura")
def http_notificar_autores_abertura(
    relatorio_id: int = Query(...),
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _t: None = Depends(check_token),
):
    return cron_admin_service.http_notificar_autores_abertura(
        relatorio_id, force, db
    )


@router.post("/lembretes")
def http_lembretes(
    tipo: str = Query("lembrete"),
    relatorio_id: int | None = Query(None),
    ignorar_calendario: bool = Query(False),
    db: Session = Depends(get_db),
    _t: None = Depends(check_token),
):
    return cron_admin_service.http_lembretes(
        tipo, relatorio_id, ignorar_calendario, db
    )


@router.post("/retry")
def http_retry(
    db: Session = Depends(get_db),
    _t: None = Depends(check_token),
):
    return cron_admin_service.http_retry(db)
