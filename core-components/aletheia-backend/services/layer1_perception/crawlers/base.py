"""
爬虫基类 - 所有平台爬虫的通用接口
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
from utils.logging import logger


class BaseCrawler(ABC):
    """爬虫基类"""

    def __init__(self, platform_name: str, rate_limit: int = 10):
        """
        初始化爬虫

        Args:
            platform_name: 平台名称
            rate_limit: 速率限制(每秒请求数)
        """
        self.platform_name = platform_name
        self.rate_limit = rate_limit
        self._last_request_time = 0.0
        self._request_count = 0

    async def rate_limit_wait(self):
        """速率限制等待"""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < (1.0 / self.rate_limit):
            await asyncio.sleep((1.0 / self.rate_limit) - time_since_last)

        self._last_request_time = asyncio.get_event_loop().time()
        self._request_count += 1

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
        logger.info(
            f"🛑 {self.platform_name} crawler closed. Total requests: {self._request_count}"
        )
