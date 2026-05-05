from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import sendgrid_events as sendgrid_events_service
from ..services.sendgrid_events import check_sendgrid_token

router = APIRouter(prefix="/admin/sendgrid", tags=["sendgrid"])


@router.post("/events")
async def sendgrid_events(
    request: Request,
    db: Session = Depends(get_db),
    _token: None = Depends(check_sendgrid_token),
):
    return await sendgrid_events_service.sendgrid_events(request, db)
