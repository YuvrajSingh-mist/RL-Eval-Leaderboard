
import docker
import logging
import os
import re
from app.core.config import settings
from docker.errors import DockerException, ContainerError, APIError

logger = logging.getLogger(__name__)

def sanitize_container_name(name: str) -> str:
    """Convert UUID to valid Docker container name"""
    # Docker names must: start with alphanumeric, contain only [a-zA-Z0-9][a-zA-Z0-9_.-]
    return re.sub(r'[^a-zA-Z0-9_.-]', '', name)[:63]

def get_docker_client():
    """Create a Docker client with proper configuration"""
    try:
        return docker.DockerClient(
            base_url=settings.DOCKER_SOCKET,
            timeout=300
        )
    except DockerException as e:
        logger.critical(f"Docker client initialization failed: {str(e)}")
        raise

def run_evaluation_container(submission_id: str, script_path: str, env_id: str):
    """Run evaluation in a secure Docker container"""
    client = get_docker_client()
    container = None
    container_name = sanitize_container_name(f"eval-{submission_id}")
    
    try:
        logger.info(f"Starting evaluation container for submission {submission_id}")
        
        # Security options
        security_opts = [
            "no-new-privileges",
            # "seccomp=unconfined"  # Uncomment in production with proper profile
        ]
        
        # Create container with submission_id integration
        container = client.containers.run(
            image=settings.EVALUATOR_IMAGE,
            command=f"/home/appuser/entrypoint.sh",
            name=container_name,  # CRITICAL: Use submission_id in container name
            labels={
                "com.rl_leaderboard.submission_id": submission_id,
                "com.rl_leaderboard.env_id": env_id
            },  # CRITICAL: Add labels for tracking
            environment={
                "ENV_ID": env_id,
                "SCRIPT_PATH": "/home/appuser/submission.py",
                "SUBMISSION_ID": submission_id  # Pass to container
            },
            volumes={
                os.path.abspath(script_path): {
                    "bind": "/home/appuser/submission.py",
                    "mode": "ro"
                }
            },
            network_mode="none",  # Disable network
            mem_limit="512m",
            pids_limit=50,
            cpu_quota=50000,  # 50% of one CPU
            security_opt=security_opts,
            cap_drop=["ALL"],
            detach=True,
            platform="linux/amd64"  # Critical for M1
        )
        
        logger.debug(f"Container created: {container.id} for submission {submission_id}")
        
        # Wait for completion
        result = container.wait(timeout=300)
        logs = container.logs(stdout=True, stderr=True).decode()
        container.remove()
        container = None  # Container is now removed
        
        logger.info(f"Evaluation completed for {submission_id}. Status: {result['StatusCode']}")
        return {
            "status": result["StatusCode"],
            "logs": logs,
            "output": parse_evaluation_output(logs)
        }
    
    except ContainerError as e:
        logger.error(f"Container error for {submission_id}: {str(e)}")
        return {"error": f"Container error: {str(e)}"}
    except APIError as e:
        logger.error(f"Docker API error for {submission_id}: {str(e)}")
        return {"error": f"Docker API error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Unexpected error for {submission_id}: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}"}
    finally:
        # Ensure container cleanup if something went wrong
        if container:
            try:
                logger.warning(f"Force-removing container for {submission_id}")
                container.remove(force=True)
            except Exception as e:
                logger.error(f"Failed to remove container: {str(e)}")
        client.close()
        logger.debug(f"Docker client closed for submission {submission_id}")

def parse_evaluation_output(logs: str) -> dict:
    """Parse structured output from evaluation script"""
    try:
        # Get the last non-empty line (should be JSON)
        lines = [line.strip() for line in logs.splitlines() if line.strip()]
        if not lines:
            return {"error": "No output received"}
        
        import json
        return json.loads(lines[-1])
    except Exception as e:
        return {
            "error": f"Invalid output format: {str(e)}", 
            "raw_output": logs[-500:],  # Last 500 chars for debugging
            "output_lines": len(lines)
        }
