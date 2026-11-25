"""
Rate limiting (tiêu chí 7) — sliding window lưu trong Redis (sorted set).

State nằm trong Redis nên mọi worker/instance dùng chung và còn nguyên sau khi
restart agent. Key theo hash của API key để không ghi secret vào Redis.
"""
import hashlib
import logging
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    limit = settings.rate_limit_per_minute
    redis_key = "rate:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    now = time.time()
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - WINDOW_SECONDS)
        pipe.zcard(redis_key)
        _, count = pipe.execute()

        if count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = 1
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": WINDOW_SECONDS,
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        pipe = r.pipeline()
        pipe.zadd(redis_key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as exc:  # Redis lỗi: không làm sập /ask, nhưng phải để lại dấu vết
        logger.warning("rate limiter unavailable (redis error): %s", exc)
