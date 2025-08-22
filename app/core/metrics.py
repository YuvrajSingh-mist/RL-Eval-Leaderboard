import os
import time
import logging
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, start_http_server
from threading import Thread, Event
import redis as redis_lib


# ----------
# Core metrics
# ----------

# Submissions
SUBMISSIONS_RECEIVED_TOTAL = Counter(
    "submissions_received_total",
    "Total RL submissions received",
    labelnames=("mode",),  # single | multi
)

SUBMISSIONS_VALIDATION_FAILURES_TOTAL = Counter(
    "submissions_validation_failures_total",
    "Submission validation failures",
    labelnames=("reason",),
)

SUBMISSIONS_UPLOAD_BYTES_TOTAL = Counter(
    "submissions_upload_bytes_total",
    "Total bytes uploaded for submissions",
)


# Evaluations
EVALUATION_STARTED_TOTAL = Counter(
    "evaluation_started_total",
    "Total evaluations started",
)

EVALUATION_COMPLETED_TOTAL = Counter(
    "evaluation_completed_total",
    "Total evaluations completed",
    labelnames=("env_id",),
)

EVALUATION_FAILED_TOTAL = Counter(
    "evaluation_failed_total",
    "Total evaluations failed",
    labelnames=("reason",),
)

EVALUATION_DURATION_SECONDS = Histogram(
    "evaluation_duration_seconds",
    "Time spent evaluating a submission",
    labelnames=("env_id",),
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)


# Leaderboard/API queries
LEADERBOARD_QUERIES_TOTAL = Counter(
    "leaderboard_queries_total",
    "Total leaderboard queries",
    labelnames=("env_id", "sort"),
)

LEADERBOARD_QUERY_DURATION_SECONDS = Histogram(
    "leaderboard_query_duration_seconds",
    "Duration of leaderboard retrieval (including Redis/DB)",
)

# Celery queue backlog
CELERY_QUEUE_LENGTH = Gauge(
    "celery_queue_length",
    "Length of Celery broker queue in Redis",
    labelnames=("queue_name",),
)


def init_fastapi_instrumentation(app) -> None:
    """Attach Prometheus instrumentation and expose /metrics.

    Imported lazily so worker processes don't need FastAPI instrumentator.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
    except Exception as e:
        logging.getLogger(__name__).error(f"Prometheus FastAPI Instrumentator not available: {e}")
        return
    instrumentator = Instrumentator()
    instrumentator.instrument(app)
    instrumentator.expose(app, include_in_schema=False)


def start_worker_metrics_server(port: Optional[int] = None) -> None:
    """Start a Prometheus metrics HTTP server for the worker process.

    For multi-process Celery setups, prefer using the multiprocess mode of
    prometheus_client. This simplified server works best for single-process
    workers (e.g., --concurrency=1) to avoid port conflicts.
    """
    p = int(port or os.getenv("WORKER_METRICS_PORT", "9100"))
    try:
        start_http_server(p)
    except OSError:
        # Port already in use; ignore to prevent crash in forked workers
        pass


def start_celery_queue_length_collector(
    redis_url: Optional[str],
    queue_names: Optional[list[str]] = None,
    interval_seconds: int = 10,
):
    """Periodically collect Redis LLEN for Celery queues and export as a gauge.

    Returns a stop_event that can be set() to stop the collector.
    """
    queue_names = queue_names or ["celery"]
    stop_event: Event = Event()

    def _run():
        client = None
        while not stop_event.is_set():
            try:
                if client is None and redis_url:
                    client = redis_lib.from_url(redis_url, socket_timeout=5)
                for q in queue_names:
                    try:
                        llen = client.llen(q) if client is not None else 0
                        CELERY_QUEUE_LENGTH.labels(queue_name=q).set(float(llen))
                    except Exception:
                        # Keep going for other queues
                        pass
            except Exception:
                client = None
            finally:
                stop_event.wait(interval_seconds)

    t = Thread(target=_run, daemon=True)
    t.start()
    return stop_event


class DurationTimer:
    """Simple context manager to measure durations with perf_counter."""

    def __init__(self):
        self._start = 0.0
        self.seconds = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.seconds = max(0.0, time.perf_counter() - self._start)
        return False


