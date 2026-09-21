"""
Rate limiting with Redis backend (distributed) + in-memory fallback.

Implements token bucket per user per key.
"""
import time
from collections import defaultdict
from typing import Optional
from fastapi import HTTPException
from ..config import settings

# In-memory fallback store
_in_memory_store = defaultdict(list)

class RateLimiter:
    def __init__(self):
        self.redis_client = None
        self.use_redis = False
        try:
            import redis
            self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            self.use_redis = True
            print(f"RateLimiter using Redis: {settings.REDIS_URL}")
        except Exception as e:
            print(f"RateLimiter fallback to in-memory: {e}")
            self.use_redis = False

    def check(self, user_id: str, key: str, limit: int, window_sec: int = 60):
        bucket_key = f"ratelimit:{user_id}:{key}"
        now = time.time()

        if self.use_redis and self.redis_client:
            try:
                # Use Redis sorted set or simple counter with expiry
                # For simplicity: INCR with expiry
                # We need sliding window: use ZSET
                # Implementation: add current timestamp to sorted set, remove old, count
                pipe = self.redis_client.pipeline()
                pipe.zadd(bucket_key, {str(now): now})
                pipe.zremrangebyscore(bucket_key, 0, now - window_sec)
                pipe.zcard(bucket_key)
                pipe.expire(bucket_key, window_sec + 10)
                results = pipe.execute()
                count = results[2]
                if count > limit:
                    # Remove the just added entry to not count failed attempt? Keep it to enforce limit
                    raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(window_sec)})
                return
            except HTTPException:
                raise
            except Exception as e:
                print(f"Redis rate limit failed {e}, fallback to memory")
                # Fall through to memory

        # In-memory fallback
        timestamps = _in_memory_store[bucket_key]
        timestamps = [t for t in timestamps if now - t < window_sec]
        if len(timestamps) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(window_sec)})
        timestamps.append(now)
        _in_memory_store[bucket_key] = timestamps

rate_limiter = RateLimiter()

def check_rate_limit(user_id: str, key: str, limit: int, window_sec: int = 60):
    return rate_limiter.check(user_id, key, limit, window_sec)
