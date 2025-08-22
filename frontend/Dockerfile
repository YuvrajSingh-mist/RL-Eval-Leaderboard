
# Frontend service Dockerfile
FROM python:3.10-slim

# Create non-root user
RUN useradd -m appuser
WORKDIR /home/appuser

# Install Gradio and requests
RUN pip install gradio requests

# Copy frontend code
COPY frontend /home/appuser/frontend

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 7860

# Default command for platforms like Render/Heroku that expect a web process
CMD ["python", "/home/appuser/frontend/gradio_app.py"]

