import os
import time
import json
import tempfile
import subprocess
import shutil
import importlib
from pathlib import Path

import pytest
import requests


API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
PROM_BASE_URL = os.environ.get("PROM_BASE_URL", "http://localhost:9090")

# Track temp dirs for cleanup
_CREATED_TEMP_DIRS: list[Path] = []


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def _compose_base_cmd() -> list[str]:
    # Prefer docker compose (v2); fall back to docker-compose
    probe = _run(["docker", "compose", "version"])  # type: ignore[list-item]
    if probe.returncode == 0:
        return ["docker", "compose"]
    return ["docker-compose"]


def compose_run(args: list[str]) -> subprocess.CompletedProcess:
    return _run(_compose_base_cmd() + args)


def wait_for_prom_alert(
    alert_name: str,
    state: str = "firing",
    timeout_seconds: int = 600,
    poll_seconds: int = 5,
) -> bool:
    # Query Prometheus ALERTS series for the alert state
    deadline = time.time() + timeout_seconds
    query = f'ALERTS{{alertname="{alert_name}",alertstate="{state}"}}'
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{PROM_BASE_URL}/api/v1/query",
                params={"query": query},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("data", {}).get("result", [])
                if result:
                    return True
        except Exception:
            pass
        time.sleep(poll_seconds)
    return False


def submit_file(filepath: Path, env_id: str, algorithm: str, user_id: str) -> None:
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, "text/x-python")}
        data = {
            "env_id": env_id,
            "algorithm": algorithm,
            "user_id": user_id,
        }
        try:
            requests.post(
                f"{API_BASE_URL}/api/submit/",
                files=files,
                data=data,
                timeout=10,
            )
        except Exception:
            pass


def _write_temp_py(contents: str) -> Path:
    tmp_dir = Path(tempfile.mkdtemp(prefix="rl_alerts_"))
    _CREATED_TEMP_DIRS.append(tmp_dir)
    p = tmp_dir / "submission.py"
    p.write_text(contents)
    return p


@pytest.fixture(scope="session", autouse=True)
def ensure_stack_cleanup():
    # If the stack is not running, bring it up and mark for teardown
    started_stack = False
    ps_api = compose_run(["ps", "-q", "api"])  # type: ignore[list-item]
    if ps_api.returncode != 0 or not ps_api.stdout.strip():
        up = compose_run(["up", "-d"])  # start all declared services
        if up.returncode == 0:
            started_stack = True
        # give services a brief settle time
        time.sleep(5)

    try:
        yield
    finally:
        # Call user-provided cleanup function if specified, e.g. CLEANUP_FUNC=app.core.docker:cleanup_all
        func_spec = os.getenv("CLEANUP_FUNC")
        if func_spec:
            try:
                mod_name, func_name = func_spec.split(":", 1)
                func = getattr(importlib.import_module(mod_name), func_name)
                try:
                    func()
                except TypeError:
                    # If callable expects optional context arg, try passing None
                    try:
                        func(None)
                    except Exception:
                        pass
            except Exception:
                pass
        # Always remove potential qdisc
        compose_run([
            "exec", "-T", "-u", "root", "api",
            "bash", "-lc",
            "tc qdisc del dev eth0 root || true",
        ])
        # Ensure api/worker are up
        compose_run(["start", "api"])  # best-effort
        compose_run(["start", "worker"])  # best-effort
        # Cleanup temp dirs
        for d in _CREATED_TEMP_DIRS:
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        _CREATED_TEMP_DIRS.clear()
        # If we started the stack, take it down to leave a clean host
        if started_stack:
            compose_run(["down"])  # best-effort


@pytest.mark.timeout(300)
def test_api_target_down():
    # Stop API and wait for APITargetDown
    compose_run(["stop", "api"])  # best-effort
    try:
        ok = wait_for_prom_alert("APITargetDown", timeout_seconds=120)
        assert ok, "APITargetDown did not fire in time"
    finally:
        compose_run(["start", "api"])  # recover


