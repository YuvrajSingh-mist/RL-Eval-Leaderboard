
import logging
import json
import redis
from datetime import datetime
from app.core.config import settings
from app.models import Submission

logger = logging.getLogger(__name__)

class RedisLeaderboard:
    """Redis-powered leaderboard with real-time sorting"""
    
    def __init__(self):
        self.redis_client = None
        self.leaderboard_key = "leaderboard:{env_id}"
        self.submission_key = "submission:{submission_id}"
        
    def connect(self):
        """Connect to Redis with proper configuration"""
        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                db=settings.REDIS_LEADERBOARD_DB,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis leaderboard")
        except Exception as e:
            logger.critical(f"Failed to connect to Redis: {str(e)}")
            raise
    
    def add_submission(self, submission: Submission):
        """Add submission to leaderboard when completed"""
        if not self.redis_client:
            self.connect()
            
        if submission.status != "completed" or submission.score is None:
            return
            
        try:
            # Create leaderboard key for this environment
            leaderboard_key = self.leaderboard_key.format(env_id=submission.env_id)
            
            # Add to sorted set (score -> submission_id)
            self.redis_client.zadd(leaderboard_key, {submission.id: submission.score})
            
            # Store submission details as hash
            submission_key = self.submission_key.format(submission_id=submission.id)
            submission_data = {
                'user_id': submission.user_id,
                'algorithm': submission.algorithm,
                'score': submission.score,
                'created_at': submission.created_at.isoformat(),
                'env_id': submission.env_id
            }
            self.redis_client.hset(submission_key, mapping=submission_data)
            
            # Set expiration (optional: keep for 30 days)
            self.redis_client.expire(leaderboard_key, 30*24*60*60)  # 30 days
            self.redis_client.expire(submission_key, 30*24*60*60)
            
            logger.info(f"Added submission {submission.id} to {submission.env_id} leaderboard")
            
        except Exception as e:
            logger.error(f"Failed to add submission {submission.id} to leaderboard: {str(e)}")
    
    def get_leaderboard(self, env_id: str, limit: int = 50):
        """Get leaderboard sorted by score (highest first)"""
        if not self.redis_client:
            self.connect()
            
        try:
            leaderboard_key = self.leaderboard_key.format(env_id=env_id)
            
            # Get top N submissions by score (descending)
            # zrevrange = reverse range (highest scores first)
            submission_ids = self.redis_client.zrevrange(
                leaderboard_key, 0, limit-1, withscores=True
            )
            
            if not submission_ids:
                return []
                
            leaderboard = []
            for i, (submission_id_bytes, score) in enumerate(submission_ids):
                submission_id = submission_id_bytes.decode('utf-8')
                submission_key = self.submission_key.format(submission_id=submission_id)
                
                # Get submission details
                data = self.redis_client.hgetall(submission_key)
                if data:
                    # Convert bytes to strings
                    data = {k.decode('utf-8'): v.decode('utf-8') for k, v in data.items()}
                    leaderboard.append({
                        'rank': i + 1,
                        'id': submission_id,
                        'user_id': data.get('user_id', 'Unknown'),
                        'algorithm': data.get('algorithm', 'Unknown'),
                        'score': float(data['score']),
                        'created_at': data['created_at'],
                        'env_id': data['env_id']
                    })
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Failed to get leaderboard for {env_id}: {str(e)}")
            return []
    
    def remove_submission(self, submission_id: str, env_id: str):
        """Remove submission from leaderboard"""
        if not self.redis_client:
            self.connect()
            
        try:
            leaderboard_key = self.leaderboard_key.format(env_id=env_id)
            submission_key = self.submission_key.format(submission_id=submission_id)
            
            # Remove from sorted set
            self.redis_client.zrem(leaderboard_key, submission_id)
            # Remove submission details
            self.redis_client.delete(submission_key)
            
            logger.info(f"Removed submission {submission_id} from {env_id} leaderboard")
            
        except Exception as e:
            logger.error(f"Failed to remove submission {submission_id}: {str(e)}")

# Global instance
redis_leaderboard = RedisLeaderboard()
