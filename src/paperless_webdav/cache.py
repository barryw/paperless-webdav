# src/paperless_webdav/cache.py
"""Caching layer for WebDAV document content and metadata.

Supports both in-memory caching (single instance) and Redis caching
(multi-instance deployments). Redis is used when configured via
REDIS_LOCK_HOST environment variable.
"""

import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


# Default TTLs in seconds
CONTENT_TTL = 300  # 5 minutes for document content
SIZE_TTL = 300  # 5 minutes for sizes (same as content for consistency)
TAG_MAP_TTL = 300  # 5 minutes for tag mappings


class CacheBackend(Protocol):
    """Protocol for cache backends."""

    def get_content(self, document_id: int) -> bytes | None: ...
    def set_content(self, document_id: int, content: bytes, ttl: float | None = None) -> None: ...
    def get_size(self, document_id: int) -> int | None: ...
    def set_size(self, document_id: int, size: int, ttl: float | None = None) -> None: ...
    def get_tag_map(self, token: str) -> dict[str, int] | None: ...
    def set_tag_map(
        self, token: str, tag_map: dict[str, int], ttl: float | None = None
    ) -> None: ...
    def invalidate_content(self, document_id: int) -> None: ...
    def clear(self) -> None: ...


@dataclass
class CacheEntry:
    """A cached item with expiration."""

    value: Any
    expires_at: float


