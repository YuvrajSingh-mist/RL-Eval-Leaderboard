from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.session import get_db
from app.models import Submission
from datetime import datetime, timedelta
from app.core.real_metrics import real_metrics

router = APIRouter()

@router.get("/prometheus-metrics")
def get_prometheus_metrics(db: Session = Depends(get_db)):
    """Get REAL evaluation metrics in Prometheus format using actual data"""
    
    # Get current counts from database
    total_completed = db.query(func.count(Submission.id)).filter(Submission.status == "completed").scalar()
    total_failed = db.query(func.count(Submission.id)).filter(Submission.status == "failed").scalar()
    total_started = db.query(func.count(Submission.id)).scalar()
    
    # Get counts by environment
    env_stats = db.query(
        Submission.env_id,
        func.count(Submission.id).filter(Submission.status == "completed").label('completed'),
        func.count(Submission.id).filter(Submission.status == "failed").label('failed')
    ).group_by(Submission.env_id).all()
    
    # Build Prometheus format
    prometheus_metrics = []
    
    # Add total metrics
    prometheus_metrics.append(f"# HELP evaluation_completed_total Total evaluations completed")
    prometheus_metrics.append(f"# TYPE evaluation_completed_total counter")
    prometheus_metrics.append(f"evaluation_completed_total {total_completed}")
    
    prometheus_metrics.append(f"# HELP evaluation_failed_total Total evaluations failed")
    prometheus_metrics.append(f"# TYPE evaluation_failed_total counter")
    prometheus_metrics.append(f"evaluation_failed_total {total_failed}")
    
    prometheus_metrics.append(f"# HELP evaluation_started_total Total evaluations started")
    prometheus_metrics.append(f"# TYPE evaluation_started_total counter")
    prometheus_metrics.append(f"evaluation_started_total {total_started}")
    
    # Add environment-specific metrics
    for env_id, completed, failed in env_stats:
        if completed > 0:
            prometheus_metrics.append(f'evaluation_completed_total{{env_id="{env_id}"}} {completed}')
        if failed > 0:
            prometheus_metrics.append(f'evaluation_failed_total{{reason="script_error",env_id="{env_id}"}} {failed}')
    
    # Add REAL evaluation duration histogram from Redis
    prometheus_metrics.append(f"# HELP evaluation_duration_seconds Time spent evaluating a submission")
    prometheus_metrics.append(f"# TYPE evaluation_duration_seconds histogram")
    
    buckets = [0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
    
    # Get REAL durations from Redis for each environment
    for env_id, completed, failed in env_stats:
        if completed > 0:
            real_durations = real_metrics.get_evaluation_durations(env_id)
            
            if real_durations:
                # Add histogram buckets for REAL durations
                for bucket in buckets:
                    count = sum(1 for d in real_durations if d <= bucket)
                    prometheus_metrics.append(f'evaluation_duration_seconds_bucket{{env_id="{env_id}",le="{bucket}"}} {count}')
                
                # Add sum and count
                total_duration = sum(real_durations)
                prometheus_metrics.append(f'evaluation_duration_seconds_sum{{env_id="{env_id}"}} {total_duration}')
                prometheus_metrics.append(f'evaluation_duration_seconds_count{{env_id="{env_id}"}} {len(real_durations)}')
    
    # Get REAL validation failures from Redis
    real_failures = real_metrics.get_validation_failures()
    prometheus_metrics.append(f"# HELP submissions_validation_failures_total Submission validation failures")
    prometheus_metrics.append(f"# TYPE submissions_validation_failures_total counter")
    for reason, count in real_failures.items():
        prometheus_metrics.append(f'submissions_validation_failures_total{{reason="{reason}"}} {count}')
    
    # Get REAL HTTP metrics from Redis
    real_http_metrics = real_metrics.get_http_metrics()
    prometheus_metrics.append(f"# HELP http_requests_total Total HTTP requests")
    prometheus_metrics.append(f"# TYPE http_requests_total counter")
    for status_code, data in real_http_metrics.items():
        prometheus_metrics.append(f'http_requests_total{{status_code="{status_code}"}} {data["count"]}')
    
    # Add HTTP request duration histogram from REAL data
    prometheus_metrics.append(f"# HELP http_request_duration_seconds HTTP request duration")
    prometheus_metrics.append(f"# TYPE http_request_duration_seconds histogram")
    
    http_buckets = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    for status_code, data in real_http_metrics.items():
        if data["durations"]:
            for bucket in http_buckets:
                count = sum(1 for d in data["durations"] if d <= bucket)
                prometheus_metrics.append(f'http_request_duration_seconds_bucket{{status_code="{status_code}",le="{bucket}"}} {count}')
            
            # Add sum and count
            total_duration = sum(data["durations"])
            prometheus_metrics.append(f'http_request_duration_seconds_sum{{status_code="{status_code}"}} {total_duration}')
            prometheus_metrics.append(f'http_request_duration_seconds_count{{status_code="{status_code}"}} {len(data["durations"])}')
    
    return Response(content="\n".join(prometheus_metrics), media_type="text/plain")