@pytest.mark.timeout(300)
def test_worker_target_down():
    # Stop worker and wait for WorkerTargetDown
    compose_run(["stop", "worker"])  # best-effort
    try:
        ok = wait_for_prom_alert("WorkerTargetDown", timeout_seconds=120)
        assert ok, "WorkerTargetDown did not fire in time"
    finally:
        compose_run(["start", "worker"])  # recover


@pytest.mark.timeout(1200)
def test_high_evaluation_failures():
    # Create failing submission and continuously submit for ~6 minutes
    bad = _write_temp_py("import sys; sys.exit(1)\n")
    deadline = time.time() + 6 * 60  # sustain condition across 'for: 5m'
    ok = False
    i = 0
    while time.time() < deadline:
        submit_file(bad, "CartPole-v1", "FailTest", "stress")
        i += 1
        # Poll for alert while feeding failures
        if i % 3 == 0:  # every ~15s if sleep=5 below
            if wait_for_prom_alert("HighEvaluationFailures", timeout_seconds=1):
                ok = True
                break
        time.sleep(5)
    if not ok:
        ok = wait_for_prom_alert("HighEvaluationFailures", timeout_seconds=300)
    assert ok, "HighEvaluationFailures did not fire in time"


@pytest.mark.long
@pytest.mark.timeout(2400)
def test_slow_evaluations_p95_long():
    # Sleep for 120s then succeed; enqueue enough to push p95>60s for 10m
    slow_script = """
import time, json
time.sleep(120)
print(json.dumps({"score": 1.0}))
"""
    slow = _write_temp_py(slow_script)
    for _ in range(12):
        submit_file(slow, "CartPole-v1", "SlowTest", "stress")
        time.sleep(2)
    ok = wait_for_prom_alert("SlowEvaluationsP95", timeout_seconds=1800)
    assert ok, "SlowEvaluationsP95 did not fire in time"


@pytest.mark.long
@pytest.mark.timeout(2400)
def test_leaderboard_latency_high_long():
    # Inject ~750ms egress delay on API container and hammer leaderboard
    install = compose_run([
        "exec", "-T", "-u", "root", "api",
        "bash", "-lc",
        "apt-get update && apt-get install -y iproute2 >/dev/null",
    ])
    if install.returncode != 0:
        pytest.skip("iproute2 install failed in api container")
    add_qdisc = compose_run([
        "exec", "-T", "-u", "root", "api",
        "bash", "-lc",
        "tc qdisc add dev eth0 root netem delay 750ms || true",
    ])
    try:
        # Generate sustained load to accumulate latency metrics
        end = time.time() + 900
        while time.time() < end:
            try:
                requests.get(
                    f"{API_BASE_URL}/api/leaderboard/?env_id=CartPole-v1&limit=50",
                    timeout=3,
                )
            except Exception:
                pass
            time.sleep(1)
        ok = wait_for_prom_alert("LeaderboardLatencyHigh", timeout_seconds=600)
        assert ok, "LeaderboardLatencyHigh did not fire in time"
    finally:
        compose_run([
            "exec", "-T", "-u", "root", "api",
            "bash", "-lc",
            "tc qdisc del dev eth0 root || true",
        ])


@pytest.mark.long
@pytest.mark.timeout(2400)
def test_celery_queue_backlog_long():
    # Stop worker so queue grows; enqueue many jobs; wait for backlog alert
    compose_run(["stop", "worker"])  # best-effort
    try:
        bad = _write_temp_py("import sys; sys.exit(1)\n")
        for _ in range(200):
            submit_file(bad, "CartPole-v1", "BacklogTest", "stress")
            time.sleep(0.2)
        ok = wait_for_prom_alert("CeleryQueueBacklog", timeout_seconds=1800)
        assert ok, "CeleryQueueBacklog did not fire in time"
    finally:
        compose_run(["start", "worker"])  # recover


