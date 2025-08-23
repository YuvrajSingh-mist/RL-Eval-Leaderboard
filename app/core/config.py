import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database configuration
    # Use env-provided DATABASE_URL. No hardcoded credentials.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Celery configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

    # Supabase configuration (all from env)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    SUPABASE_BUCKET: str = os.getenv("SUPABASE_BUCKET", "submissions")

    # Security (removed SECRET_KEY; not used)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Docker socket configuration
    DOCKER_SOCKET: str = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")

    # Evaluator image
    EVALUATOR_IMAGE: str = os.getenv("EVALUATOR_IMAGE", "rl-evaluator:latest")

    # Visitor JWT settings
    VISITOR_JWT_SECRET: str = os.getenv("VISITOR_JWT_SECRET", "change-me-visitors")
    VISITOR_JWT_ISSUER: str = os.getenv("VISITOR_JWT_ISSUER", "simple-rl")
    VISITOR_JWT_AUDIENCE: str = os.getenv("VISITOR_JWT_AUDIENCE", "visitor")
    VISITOR_JWT_TTL_DAYS: int = int(os.getenv("VISITOR_JWT_TTL_DAYS", "30"))

    class Config:
        # Let BaseSettings read from project .env if present (local dev).
        env_file = ".env"


settings = Settings()
