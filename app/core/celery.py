from celery import Celery
from app.core.config import settings

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

@celery_app.task(bind=True, max_retries=3)
def evaluate_submission_task(self, submission_id: str):
    """Celery task to evaluate a submission"""
    from app.services.evaluation import evaluate_submission
    try:
        return evaluate_submission(submission_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)