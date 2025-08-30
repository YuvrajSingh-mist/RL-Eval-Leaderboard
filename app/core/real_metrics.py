import redis
import json
import time
from typing import Dict, List, Optional
from app.core.config import settings

class RealMetricsTracker:
    """Track REAL metrics using Redis for persistence across processes"""
    
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL)
        self.metrics_prefix = "real_metrics:"
    
    def record_evaluation_duration(self, env_id: str, duration_seconds: float):
        """Record REAL evaluation duration"""
        key = f"{self.metrics_prefix}evaluation_duration:{env_id}"
        self.redis_client.lpush(key, duration_seconds)
        # Keep only last 1000 durations per environment
        self.redis_client.ltrim(key, 0, 999)
        # Set expiry to 7 days
        self.redis_client.expire(key, 7 * 24 * 3600)
    
    def record_validation_failure(self, reason: str):
        """Record REAL validation failure"""
        key = f"{self.metrics_prefix}validation_failures:{reason}"
        self.redis_client.incr(key)
        # Set expiry to 7 days
        self.redis_client.expire(key, 7 * 24 * 3600)
    
    def record_http_request(self, status_code: str, duration_seconds: float):
        """Record REAL HTTP request"""
        # Count by status code
        count_key = f"{self.metrics_prefix}http_requests:{status_code}"
        self.redis_client.incr(count_key)
        self.redis_client.expire(count_key, 7 * 24 * 3600)
        
        # Duration histogram
        duration_key = f"{self.metrics_prefix}http_duration:{status_code}"
        self.redis_client.lpush(duration_key, duration_seconds)
        self.redis_client.ltrim(duration_key, 0, 999)
        self.redis_client.expire(duration_key, 7 * 24 * 3600)
    
    def get_evaluation_durations(self, env_id: str) -> List[float]:
        """Get REAL evaluation durations for an environment"""
        key = f"{self.metrics_prefix}evaluation_duration:{env_id}"
        durations = self.redis_client.lrange(key, 0, -1)
        return [float(d) for d in durations]
    
    def get_validation_failures(self) -> Dict[str, int]:
        """Get REAL validation failure counts"""
        pattern = f"{self.metrics_prefix}validation_failures:*"
        keys = self.redis_client.keys(pattern)
        failures = {}
        for key in keys:
            reason = key.decode().split(":")[-1]
            count = int(self.redis_client.get(key) or 0)
            failures[reason] = count
        return failures
    
    def get_http_metrics(self) -> Dict[str, Dict]:
        """Get REAL HTTP request metrics"""
        # Get counts by status code
        count_pattern = f"{self.metrics_prefix}http_requests:*"
        count_keys = self.redis_client.keys(count_pattern)
        
        # Get durations by status code
        duration_pattern = f"{self.metrics_prefix}http_duration:*"
        duration_keys = self.redis_client.keys(duration_pattern)
        
        metrics = {}
        for key in count_keys:
            status_code = key.decode().split(":")[-1]
            count = int(self.redis_client.get(key) or 0)
            metrics[status_code] = {"count": count, "durations": []}
        
        for key in duration_keys:
            status_code = key.decode().split(":")[-1]
            durations = self.redis_client.lrange(key, 0, -1)
            if status_code in metrics:
                metrics[status_code]["durations"] = [float(d) for d in durations]
        
        return metrics

# Global instance
real_metrics = RealMetricsTracker()
