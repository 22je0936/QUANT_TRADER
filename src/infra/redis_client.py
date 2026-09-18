"""Redis client factory for low-latency caching (LTP, session state)."""
from __future__ import annotations

from functools import lru_cache

import redis

from src.config.settings import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)
