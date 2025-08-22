
import logging
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models import Submission
from app.core.docker import run_evaluation_container
from app.core.config import settings
from app.services.leaderboard import redis_leaderboard
from app.core.metrics import (
    EVALUATION_STARTED_TOTAL,
    EVALUATION_COMPLETED_TOTAL,
    EVALUATION_FAILED_TOTAL,
    EVALUATION_DURATION_SECONDS,
    DurationTimer,
)
from app.core.client import supabase_client

logger = logging.getLogger(__name__)

def _cleanup_submission_artifacts(submission_id: str) -> None:
    """Best-effort removal of uploaded artifacts from Supabase storage.

    Removes both <id>.tar and <id>.py if present. Errors are logged and ignored.
    """
    try:
        bucket = settings.SUPABASE_BUCKET
        # Supabase Python client expects a list of paths
        paths = [f"{submission_id}.tar", f"{submission_id}.py"]
        try:
            supabase_client.storage.from_(bucket).remove(paths)
        except Exception as e:
            # Some SDK versions return an object with .error; to be tolerant, log and continue
            logger.info(
                f"Supabase remove returned error for {submission_id}: {str(e)}",
                extra={"submission_id": submission_id},
            )
        logger.info(
            f"Cleaned up Supabase artifacts for {submission_id}",
            extra={"submission_id": submission_id},
        )
    except Exception as e:
        logger.warning(
            f"Supabase artifact cleanup failed for {submission_id}: {str(e)}",
            extra={"submission_id": submission_id},
        )

def evaluate_submission(submission_id: str) -> dict:
    """
    Evaluate a submission by running it in a secure container
    """
    db = SessionLocal()
    
    try:
        # Get submission
        submission = db.query(Submission).get(submission_id)
        if not submission:
            logger.error(f"Submission {submission_id} not found in database")
            return {"status": "error", "message": "Submission not found"}
        
        # Update status to processing
        submission.status = "processing"
        db.commit()
        logger.info(
            f"Started evaluation for submission {submission_id}",
            extra={
                "submission_id": submission_id,
                "env_id": submission.env_id,
                "algorithm": submission.algorithm,
            },
        )
        
        # Run in isolated container
        EVALUATION_STARTED_TOTAL.inc()
        with DurationTimer() as timer:
            result = run_evaluation_container(
                submission_id=submission_id,
                env_id=submission.env_id
            )
        
        # Process results
        parsed_output = result.get("output", {}) if isinstance(result, dict) else {}
        is_success = (result.get("status") == 0) and isinstance(parsed_output, dict) and ("score" in parsed_output)

        if is_success:
            # Successful evaluation
            submission.score = parsed_output["score"]
            submission.status = "completed"

            # Detailed per-episode metrics removed

            logger.info(
                f"Evaluation completed for {submission_id}. Score: {submission.score}",
                extra={
                    "submission_id": submission_id,
                    "env_id": submission.env_id,
                    "algorithm": submission.algorithm,
                },
            )
            db.commit()
            try:
                EVALUATION_COMPLETED_TOTAL.labels(env_id=submission.env_id).inc()
                EVALUATION_DURATION_SECONDS.labels(env_id=submission.env_id).observe(timer.seconds)
            except Exception:
                pass
            # Push to Redis leaderboard for immediate visibility
            try:
                redis_leaderboard.add_submission(submission)
            except Exception as e:
                logger.error(
                    f"Failed to update Redis leaderboard for {submission_id}: {str(e)}",
                    extra={
                        "submission_id": submission_id,
                        "env_id": submission.env_id,
                        "algorithm": submission.algorithm,
                    },
                )
            return {"status": "completed", "score": submission.score}

        # Evaluation failed
        error_msg = result.get("error") if isinstance(result, dict) else None
        if not error_msg:
            # Provide actionable message when JSON/score missing
            error_msg = "No 'score' found in script output or evaluator exited non-zero. Ensure your script prints a single JSON line with a 'score' field."

        # Attach a short tail of logs for debugging
        logs_tail = (result.get("logs", "")[-500:] if isinstance(result, dict) else "")
        if logs_tail:
            error_msg = f"{error_msg} | logs_tail=\n{logs_tail}"

        submission.status = "failed"
        submission.error = error_msg[:2000]
        logger.error(
            f"Evaluation failed for {submission_id}: {error_msg}",
            extra={
                "submission_id": submission_id,
                "env_id": submission.env_id if 'submission' in locals() and submission else None,
                "algorithm": submission.algorithm if 'submission' in locals() and submission else None,
            },
        )

        # Commit final status
        db.commit()
        try:
            EVALUATION_FAILED_TOTAL.labels(reason="script_error").inc()
            EVALUATION_DURATION_SECONDS.labels(env_id=submission.env_id).observe(timer.seconds)
        except Exception:
            pass
        return {"status": "failed", "error": error_msg}
    
    except Exception as e:
        # Handle unexpected errors
        error_msg = str(e)
        logger.exception(
            f"Unexpected error evaluating submission {submission_id}: {str(e)}",
            extra={
                "submission_id": submission_id,
            },
        )
        
        if db:
            try:
                submission = db.query(Submission).get(submission_id)
                if submission:
                    submission.status = "failed"
                    submission.error = f"System error: {error_msg[:500]}"
                    db.commit()
            except Exception as db_error:
                logger.error(
                    f"Failed to update DB after error: {str(db_error)}",
                    extra={"submission_id": submission_id},
                )
        
        try:
            EVALUATION_FAILED_TOTAL.labels(reason="unexpected_exception").inc()
        except Exception:
            pass
        return {"status": "error", "message": error_msg}
    
    finally:
        # Best-effort artifact cleanup regardless of outcome
        try:
            _cleanup_submission_artifacts(submission_id)
        except Exception:
            pass
        db.close()
