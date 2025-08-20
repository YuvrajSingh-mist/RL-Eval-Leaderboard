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
