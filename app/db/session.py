from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.core.config import settings
from app.db.base import Base

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 30} if settings.DATABASE_URL.startswith("postgresql://") else {}
)



# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Scoped session for thread safety
db_session = scoped_session(SessionLocal)

def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database - create tables.
    If DB is temporarily unreachable, skip creation to allow API to start and healthcheck to pass; other endpoints will fail until DB returns.
    """
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # Log happens via caller; avoid crashing startup
        import logging
        logging.getLogger(__name__).warning("init_db_create_all_failed", extra={"error": str(e)})