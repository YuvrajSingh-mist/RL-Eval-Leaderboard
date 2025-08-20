
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Submission
from app.core.celery import evaluate_submission_task
import uuid
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/submit/")
async def submit_rl_script(
    file: UploadFile = File(...),
    env_id: str = "CartPole-v1",
    algorithm: str = "Custom",
    user_id: str = "anonymous",
    db: Session = Depends(get_db)
):
    # Validate file
    if not file.filename.endswith(".py"):
        logger.warning(f"Invalid file type submitted: {file.filename}")
        raise HTTPException(400, "Only Python scripts allowed")
    
    # Create secure submission ID
    submission_id = str(uuid.uuid4())
    file_path = f"./submissions/{submission_id}.py"
    
    # Save to secure location
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        logger.error(f"Failed to save submission {submission_id}: {str(e)}")
        raise HTTPException(500, "Failed to save submission")
    
    # Create DB record
    try:
        submission = Submission(
            id=submission_id,
            user_id=user_id,
            env_id=env_id,
            algorithm=algorithm,
            status="pending"
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)
    except Exception as e:
        logger.error(f"Database error creating submission {submission_id}: {str(e)}")
        raise HTTPException(500, "Failed to create submission record")
    
    # Queue async evaluation
    logger.info(f"Queuing evaluation for submission {submission_id}")
    evaluate_submission_task.delay(submission_id)
    
    return {
        "id": submission_id,
        "status": "queued",
        "env_id": env_id,
        "algorithm": algorithm
    }

@router.get("/results/{submission_id}")
def get_evaluation_results(submission_id: str, db: Session = Depends(get_db)):
    submission = db.query(Submission).get(submission_id)
    if not submission:
        logger.warning(f"Submission not found: {submission_id}")
        raise HTTPException(404, "Submission not found")
    
    return {
        "id": submission.id,
        "status": submission.status,
        "score": submission.score,
        "env_id": submission.env_id,
        "algorithm": submission.algorithm,
        "created_at": submission.created_at.isoformat() if submission.created_at else None,
        "error": submission.error
    }