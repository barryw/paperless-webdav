# src/paperless_webdav/cache.py
"""Caching layer for WebDAV document content and metadata."""

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from paperless_webdav.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """A cached item with expiration."""

    value: Any
    expires_at: float


class DocumentCache:
    """Thread-safe cache for document content and metadata.

    Caches:
    - Document content (bytes) - larger TTL since content rarely changes
    - Document sizes (int) - used for PROPFIND responses
    - Tag mappings (dict) - tag name to ID mappings per user

    The cache uses a simple time-based expiration. Entries are lazily
    cleaned up when accessed after expiration.
    """

    # Default TTLs in seconds
    CONTENT_TTL = 300  # 5 minutes for document content
    SIZE_TTL = 60  # 1 minute for sizes (quick to fetch anyway)
    TAG_MAP_TTL = 300  # 5 minutes for tag mappings

    def __init__(self) -> None:
        self._content_cache: dict[int, CacheEntry] = {}
        self._size_cache: dict[int, CacheEntry] = {}
        self._tag_map_cache: dict[str, CacheEntry] = {}  # keyed by user token
        self._lock = Lock()

    def get_content(self, document_id: int) -> bytes | None:
        """Get cached document content.

        Args:
            document_id: The document ID

        Returns:
            Cached content bytes, or None if not cached or expired
        """
        with self._lock:
            entry = self._content_cache.get(document_id)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._content_cache[document_id]
                return None
            logger.debug("cache_hit_content", document_id=document_id)
            return entry.value

    def set_content(self, document_id: int, content: bytes, ttl: float | None = None) -> None:
        """Cache document content.

        Args:
            document_id: The document ID
            content: The document content bytes
            ttl: Optional TTL override in seconds
        """
        if ttl is None:
            ttl = self.CONTENT_TTL
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
        logger.debug("cache_set_content", document_id=document_id, size=len(content))

    def get_size(self, document_id: int) -> int | None:
        """Get cached document size.

        Args:
            document_id: The document ID

        Returns:
            Cached size in bytes, or None if not cached or expired
        """
        with self._lock:
            entry = self._size_cache.get(document_id)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._size_cache[document_id]
                return None
            logger.debug("cache_hit_size", document_id=document_id)
            return entry.value

    def set_size(self, document_id: int, size: int, ttl: float | None = None) -> None:
        """Cache document size.

        Args:
            document_id: The document ID
            size: The document size in bytes
            ttl: Optional TTL override in seconds
        """
        if ttl is None:
            ttl = self.SIZE_TTL
        with self._lock:
            self._size_cache[document_id] = CacheEntry(
                value=size,
                expires_at=time.time() + ttl,
            )
        logger.debug("cache_set_size", document_id=document_id, size=size)

    def get_tag_map(self, token: str) -> dict[str, int] | None:
        """Get cached tag name to ID mapping.

        Args:
            token: The user's API token (used as cache key)

        Returns:
            Dict mapping tag names to IDs, or None if not cached or expired
        """
        # Use first 16 chars of token as key for privacy
        cache_key = token[:16] if len(token) >= 16 else token
        with self._lock:
            entry = self._tag_map_cache.get(cache_key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._tag_map_cache[cache_key]
                return None
            logger.debug("cache_hit_tag_map")
            return entry.value

    def set_tag_map(self, token: str, tag_map: dict[str, int], ttl: float | None = None) -> None:
        """Cache tag name to ID mapping.

        Args:
            token: The user's API token (used as cache key)
            tag_map: Dict mapping tag names to IDs
            ttl: Optional TTL override in seconds
        """
        if ttl is None:
            ttl = self.TAG_MAP_TTL
        cache_key = token[:16] if len(token) >= 16 else token
        with self._lock:
            self._tag_map_cache[cache_key] = CacheEntry(
                value=tag_map,
                expires_at=time.time() + ttl,
            )
        logger.debug("cache_set_tag_map", tag_count=len(tag_map))

    def invalidate_content(self, document_id: int) -> None:
        """Invalidate cached content for a document.

        Args:
            document_id: The document ID
        """
        with self._lock:
            self._content_cache.pop(document_id, None)
            self._size_cache.pop(document_id, None)
        logger.debug("cache_invalidate", document_id=document_id)

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._content_cache.clear()
            self._size_cache.clear()
            self._tag_map_cache.clear()
        logger.info("cache_cleared")


# Global cache instance
_cache = DocumentCache()


def get_cache() -> DocumentCache:
    """Get the global document cache instance."""
    return _cache
