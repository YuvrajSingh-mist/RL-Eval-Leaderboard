import os
import time
import logging
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, start_http_server
from threading import Thread, Event
import redis as redis_lib

# Simple metrics configuration (no multiprocess)
_is_mp = False
_gauge_kwargs = {}

# Ensure Prometheus multiprocess directory exists if needed
mp_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
if mp_dir:
    try:
        os.makedirs(mp_dir, exist_ok=True)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to create Prometheus multiprocess directory {mp_dir}: {e}")


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
    **_gauge_kwargs,
)

# System health metrics
DATABASE_HEALTH = Gauge(
    "database_health",
    "Database connection health status (1=healthy, 0=unhealthy)",
    **_gauge_kwargs,
)

REDIS_HEALTH = Gauge(
    "redis_health",
    "Redis connection health status (1=healthy, 0=unhealthy)",
    **_gauge_kwargs,
)

CELERY_WORKER_HEALTH = Gauge(
    "celery_worker_health",
    "Celery worker health status (1=healthy, 0=unhealthy)",
    **_gauge_kwargs,
)

CELERY_WORKER_COUNT = Gauge(
    "celery_worker_count",
    "Number of active Celery workers",
    labelnames=("queue",),
    **_gauge_kwargs,
)

CELERY_ACTIVE_TASKS = Gauge(
    "celery_active_tasks",
    "Number of active tasks across all workers",
    **_gauge_kwargs,
)

CELERY_RESERVED_TASKS = Gauge(
    "celery_reserved_tasks",
    "Number of reserved tasks across all workers",
    **_gauge_kwargs,
)

SUPABASE_STORAGE_HEALTH = Gauge(
    "supabase_storage_health",
    "Supabase storage health status (1=healthy, 0=unhealthy)",
    **_gauge_kwargs,
)

OVERALL_SYSTEM_HEALTH = Gauge(
    "overall_system_health",
    "Overall system health status (1=healthy, 0=unhealthy)",
    **_gauge_kwargs,
)

# Set initial values for health metrics so they appear in Prometheus
DATABASE_HEALTH.set(0)  # Start as unhealthy until checked
REDIS_HEALTH.set(0)  # Start as unhealthy until checked
CELERY_WORKER_HEALTH.set(0)  # Start as unhealthy until checked
SUPABASE_STORAGE_HEALTH.set(0)  # Start as unhealthy until checked
OVERALL_SYSTEM_HEALTH.set(0)  # Start as unhealthy until checked


def check_database_health():
    """Check database health and update metrics"""
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        DATABASE_HEALTH.set(1)  # Healthy
        return True
    except Exception as e:
        DATABASE_HEALTH.set(0)  # Unhealthy
        logging.getLogger(__name__).error(f"Database health check failed: {str(e)}")
        return False


def check_redis_health():
    """Check Redis health and update metrics"""
    try:
        import redis
        from app.core.config import settings
        r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        REDIS_HEALTH.set(1)  # Healthy
        return True
    except Exception as e:
        REDIS_HEALTH.set(0)  # Unhealthy
        logging.getLogger(__name__).error(f"Redis health check failed: {str(e)}")
        return False


