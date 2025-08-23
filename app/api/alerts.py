from fastapi import APIRouter, Request, Response
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/alertmanager/webhook")
async def alertmanager_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        payload = None
        logger.debug("alert_webhook_json_parse_failed", extra={"error": str(e)})
    # Log receipt for observability
    try:
        logger.info("alertmanager_webhook_received", extra={"service": "api"})
    except Exception as e:
        logger.debug("alert_webhook_log_failed", extra={"error": str(e)})
    return {"status": "ok"}


