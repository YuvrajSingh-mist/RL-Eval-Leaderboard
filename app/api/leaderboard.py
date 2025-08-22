
from fastapi import APIRouter, Query
from typing import Optional
from app.services.leaderboard import redis_leaderboard
from app.core.metrics import (
    LEADERBOARD_QUERIES_TOTAL,
    LEADERBOARD_QUERY_DURATION_SECONDS,
    ENVIRONMENTS_LIST_REQUESTS_TOTAL,
    ENVIRONMENTS_LIST_FAILURES_TOTAL,
    DurationTimer,
)
import logging
import gymnasium as gym

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/environments")
def list_environments():
    """List available Gymnasium environments. Best-effort; fallback to curated list."""
    ENVIRONMENTS_LIST_REQUESTS_TOTAL.inc()
    try:
        
        envs: list[str] = []
        registry = getattr(gym.envs, "registry", None)
        if registry and hasattr(registry, "items"):
            for _, spec in registry.items():
                try:
                    spec_id = getattr(spec, "id", None)
                    if isinstance(spec_id, str):
                        envs.append(spec_id)
                except Exception:
                    continue
        envs = sorted(set(envs))
        if len(envs) > 500:
            envs = [e for e in envs if any(k in e for k in ("CartPole", "LunarLander", "MountainCar", "Acrobot", "Pendulum", "FrozenLake"))]
        return {"envs": envs}
    except Exception as e:
        logger.exception("Environment discovery failed")
        ENVIRONMENTS_LIST_FAILURES_TOTAL.inc()
        return {"envs": [
            "CartPole-v1", "LunarLander-v2", "LunarLanderContinuous-v2",
            "MountainCar-v0", "Acrobot-v1", "Pendulum-v1", "FrozenLake-v1"
        ]}

@router.get("/")
@router.get("")
def get_leaderboard(
    env_id: str = Query("CartPole-v1", description="Gym environment ID"),
    limit: int = Query(50, ge=1, le=500, description="Number of results to return"),
    id_query: Optional[str] = Query(None, description="Filter by submission ID contains"),
    user: Optional[str] = Query(None, description="Filter by user contains"),
    algorithm: Optional[str] = Query(None, description="Filter by algorithm contains"),
    score_min: Optional[float] = Query(None, description="Minimum score inclusive"),
    score_max: Optional[float] = Query(None, description="Maximum score inclusive"),
    date_from: Optional[str] = Query(None, description="From date YYYY-MM-DD (inclusive)"),
    date_to: Optional[str] = Query(None, description="To date YYYY-MM-DD (inclusive)"),
    sort: str = Query("score_desc", description="Sort order: score_desc | date_desc | date_asc"),
):
    """
    Get leaderboard from Redis (real-time, sorted)
    Falls back to database if Redis fails
    """
    try:
        with DurationTimer() as t:
            # Get from Redis (primary source) with DB fallback handled inside
            leaderboard = redis_leaderboard.get_leaderboard(
                env_id=env_id,
                limit=limit,
                id_query=id_query,
                user=user,
                algorithm=algorithm,
                score_min=score_min,
                score_max=score_max,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
            )
            LEADERBOARD_QUERIES_TOTAL.labels(env_id=env_id, sort=sort).inc()
            LEADERBOARD_QUERY_DURATION_SECONDS.observe(t.seconds)
            logger.info(
                "leaderboard_query",
                extra={
                    "env_id": env_id,
                    "sort": sort,
                },
            )
            return leaderboard
    except Exception as e:
        logger.error(
            f"Leaderboard retrieval failed: {str(e)}",
            extra={"env_id": env_id, "sort": sort},
        )
        return []
