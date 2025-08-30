import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.real_metrics import real_metrics

class RealMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Record REAL HTTP metrics
        status_code = str(response.status_code)
        real_metrics.record_http_request(status_code, duration)
        
        return response
