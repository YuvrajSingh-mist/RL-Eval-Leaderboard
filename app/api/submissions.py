from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Submission
from app.core.celery import evaluate_submission_task
from app.core.client import supabase_client
from app.core.config import settings
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/submit/")
async def submit_rl_script(
    file: UploadFile = File(...),
    env_id: str = Form("CartPole-v1"),
    algorithm: str = Form("Custom"),
    user_id: str = Form("anonymous"),
    client_id: str | None = Form(None),
    db: Session = Depends(get_db)
):
    # Validate file
    if not file.filename.endswith(".py"):
        logger.warning(f"Invalid file type submitted: {file.filename}")
        raise HTTPException(400, "Only Python scripts allowed")
    
    # Create or accept a client-provided submission ID (UUID)
    try:
        if client_id:
            # Validate UUID format
            _ = uuid.UUID(client_id)
            submission_id = str(client_id)
        else:
            submission_id = str(uuid.uuid4())
    except Exception:
        logger.warning(f"Invalid client_id provided: {client_id}")
        raise HTTPException(400, "client_id must be a valid UUID")
    
    try:
        # Upload to Supabase Storage
        content = await file.read()
        result = supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
            f"{submission_id}.py",
            content,
            file_options={"content-type": "text/plain", "upsert": "true"}
        )
        
        if hasattr(result, 'error') and result.error:
            raise Exception(f"Supabase upload failed: {result.error}")
            
        logger.info(f"Uploaded {submission_id}.py to Supabase")
        
    except Exception as e:
        logger.error(f"Failed to upload to Supabase {submission_id}: {str(e)}")
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