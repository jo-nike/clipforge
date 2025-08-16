"""
Caching Service for ClipForge
Provides in-memory caching for frequently accessed data like Plex metadata and user sessions
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheService:
    """In-memory cache service with TTL support"""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        # Default TTL values (in seconds)
        self.default_ttl = 300  # 5 minutes
        self.plex_metadata_ttl = 600  # 10 minutes
        self.user_session_ttl = 3600  # 1 hour
        self.storage_stats_ttl = 60  # 1 minute

        logger.info("Cache service initialized with in-memory storage")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        async with self._lock:
            if key not in self._cache:
                return None

            cache_entry = self._cache[key]

            # Check if expired
            if cache_entry["expires_at"] < time.time():
                del self._cache[key]
                logger.debug(f"Cache entry expired and removed: {key}")
                return None

            logger.debug(f"Cache hit: {key}")
            return cache_entry["value"]

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL"""
        if ttl is None:
            ttl = self.default_ttl

        expires_at = time.time() + ttl

        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": time.time(),
            }

        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")

    async def delete(self, key: str) -> bool:
        """Delete value from cache"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache entry deleted: {key}")
                return True
            return False

    async def clear(self) -> None:
        """Clear all cache entries"""
        async with self._lock:
            self._cache.clear()
        logger.info("Cache cleared")

    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed items"""
        current_time = time.time()
        expired_keys = []

        async with self._lock:
            for key, entry in self._cache.items():
                if entry["expires_at"] < current_time:
                    expired_keys.append(key)

            for key in expired_keys:
                del self._cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        async with self._lock:
            current_time = time.time()
            active_entries = 0
            expired_entries = 0
            total_size = 0

            for entry in self._cache.values():
                if entry["expires_at"] >= current_time:
                    active_entries += 1
                else:
                    expired_entries += 1

                # Rough size calculation
                try:
                    entry_size = len(json.dumps(entry["value"], default=str))
                    total_size += entry_size
                except (TypeError, ValueError):
                    total_size += 1024  # Estimate for non-serializable objects

            return {
                "active_entries": active_entries,
                "expired_entries": expired_entries,
                "total_entries": len(self._cache),
                "estimated_size_bytes": total_size,
                "hit_ratio": getattr(self, "_hit_ratio", 0.0),
            }

    # Helper methods for specific cache types

    async def get_plex_metadata(self, library_key: str, media_key: str) -> Optional[Dict[str, Any]]:
        """Get cached Plex metadata"""
        cache_key = f"plex_metadata:{library_key}:{media_key}"
        return await self.get(cache_key)

    async def set_plex_metadata(
        self, library_key: str, media_key: str, metadata: Dict[str, Any]
    ) -> None:
        """Cache Plex metadata"""
        cache_key = f"plex_metadata:{library_key}:{media_key}"
        await self.set(cache_key, metadata, self.plex_metadata_ttl)

    async def get_user_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user session data"""
        cache_key = f"user_session:{session_id}"
        return await self.get(cache_key)

    async def set_user_session_data(self, session_id: str, data: Dict[str, Any]) -> None:
        """Cache user session data"""
        cache_key = f"user_session:{session_id}"
        await self.set(cache_key, data, self.user_session_ttl)

    async def invalidate_user_session(self, session_id: str) -> None:
        """Invalidate cached user session"""
        cache_key = f"user_session:{session_id}"
        await self.delete(cache_key)

    async def get_storage_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached storage statistics"""
        cache_key = f"storage_stats:{user_id}"
        return await self.get(cache_key)

    async def set_storage_stats(self, user_id: str, stats: Dict[str, Any]) -> None:
        """Cache storage statistics"""
        cache_key = f"storage_stats:{user_id}"
        await self.set(cache_key, stats, self.storage_stats_ttl)

    async def invalidate_storage_stats(self, user_id: str) -> None:
        """Invalidate cached storage stats (when files are modified)"""
        cache_key = f"storage_stats:{user_id}"
        await self.delete(cache_key)


class CacheManager:
    """Global cache manager with background cleanup"""

    def __init__(self) -> None:
        self.cache = CacheService()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300  # 5 minutes

    async def start(self) -> None:
        """Start the cache manager with background cleanup"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Cache manager started with background cleanup")

    async def stop(self) -> None:
        """Stop the cache manager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Cache manager stopped")

    async def _cleanup_loop(self) -> None:
        """Background task for cleaning up expired cache entries"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cache.cleanup_expired()

                # Log cache stats periodically
                stats = await self.cache.get_stats()
                logger.debug(
                    f"Cache stats: {stats['active_entries']} active, "
                    f"{stats['expired_entries']} expired, "
                    f"~{stats['estimated_size_bytes']} bytes"
                )

            except asyncio.CancelledError:
                logger.info("Cache cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}", exc_info=True)
                # Continue running even if cleanup fails


# Global cache instance
cache_manager = CacheManager()


def get_cache() -> CacheService:
    """Get the global cache service instance"""
    return cache_manager.cache


async def startup_cache() -> None:
    """Initialize cache on application startup"""
    await cache_manager.start()


async def shutdown_cache() -> None:
    """Cleanup cache on application shutdown"""
    await cache_manager.stop()
