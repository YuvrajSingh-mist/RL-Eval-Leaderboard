
from fastapi import APIRouter, Request, Response, HTTPException
import logging
from app.core.config import settings
import time
import jwt
import uuid
import datetime as dt
import redis
from prometheus_client import Gauge, Counter

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis client for visitor metrics (DB 0)
_r = None
def _redis():
    global _r
    if _r is None:
        _r = redis.from_url(settings.REDIS_URL, socket_timeout=5, retry_on_timeout=True)
    return _r

# Prometheus gauges for uniques (single-process safe)
# Use same configuration as other metrics
import os
_is_mp = False  # bool(os.getenv("PROMETHEUS_MULTIPROC_DIR"))
_gauge_kwargs = {}  # {"multiprocess_mode": "max"} if _is_mp else {}

UNIQUE_VISITORS_TODAY = Gauge("unique_visitors_today", "Approx unique visitors today (JWT)", **_gauge_kwargs)
UNIQUE_VISITORS_7D = Gauge("unique_visitors_7d", "Approx unique visitors over last 7 days (JWT)", **_gauge_kwargs)
UNIQUE_VISITORS_ALLTIME = Gauge("unique_visitors_alltime", "All-time unique visitors (JWT)", **_gauge_kwargs)
UNIQUE_VISITORS_MONTH = Gauge("unique_visitors_month", "Unique visitors by month (JWT)", labelnames=("month",), **_gauge_kwargs)
# Gauge to track historical progression of all-time visitors with timestamp
UNIQUE_VISITORS_ALLTIME_HISTORY = Gauge("unique_visitors_alltime_history", "Historical progression of all-time unique visitors (JWT)", labelnames=("timestamp",), **_gauge_kwargs)

def _hll_key(d: dt.date) -> str:
    return f"hll:visitors:{d.isoformat()}"

def _hll_month_key(d: dt.date) -> str:
    return f"hll:visitors:month:{d.strftime('%Y-%m')}"

_HLL_ALLTIME_KEY = "hll:visitors:alltime"


def _issue_visitor_token(sub: str | None = None) -> str:
    now = int(time.time())
    exp = now + settings.VISITOR_JWT_TTL_DAYS * 86400
    payload = {
        "iss": settings.VISITOR_JWT_ISSUER,
        "aud": settings.VISITOR_JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "sub": sub or str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.VISITOR_JWT_SECRET, algorithm="HS256")


@router.get("/visitor/token")
def get_visitor_token(request: Request):
    # If a valid token is already present, return it; otherwise issue a new one
    token = request.cookies.get("visitor_token") or request.headers.get("X-Visitor-Token")
    if token:
        try:
            jwt.decode(
                token,
                settings.VISITOR_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.VISITOR_JWT_AUDIENCE,
                issuer=settings.VISITOR_JWT_ISSUER,
                options={"verify_exp": True},
            )
            return {"token": token}
        except Exception as e:
            logger.warning(
                "visitor_token_invalid",
                extra={"error": str(e)},
            )
    new_token = _issue_visitor_token()
    resp = Response(content=f"{{\"token\": \"{new_token}\"}}", media_type="application/json")
    # 30 days ~ 2592000 seconds
    resp.set_cookie(
        key="visitor_token",
        value=new_token,
        max_age=settings.VISITOR_JWT_TTL_DAYS * 86400,
        expires=settings.VISITOR_JWT_TTL_DAYS * 86400,
        path="/",
        secure=True,
        httponly=False,
        samesite="None",
    )
    return resp


@router.get("/visitor/pixel")
def visitor_pixel(request: Request):
    # Tiny 1x1 transparent PNG
    token = request.cookies.get("visitor_token") or request.headers.get("X-Visitor-Token")
    vid = None
    if token:
        try:
            payload = jwt.decode(
                token,
                settings.VISITOR_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.VISITOR_JWT_AUDIENCE,
                issuer=settings.VISITOR_JWT_ISSUER,
                options={"verify_exp": True},
            )
            vid = payload.get("sub")
        except Exception as e:
            logger.debug("visitor_pixel_jwt_decode_failed", extra={"error": str(e)})
            vid = None

    # Count unique visitors via Redis HyperLogLog per day
    try:
        if vid:
            today = dt.date.today()
            _redis().pfadd(_hll_key(today), vid)
            _redis().pfadd(_hll_month_key(today), vid)
            _redis().pfadd(_HLL_ALLTIME_KEY, vid)
            
            # Update historical metric immediately when visitor is tracked
            alltime_count = _redis().pfcount(_HLL_ALLTIME_KEY)
            current_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            UNIQUE_VISITORS_ALLTIME_HISTORY.labels(timestamp=current_time).set(float(alltime_count))
    except Exception as e:
        logger.exception(
            "visitor_hll_update_failed",
            extra={"visitor_id": vid, "error": str(e)},
        )

    # Minimal logging via application logger
    import logging
    logging.getLogger("visitor").info("visitor_pixel", extra={"visitor_id": vid})

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDAT\x08\x99c\x60\x00\x00\x00\x02\x00\x01E\xdd\x85\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    headers = {"Cache-Control": "no-store, max-age=0"}
    return Response(content=png_bytes, media_type="image/png", headers=headers)


@router.head("/visitor/pixel")
def visitor_pixel_head():
    # Allow HEAD requests to succeed for monitoring and curl -I
    return Response(status_code=200)



def refresh_unique_visitor_metrics() -> None:
    """Compute and set Prometheus gauges for uniques today and rolling 7d."""
    try:
        today = dt.date.today()
        keys7 = [_hll_key(today - dt.timedelta(days=i)) for i in range(7)]
        

        # Check if we need to clear old daily data (older than 7 days)
        for i in range(7, 30):  # Clear data older than 7 days
            old_date = today - dt.timedelta(days=i)
            old_key = _hll_key(old_date)
            if _redis().exists(old_key):
                _redis().delete(old_key)
                logger.debug(f"Cleared old daily visitor data for {old_date}")
        
        # Get counts from Redis
        today_count = _redis().pfcount(_hll_key(today))
        week_count = _redis().pfcount(*keys7)
        alltime_count = _redis().pfcount(_HLL_ALLTIME_KEY)
        
        # Set Prometheus metrics
        UNIQUE_VISITORS_TODAY.set(float(today_count))
        UNIQUE_VISITORS_7D.set(float(week_count))
        UNIQUE_VISITORS_ALLTIME.set(float(alltime_count))
        
        # Update historical gauge with current timestamp
        current_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        UNIQUE_VISITORS_ALLTIME_HISTORY.labels(timestamp=current_time).set(float(alltime_count))
        
        logger.info("visitor_metrics_refreshed", extra={
            "today_count": today_count,
            "week_count": week_count,
            "alltime_count": alltime_count
        })

        # Per-month for last 13 months (current + 12 back)
        m = today.replace(day=1)
        for _ in range(13):
            key = _hll_month_key(m)
            try:
                val = float(_redis().pfcount(key))
                UNIQUE_VISITORS_MONTH.labels(month=m.strftime('%Y-%m')).set(val)
            except Exception as e:
                logger.debug(
                    "visitor_month_metric_refresh_failed",
                    extra={"month": m.strftime('%Y-%m'), "error": str(e)},
                )
            # Step back one month
            m = (m - dt.timedelta(days=1)).replace(day=1)
    except Exception as e:
        # do not raise; metrics are best-effort
        logger.warning("visitor_metrics_refresh_failed", extra={"error": str(e)})

