"""
MediaCrawler Service Module

Provides multi-platform social media crawling capabilities.
"""

from services.mediacrawler.factory import CrawlerFactory
from services.mediacrawler.base_crawler import (
    AbstractCrawler,
    AbstractLogin,
    AbstractStore,
    AbstractApiClient,
)
from services.mediacrawler.manager import CrawlerManager

__all__ = [
    "CrawlerFactory",
    "CrawlerManager",
    "AbstractCrawler",
    "AbstractLogin",
    "AbstractStore",
    "AbstractApiClient",
]