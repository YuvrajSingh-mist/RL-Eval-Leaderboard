from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Submission
from app.core.celery import evaluate_submission_task
from app.core.client import supabase_client
from app.core.config import settings
from app.core.metrics import (
    SUBMISSIONS_RECEIVED_TOTAL,
    SUBMISSIONS_UPLOAD_BYTES_TOTAL,
    SUBMISSIONS_VALIDATION_FAILURES_TOTAL,
)
import uuid
import logging
import io
import tarfile
import os

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/submit/")
async def submit_rl_script(
    # Backward-compat single file
    file: UploadFile | None = File(None),
    # New: multiple files support
    files: list[UploadFile] | None = File(None),
    main_file: str | None = Form(None),
    env_id: str = Form("CartPole-v1"),
    algorithm: str = Form("Custom"),
    user_id: str = Form("anonymous"),
    client_id: str | None = Form(None),
    db: Session = Depends(get_db)
):
    """
    Submit RL agent code.

    - If `files` provided: bundle as a tar archive and upload as <submission_id>.tar.
      Additional support files of any type are allowed, but at least one `.py` must be included.
      The chosen `main_file` (must be a `.py`) will be included as submission.py inside the archive.
    - Else if `file` provided: legacy single-script upload as <submission_id>.py.
    """
    # Create or accept a client-provided submission ID (UUID)
    try:
        if client_id:
            _ = uuid.UUID(client_id)
            submission_id = str(client_id)
        else:
            submission_id = str(uuid.uuid4())
    except Exception:
        logger.warning(f"Invalid client_id provided: {client_id}")
        raise HTTPException(400, "client_id must be a valid UUID")

    has_many = bool(files and len(files) > 0)
    has_one = bool(file is not None)
    if not has_many and not has_one:
        SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="no_file").inc()
        raise HTTPException(400, "Please upload at least one Python file")

    # Multi-file path
    if has_many:
        # Accept any file types but require at least one Python file among them
        safe_names = []
        for f in files:
            if not f.filename:
                logger.warning("Empty filename in upload")
                SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="empty_filename").inc()
                raise HTTPException(400, "Invalid file in upload")
            safe_names.append(os.path.basename(f.filename))
        if not any(name.lower().endswith('.py') for name in safe_names):
            SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="no_py").inc()
            raise HTTPException(400, "At least one Python (.py) file is required when uploading multiple files")

        # Choose main file
        chosen_main = None
        if main_file:
            cand = os.path.basename(main_file)
            if cand in safe_names:
                chosen_main = cand
            else:
                logger.warning(f"main_file not in uploaded files: {main_file}")
                raise HTTPException(400, "main_file must match one of the uploaded file names")
        else:
            # Explicitly require main_file when multiple files are uploaded
            SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="missing_main").inc()
            raise HTTPException(400, "main_file is required when uploading multiple files")
        if not chosen_main.lower().endswith('.py'):
            SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="main_not_py").inc()
            raise HTTPException(400, "main_file must be a Python (.py) file")

        # Build tar archive in-memory; include all files at root
        try:
            # Read all files exactly once and keep in-memory bytes
            file_bytes_map: dict[str, bytes] = {}
            total_bytes = 0
            now_ts = int(__import__("time").time())
            for f in files:
                content = await f.read()
                file_bytes_map[os.path.basename(f.filename)] = content
                try:
                    total_bytes += len(content) if content is not None else 0
                except Exception:
                    pass

            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                # Add uploaded files
                for name, content in file_bytes_map.items():
                    info = tarfile.TarInfo(name=name)
                    info.size = len(content)
                    info.mtime = now_ts
                    info.mode = 0o444
                    tar.addfile(info, io.BytesIO(content))
                # Add alias for main file as submission.py if needed
                if chosen_main != "submission.py":
                    mf_content = file_bytes_map.get(chosen_main)
                    if mf_content is None:
                        raise Exception(f"main_file {chosen_main} not found in upload set")
                    info = tarfile.TarInfo(name="submission.py")
                    info.size = len(mf_content)
                    info.mtime = now_ts
                    info.mode = 0o444
                    tar.addfile(info, io.BytesIO(mf_content))

            tar_stream.seek(0)
            result = supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
                f"{submission_id}.tar",
                tar_stream.getvalue(),
                file_options={"content-type": "application/x-tar", "upsert": "true"}
            )
            if hasattr(result, 'error') and result.error:
                raise Exception(str(result.error))
            logger.info(f"Uploaded {submission_id}.tar to Supabase (main={chosen_main})")
            SUBMISSIONS_RECEIVED_TOTAL.labels(mode="multi").inc()
            SUBMISSIONS_UPLOAD_BYTES_TOTAL.inc(total_bytes)
        except Exception as e:
            logger.error(f"Failed to upload tar to Supabase {submission_id}: {str(e)}")
            raise HTTPException(500, "Failed to save submission bundle")

    # Legacy single-file path
    else:
        if not file.filename.endswith(".py"):
            logger.warning(f"Invalid file type submitted: {file.filename}")
            SUBMISSIONS_VALIDATION_FAILURES_TOTAL.labels(reason="not_py").inc()
            raise HTTPException(400, "Only Python scripts allowed")
        try:
            content = await file.read()
            result = supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
                f"{submission_id}.py",
                content,
                file_options={"content-type": "text/plain", "upsert": "true"}
            )
            if hasattr(result, 'error') and result.error:
                raise Exception(str(result.error))
            logger.info(f"Uploaded {submission_id}.py to Supabase")
            SUBMISSIONS_RECEIVED_TOTAL.labels(mode="single").inc()
            try:
                SUBMISSIONS_UPLOAD_BYTES_TOTAL.inc(len(content) if content is not None else 0)
            except Exception:
                pass
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