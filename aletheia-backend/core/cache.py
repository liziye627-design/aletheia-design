"""
Redis缓存管理 - 增强版

Features:
- Connection pool for efficient connection management
- Auto-reconnect with exponential backoff
- Graceful error handling in all methods
- Health check functionality
- Clean shutdown support
"""

import asyncio
import json
from typing import Any, Optional

from redis.asyncio import ConnectionPool, Redis
from loguru import logger

from core.config import settings


class RedisCache:
    """Redis缓存管理器 - 支持连接池和自动重连"""

    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self.redis: Optional[Redis] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._is_reconnecting = False
        self._reconnect_backoff = 1.0  # Initial backoff in seconds
        self._max_backoff = 60.0  # Maximum backoff in seconds
        self._check_interval = 10  # Health check interval in seconds
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Redis with connection pool"""
        async with self._lock:
            try:
                # Close existing connections if any
                if self.redis:
                    try:
                        await self.redis.close()
                    except Exception:
                        pass
                if self.pool:
                    try:
                        await self.pool.disconnect()
                    except Exception:
                        pass

                # Create connection pool
                self.pool = ConnectionPool.from_url(
                    str(settings.REDIS_URL),
                    max_connections=20,
                    socket_connect_timeout=2,
                    socket_timeout=5,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                    decode_responses=True,
                )
                self.redis = Redis(connection_pool=self.pool)

                # Test connection
                await self.redis.ping()
                self._reconnect_backoff = 1.0  # Reset backoff on success
                logger.info("Redis connection pool established")

            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                self.redis = None
                raise

    async def _reconnect_loop(self) -> None:
        """Background task to reconnect on failure"""
        while True:
            try:
                await asyncio.sleep(self._check_interval)

                if self.redis is None and settings.REDIS_ENABLED:
                    try:
                        await self.connect()
                        logger.info("Redis reconnected successfully")
                        self._is_reconnecting = False
                    except Exception as e:
                        logger.warning(
                            f"Redis reconnect failed: {e}, retrying in {self._reconnect_backoff}s"
                        )
                        self._is_reconnecting = True
                        await asyncio.sleep(self._reconnect_backoff)
                        self._reconnect_backoff = min(
                            self._reconnect_backoff * 2, self._max_backoff
                        )
                elif self.redis:
                    # Health check for existing connection
                    try:
                        await self.redis.ping()
                    except Exception as e:
                        logger.warning(f"Redis health check failed: {e}, marking for reconnection")
                        self.redis = None
                        self._is_reconnecting = True

            except asyncio.CancelledError:
                logger.info("Redis reconnect loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in reconnect loop: {e}")
                await asyncio.sleep(self._check_interval)

    async def start_reconnect_task(self) -> None:
        """Start the background reconnection task"""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            logger.info("Redis reconnect background task started")

    async def _ensure_connection(self) -> bool:
        """Ensure we have a valid connection

        Returns:
            True if connected, False otherwise
        """
        if self.redis is None:
            return False

        try:
            await self.redis.ping()
            return True
        except Exception:
            logger.warning("Redis connection lost, marking for reconnection")
            self.redis = None
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis:
            return None

        try:
            value = await self.redis.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.warning(f"Redis get error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return None

    async def set(
        self, key: str, value: Any, expire: int = None
    ) -> bool:
        """Set value in cache

        Args:
            key: Cache key
            value: Value to cache
            expire: Expiration time in seconds (defaults to CACHE_DEFAULT_TIMEOUT)

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)

            ttl = expire if expire is not None else settings.CACHE_DEFAULT_TIMEOUT
            await self.redis.set(key, value, ex=ttl)
            return True
        except Exception as e:
            logger.warning(f"Redis set error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis delete error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.redis:
            return False

        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter

        Returns:
            New value after increment, or 0 on error
        """
        if not self.redis:
            return 0

        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.warning(f"Redis increment error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return 0

    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement counter

        Returns:
            New value after decrement, or 0 on error
        """
        if not self.redis:
            return 0

        try:
            return await self.redis.decrby(key, amount)
        except Exception as e:
            logger.warning(f"Redis decrement error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration time for key

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            await self.redis.expire(key, seconds)
            return True
        except Exception as e:
            logger.warning(f"Redis expire error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return False

    async def ttl(self, key: str) -> int:
        """Get remaining TTL for key

        Returns:
            TTL in seconds, -1 if no expiration, -2 on error
        """
        if not self.redis:
            return -2

        try:
            return await self.redis.ttl(key)
        except Exception as e:
            logger.warning(f"Redis ttl error for key '{key}': {e}")
            self.redis = None  # Mark for reconnection
            return -2

    async def keys(self, pattern: str) -> list[str]:
        """Find keys matching pattern

        Returns:
            List of matching keys
        """
        if not self.redis:
            return []

        try:
            return await self.redis.keys(pattern)
        except Exception as e:
            logger.warning(f"Redis keys error for pattern '{pattern}': {e}")
            self.redis = None  # Mark for reconnection
            return []

    async def flush_db(self) -> bool:
        """Clear all keys in current database

        Use with caution!

        Returns:
            True if successful, False otherwise
        """
        if not self.redis:
            return False

        try:
            await self.redis.flushdb()
            logger.warning("Redis database flushed")
            return True
        except Exception as e:
            logger.error(f"Redis flush_db error: {e}")
            self.redis = None
            return False

    async def mget(self, keys: list[str]) -> list[Optional[Any]]:
        """Get multiple values at once

        Returns:
            List of values (None for missing keys or errors)
        """
        if not self.redis or not keys:
            return [None] * len(keys)

        try:
            values = await self.redis.mget(keys)
            result = []
            for value in values:
                if value:
                    try:
                        result.append(json.loads(value))
                    except json.JSONDecodeError:
                        result.append(value)
                else:
                    result.append(None)
            return result
        except Exception as e:
            logger.warning(f"Redis mget error: {e}")
            self.redis = None  # Mark for reconnection
            return [None] * len(keys)

    async def mset(self, mapping: dict[str, Any], expire: int = None) -> bool:
        """Set multiple values at once

        Args:
            mapping: Dict of key-value pairs to set
            expire: Optional expiration time in seconds for all keys

        Returns:
            True if successful, False otherwise
        """
        if not self.redis or not mapping:
            return False

        try:
            # Serialize values
            serialized = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    serialized[key] = json.dumps(value, ensure_ascii=False)
                else:
                    serialized[key] = value

            # Use pipeline for atomic operation with TTL
            async with self.redis.pipeline() as pipe:
                pipe.mset(serialized)
                if expire:
                    for key in serialized.keys():
                        pipe.expire(key, expire)
                await pipe.execute()
            return True
        except Exception as e:
            logger.warning(f"Redis mset error: {e}")
            self.redis = None  # Mark for reconnection
            return False

    async def close(self) -> None:
        """Close connection and stop reconnection task"""
        logger.info("Closing Redis connection...")

        # Cancel reconnect task
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Close Redis connection
        if self.redis:
            try:
                await self.redis.close()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            self.redis = None

        # Disconnect pool
        if self.pool:
            try:
                await self.pool.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting Redis pool: {e}")
            self.pool = None

        logger.info("Redis connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self.redis is not None

    @property
    def is_reconnecting(self) -> bool:
        """Check if currently attempting to reconnect"""
        return self._is_reconnecting


# Global cache instance
cache = RedisCache()


async def get_cache() -> RedisCache:
    """Dependency injection: get cache instance"""
    return cache


async def check_redis_health() -> dict:
    """Check Redis health status

    Returns:
        Dict with health status information
    """
    result = {
        "status": "unknown",
        "enabled": settings.REDIS_ENABLED,
        "connected": False,
    }

    if not settings.REDIS_ENABLED:
        result["status"] = "disabled"
        return result

    try:
        if cache.redis is None:
            result["status"] = "unavailable"
            result["is_reconnecting"] = cache.is_reconnecting
            return result

        # Ping to verify connection
        await cache.redis.ping()
        result["connected"] = True

        # Get server info
        info = await cache.redis.info()

        result.update(
            {
                "status": "healthy",
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "total_connections_received": info.get("total_connections_received"),
                "total_commands_processed": info.get("total_commands_processed"),
                "uptime_in_seconds": info.get("uptime_in_seconds"),
                "redis_version": info.get("redis_version"),
            }
        )

        # Get pool stats if available
        if cache.pool:
            result["pool_max_connections"] = 20  # From our configuration

    except Exception as e:
        result["status"] = "unhealthy"
        result["error"] = str(e)
        result["is_reconnecting"] = cache.is_reconnecting

    return result


async def init_redis() -> None:
    """Initialize Redis connection and start reconnect task

    This should be called during application startup.
    """
    if not settings.REDIS_ENABLED:
        logger.info("Redis is disabled, skipping connection")
        return

    try:
        await cache.connect()
        await cache.start_reconnect_task()
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        # Start reconnect task anyway to retry in background
        await cache.start_reconnect_task()


async def shutdown_redis() -> None:
    """Shutdown Redis connection

    This should be called during application shutdown.
    """
    await cache.close()