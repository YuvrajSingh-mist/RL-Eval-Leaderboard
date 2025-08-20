
# API service Dockerfile
FROM  python:3.10-slim

# Create non-root user
RUN useradd -m appuser
WORKDIR /home/appuser

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /home/appuser/app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Command will be set in docker-compose