class InMemoryCache:
    """Thread-safe in-memory cache for single-instance deployments."""

    def __init__(self) -> None:
        self._content_cache: dict[int, CacheEntry] = {}
        self._size_cache: dict[int, CacheEntry] = {}
        self._tag_map_cache: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get_content(self, document_id: int) -> bytes | None:
        with self._lock:
            entry = self._content_cache.get(document_id)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._content_cache[document_id]
                return None
            logger.debug("cache_hit_content", document_id=document_id, backend="memory")
            return entry.value

    def set_content(self, document_id: int, content: bytes, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = CONTENT_TTL
        with self._lock:
            self._content_cache[document_id] = CacheEntry(
                value=content,
                expires_at=time.time() + ttl,
            )
            # Also cache the size since we have the content
            self._size_cache[document_id] = CacheEntry(
                value=len(content),
                expires_at=time.time() + ttl,
            )
        logger.debug(
            "cache_set_content", document_id=document_id, size=len(content), backend="memory"
        )

    def get_size(self, document_id: int) -> int | None:
        with self._lock:
            entry = self._size_cache.get(document_id)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._size_cache[document_id]
                return None
            logger.debug("cache_hit_size", document_id=document_id, backend="memory")
            return entry.value

    def set_size(self, document_id: int, size: int, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = SIZE_TTL
        with self._lock:
            self._size_cache[document_id] = CacheEntry(
                value=size,
                expires_at=time.time() + ttl,
            )
        logger.debug("cache_set_size", document_id=document_id, size=size, backend="memory")

    def get_tag_map(self, token: str) -> dict[str, int] | None:
        cache_key = token[:16] if len(token) >= 16 else token
        with self._lock:
            entry = self._tag_map_cache.get(cache_key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._tag_map_cache[cache_key]
                return None
            logger.debug("cache_hit_tag_map", backend="memory")
            return entry.value

    def set_tag_map(self, token: str, tag_map: dict[str, int], ttl: float | None = None) -> None:
        if ttl is None:
            ttl = TAG_MAP_TTL
        cache_key = token[:16] if len(token) >= 16 else token
        with self._lock:
            self._tag_map_cache[cache_key] = CacheEntry(
                value=tag_map,
                expires_at=time.time() + ttl,
            )
        logger.debug("cache_set_tag_map", tag_count=len(tag_map), backend="memory")

    def invalidate_content(self, document_id: int) -> None:
        with self._lock:
            self._content_cache.pop(document_id, None)
            self._size_cache.pop(document_id, None)
        logger.debug("cache_invalidate", document_id=document_id, backend="memory")

    def clear(self) -> None:
        with self._lock:
            self._content_cache.clear()
            self._size_cache.clear()
            self._tag_map_cache.clear()
        logger.info("cache_cleared", backend="memory")


class RedisCache:
    """Redis-based cache for multi-instance deployments.

    Shares cache across all pods to ensure consistency.
    """

    def __init__(
        self,
        host: str,
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
    ) -> None:
        import redis

        self._redis = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False,  # We handle encoding ourselves
        )
        self._prefix = "paperless-webdav:cache:"
        logger.info("redis_cache_initialized", host=host, port=port, db=db)

    def _content_key(self, document_id: int) -> str:
        return f"{self._prefix}content:{document_id}"

    def _size_key(self, document_id: int) -> str:
        return f"{self._prefix}size:{document_id}"

    def _tag_map_key(self, token: str) -> str:
        cache_key = token[:16] if len(token) >= 16 else token
        return f"{self._prefix}tagmap:{cache_key}"

    def get_content(self, document_id: int) -> bytes | None:
        try:
            content = self._redis.get(self._content_key(document_id))
            if content is not None:
                logger.debug("cache_hit_content", document_id=document_id, backend="redis")
            return content
        except Exception as e:
            logger.warning("redis_cache_error", operation="get_content", error=str(e))
            return None

    def set_content(self, document_id: int, content: bytes, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = CONTENT_TTL
        try:
            # Set content and size atomically with pipeline
            pipe = self._redis.pipeline()
            pipe.setex(self._content_key(document_id), int(ttl), content)
            pipe.setex(self._size_key(document_id), int(ttl), str(len(content)).encode())
            pipe.execute()
            logger.debug(
                "cache_set_content", document_id=document_id, size=len(content), backend="redis"
            )
        except Exception as e:
            logger.warning("redis_cache_error", operation="set_content", error=str(e))

    def get_size(self, document_id: int) -> int | None:
        try:
            size_bytes = self._redis.get(self._size_key(document_id))
            if size_bytes is not None:
                logger.debug("cache_hit_size", document_id=document_id, backend="redis")
                return int(size_bytes.decode())
            return None
        except Exception as e:
            logger.warning("redis_cache_error", operation="get_size", error=str(e))
            return None

    def set_size(self, document_id: int, size: int, ttl: float | None = None) -> None:
        if ttl is None:
            ttl = SIZE_TTL
        try:
            self._redis.setex(self._size_key(document_id), int(ttl), str(size).encode())
            logger.debug("cache_set_size", document_id=document_id, size=size, backend="redis")
        except Exception as e:
            logger.warning("redis_cache_error", operation="set_size", error=str(e))

    def get_tag_map(self, token: str) -> dict[str, int] | None:
        try:
            data = self._redis.get(self._tag_map_key(token))
            if data is not None:
                logger.debug("cache_hit_tag_map", backend="redis")
                return json.loads(data.decode())
            return None
        except Exception as e:
            logger.warning("redis_cache_error", operation="get_tag_map", error=str(e))
            return None

    def set_tag_map(self, token: str, tag_map: dict[str, int], ttl: float | None = None) -> None:
        if ttl is None:
            ttl = TAG_MAP_TTL
        try:
            self._redis.setex(self._tag_map_key(token), int(ttl), json.dumps(tag_map).encode())
            logger.debug("cache_set_tag_map", tag_count=len(tag_map), backend="redis")
        except Exception as e:
            logger.warning("redis_cache_error", operation="set_tag_map", error=str(e))

    def invalidate_content(self, document_id: int) -> None:
        try:
            self._redis.delete(self._content_key(document_id), self._size_key(document_id))
            logger.debug("cache_invalidate", document_id=document_id, backend="redis")
        except Exception as e:
            logger.warning("redis_cache_error", operation="invalidate_content", error=str(e))

    def clear(self) -> None:
        try:
            # Delete all keys with our prefix
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=f"{self._prefix}*", count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
            logger.info("cache_cleared", backend="redis")
        except Exception as e:
            logger.warning("redis_cache_error", operation="clear", error=str(e))


# Global cache instance - initialized lazily
_cache: CacheBackend | None = None
_cache_lock = Lock()


def init_cache(
    redis_host: str | None = None,
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: str | None = None,
) -> None:
    """Initialize the global cache.

    Args:
        redis_host: Redis host (if None, uses in-memory cache)
        redis_port: Redis port (default 6379)
        redis_db: Redis database number (default 0)
        redis_password: Redis password (optional)
    """
    global _cache
    with _cache_lock:
        if redis_host:
            _cache = RedisCache(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
            )
        else:
            _cache = InMemoryCache()
            logger.info("in_memory_cache_initialized")


def get_cache() -> CacheBackend:
    """Get the global cache instance.

    Returns in-memory cache if not explicitly initialized.
    """
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = InMemoryCache()
                logger.info("in_memory_cache_initialized_default")
    return _cache
