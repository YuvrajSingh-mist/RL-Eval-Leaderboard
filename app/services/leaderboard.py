
import logging
import json
import redis
from datetime import datetime
from app.core.config import settings
from app.models import Submission, LeaderboardEntry
from app.db.session import SessionLocal

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
                settings.REDIS_URL,  # This uses DB 0
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis leaderboard (DB 0)")
        except Exception as e:
            logger.critical(f"Failed to connect to Redis: {str(e)}")
            raise

    def sync_from_submissions(self, limit: int = 10000):
        """Backfill persistent leaderboard entries from completed submissions.

        This ensures DB durability even if older runs happened before this feature
        or if Redis was empty. Safe to run repeatedly (uses merge/upsert).
        """
        try:
            db = SessionLocal()
            rows = (
                db.query(Submission)
                .filter(Submission.status == "completed")
                .filter(Submission.score.isnot(None))
                .order_by(Submission.created_at.asc())
                .limit(limit)
                .all()
            )
            for s in rows:
                entry = LeaderboardEntry(
                    id=s.id,
                    submission_id=s.id,
                    user_id=s.user_id,
                    env_id=s.env_id,
                    algorithm=s.algorithm,
                    score=s.score,
                    created_at=s.created_at,
                )
                db.merge(entry)
            db.commit()
            logger.info(f"Backfilled {len(rows)} leaderboard entries from submissions")
        except Exception as e:
            logger.error(f"Backfill from submissions failed: {str(e)}")
        finally:
            try:
                db.close()
            except Exception:
                pass

    def warm_redis_from_db(self, limit_per_env: int = 1000):
        """Populate Redis sorted sets from persistent DB entries."""
        if not self.redis_client:
            self.connect()
        try:
            db = SessionLocal()
            # Distinct env_ids
            env_ids = [r[0] for r in db.query(LeaderboardEntry.env_id).distinct().all()]
            for env_id in env_ids:
                rows = (
                    db.query(LeaderboardEntry)
                    .filter(LeaderboardEntry.env_id == env_id)
                    .order_by(LeaderboardEntry.score.desc(), LeaderboardEntry.created_at.asc())
                    .limit(limit_per_env)
                    .all()
                )
                if not rows:
                    continue
                leaderboard_key = self.leaderboard_key.format(env_id=env_id)
                # Clear existing to avoid stale data
                try:
                    self.redis_client.delete(leaderboard_key)
                except Exception:
                    pass
                # Write fresh
                for row in rows:
                    self.redis_client.zadd(leaderboard_key, {row.id: float(row.score)})
                    submission_key = self.submission_key.format(submission_id=row.id)
                    self.redis_client.hset(
                        submission_key,
                        mapping={
                            'user_id': row.user_id or 'Unknown',
                            'algorithm': row.algorithm or 'Unknown',
                            'score': float(row.score),
                            'created_at': row.created_at.isoformat(),
                            'env_id': row.env_id,
                        },
                    )
                    self.redis_client.expire(leaderboard_key, 30*24*60*60)
                    self.redis_client.expire(submission_key, 30*24*60*60)
            logger.info("Redis leaderboard warmed from DB")
        except Exception as e:
            logger.error(f"Warm Redis from DB failed: {str(e)}")
        finally:
            try:
                db.close()
            except Exception:
                pass
    
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
            
            # Set expiration
            self.redis_client.expire(leaderboard_key, 30*24*60*60)
            self.redis_client.expire(submission_key, 30*24*60*60)
            
            logger.info(f"Added submission {submission.id} to {submission.env_id} leaderboard")
            
            # Persist to DB table for durability
            try:
                db = SessionLocal()
                entry = LeaderboardEntry(
                    id=submission.id,
                    submission_id=submission.id,
                    user_id=submission.user_id,
                    env_id=submission.env_id,
                    algorithm=submission.algorithm,
                    score=submission.score,
                    created_at=submission.created_at
                )
                db.merge(entry)  # upsert by primary key
                db.commit()
            except Exception as e:
                logger.error(f"Failed to persist leaderboard entry {submission.id}: {str(e)}")
            finally:
                try:
                    db.close()
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"Failed to add submission {submission.id} to leaderboard: {str(e)}")
    
    def get_leaderboard(self, env_id: str, limit: int = 50):
        """Get leaderboard sorted by score (highest first)"""
        if not self.redis_client:
            self.connect()
            
        try:
            leaderboard_key = self.leaderboard_key.format(env_id=env_id)
            
            # Get top N submissions by score (descending)
            submission_ids = self.redis_client.zrevrange(
                leaderboard_key, 0, limit-1, withscores=True
            )
            
            if not submission_ids:
                # Fallback to DB if Redis empty
                try:
                    db = SessionLocal()
                    rows = db.query(LeaderboardEntry).filter(LeaderboardEntry.env_id == env_id).order_by(LeaderboardEntry.score.desc(), LeaderboardEntry.created_at.asc()).limit(limit).all()
                    return [
                        {
                            'rank': i + 1,
                            'id': row.id,
                            'user_id': row.user_id,
                            'algorithm': row.algorithm,
                            'score': float(row.score),
                            'created_at': row.created_at.isoformat(),
                            'env_id': row.env_id
                        }
                        for i, row in enumerate(rows)
                    ]
                except Exception as e:
                    logger.error(f"DB fallback failed for leaderboard {env_id}: {str(e)}")
                    return []
                finally:
                    try:
                        db.close()
                    except Exception:
                        pass
                
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
