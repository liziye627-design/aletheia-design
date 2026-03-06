# -*- coding: utf-8 -*-
"""
Crawler Factory

Factory class for creating platform-specific crawler instances.
"""

from typing import Dict, Optional, Type

from services.mediacrawler.base_crawler import AbstractCrawler


class CrawlerFactory:
    """
    Factory for creating platform-specific crawlers.

    Supported platforms:
    - xhs: XiaoHongShu (小红书)
    - dy: Douyin (抖音)
    - ks: Kuaishou (快手)
    - bili: Bilibili (B站)
    - wb: Weibo (微博)
    - tieba: Tieba (贴吧)
    - zhihu: Zhihu (知乎)
    """

    # Platform crawler registry - will be populated when platform implementations are added
    _CRAWLERS: Dict[str, Type[AbstractCrawler]] = {}

    @classmethod
    def register(cls, platform: str, crawler_class: Type[AbstractCrawler]):
        """
        Register a crawler class for a platform.

        Args:
            platform: Platform identifier
            crawler_class: Crawler class to register
        """
        cls._CRAWLERS[platform] = crawler_class

    @classmethod
    def create_crawler(cls, platform: str) -> AbstractCrawler:
        """
        Create a crawler instance for the specified platform.

        Args:
            platform: Platform identifier (e.g., 'xhs', 'dy', 'wb')

        Returns:
            Crawler instance

        Raises:
            ValueError: If platform is not supported
        """
        crawler_class = cls._CRAWLERS.get(platform)
        if not crawler_class:
            supported = ", ".join(sorted(cls._CRAWLERS.keys()))
            raise ValueError(
                f"Invalid media platform: {platform!r}. Supported: {supported}"
            )
        return crawler_class()

    @classmethod
    def list_platforms(cls) -> list:
        """List all supported platforms."""
        return list(cls._CRAWLERS.keys())


def _register_platforms():
    """Register all available platform crawlers."""
    try:
        from services.mediacrawler.platforms.xhs import XiaoHongShuCrawler
        CrawlerFactory.register("xhs", XiaoHongShuCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.douyin import DouYinCrawler
        CrawlerFactory.register("dy", DouYinCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.bilibili import BilibiliCrawler
        CrawlerFactory.register("bili", BilibiliCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.weibo import WeiboCrawler
        CrawlerFactory.register("wb", WeiboCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.zhihu import ZhihuCrawler
        CrawlerFactory.register("zhihu", ZhihuCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.kuaishou import KuaishouCrawler
        CrawlerFactory.register("ks", KuaishouCrawler)
    except ImportError:
        pass

    try:
        from services.mediacrawler.platforms.tieba import TieBaCrawler
        CrawlerFactory.register("tieba", TieBaCrawler)
    except ImportError:
        pass


# Auto-register platforms when module is imported
_register_platforms()