
from fastapi import APIRouter, Query
from app.services.leaderboard import redis_leaderboard
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
def get_leaderboard(
    env_id: str = Query("CartPole-v1", description="Gym environment ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
):
    """
    Get leaderboard from Redis (real-time, sorted)
    Falls back to database if Redis fails
    """
    try:
        # Get from Redis (primary source)
        leaderboard = redis_leaderboard.get_leaderboard(env_id, limit)
        
        if leaderboard:
            logger.info(f"Retrieved leaderboard from Redis for {env_id}")
            return leaderboard
        

        
    except Exception as e:
        logger.error(f"Redis leaderboard failed: {str(e)}")
        
