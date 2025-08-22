
from fastapi import FastAPI
from fastapi import Request
from app.api import submissions, leaderboard
from app.db.session import init_db
from app.core.config import settings
from app.services.leaderboard import redis_leaderboard
from app.core.metrics import init_fastapi_instrumentation
from app.core.logging_config import setup_logging
import logging
import os

# Configure logging (JSON)
setup_logging()

app = FastAPI(
    title="RL Leaderboard",
    description="API for evaluating and ranking RL agents",
    version="1.0.0"
)

## Sentry removed; using Loki/Promtail for logs


# Expose Prometheus /metrics immediately (not only on startup)
try:
    init_fastapi_instrumentation(app)
except Exception as _e:
    logging.getLogger(__name__).error(f"Prometheus metrics init failed: {_e}")


# Initialize database, Redis, and metrics
@app.on_event("startup")
def startup_event():
    # Initialize database
    init_db()
    logger = logging.getLogger(__name__)
    logger.info("Database initialized successfully")
    
    # Logs: Structured JSON to stdout, collected by Promtail -> Loki

    # Prometheus /metrics already exposed at import time

    # Initialize Redis leaderboard
    try:
        redis_leaderboard.connect()
        logger.info("Redis leaderboard connected successfully")
        # Backfill persistent entries and warm Redis
        redis_leaderboard.sync_from_submissions()
        redis_leaderboard.warm_redis_from_db()
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        logger.info("Will use database fallback for leaderboard")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    import time
    from uuid import uuid4
    logger = logging.getLogger("request")
    start = time.perf_counter()
    request_id = str(uuid4())
    client = request.client.host if request.client else "-"
    try:
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": getattr(response, "status_code", 0),
            "duration_ms": duration_ms,
            "client": client,
        }
        logger.info("request_completed", extra=extra)
        return response
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "duration_ms": duration_ms,
            "client": client,
        }
        logger.exception("request_failed", extra=extra)
        raise

# Include API routes
app.include_router(submissions.router, prefix="/api", tags=["submissions"])
app.include_router(leaderboard.router, prefix="/api/leaderboard", tags=["leaderboard"])

@app.get("/health")
def health_check():
    """Health check endpoint"""
    import datetime
    return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}
