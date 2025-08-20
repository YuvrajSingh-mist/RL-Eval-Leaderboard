
# Frontend service Dockerfile
FROM python:3.10-slim

# Create non-root user
RUN useradd -m appuser
WORKDIR /home/appuser

# Install Gradio and requests
RUN pip install --no-cache-dir gradio requests

# Copy frontend code
COPY frontend /home/appuser/frontend

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 7860