def check_celery_worker_health():
    """Check Celery worker health and update metrics"""
    try:
        from app.core.celery import celery_app
        
        # Check 1: Basic ping with longer timeout
        pongs = celery_app.control.ping(timeout=5.0)
        if not isinstance(pongs, list) or len(pongs) == 0:
            CELERY_WORKER_HEALTH.set(0)  # Unhealthy
            logging.getLogger(__name__).error("No Celery workers responding to ping")
            return False
        
        # Check 2: Get active workers and their stats
        stats = celery_app.control.inspect().stats()
        if not stats:
            CELERY_WORKER_HEALTH.set(0)  # Unhealthy
            logging.getLogger(__name__).error("No Celery worker stats available")
            return False
        
        # Check 3: Get active tasks to see if workers are processing
        active = celery_app.control.inspect().active()
        if active is None:
            CELERY_WORKER_HEALTH.set(0)  # Unhealthy
            logging.getLogger(__name__).error("Cannot get active tasks from workers")
            return False
        
        # Check 4: Get reserved tasks (tasks that have been received but not yet executed)
        reserved = celery_app.control.inspect().reserved()
        if reserved is None:
            CELERY_WORKER_HEALTH.set(0)  # Unhealthy
            logging.getLogger(__name__).error("Cannot get reserved tasks from workers")
            return False
        
        # Log worker status for debugging
        worker_count = len(stats)
        total_active = sum(len(tasks) for tasks in (active.values() if active else []))
        total_reserved = sum(len(tasks) for tasks in (reserved.values() if reserved else []))
        
        # Update metrics - track workers by queue
        # Reset all queue worker counts first
        CELERY_WORKER_COUNT.labels(queue="celery").set(0)
        CELERY_WORKER_COUNT.labels(queue="heavy").set(0)
        
        # Get active queues for each worker to properly categorize them
        active_queues = celery_app.control.inspect().active_queues()
        if active_queues is None:
            active_queues = {}
        
        # Count workers by queue based on their actual queue configuration
        celery_workers = 0
        heavy_workers = 0
        
        for worker_name, worker_stats in stats.items():
            worker_queues = active_queues.get(worker_name, [])
            queue_names = [q.get('name', '') for q in worker_queues]
            
            # Check if worker can handle heavy queue
            if 'heavy' in queue_names:
                heavy_workers += 1
            if 'celery' in queue_names:
                celery_workers += 1
        
        CELERY_WORKER_COUNT.labels(queue="celery").set(celery_workers)
        CELERY_WORKER_COUNT.labels(queue="heavy").set(heavy_workers)
        CELERY_ACTIVE_TASKS.set(total_active)
        CELERY_RESERVED_TASKS.set(total_reserved)
        
        logging.getLogger(__name__).info(
            f"Celery workers healthy: {worker_count} workers, {total_active} active tasks, {total_reserved} reserved tasks"
        )
        
        CELERY_WORKER_HEALTH.set(1)  # Healthy
        return True
        
    except Exception as e:
        CELERY_WORKER_HEALTH.set(0)  # Unhealthy
        logging.getLogger(__name__).error(f"Celery worker health check failed: {str(e)}")
        return False


def check_supabase_storage_health():
    """Check Supabase storage health and update metrics"""
    try:
        from app.core.client import supabase_client
        from app.core.config import settings
        bucket = settings.SUPABASE_BUCKET
        try:
            supabase_client.storage.from_(bucket).list(path="", limit=1)
        except TypeError:
            supabase_client.storage.from_(bucket).list()
        SUPABASE_STORAGE_HEALTH.set(1)  # Healthy
        return True
    except Exception as e:
        SUPABASE_STORAGE_HEALTH.set(0)  # Unhealthy
        logging.getLogger(__name__).error(f"Supabase storage health check failed: {str(e)}")
        return False


def check_overall_system_health():
    """Check all system components and update overall health"""
    db_ok = check_database_health()
    redis_ok = check_redis_health()
    celery_ok = check_celery_worker_health()
    storage_ok = check_supabase_storage_health()
    
    overall_healthy = all([db_ok, redis_ok, celery_ok, storage_ok])
    OVERALL_SYSTEM_HEALTH.set(1 if overall_healthy else 0)
    
    return {
        "database": db_ok,
        "redis": redis_ok,
        "celery_workers": celery_ok,
        "storage": storage_ok,
        "overall": overall_healthy
    }


# Environment listing
ENVIRONMENTS_LIST_REQUESTS_TOTAL = Counter(
    "environments_list_requests_total",
    "Total /environments requests",
)

ENVIRONMENTS_LIST_FAILURES_TOTAL = Counter(
    "environments_list_failures_total",
    "Failures during environment list discovery",
)


