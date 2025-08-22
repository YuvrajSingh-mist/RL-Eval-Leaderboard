
import docker
import logging
import os
from app.core.config import settings
from docker.errors import DockerException, APIError, NotFound
from app.core.client import supabase_client
import io
import tarfile
import time
import re

logger = logging.getLogger(__name__)

def parse_evaluation_output(logs: str) -> dict:
    """Extract the last valid JSON object emitted by the user script from mixed logs."""
    import json
    # Fast path: scan from the bottom for a JSON line
    lines = [line.strip() for line in (logs or "").splitlines() if line.strip()]
    if not lines:
        return {"error": "No output received"}
    for line in reversed(lines):
        # Heuristic: JSON result should start with '{' and end with '}' on a single line
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue
    # As a fallback, try to find a JSON object anywhere in logs
    try:
        start = logs.rfind("{")
        end = logs.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = logs[start:end+1]
            return json.loads(candidate)
    except Exception:
        pass
    return {"error": "No JSON result found in logs", "raw_output": logs[-500:]}


def _normalize_docker_host(value: str) -> str:
    """Ensure Docker host has a proper scheme for docker-py.

    Examples accepted by docker SDK:
      - unix:///var/run/docker.sock
      - unix://var/run/docker.sock
      - tcp://docker:2375

    Common mistakes we correct here:
      - "/var/run/docker.sock" -> "unix:///var/run/docker.sock"
      - "unix:/var/run/docker.sock" -> "unix:///var/run/docker.sock"
    """
    host = (value or "").strip()
    if not host:
        return "unix:///var/run/docker.sock"

    # If it's a plain path, prefix with unix://
    if host.startswith("/"):
        return f"unix://{host}"

    # Fix single-slash scheme typo
    if host.startswith("unix:/") and not host.startswith("unix://"):
        return "unix://" + host[len("unix:/"):].lstrip("/")

    return host

def get_docker_client():
    """Create a Docker client with proper configuration"""
    try:
        # Respect DOCKER_HOST if set, otherwise use settings. Normalize either way.
        configured_host = os.getenv("DOCKER_HOST") or settings.DOCKER_SOCKET
        base_url = _normalize_docker_host(configured_host)
        logger.debug(f"Initializing Docker client with base_url={base_url}")
        # Give extra headroom over in-container timeout (300s)
        return docker.DockerClient(
            base_url=base_url,
            timeout=420,
            version='auto'
        )
    except APIError as e:
        logger.critical(f"Docker API error: {str(e)}")
        raise
    except DockerException as e:
        logger.critical(f"Docker client initialization failed: {str(e)}")
        raise

def _download_submission_bytes(submission_id: str):
    """Download submission from Supabase.

    Returns a tuple of (bytes, kind) where kind is 'tar' or 'py'. Prefers tar bundles.
    """
    # Try tar bundle first
    try:
        tar_resp = supabase_client.storage.from_(settings.SUPABASE_BUCKET).download(f"{submission_id}.tar")
        if isinstance(tar_resp, (bytes, bytearray)):
            return bytes(tar_resp), 'tar'
        if hasattr(tar_resp, 'error') and tar_resp.error:
            logger.debug(f"No tar found for {submission_id}: {tar_resp.error}")
    except Exception as e:
        logger.debug(f"Tar download failed for {submission_id}: {str(e)}")

    # Fallback to single .py
    py_resp = supabase_client.storage.from_(settings.SUPABASE_BUCKET).download(f"{submission_id}.py")
    if hasattr(py_resp, 'error') and py_resp.error:
        raise Exception(f"Download failed: {py_resp.error}")
    if not isinstance(py_resp, (bytes, bytearray)):
        raise Exception("Unexpected response downloading submission")
    return bytes(py_resp), 'py'

