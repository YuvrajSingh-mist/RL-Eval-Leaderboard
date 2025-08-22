import logging
import os
from pythonjsonlogger import jsonlogger


def setup_logging() -> None:
    """Configure root logger to output structured JSON logs to stdout."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    fmt = (
        "%(asctime)s %(levelname)s %(name)s %(message)s "
        "request_id=%(request_id)s method=%(method)s path=%(path)s "
        "status_code=%(status_code)s duration_ms=%(duration_ms)s client=%(client)s"
    )
    formatter = jsonlogger.JsonFormatter(fmt)
    handler.setFormatter(formatter)

    # Replace existing handlers to avoid duplicate logs
    root.handlers.clear()
    root.addHandler(handler)


