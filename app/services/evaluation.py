
import logging
from sqlalchemy.orm import Session
from app.core.docker import run_evaluation_container
from app.db.session import SessionLocal
from app.models import Submission, EvaluationMetric
from app.services.leaderboard import redis_leaderboard
import os

logger = logging.getLogger(__name__)

def evaluate_submission(submission_id: str) -> dict:
    """
    Evaluate a submission by running it in a secure container
    Returns evaluation results or error information
    """
    db = SessionLocal()
    script_path = f"./submissions/{submission_id}.py"
    cleanup_file = False
    
    try:
        # Get submission
        submission = db.query(Submission).get(submission_id)
        if not submission:
            logger.error(f"Submission {submission_id} not found in database")
            return {"status": "error", "message": "Submission not found"}
        
        # Check if file exists
        if not os.path.exists(script_path):
            logger.error(f"Script file not found: {script_path}")
            submission.status = "failed"
            submission.error = "Script file was not saved properly"
            db.commit()
            return {"status": "error", "message": "Script file not found"}
        
        # Mark for cleanup
        cleanup_file = True
        
        # Update status to processing
        submission.status = "processing"
        db.commit()
        logger.info(f"Started evaluation for submission {submission_id}")
        
        # Run in isolated container
        result = run_evaluation_container(
            submission_id=submission_id,
            script_path=script_path,
            env_id=submission.env_id
        )
        
        # CRITICAL: Check if container run was successful
        if "error" in result:
            logger.error(f"Container execution failed for {submission_id}: {result['error']}")
            submission.status = "failed"
            submission.error = result["error"]
            db.commit()
            
            # Remove from leaderboard
            try:
                redis_leaderboard.remove_submission(submission_id, submission.env_id)
            except Exception as e:
                logger.error(f"Failed to remove from Redis leaderboard: {str(e)}")
            
            # Return proper error response
            return {"status": "error", "message": result["error"]}
        
        # Process results
        if result.get("status") == 0 and "score" in result.get("output", {}):
            # Successful evaluation
            submission.score = result["output"]["score"]
            submission.status = "completed"
            
            # Store detailed metrics if available
            metrics = result["output"].get("metrics", [])
            if metrics:
                for episode, reward in enumerate(metrics):
                    metric = EvaluationMetric(
                        submission_id=submission_id,
                        episode=episode,
                        reward=reward
                    )
                    db.add(metric)
            
            # Add to Redis leaderboard
            try:
                redis_leaderboard.add_submission(submission)
                logger.info(f"Added {submission_id} to Redis leaderboard")
            except Exception as e:
                logger.error(f"Failed to update Redis leaderboard: {str(e)}")
                
            logger.info(f"Evaluation completed for {submission_id}. Score: {submission.score}")
        else:
            # Evaluation failed
            error_msg = result.get("error", "Evaluation failed without specific error")
            if "output" in result:
                error_msg += f" | Output: {result['output']}"
                
            submission.status = "failed"
            submission.error = error_msg[:500]
            logger.error(f"Evaluation failed for {submission_id}: {error_msg}")
            
            # Remove from leaderboard
            try:
                redis_leaderboard.remove_submission(submission_id, submission.env_id)
            except Exception as e:
                logger.error(f"Failed to remove from Redis leaderboard: {str(e)}")
        
        # Commit final status
        db.commit()
        
        # Return success only if evaluation was truly successful
        if submission.status == "completed":
            return {"status": "success", "score": submission.score}
        else:
            return {"status": "error", "message": submission.error}
    
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
                    
                    # Remove from leaderboard
                    try:
                        redis_leaderboard.remove_submission(submission_id, submission.env_id)
                    except Exception as e:
                        logger.error(f"Failed to remove from Redis leaderboard: {str(e)}")
            except Exception as db_error:
                logger.error(f"Failed to update DB after error: {str(db_error)}")
        
        return {"status": "error", "message": error_msg}
    
    finally:
        # Clean up file if requested
        if cleanup_file and os.path.exists(script_path):
            try:
                os.remove(script_path)
                logger.debug(f"Cleaned up script file for {submission_id}")
            except Exception as e:
                logger.error(f"Failed to clean up {script_path}: {str(e)}")
        
        db.close()
