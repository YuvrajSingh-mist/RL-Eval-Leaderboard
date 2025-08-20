from app.core.celery import celery_app

if __name__ == "__main__":
    # Start the Celery worker
    celery_app.start()
