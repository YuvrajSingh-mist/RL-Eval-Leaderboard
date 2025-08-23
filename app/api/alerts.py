from fastapi import APIRouter, Request, Response
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/alertmanager/webhook")
async def alertmanager_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = None
    # Log receipt for observability
    try:
        logger.info("alertmanager_webhook_received", extra={"service": "api"})
    except Exception:
        pass
    return {"status": "ok"}


