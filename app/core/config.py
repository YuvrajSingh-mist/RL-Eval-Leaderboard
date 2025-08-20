
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database configuration
    DATABASE_URL: str = "postgresql://leaderboard:securepassword123@db:5432/leaderboard"
    
    # Redis configuration - ENHANCED
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_LEADERBOARD_DB: int = 1  # Separate DB for leaderboard
    REDIS_TASKS_DB: int = 2       # Separate DB for tasks
    
    # Celery configuration
    CELERY_BROKER_URL: str = "redis://redis:6379/2"  # Tasks DB
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"  # Tasks DB
    
    # Docker configuration
    DOCKER_SOCKET: str = "unix://var/run/docker.sock"
    EVALUATOR_IMAGE: str = "rl-evaluator:latest"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