def run_evaluation_container(submission_id: str, env_id: str):
    """Run evaluation in a secure Docker container"""
    client = None
    container = None
    stage = "init"
    
    try:
        # Validate required inputs early
        if not env_id or not str(env_id).strip():
            raise ValueError("ENV_ID is required to run the evaluator container")
        client = get_docker_client()
        logger.info(
            f"Starting evaluation container for submission {submission_id}",
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "stage": stage,
            },
        )
        
        # Create container name
        
        container_name = re.sub(r'[^a-zA-Z0-9_.-]', '', f"eval-{submission_id}")[:63]
        
        # Security options
        security_opts = [
            "no-new-privileges",
        ]
        
        # Download script content into memory
        stage = "download_submission"
        script_bytes, file_kind = _download_submission_bytes(submission_id)

        # Prepare env and create container (do not start yet)
        env_vars = {
            "ENV_ID": str(env_id),
            "SCRIPT_PATH": "/home/appuser/submission.py",
            "SUBMISSION_ID": str(submission_id)
        }
        logger.info(
            f"Evaluator env: {{'ENV_ID': '{env_id}', 'SUBMISSION_ID': '{submission_id}'}}",
            extra={"submission_id": submission_id, "env_id": env_id, "stage": stage},
        )
        stage = "create_container"
        container = client.containers.create(
            command = f"/home/appuser/entrypoint.sh",
            image=settings.EVALUATOR_IMAGE,
            name=container_name,
            labels={
                "com.rl_leaderboard.submission_id": submission_id,
                "com.rl_leaderboard.env_id": env_id
            },
            environment=env_vars,
            network_mode="none",  # No network access
            mem_limit="512m",     # 512MB memory limit
            pids_limit=50,        # Max 50 processes
            cpu_quota=50000,      # 50% of one CPU
            security_opt=security_opts,
            cap_drop=["ALL"],     # Drop all capabilities
            detach=True
        )
        logger.info(
            f"Container created: {container.id}",
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "container_id": (getattr(container, "id", None) or None),
                "stage": stage,
            },
        )
        # Inject code into container at /home/appuser
        stage = "inject_script"
        if file_kind == 'tar':
            # Assume tar contains files at root, including submission.py
            container.put_archive(path="/home/appuser", data=script_bytes)
            logger.info("Bundle imported (tar)", extra={"submission_id": submission_id, "env_id": env_id, "stage": stage})
        else:
            # Single file -> write as submission.py
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                ti = tarfile.TarInfo(name="submission.py")
                ti.size = len(script_bytes)
                ti.mtime = int(time.time())
                ti.mode = 0o444
                tar.addfile(ti, io.BytesIO(script_bytes))
            tar_stream.seek(0)
            container.put_archive(path="/home/appuser", data=tar_stream.getvalue())
            logger.info("Single script imported", extra={"submission_id": submission_id, "env_id": env_id, "stage": stage})
        # Start execution
        stage = "start"
        container.start()
        logger.info(
            f"Container started: {container.id}",
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "container_id": (getattr(container, "id", None) or None),
                "stage": stage,
            },
        )

        # Wait for completion and capture exit code
        stage = "wait"
        wait_result = container.wait()
        try:
            exit_code = int(wait_result.get("StatusCode", 1))
        except Exception:
            exit_code = 1

        # Collect logs
        stage = "collect_logs"
        logs = container.logs(stdout=True, stderr=True).decode(errors="replace")

        logger.info(
            f"Evaluation completed for {submission_id}. Exit code: {exit_code}",
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "container_id": (getattr(container, "id", None) or None),
                "stage": stage,
            },
        )
        parsed_output = parse_evaluation_output(logs)
        response = {
            "status": exit_code,
            "logs": logs,
            "output": parsed_output
        }
        # Promote parse errors or missing score to top-level error for clearer reporting
        if exit_code != 0:
            response["error"] = "Evaluator exited non-zero"
        else:
            has_score = isinstance(parsed_output, dict) and ("score" in parsed_output)
            if not has_score:
                # If parser produced an explicit error, surface it; otherwise explain what's missing
                parsed_error = parsed_output.get("error") if isinstance(parsed_output, dict) else None
                response["error"] = parsed_error or "No 'score' found in script output. Ensure your script prints a single JSON line with a 'score' field."
        return response
    
    except NotFound as e:
        error_msg = f"Docker image not found: {settings.EVALUATOR_IMAGE}. Build it with: docker build -f docker/Dockerfile.evaluator -t rl-evaluator:latest ."
        logger.error(error_msg)
        return {"error": error_msg}
    except APIError as e:
        error_msg = f"Docker API error: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        # Return precise stage and any available logs for clarity
        try:
            logs = container.logs(stdout=True, stderr=True).decode() if container else ""
        except Exception:
            logs = ""
        error_msg = f"Container execution failed at stage '{stage}': {str(e)}"
        logger.exception(
            error_msg,
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "container_id": (getattr(container, "id", None) or None),
                "stage": stage,
            },
        )
        return {"error": error_msg, "stage": stage, "logs": logs[-1000:]}
    
    finally:
        if container:
            try:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
                container.remove(force=True)
            except:
                pass
        if client:
            client.close()
        logger.debug(
            f"Resources cleaned up for submission {submission_id}",
            extra={
                "submission_id": submission_id,
                "env_id": env_id,
                "container_id": (getattr(container, "id", None) or None),
                "stage": stage,
            },
        )

