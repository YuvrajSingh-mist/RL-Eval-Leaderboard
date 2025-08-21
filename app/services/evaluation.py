
import logging
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models import Submission, EvaluationMetric
from app.core.docker import run_evaluation_container
from app.core.config import settings
from app.services.leaderboard import redis_leaderboard

logger = logging.getLogger(__name__)

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
        logger.info(f"Started evaluation for submission {submission_id}")
        
        # Run in isolated container
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

            # Store detailed metrics if available
            metrics = parsed_output.get("metrics", [])
            if metrics:
                for episode, reward in enumerate(metrics):
                    metric = EvaluationMetric(
                        submission_id=submission_id,
                        episode=episode,
                        reward=reward
                    )
                    db.add(metric)

            logger.info(f"Evaluation completed for {submission_id}. Score: {submission.score}")
            db.commit()
            # Push to Redis leaderboard for immediate visibility
            try:
                redis_leaderboard.add_submission(submission)
            except Exception as e:
                logger.error(f"Failed to update Redis leaderboard for {submission_id}: {str(e)}")
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
        logger.error(f"Evaluation failed for {submission_id}: {error_msg}")

        # Commit final status
        db.commit()
        return {"status": "failed", "error": error_msg}
    
    except Exception as e:
        # Handle unexpected errors
        error_msg = str(e)
        logger.exception(f"Unexpected error evaluating submission {submission_id}: {str(e)}")
        
        if db:
            try:
                submission = db.query(Submission).get(submission_id)
                if submission:
                    submission.status = "failed"
                    submission.error = f"System error: {error_msg[:500]}"
                    db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update DB after error: {str(db_error)}")
        
        return {"status": "error", "message": error_msg}
    
    finally:
        db.close()
