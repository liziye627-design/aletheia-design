"""
Aletheia 缓存工具模块

提供统一的缓存接口、键名管理和缓存策略
"""

import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
from datetime import timedelta
from loguru import logger


class CacheKeyBuilder:
    """缓存键名构建器"""

    # 键名前缀
    PREFIXES = {
        "search": "search",
        "analysis": "analysis",
        "crawler": "crawler",
        "report": "report",
        "user": "user",
        "rate_limit": "rate_limit",
        "session": "session",
    }

    @classmethod
    def build(cls, prefix: str, identifier: str, *args, **kwargs) -> str:
        """
        构建缓存键名

        Args:
            prefix: 前缀类型
            identifier: 标识符
            *args: 额外参数
            **kwargs: 关键字参数

        Returns:
            完整的缓存键名
        """
        key_parts = ["aletheia", cls.PREFIXES.get(prefix, prefix), identifier]

        # 添加额外参数
        if args:
            key_parts.extend(str(arg) for arg in args)

        # 添加关键字参数
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = "_".join(f"{k}:{v}" for k, v in sorted_kwargs)
            key_parts.append(kwargs_str)

        return ":".join(key_parts)

    @classmethod
    def build_hash(cls, prefix: str, data: Any, hash_length: int = 16) -> str:
        """
        基于数据哈希构建缓存键名

        Args:
            prefix: 前缀
            data: 数据（会被 JSON 序列化后哈希）
            hash_length: 哈希长度

        Returns:
            哈希键名
        """
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        hash_value = hashlib.md5(data_str.encode()).hexdigest()[:hash_length]
        return cls.build(prefix, hash_value)


class CacheManager:
    """缓存管理器"""

    def __init__(self, redis_client=None):
        """
        初始化缓存管理器

        Args:
            redis_client: Redis 客户端实例
        """
        self.redis = redis_client
        self._local_cache = {}  # 本地缓存（备用）

    async def get_or_set(
        self,
        key: str,
        getter: Callable[[], Any],
        expire: Optional[int] = None,
        use_local: bool = False,
    ) -> Any:
        """
        获取或设置缓存

        Args:
            key: 缓存键
            getter: 数据获取函数
            expire: 过期时间（秒）
            use_local: 是否使用本地缓存

        Returns:
            缓存值
        """
        # 先尝试获取缓存
        value = await self.get(key, use_local)
        if value is not None:
            logger.debug(f"Cache hit: {key}")
            return value

        # 获取数据
        logger.debug(f"Cache miss: {key}, fetching data...")
        value = await getter() if hasattr(getter, "__call__") else getter

        # 设置缓存
        await self.set(key, value, expire, use_local)

        return value

    async def get(self, key: str, use_local: bool = False) -> Optional[Any]:
        """获取缓存值"""
        try:
            if self.redis:
                value = await self.redis.get(key)
                if value:
                    return json.loads(value)

            if use_local and key in self._local_cache:
                return self._local_cache[key]

        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        use_local: bool = False,
    ) -> bool:
        """设置缓存值"""
        try:
            serialized = json.dumps(value, ensure_ascii=False)

            if self.redis:
                if expire:
                    await self.redis.setex(key, expire, serialized)
                else:
                    await self.redis.set(key, serialized)

            if use_local:
                self._local_cache[key] = value

            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            if self.redis:
                await self.redis.delete(key)

            if key in self._local_cache:
                del self._local_cache[key]

            return True

        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        按模式删除缓存

        Args:
            pattern: 匹配模式（如 "aletheia:search:*"）

        Returns:
            删除的键数量
        """
        try:
            if self.redis:
                keys = await self.redis.keys(pattern)
                if keys:
                    return await self.redis.delete(*keys)

            # 本地缓存清理
            local_keys = [
                k for k in self._local_cache.keys() if pattern.replace("*", "") in k
            ]
            for k in local_keys:
                del self._local_cache[k]

            return len(local_keys)

        except Exception as e:
            logger.warning(f"Cache delete pattern error: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            if self.redis:
                return await self.redis.exists(key) > 0
            return key in self._local_cache
        except Exception:
            return False

    async def ttl(self, key: str) -> int:
        """获取缓存剩余时间"""
        try:
            if self.redis:
                return await self.redis.ttl(key)
            return -1
        except Exception:
            return -1


# 全局缓存管理器实例
cache_manager = CacheManager()


def cached(prefix: str, expire: int = 3600, key_builder: Optional[Callable] = None):
    """
    缓存装饰器

    使用示例:
        @cached("search", expire=300)
        async def search_content(query: str):
            # 搜索逻辑
            return results
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 构建缓存键
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # 默认使用函数名和参数构建键
                key_parts = [prefix, func.__name__]
                if args:
                    key_parts.append(str(args))
                if kwargs:
                    key_parts.append(str(sorted(kwargs.items())))
                cache_key = ":".join(key_parts)

            # 尝试获取缓存
            cached_value = await cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"[Cache Hit] {cache_key}")
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 设置缓存
            await cache_manager.set(cache_key, result, expire)
            logger.debug(f"[Cache Set] {cache_key}, expire={expire}s")

            return result

        return wrapper

    return decorator


def invalidate_cache(prefix: str, pattern: Optional[str] = None):
    """
    缓存失效装饰器

    在函数执行后清除匹配的缓存

    使用示例:
        @invalidate_cache("search", "aletheia:search:*")
        async def update_search_index():
            # 更新逻辑
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # 清除缓存
            cache_pattern = pattern or f"aletheia:{prefix}:*"
            deleted = await cache_manager.delete_pattern(cache_pattern)
            logger.info(f"[Cache Invalidated] {cache_pattern}, deleted={deleted}")

            return result

        return wrapper

    return decorator


# 便捷函数
def get_search_cache_key(query: str, platforms: Optional[list] = None) -> str:
    """获取搜索缓存键"""
    return CacheKeyBuilder.build("search", query, platforms=platforms)


def get_analysis_cache_key(content_hash: str) -> str:
    """获取分析缓存键"""
    return CacheKeyBuilder.build("analysis", content_hash)


def get_crawler_cache_key(platform: str, query: str) -> str:
    """获取爬虫缓存键"""
    return CacheKeyBuilder.build("crawler", platform, query)


# 缓存策略常量
class CacheStrategy:
    """缓存策略配置"""

    # 搜索相关
    SEARCH_RESULTS = 300  # 5分钟
    HOT_TOPICS = 600  # 10分钟
    TRENDING = 300  # 5分钟

    # 分析相关
    ANALYSIS_RESULT = 3600  # 1小时
    CREDIBILITY_SCORE = 1800  # 30分钟

    # 爬虫相关
    CRAWLER_DATA = 1800  # 30分钟
    PLATFORM_STATS = 600  # 10分钟

    # 用户相关
    USER_SESSION = 86400  # 24小时
    USER_PREFERENCES = 3600  # 1小时

    # 限流相关
    RATE_LIMIT = 60  # 1分钟

    # 报告相关
    GENERATED_REPORT = 7200  # 2小时
