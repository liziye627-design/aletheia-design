# -*- coding: utf-8 -*-
"""
Kuaishou API Client.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import httpx
from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class KuaishouClient(AbstractApiClient):
    """Kuaishou API client."""

    def __init__(
        self,
        timeout: int = 60,
        proxy: Optional[str] = None,
        *,
        headers: Dict[str, str],
        playwright_page: Page,
        cookie_dict: Dict[str, str],
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self._host = "https://www.kuaishou.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._proxy_ip_pool = proxy_ip_pool

    async def request(self, method: str, url: str, **kwargs) -> Any:
        """Make HTTP request."""
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code != 200:
            raise DataFetchError(f"Request failed: {response.status_code}")

        return response.json()

    async def get(self, uri: str, params: Dict = None) -> Dict:
        """GET request."""
        return await self.request("GET", f"{self._host}{uri}", params=params, headers=self.headers)

    async def pong(self) -> bool:
        """Check login state."""
        return bool(self.cookie_dict.get("kuaishou.cp.token"))

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_video_by_keyword(self, keyword: str, page: int = 1) -> Dict:
        """Search videos by keyword."""
        uri = "/graphql"
        return await self.get(uri, {"keyword": keyword, "page": page})

    async def get_video_info(self, video_id: str) -> Dict:
        """Get video detail."""
        return await self.get(f"/short-video/{video_id}")

    async def get_video_comments(self, video_id: str, page: int = 1) -> Dict:
        """Get video comments."""
        return await self.get(f"/short-video/{video_id}/comments", {"page": page})

    async def get_video_all_comments(
        self,
        video_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all comments."""
        result = []
        page = 1
        while len(result) < max_count:
            try:
                response = await self.get_video_comments(video_id, page)
                comments = response.get("comments", [])
                if not comments:
                    break
                result.extend(comments[:max_count - len(result)])
                if callback:
                    await callback(video_id, comments)
                page += 1
                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break
        return result

    async def get_creator_info(self, creator_id: str) -> Dict:
        """Get creator profile."""
        return await self.get(f"/profile/{creator_id}")

    async def get_creator_videos(self, creator_id: str, page: int = 1) -> Dict:
        """Get creator's videos."""
        return await self.get(f"/profile/{creator_id}/videos", {"page": page})