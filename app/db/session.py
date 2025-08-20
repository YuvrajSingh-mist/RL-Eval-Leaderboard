from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.core.config import settings
from app.db.base import Base

engine = create_engine(settings.DATABASE_URL,pool_pre_ping=True,
    connect_args={"connect_timeout": 30})



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
    """Initialize database - create tables"""
    Base.metadata.create_all(bind=engine)