import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database configuration
    DATABASE_URL: str = "postgresql://leaderboard:securepassword123@db:5432/leaderboard"
    
    # Redis configuration
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Celery configuration
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    
    # Supabase configuration
    SUPABASE_URL: str = "https://ugruhveupflxhdfgkbvu.supabase.co"
    SUPABASE_ANON_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVncnVodmV1cGZseGhkZmdrYnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU3MDM3NDAsImV4cCI6MjA3MTI3OTc0MH0.d5hEy8nRnX0fv8fKj7xQPupLqrJVh2PKsjE41u62LZA"
    SUPABASE_SERVICE_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVncnVodmV1cGZseGhkZmdrYnZ1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTcwMzc0MCwiZXhwIjoyMDcxMjc5NzQwfQ.5UrsR8z9n0etAzr1SkHp5eRZFTcsE5NH0SxYMT0OhfQ"
    SUPABASE_BUCKET: str = "submissions"
    SUPABASE_PASSWORD: str = "omsairam786%"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecret")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Docker socket configuration
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"

    # Evaluator image
    EVALUATOR_IMAGE: str = "rl-evaluator:latest"

    class Config:
        env_file = ".env"

settings = Settings()
