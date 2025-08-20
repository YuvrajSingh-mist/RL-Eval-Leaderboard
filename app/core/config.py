import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database configuration
    DATABASE_URL: str = "postgresql://leaderboard:securepassword123@db:5432/leaderboard"
    
    # Redis configuration
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Celery configuration - USING DB 1 FOR TASKS
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    
    # Docker configuration
    EVALUATOR_IMAGE: str = "rl-evaluator:latest"
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
