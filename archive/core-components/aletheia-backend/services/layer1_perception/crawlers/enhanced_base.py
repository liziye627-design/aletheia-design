"""
增强爬虫基类 - 集成反爬、性能、稳定性优化
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import time
from .enhanced_utils import (
    UserAgentPool,
    HeaderBuilder,
    retry_on_failure,
    RateLimiter,
    CircuitBreaker,
    SessionPool,
    CrawlerStats,
)
from utils.logging import logger


class EnhancedBaseCrawler(ABC):
    """增强爬虫基类 - 包含完整的反爬与稳定性优化"""

    def __init__(
        self,
        platform_name: str,
        rate_limit: int = 10,
        max_retries: int = 3,
        enable_circuit_breaker: bool = True,
        pool_size: int = 10,
    ):
        """
        初始化增强爬虫

        Args:
            platform_name: 平台名称
            rate_limit: 速率限制(每秒请求数)
            max_retries: 最大重试次数
            enable_circuit_breaker: 是否启用熔断器
            pool_size: 连接池大小
        """
        self.platform_name = platform_name
        self.max_retries = max_retries

        # 速率限制器
        self.rate_limiter = RateLimiter(rate=rate_limit, burst=rate_limit * 2)

        # 熔断器
        self.circuit_breaker = (
            CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60.0,
            )
            if enable_circuit_breaker
            else None
        )

        # HTTP会话池
        self.session_pool = SessionPool(pool_size=pool_size)

        # 统计信息
        self.stats = CrawlerStats()

    async def _make_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_random_ua: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        发起HTTP请求(集成速率限制、重试、熔断)

        Args:
            url: 请求URL
            method: HTTP方法
            headers: 请求头
            params: URL参数
            json_data: JSON数据
            use_random_ua: 是否使用随机User-Agent

        Returns:
            响应数据
        """
        # 速率限制
        await self.rate_limiter.acquire()

        # 构建请求头
        if headers is None:
            headers = HeaderBuilder.build_standard_headers(
                user_agent=UserAgentPool.get_random() if use_random_ua else None
            )

        # 使用重试装饰器包装请求
        @retry_on_failure(max_retries=self.max_retries, base_delay=1.0)
        async def _request():
            start_time = time.time()
            try:
                session = await self.session_pool.get_session()
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                ) as response:
                    latency = time.time() - start_time

                    if response.status >= 400:
                        self.stats.record_request(success=False, latency=latency)
                        raise Exception(
                            f"HTTP {response.status}: {await response.text()}"
                        )

                    self.stats.record_request(success=True, latency=latency)

                    # 根据Content-Type返回不同格式
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        return await response.json()
                    else:
                        return {"text": await response.text()}

            except Exception as e:
                latency = time.time() - start_time
                self.stats.record_request(success=False, latency=latency)
                raise e

        # 使用熔断器
        if self.circuit_breaker:
            return await self.circuit_breaker.call(_request)
        else:
            return await _request()

    def generate_id(self, url: str) -> str:
        """生成唯一ID"""
        return hashlib.md5(f"{self.platform_name}_{url}".encode()).hexdigest()

    def standardize_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据格式

        Returns:
            标准化的数据格式
        """
        return {
            "id": self.generate_id(raw_data.get("url", "")),
            "source_platform": self.platform_name,
            "original_url": raw_data.get("url"),
            "content_text": raw_data.get("text", ""),
            "content_type": self._detect_content_type(raw_data),
            "image_urls": raw_data.get("images", []),
            "video_url": raw_data.get("video"),
            "metadata": {
                "timestamp": raw_data.get("created_at", datetime.utcnow().isoformat()),
                "author_id": raw_data.get("author_id"),
                "author_name": raw_data.get("author_name"),
                "author_follower_count": raw_data.get("followers", 0),
                "engagement_rate": self._calculate_engagement(raw_data),
                "account_age_days": raw_data.get("account_age_days"),
                "likes": raw_data.get("likes", 0),
                "comments": raw_data.get("comments", 0),
                "shares": raw_data.get("shares", 0),
            },
            "entities": raw_data.get("entities", []),
            "created_at": datetime.utcnow().isoformat(),
        }

    def _detect_content_type(self, data: Dict[str, Any]) -> str:
        """检测内容类型"""
        has_image = bool(data.get("images"))
        has_video = bool(data.get("video"))
        has_text = bool(data.get("text"))

        if has_video:
            return "VIDEO" if not has_text else "MIXED"
        elif has_image:
            return "IMAGE" if not has_text else "MIXED"
        else:
            return "TEXT"

    def _calculate_engagement(self, data: Dict[str, Any]) -> float:
        """计算互动率"""
        likes = data.get("likes", 0)
        comments = data.get("comments", 0)
        shares = data.get("shares", 0)
        followers = data.get("followers", 1)  # 避免除零

        total_engagement = likes + comments + shares
        return round(total_engagement / followers, 4) if followers > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.get_stats()

    def is_healthy(self) -> bool:
        """健康检查"""
        return self.stats.is_healthy(min_success_rate=0.8)

    @abstractmethod
    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取热门话题

        Args:
            limit: 返回数量限制

        Returns:
            热门话题列表
        """
        pass

    @abstractmethod
    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户发布的内容

        Args:
            user_id: 用户ID
            limit: 返回数量限制

        Returns:
            用户发布内容列表
        """
        pass

    @abstractmethod
    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取评论

        Args:
            post_id: 帖子ID
            limit: 返回数量限制

        Returns:
            评论列表
        """
        pass

    async def close(self):
        """关闭爬虫,释放资源"""
        await self.session_pool.close()
        stats = self.get_stats()
        logger.info(
            f"🛑 {self.platform_name} crawler closed. "
            f"Stats: {stats['total_requests']} requests, "
            f"{stats['success_rate']:.2%} success rate, "
            f"{stats['average_latency']:.2f}s avg latency"
        )
