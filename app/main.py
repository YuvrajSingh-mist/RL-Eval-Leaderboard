
from fastapi import FastAPI
from app.api import submissions, leaderboard
from app.db.session import init_db
from app.core.config import settings
from app.services import redis_leaderboard
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

app = FastAPI(
    title="RL Leaderboard",
    description="API for evaluating and ranking RL agents",
    version="1.0.0"
)

# Initialize database and Redis
@app.on_event("startup")
def startup_event():
    # Initialize database
    init_db()
    logger = logging.getLogger(__name__)
    logger.info("Database initialized successfully")
    
    # Initialize Redis leaderboard
    try:
        redis_leaderboard.connect()
        logger.info("Redis leaderboard connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        logger.info("Will use database fallback for leaderboard")

# Include API routes
app.include_router(submissions.router, prefix="/api", tags=["submissions"])
app.include_router(leaderboard.router, prefix="/api/leaderboard", tags=["leaderboard"])

@app.get("/health")
def health_check():
    """Health check endpoint"""
    import datetime
    return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}
