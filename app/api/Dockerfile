
# API service Dockerfile
FROM  python:3.10-slim

RUN set -eux; \
  echo 'Acquire::Retries "5"; Acquire::http::Timeout "20"; Acquire::https::Timeout "20";' > /etc/apt/apt.conf.d/99-retries; \
  apt-get update; \
  apt-get install -y --no-install-recommends \
    build-essential swig ffmpeg libsm6 libxext6 libgl1; \
  rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser
WORKDIR /home/appuser

# Copy minimal API requirements and install (keeps cache stable)
COPY requirements.api.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /home/appuser/app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Command will be set in docker-compose
