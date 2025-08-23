import logging
import os
from pythonjsonlogger import jsonlogger


class ContextDefaultsFilter(logging.Filter):
    """Ensure logs always include common context keys and a service name.

    This prevents missing-key issues and guarantees a consistent schema for Promtail/Loki.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        # Request/HTTP context
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "method"):
            record.method = "-"
        if not hasattr(record, "path"):
            record.path = "-"
        if not hasattr(record, "status_code"):
            record.status_code = 0
        if not hasattr(record, "duration_ms"):
            record.duration_ms = 0
        if not hasattr(record, "client"):
            record.client = "-"

        # Domain context (nullable/high-cardinality; keep for search, not labels)
        for key in (
            "submission_id",
            "env_id",
            "algorithm",
            "task_name",
            "task_id",
            "container_id",
            "stage",
            "user_id",
            "client_id",
            "visitor_id",
        ):
            if not hasattr(record, key):
                setattr(record, key, None)

        # Service name
        if not hasattr(record, "service"):
            record.service = self.service_name
        return True


def setup_logging() -> None:
    """Configure root logger to output structured JSON logs to stdout."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    service_name = os.getenv("SERVICE_NAME", "api")

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Structured JSON handler
    handler = logging.StreamHandler()
    fmt = (
        "%(asctime)s %(levelname)s %(name)s %(message)s "
        "request_id=%(request_id)s method=%(method)s path=%(path)s "
        "status_code=%(status_code)s duration_ms=%(duration_ms)s client=%(client)s "
        "service=%(service)s submission_id=%(submission_id)s env_id=%(env_id)s algorithm=%(algorithm)s "
        "task_name=%(task_name)s task_id=%(task_id)s container_id=%(container_id)s stage=%(stage)s visitor_id=%(visitor_id)s"
    )
    formatter = jsonlogger.JsonFormatter(
        fmt,
        rename_fields={
            "levelname": "level",
            "asctime": "time",
        },
    )
    handler.setFormatter(formatter)
    handler.addFilter(ContextDefaultsFilter(service_name))

    # Replace existing handlers to avoid duplicate logs and capture warnings
    root.handlers.clear()
    root.addHandler(handler)
    logging.captureWarnings(True)

    # Make common noisy libraries propagate into root JSON logs
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery"):
        try:
            lg = logging.getLogger(name)
            # Remove existing handlers to avoid duplicate non-JSON output
            try:
                lg.handlers.clear()
            except Exception:
                pass
            lg.propagate = True
        except Exception:
            pass


