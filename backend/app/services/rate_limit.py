# File Path: backend/app/services/rate_limit.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from datetime import UTC, datetime

from app.core.redis_client import get_redis_client


class RateLimitResult:
    def __init__(self, allowed: bool, remaining: int) -> None:
        self.allowed = allowed
        self.remaining = remaining


def check_rpm_limit(scope_key: str, rpm_limit: int) -> RateLimitResult:
    now = datetime.now(UTC)
    minute_bucket = now.strftime("%Y%m%d%H%M")
    redis_key = f"ratelimit:{scope_key}:{minute_bucket}"

    client = get_redis_client()
    pipeline = client.pipeline()
    pipeline.incr(redis_key)
    pipeline.expire(redis_key, 120)
    result = pipeline.execute()
    current_count = int(result[0])

    if current_count > rpm_limit:
        return RateLimitResult(allowed=False, remaining=0)
    return RateLimitResult(allowed=True, remaining=max(0, rpm_limit - current_count))