def init_fastapi_instrumentation(app) -> None:
    """Attach Prometheus instrumentation and expose /metrics.

    Imported lazily so worker processes don't need FastAPI instrumentator.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
        from prometheus_client import CollectorRegistry, multiprocess, REGISTRY
    except Exception as e:
        logging.getLogger(__name__).warning("fastapi_instrumentator_unavailable", extra={"error": str(e)})
        return
    
    # Check if we're in multiprocess mode
    mp_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if mp_dir:
        # Use multiprocess collector
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        instrumentator = Instrumentator(registry=registry)
    else:
        # Use the default registry that includes our custom metrics
        instrumentator = Instrumentator(registry=REGISTRY)
    
    instrumentator.instrument(app)
    # Don't expose the instrumentator's /metrics endpoint - we'll create our own
    # instrumentator.expose(app, include_in_schema=False)


def start_worker_metrics_server(port: Optional[int] = None) -> None:
    """Start a Prometheus metrics HTTP server for the worker process.

    Supports both single-process and multiprocess (prefork) Celery workers.
    When PROMETHEUS_MULTIPROC_DIR is set, we expose a registry backed by
    prometheus_client.multiprocess.MultiProcessCollector so that counters
    aggregated from child processes are visible to Prometheus.
    """    
    logger = logging.getLogger(__name__)
    p = int(port or os.getenv("WORKER_METRICS_PORT", "9101"))
    logger.info(f"Starting worker metrics server on port {p}")
    
    try:
        mp_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
        logger.info(f"PROMETHEUS_MULTIPROC_DIR: {mp_dir}")
        
        if mp_dir:
            try:
                # Ensure directory exists and clean stale files on startup
                os.makedirs(mp_dir, exist_ok=True)
                logger.info(f"Created/verified multiprocess directory: {mp_dir}")
                
                for fname in os.listdir(mp_dir):
                    if fname.endswith(".db"):
                        try:
                            os.remove(os.path.join(mp_dir, fname))
                            logger.info(f"Cleaned up stale file: {fname}")
                        except Exception as e:
                            logger.debug("mp_dir_cleanup_failed", extra={"file": fname, "error": str(e)})
            except Exception as e:
                # best effort; do not crash worker
                logger.debug("mp_dir_prepare_failed", extra={"error": str(e)})

            # Build a dedicated multiprocess registry
            from prometheus_client import CollectorRegistry, multiprocess

            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            logger.info(f"Starting multiprocess HTTP server on 0.0.0.0:{p}")
            start_http_server(p, addr='0.0.0.0', registry=registry)
            logger.info("Multiprocess HTTP server started successfully")
        else:
            logger.info(f"Starting single-process HTTP server on 0.0.0.0:{p}")
            start_http_server(p, addr='0.0.0.0')
            logger.info("Single-process HTTP server started successfully")
    except OSError as e:
        # Port already in use; ignore to prevent crash in forked workers
        logger.error(f"Failed to start worker metrics server on port {p}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error starting worker metrics server: {str(e)}")


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
                    except Exception as e:
                        # Keep going for other queues
                        logging.getLogger(__name__).debug("queue_length_collect_failed", extra={"queue": q, "error": str(e)})
            except Exception as e:
                client = None
                logging.getLogger(__name__).debug("queue_length_loop_error", extra={"error": str(e)})
            finally:
                stop_event.wait(interval_seconds)

    t = Thread(target=_run, daemon=True)
    t.start()
    return stop_event


def start_health_metrics_collector(interval_seconds: int = 30):
    """Periodically collect health metrics and export as gauges.

    Returns a stop_event that can be set() to stop the collector.
    """
    stop_event: Event = Event()

    def _run():
        while not stop_event.is_set():
            try:
                # Update all health metrics
                check_overall_system_health()
                logging.getLogger(__name__).debug("Health metrics updated successfully")
            except Exception as e:
                logging.getLogger(__name__).error(f"Health metrics collection failed: {str(e)}")
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


