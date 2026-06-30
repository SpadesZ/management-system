# File Path: backend/app/core/redis_client.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from functools import lru_cache

import redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)
