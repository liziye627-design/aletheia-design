# -*- coding: utf-8 -*-
"""
Abstract Base Classes for MediaCrawler

Provides abstract interfaces for crawlers, login handlers, storage, and API clients.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from playwright.async_api import BrowserContext, BrowserType, Playwright


class AbstractCrawler(ABC):
    """Abstract base class for all platform crawlers."""

    @abstractmethod
    async def start(self):
        """Start the crawler."""
        pass

    @abstractmethod
    async def search(self):
        """Perform search operation."""
        pass

    @abstractmethod
    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        Launch browser for crawling.

        Args:
            chromium: Chromium browser type
            playwright_proxy: Proxy configuration
            user_agent: User agent string
            headless: Whether to run in headless mode

        Returns:
            Browser context
        """
        pass

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        Launch browser using CDP mode (optional implementation).

        Args:
            playwright: Playwright instance
            playwright_proxy: Proxy configuration
            user_agent: User agent string
            headless: Whether to run in headless mode

        Returns:
            Browser context
        """
        return await self.launch_browser(
            playwright.chromium, playwright_proxy, user_agent, headless
        )


class AbstractLogin(ABC):
    """Abstract base class for login handlers."""

    @abstractmethod
    async def begin(self):
        """Begin login process."""
        pass

    @abstractmethod
    async def login_by_qrcode(self):
        """Login using QR code."""
        pass

    @abstractmethod
    async def login_by_mobile(self):
        """Login using mobile number."""
        pass

    @abstractmethod
    async def login_by_cookies(self):
        """Login using cookies."""
        pass


class AbstractStore(ABC):
    """Abstract base class for data storage."""

    @abstractmethod
    async def store_content(self, content_item: Dict):
        """Store content item."""
        pass

    @abstractmethod
    async def store_comment(self, comment_item: Dict):
        """Store comment item."""
        pass

    @abstractmethod
    async def store_creator(self, creator: Dict):
        """Store creator information."""
        pass


class AbstractStoreImage(ABC):
    """Abstract base class for image storage."""

    async def store_image(self, image_content_item: Dict):
        """Store image content."""
        pass


class AbstractStoreVideo(ABC):
    """Abstract base class for video storage."""

    async def store_video(self, video_content_item: Dict):
        """Store video content."""
        pass


class AbstractApiClient(ABC):
    """Abstract base class for API clients."""

    @abstractmethod
    async def request(self, method, url, **kwargs):
        """Make HTTP request."""
        pass

    @abstractmethod
    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies from browser context."""
        pass