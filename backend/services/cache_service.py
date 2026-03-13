"""Cache service with Redis backend and in-memory fallback.

If Redis is unavailable, falls back to a dict-based TTL cache
that respects per-key TTL.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("astrobtc.cache")

REDIS_URL = os.getenv("ASTROBTC_REDIS_URL", "")
_redis_client = None
_redis_checked = False

# In-memory fallback: dict of key → (value, expire_timestamp)
_memory_cache: dict[str, tuple[Any, float]] = {}
_MEMORY_MAX_SIZE = 64


def _get_redis():
    """Lazy-init Redis connection with reconnect on failure."""
    global _redis_client, _redis_checked
    if not REDIS_URL:
        return None
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            logger.warning("Redis connection lost, attempting reconnect...")
            _redis_client = None
    if _redis_checked and _redis_client is None:
        return None
    try:
        import redis as redis_lib
        _redis_client = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        logger.info("Redis connected: %s", REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL)
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable, using in-memory cache")
        _redis_client = None
        _redis_checked = True
        return None


def _memory_get(key: str) -> Any | None:
    entry = _memory_cache.get(key)
    if entry is None:
        return None
    value, expires = entry
    if time.monotonic() > expires:
        _memory_cache.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: Any, ttl: int) -> None:
    if len(_memory_cache) >= _MEMORY_MAX_SIZE:
        now = time.monotonic()
        expired = [k for k, (_, exp) in _memory_cache.items() if now > exp]
        for k in expired:
            _memory_cache.pop(k, None)
        if len(_memory_cache) >= _MEMORY_MAX_SIZE:
            oldest = sorted(_memory_cache, key=lambda k: _memory_cache[k][1])
            for k in oldest[: len(oldest) // 2]:
                _memory_cache.pop(k, None)
    _memory_cache[key] = (value, time.monotonic() + ttl)


def cache_get(key: str) -> Any | None:
    """Get cached value by key."""
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"astrobtc:{key}")
            if raw:
                return json.loads(raw)
            return None
        except Exception:
            logger.debug("Redis get failed for %s", key)
    return _memory_get(key)


def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    """Cache a value with TTL (seconds)."""
    r = _get_redis()
    if r:
        try:
            r.setex(f"astrobtc:{key}", ttl, json.dumps(value, default=str))
            return
        except Exception:
            logger.debug("Redis set failed for %s", key)
    _memory_set(key, value, ttl)


def delete(key: str) -> None:
    """Delete a cached value."""
    r = _get_redis()
    if r:
        try:
            r.delete(f"astrobtc:{key}")
        except Exception:
            logger.debug("Redis delete failed for %s", key)
    _memory_cache.pop(key, None)


def invalidate_all() -> None:
    """Clear all astrobtc keys (after data update)."""
    r = _get_redis()
    if r:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match="astrobtc:*", count=100)
                if keys:
                    r.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            logger.debug("Redis invalidate_all failed")
    _memory_cache.clear()


def is_redis_available() -> bool:
    return _get_redis() is not None


# Backward-compatible aliases (used as `cache_service.get(...)` / `cache_service.set(...)`)
get = cache_get
set = cache_set
