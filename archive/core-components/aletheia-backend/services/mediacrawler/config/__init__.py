# -*- coding: utf-8 -*-
"""
Platform Configuration Module

Contains platform-specific configuration settings.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import os


@dataclass
class CrawlerConfig:
    """Configuration for a crawler instance."""
    # Platform settings
    PLATFORM: str = "xhs"
    LOGIN_TYPE: str = "qrcode"  # qrcode, phone, cookie
    COOKIES: str = ""

    # Browser settings
    HEADLESS: bool = True
    SAVE_LOGIN_STATE: bool = False  # Disabled by default to avoid persistent context issues
    USER_DATA_DIR: str = "user_%s"
    ENABLE_CDP_MODE: bool = False
    CDP_HEADLESS: bool = True

    # Proxy settings
    ENABLE_IP_PROXY: bool = False
    IP_PROXY_POOL_COUNT: int = 5

    # Crawler settings
    CRAWLER_TYPE: str = "search"  # search, detail, creator
    KEYWORDS: str = ""
    START_PAGE: int = 1
    CRAWLER_MAX_NOTES_COUNT: int = 50
    CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES: int = 10
    CRAWLER_MAX_SLEEP_SEC: float = 2.0
    MAX_CONCURRENCY_NUM: int = 5
    SORT_TYPE: str = ""  # general, popularity_descending, time_descending
    ENABLE_GET_COMMENTS: bool = True
    ENABLE_GET_SUB_COMMENTS: bool = False
    ENABLE_GET_MEDIAS: bool = False

    # Platform-specific settings
    XHS_CREATOR_ID_LIST: List[str] = field(default_factory=list)
    XHS_SPECIFIED_NOTE_URL_LIST: List[str] = field(default_factory=list)

    # Storage settings
    SAVE_DATA_OPTION: str = "json"  # json, csv, db
    REQUEST_TIMEOUT: int = 30


@dataclass
class PlatformConfig:
    """Base configuration for a platform crawler."""
    platform: str
    headless: bool = True
    max_concurrent: int = 1
    request_timeout: int = 30
    save_data_option: str = "json"
    enable_comments: bool = False
    enable_sub_comments: bool = False
    cookies: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """Manages platform configurations."""

    _configs: Dict[str, PlatformConfig] = {}
    _crawler_config: Optional[CrawlerConfig] = None

    @classmethod
    def register(cls, config: PlatformConfig):
        """Register a platform configuration."""
        cls._configs[config.platform] = config

    @classmethod
    def get(cls, platform: str) -> Optional[PlatformConfig]:
        """Get configuration for a platform."""
        return cls._configs.get(platform)

    @classmethod
    def update(cls, platform: str, **kwargs):
        """Update configuration for a platform."""
        config = cls._configs.get(platform)
        if config:
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)

    @classmethod
    def set_crawler_config(cls, config: CrawlerConfig):
        """Set the current crawler configuration."""
        cls._crawler_config = config

    @classmethod
    def get_crawler_config(cls) -> Optional[CrawlerConfig]:
        """Get the current crawler configuration."""
        return cls._crawler_config


# Global config instance
_config: Optional[CrawlerConfig] = None


def get_config() -> CrawlerConfig:
    """Get the global crawler configuration."""
    global _config
    if _config is None:
        _config = CrawlerConfig()
    return _config


def set_config(config: CrawlerConfig):
    """Set the global crawler configuration."""
    global _config
    _config = config


def load_config_from_env() -> CrawlerConfig:
    """Load configuration from environment variables."""
    config = CrawlerConfig()
    config.PLATFORM = os.getenv("CRAWLER_PLATFORM", "xhs")
    config.LOGIN_TYPE = os.getenv("CRAWLER_LOGIN_TYPE", "qrcode")
    config.HEADLESS = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
    config.KEYWORDS = os.getenv("CRAWLER_KEYWORDS", "")
    config.CRAWLER_TYPE = os.getenv("CRAWLER_TYPE", "search")
    config.ENABLE_GET_COMMENTS = os.getenv("CRAWLER_ENABLE_COMMENTS", "true").lower() == "true"
    config.ENABLE_GET_MEDIAS = os.getenv("CRAWLER_ENABLE_MEDIAS", "false").lower() == "true"
    return config


# Default configurations for supported platforms
DEFAULT_CONFIGS = {
    "xhs": PlatformConfig(
        platform="xhs",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "dy": PlatformConfig(
        platform="dy",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "bili": PlatformConfig(
        platform="bili",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "wb": PlatformConfig(
        platform="wb",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "zhihu": PlatformConfig(
        platform="zhihu",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "ks": PlatformConfig(
        platform="ks",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
    "tieba": PlatformConfig(
        platform="tieba",
        headless=True,
        max_concurrent=1,
        request_timeout=30,
    ),
}


def _init_configs():
    """Initialize default configurations."""
    for config in DEFAULT_CONFIGS.values():
        ConfigManager.register(config)


_init_configs()