from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure, task_retry
from app.core.config import settings
import os
import logging
from app.core.metrics import start_worker_metrics_server, start_celery_queue_length_collector
from app.core.logging_config import setup_logging

# Ensure structured JSON logging for the worker process
setup_logging()

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
    broker_connection_retry_on_startup=True,
    task_routes={
        # Default route for evaluate_submission_task (can be overridden by apply_async)
        "app.core.celery.evaluate_submission_task": {"queue": "celery"},
    },
)

## Sentry removed; logs flow to Loki via Promtail


@celery_app.on_after_configure.connect
def setup_observability(sender, **kwargs):
    logger = logging.getLogger(__name__)
    logger.info("Setting up observability for Celery worker")
    
    # Start metrics endpoint for worker
    try:
        logger.info("Starting worker metrics server...")
        start_worker_metrics_server()
        logger.info("Worker metrics server started successfully")
    except Exception as e:
        logger.error(f"Failed to start worker metrics server: {str(e)}")
    
    # Queue length collector for Celery broker
    try:
        logger.info("Starting queue length collector...")
        start_celery_queue_length_collector(
            os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
            queue_names=["celery", "heavy"],
            interval_seconds=10,
        )
        logger.info("Queue length collector started successfully")
    except Exception as e:
        logger.error(f"Failed to start queue length collector: {str(e)}")


# ---- Celery task lifecycle structured logs ----

@task_prerun.connect
def _on_task_start(task_id=None, task=None, args=None, kwargs=None, **extra_kwargs):
    try:
        logger = logging.getLogger("celery.task")
        submission_id = None
        if isinstance(args, (list, tuple)) and len(args) > 0 and isinstance(args[0], str):
            submission_id = args[0]
        if isinstance(kwargs, dict) and kwargs.get("submission_id"):
            submission_id = kwargs.get("submission_id")
        logger.info(
            "task_started",
            extra={
                "task_name": getattr(task, "name", None),
                "task_id": task_id,
                "submission_id": submission_id,
            },
        )
    except Exception as e:
        logging.getLogger(__name__).debug("celery_task_start_log_failed", extra={"error": str(e)})


@task_postrun.connect
def _on_task_success(task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extra_kwargs):
    try:
        logger = logging.getLogger("celery.task")
        submission_id = None
        if isinstance(args, (list, tuple)) and len(args) > 0 and isinstance(args[0], str):
            submission_id = args[0]
        if isinstance(kwargs, dict) and kwargs.get("submission_id"):
            submission_id = kwargs.get("submission_id")
        logger.info(
            "task_succeeded",
            extra={
                "task_name": getattr(task, "name", None),
                "task_id": task_id,
                "submission_id": submission_id,
            },
        )
    except Exception as e:
        logging.getLogger(__name__).debug("celery_task_success_log_failed", extra={"error": str(e)})


@task_failure.connect
def _on_task_failure(task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, sender=None, **extra_kwargs):
    try:
        logger = logging.getLogger("celery.task")
        submission_id = None
        if isinstance(args, (list, tuple)) and len(args) > 0 and isinstance(args[0], str):
            submission_id = args[0]
        if isinstance(kwargs, dict) and kwargs.get("submission_id"):
            submission_id = kwargs.get("submission_id")
        logger.error(
            f"task_failed: {str(exception)}",
            extra={
                "task_name": getattr(sender, "name", None),
                "task_id": task_id,
                "submission_id": submission_id,
            },
        )
    except Exception as e:
        logging.getLogger(__name__).debug("celery_task_failure_log_failed", extra={"error": str(e)})


@task_retry.connect
def _on_task_retry(request=None, reason=None, einfo=None, **extra_kwargs):
    try:
        logger = logging.getLogger("celery.task")
        logger.warning(
            f"task_retry: {str(reason)}",
            extra={
                "task_name": getattr(getattr(request, "task", None), "name", None),
                "task_id": getattr(request, "id", None),
                "submission_id": (getattr(request, "args", None) or [None])[0],
            },
        )
    except Exception as e:
        logging.getLogger(__name__).debug("celery_task_retry_log_failed", extra={"error": str(e)})

@celery_app.task(bind=True, max_retries=3)
def evaluate_submission_task(self, submission_id: str):
    """Celery task to evaluate a submission"""
    from app.services.evaluation import evaluate_submission
    from app.db.session import SessionLocal
    from app.models import Submission
    
    # Get user_id from submission for task metadata
    db = SessionLocal()
    try:
        submission = db.query(Submission).get(submission_id)
        if submission:
            # Update task metadata with name and submission details
            self.update_state(
                state='STARTED',
                meta={
                    'submission_id': submission_id,
                    'name': submission.user_id,  # user_id field stores the name
                    'env_id': submission.env_id,
                    'algorithm': submission.algorithm
                }
            )
    except Exception as e:
        logging.getLogger(__name__).debug(f"Failed to update task metadata: {str(e)}")
    finally:
        db.close()
    
    try:
        return evaluate_submission(submission_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)