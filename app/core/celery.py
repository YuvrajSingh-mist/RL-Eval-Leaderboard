from celery import Celery
from app.core.config import settings
import os
import logging
from app.core.metrics import start_worker_metrics_server, start_celery_queue_length_collector

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.services.evaluation"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=600,
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True
)

## Sentry removed; logs flow to Loki via Promtail


@celery_app.on_after_configure.connect
def setup_observability(sender, **kwargs):
    # Start metrics endpoint for worker
    try:
        start_worker_metrics_server()
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start worker metrics server: {str(e)}")
    # Queue length collector for Celery broker
    try:
        start_celery_queue_length_collector(
            os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
            queue_names=["celery"],
            interval_seconds=10,
        )
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start queue length collector: {str(e)}")

@celery_app.task(bind=True, max_retries=3)
def evaluate_submission_task(self, submission_id: str):
    """Celery task to evaluate a submission"""
    from app.services.evaluation import evaluate_submission
    try:
        return evaluate_submission(submission_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)