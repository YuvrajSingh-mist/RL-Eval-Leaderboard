
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True)
    env_id = Column(String, index=True)
    algorithm = Column(String, index=True)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    error = Column(String, nullable=True)

    # Relationship to metrics
    metrics = relationship("EvaluationMetric", back_populates="submission")

class EvaluationMetric(Base):
    __tablename__ = "metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(String, ForeignKey("submissions.id"))
    episode = Column(Integer)
    reward = Column(Float)
    
    # Relationship to submission
    submission = relationship("Submission", back_populates="metrics")


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"

    id = Column(String, primary_key=True, index=True)  # UUID
    submission_id = Column(String, index=True)
    user_id = Column(String, index=True)
    env_id = Column(String, index=True)
    algorithm = Column(String, index=True)
    score = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
