# RL Leaderboard

A production-ready, containerized leaderboard system for evaluating Reinforcement Learning (RL) agents. It provides a FastAPI backend, a Celery worker that safely evaluates submissions inside a locked-down Docker container, real-time leaderboards powered by Redis, persistent results in PostgreSQL, and a Gradio-based frontend.

---

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
  - [Using the Gradio Frontend](#using-the-gradio-frontend)
  - [Submitting via API](#submitting-via-api)
  - [Checking Results](#checking-results)
  - [Querying the Leaderboard](#querying-the-leaderboard)
- [Submission Contract](#submission-contract)
- [Project Structure](#project-structure)
- [Local Development (without Docker)](#local-development-without-docker)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features
- **Real-time leaderboard**: Redis-sorted sets with DB durability fallback.
- **Asynchronous evaluation**: Celery worker executes user submissions in an isolated Docker container.
- **Safe execution**: Containers run with no network, memory/CPU/pids limits, and capability drops.
- **Persistent storage**: PostgreSQL for submissions and durable leaderboard entries.
- **Object storage**: Supabase Storage for user-submitted scripts.
- **Gradio UI**: Simple web app to submit agents, check status, and view leaderboards.
- **Dockerized**: One command to bring up the full stack.

---

## Architecture
```
┌─────────────────┐      ┌─────────────────┐      ┌────────────────────┐
│  Gradio Frontend│ <--> │   API (FastAPI) │ <--> │  Celery Worker      │
└─────────────────┘      └─────────────────┘      └────────────────────┘
          │                       │                          │
          v                       v                          v
┌─────────────────┐      ┌─────────────────┐      ┌────────────────────┐
│ PostgreSQL (DB) │      │  Redis (cache)  │      │ Docker Engine (host│
└─────────────────┘      └─────────────────┘      └────────────────────┘
                                                (runs evaluator containers)
```

- The API exposes submission, results, and leaderboard endpoints.
- Submissions are uploaded to Supabase Storage, recorded in PostgreSQL, and queued via Celery.
- The worker pulls the script, runs it inside the `rl-evaluator:latest` image with strict limits, parses the JSON result, updates DB and Redis.
- Leaderboards are served from Redis for speed with an automatic fallback to DB for durability.

---

## Quickstart

### Prerequisites
- Docker and Docker Compose v2
- Git

### Clone
```bash
git clone <your-repo-url>
cd RL\ Leaderboard
```

### Environment
Create a `.env` file at the repo root (values are examples; use your own secrets):
```env
# Database used by docker-compose
DB_USER=leaderboard
DB_PASSWORD=change-me-strong

# FastAPI app security
SECRET_KEY=please-change-this

# Supabase (required for uploads/downloads)
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_ANON_KEY=your-public-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_BUCKET=submissions

# Optional: override (compose provides sane defaults)
# DATABASE_URL=postgresql://leaderboard:change-me-strong@db:5432/leaderboard
# REDIS_URL=redis://redis:6379/0
# CELERY_BROKER_URL=redis://redis:6379/1
# CELERY_RESULT_BACKEND=redis://redis:6379/1
```

In Supabase, create a Storage bucket named `submissions`. The backend uses the service role key to upload and download submission files.

### Build the evaluator image
The worker launches evaluation jobs using the `rl-evaluator:latest` image. Build it once:
```bash
docker build -f docker/Dockerfile.evaluator -t rl-evaluator:latest .
```

Alternatively (Compose profile):
```bash
docker compose build evaluator
```

### Start the stack
```bash
docker compose up -d --build
```

### Open the apps
- Gradio Frontend: `http://localhost:7860`
- API (OpenAPI docs): `http://localhost:8000/docs`
- Redis Commander (optional UI): `http://localhost:8081`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

To stop everything: `docker compose down`

---

## Environment Variables

These are consumed by the services (see `docker-compose.yml` and `app/core/config.py`).

| Variable                 | Description                               | Default (compose/app)                     |
|--------------------------|-------------------------------------------|-------------------------------------------|
| DB_USER                  | PostgreSQL username                       | `leaderboard`                             |
| DB_PASSWORD              | PostgreSQL password                       | n/a                                       |
| DATABASE_URL             | SQLAlchemy URL                            | `postgresql://leaderboard:...@db:5432/...`|
| REDIS_URL                | Redis URL (leaderboard cache)             | `redis://redis:6379/0`                    |
| CELERY_BROKER_URL        | Celery broker                             | `redis://redis:6379/1`                    |
| CELERY_RESULT_BACKEND    | Celery result backend                     | `redis://redis:6379/1`                    |
| SUPABASE_URL             | Supabase project URL                      | required                                  |
| SUPABASE_ANON_KEY        | Supabase anon key                         | optional (frontend or clients)            |
| SUPABASE_SERVICE_KEY     | Supabase service role key                 | required (server-side Storage access)     |
| SUPABASE_BUCKET          | Supabase Storage bucket name              | `submissions`                             |
| SECRET_KEY               | FastAPI app secret                        | `supersecret` (override in prod)          |
| DOCKER_HOST              | Docker socket for worker                  | `unix:///var/run/docker.sock`             |
| SENTRY_DSN               | Sentry DSN (optional)                     | -                                         |
| SENTRY_ENVIRONMENT       | Sentry environment name                   | `development`                             |
| SENTRY_TRACES_SAMPLE_RATE| Sentry APM sampling rate (0..1)           | `0.1`                                     |

---

## Usage

### Using the Gradio Frontend
1. Go to `http://localhost:7860`.
2. In the Submit tab, choose an environment (e.g., `CartPole-v1`), provide optional user/algorithm labels, and upload your `.py` file.
3. Copy the shown Submission ID and check its status in the Check Status tab.
4. View the Leaderboard tab for real-time rankings.

### Submitting via API

Endpoint: `POST /api/submit/`

Multipart form fields:
- Single-file mode (backward compatible):
  - `file`: Python file to evaluate (`.py`)
- Multi-file mode:
  - `files`: Repeatable field for multiple files (pass multiple `-F files=@...`). Non-.py support files (e.g., JSON) are allowed.
  - `main_file` (required when using `files`): The Python filename to execute (must end with `.py`). The server aliases it to `submission.py` inside the evaluator container.
  - Requirement: At least one uploaded file must be a `.py` when using multi-file mode.
- Common fields:
  - `env_id`: Gym environment ID (default `CartPole-v1`)
  - `algorithm`: Label for your method (default `Custom`)
  - `user_id`: Your identifier (default `anonymous`)
  - `client_id` (optional): Provide your own UUID to track the submission immediately.

Examples:

Single file:
```bash
curl -X POST \
  -F "file=@example_agents/dqn.py" \
  -F "env_id=CartPole-v1" \
  -F "algorithm=DQN" \
  -F "user_id=team-rocket" \
  http://localhost:8000/api/submit/
```

Multiple files with explicit main:
```bash
curl -X POST \
  -F "files=@my_agent/__init__.py" \
  -F "files=@my_agent/policy.py" \
  -F "files=@my_agent/runner.py" \
  -F "main_file=runner.py" \
  -F "env_id=CartPole-v1" \
  -F "algorithm=Custom" \
  -F "user_id=team-rocket" \
  http://localhost:8000/api/submit/
```

Response:
```json
{
  "id": "<submission_uuid>",
  "status": "queued",
  "env_id": "CartPole-v1",
  "algorithm": "DQN"
}
```

### Checking Results

Endpoint: `GET /api/results/{submission_id}`

Returns status (`pending` | `processing` | `completed` | `failed`), final score if completed, and any error.

```bash
curl http://localhost:8000/api/results/<submission_uuid>
```

### Querying the Leaderboard

Endpoint: `GET /api/leaderboard/`

Query params:
- `env_id` (string, default `CartPole-v1`)
- `limit` (int, 1..100, default 50)

```bash
curl "http://localhost:8000/api/leaderboard/?env_id=CartPole-v1&limit=50"
```

### Health
`GET /health` → `{ "status": "healthy", ... }`

---

## Submission Contract

Your submission must:
1. Consist of one or more Python files (`.py`).
2. Include a main file that will run as `submission.py`. When using multi-file mode, specify `main_file` (e.g., `runner.py`); the server aliases it to `submission.py` inside the container.
3. Accept the environment ID as its first CLI argument: your script will be invoked as:
   ```bash
   python -u submission.py <ENV_ID>
   ```
4. Print exactly one final JSON line to stdout that includes a numeric `score`. Optionally include `metrics` for per-episode rewards.

Example final output (printed as a single line):
```json
{"score": 123.45, "metrics": [9.0, 10.0, 11.0]}
```

Notes on the evaluator runtime (see `scripts/entrypoint.sh` and `app/core/docker.py`):
- Network disabled (`network_mode="none"`).
- Memory limit `512MiB`, CPU quota ~50% of one core, PIDs limit 50.
- Process is wrapped with `timeout 300s`, `nice`, `ionice`, and `ulimit`.
- Multi-file uploads are bundled and extracted into `/home/appuser`; your local imports like `import policy` will work when `policy.py` is uploaded alongside the main file.
- The worker parses container logs and extracts the last valid JSON line. If no `score` is found or the process exits non-zero, the submission is marked failed with a helpful log tail.

See `example_agents/dqn.py` for a simple reference implementation.

---

## Project Structure

```
app/
  api/                 # FastAPI routers (submissions, leaderboard)
  core/                # Config, Celery, Docker client, Supabase client
  db/                  # SQLAlchemy engine/session and Base
  models/              # SQLAlchemy models (Submission, EvaluationMetric, LeaderboardEntry)
  services/            # Leaderboard (Redis) and evaluation orchestration
  main.py              # FastAPI app factory and startup hooks
frontend/              # Gradio web app
docker/                # Evaluator Dockerfile
scripts/entrypoint.sh  # Evaluator container entrypoint
example_agents/        # Sample agents (e.g., dqn.py)
docker-compose.yml     # Orchestrates API, Worker, DB, Redis, Frontend
```

---

## Local Development (without Docker)

This is useful for iterating on API/worker code. You still need Docker Engine installed to run evaluator containers.

### 1) Python deps
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2) Services
Run local Postgres and Redis (e.g., via Docker):
```bash
docker run -d --name rl-db -e POSTGRES_DB=leaderboard -e POSTGRES_USER=leaderboard -e POSTGRES_PASSWORD=change-me-strong -p 5432:5432 postgres:15
docker run -d --name rl-redis -p 6379:6379 redis:7
```

Export environment (adjust as needed):
```bash
export DATABASE_URL=postgresql://leaderboard:change-me-strong@localhost:5432/leaderboard
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/1
export CELERY_RESULT_BACKEND=redis://localhost:6379/1
export SUPABASE_URL=...; export SUPABASE_SERVICE_KEY=...; export SUPABASE_BUCKET=submissions
```

Build the evaluator image once:
```bash
docker build -f docker/Dockerfile.evaluator -t rl-evaluator:latest .
```

Ensure the worker can reach Docker (often default works):
```bash
export DOCKER_HOST=unix:///var/run/docker.sock
```

### 3) Run API and Worker
```bash
uvicorn app.main:app --reload --port 8000
celery -A app.core.celery.celery_app worker --loglevel=info
```

Open `http://localhost:8000/docs` for API docs. Optionally run the frontend via `python frontend/gradio_app.py`.

---

## Troubleshooting

- **Evaluator image not found**: Build it with `docker build -f docker/Dockerfile.evaluator -t rl-evaluator:latest .`.
- **Docker socket permission denied**: On Linux/macOS, ensure your user can access `/var/run/docker.sock`. In Compose, the worker runs as `root` and mounts the socket.
- **Redis/DB connection errors**: Verify services are healthy (`docker compose ps`) and env vars match.
- **Supabase upload/download errors**: Check keys and that the `submissions` bucket exists.
- **Submission fails with "No 'score' found"**: Ensure your script prints one final JSON line with a `score` field.
- **Frontend cannot reach API**: The frontend container uses `API_URL=http://api:8000`. When running locally without Compose, set `API_URL=http://localhost:8000`.

---

## Contributing
1. Fork the repository
2. Create a feature branch
3. Make changes with clear commit messages
4. Open a Pull Request

---

## License
MIT

---

## Observability Stack (Prometheus, Grafana, Sentry)

Production-grade observability is included:

- Prometheus metrics from API and Celery worker
- Grafana dashboards (pre-provisioned)
- Sentry error and performance monitoring for API and worker

### New endpoints/ports
- API `/metrics` on port 8000
- Celery worker metrics server on port 9100
- Prometheus on port 9090
- Grafana on port 3000

### Configure Sentry (optional)
Add these to `.env`:

```
SENTRY_DSN=<your sentry dsn>
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Metrics exposed
- `submissions_received_total{mode}`
- `submissions_validation_failures_total{reason}`
- `submissions_upload_bytes_total`
- `evaluation_started_total`
- `evaluation_completed_total{env_id}`
- `evaluation_failed_total{reason}`
- `evaluation_duration_seconds_bucket/sum/count{env_id}`
- `leaderboard_queries_total{env_id,sort}`
- `leaderboard_query_duration_seconds_bucket/sum/count`

Plus default FastAPI metrics (requests, latencies, status codes, exceptions).

# RL Leaderboard

A scalable, containerized leaderboard system for Reinforcement Learning (RL) agent evaluation. Supports real-time score updates, submission management, and a Gradio-based frontend.

---

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Submission Format](#submission-format)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features
- **Leaderboard**: Real-time, Redis-powered sorting and ranking of RL agent submissions.
- **Submission Management**: Track, evaluate, and store agent submissions.
- **Celery Worker**: Asynchronous evaluation of agents using Docker containers.
- **Gradio Frontend**: User-friendly interface for viewing leaderboard and submitting agents.
- **PostgreSQL Database**: Persistent storage for submissions and metadata.
- **Redis**: Fast, in-memory data store for leaderboard and task queues.
- **Dockerized**: All components run in containers for easy deployment.

---

## Architecture
```
+-------------------+      +-------------------+      +-------------------+
|   Gradio Frontend |<---->|      API Server   |<---->|   Celery Worker   |
+-------------------+      +-------------------+      +-------------------+
         |                        |                          |
         v                        v                          v
+-------------------+      +-------------------+      +-------------------+
|   PostgreSQL DB   |      |      Redis        |      |   Docker Engine   |
+-------------------+      +-------------------+      +-------------------+
```
- **Gradio Frontend**: User interface for leaderboard and submissions.
- **API Server**: FastAPI backend serving REST endpoints.
- **Celery Worker**: Handles agent evaluation asynchronously.
- **PostgreSQL**: Stores submission data.
- **Redis**: Leaderboard and task queue.
- **Docker**: Runs agent evaluation in isolated containers.

---

## Setup & Installation

### Prerequisites
- Docker & Docker Compose
- Python 3.8+
- Git

### Clone the Repository
```bash
git clone <your-repo-url>
cd RL Leaderboard
```

### Environment Variables
Create a `.env` file in the root directory:
```env
DB_USER=leaderboard
DB_PASSWORD=securepassword123
SECRET_KEY=supersecret
```

### Build & Start Services
```bash
docker-compose up --build -d
```

### Access the Frontend
Open [http://localhost:7860](http://localhost:7860) in your browser.

---

## Environment Variables
| Variable         | Description                       | Default                |
|------------------|-----------------------------------|------------------------|
| DB_USER          | PostgreSQL username               | leaderboard            |
| DB_PASSWORD      | PostgreSQL password               | securepassword123      |
| SECRET_KEY       | API secret key                    | supersecret            |
| DATABASE_URL     | PostgreSQL connection string      | postgresql://...       |
| REDIS_URL        | Redis connection string           | redis://redis:6379/0   |
| CELERY_BROKER_URL| Celery broker (Redis)             | redis://redis:6379/2   |
| CELERY_RESULT_BACKEND | Celery result backend (Redis) | redis://redis:6379/2   |

---

## Usage
- Submit RL agents via the frontend or API.
- View leaderboard rankings in real-time.
- Submissions are evaluated asynchronously in Docker containers.

---

## API Endpoints

### Leaderboard
- `GET /leaderboard/{env_id}`: Get leaderboard for environment.

### Submissions
- `POST /submissions/`: Submit a new agent.
- `GET /submissions/{id}`: Get submission details.
- `DELETE /submissions/{id}`: Remove a submission.

### Example Submission
```json
{
  "user_id": "user123",
  "algorithm": "DQN",
  "env_id": "CartPole-v1",
  "agent_file": "dqn.py"
}
```

---

## Development

### Install Python Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Backend Locally
```bash
uvicorn app.main:app --reload
```

### Run Celery Worker
```bash
celery -A app.core.celery.celery_app worker --loglevel=info
```

---

## Testing
- Add unit tests in the `tests/` directory.
- Run tests with `pytest`:
```bash
pytest
```

---

## Troubleshooting
- **Database Connection Issues**: Ensure PostgreSQL is running and credentials match `.env`.
- **Redis Connection Issues**: Ensure Redis is running and accessible.
- **Docker Errors**: Check Docker daemon status and permissions.
- **Celery Worker Not Running**: Check logs for errors and verify Redis connection.

---

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a pull request

---

## License
MIT License
