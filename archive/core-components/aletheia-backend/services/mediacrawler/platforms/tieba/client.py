# -*- coding: utf-8 -*-
"""
Tieba API Client.
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


class TieBaClient(AbstractApiClient):
    """Tieba API client."""

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
        self._host = "https://tieba.baidu.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._proxy_ip_pool = proxy_ip_pool

    async def request(self, method: str, url: str, **kwargs) -> Any:
        """Make HTTP request."""
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code != 200:
            raise DataFetchError(f"Request failed: {response.status_code}")

        try:
            return response.json()
        except Exception:
            return {"html": response.text}

    async def get(self, uri: str, params: Dict = None) -> Dict:
        """GET request."""
        return await self.request("GET", f"{self._host}{uri}", params=params, headers=self.headers)

    async def pong(self) -> bool:
        """Check login state."""
        return bool(self.cookie_dict.get("BDUSS"))

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_by_keyword(self, keyword: str, page: int = 1) -> Dict:
        """Search tiezi by keyword."""
        uri = "/f/search/res"
        params = {"qw": keyword, "pn": page}
        return await self.get(uri, params)

    async def get_tiezi_info(self, tiezi_id: str) -> Dict:
        """Get tiezi detail."""
        return await self.get(f"/p/{tiezi_id}")

    async def get_tiezi_comments(
        self,
        tiezi_id: str,
        page: int = 1,
    ) -> Dict:
        """Get tiezi comments (replies)."""
        uri = f"/p/totalComment"
        params = {"tid": tiezi_id, "pn": page}
        return await self.get(uri, params)

    async def get_tiezi_all_comments(
        self,
        tiezi_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all comments for a tiezi."""
        result = []
        page = 1
        while len(result) < max_count:
            try:
                response = await self.get_tiezi_comments(tiezi_id, page)
                comments = response.get("data", {}).get("comment_list", [])
                if not comments:
                    break
                result.extend(comments[:max_count - len(result)])
                if callback:
                    await callback(tiezi_id, comments)
                page += 1
                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break
        return result

    async def get_forum_info(self, forum_name: str) -> Dict:
        """Get forum info."""
        return await self.get(f"/f?kw={forum_name}")

    async def get_forum_tiezis(self, forum_name: str, page: int = 1) -> Dict:
        """Get tiezis from a forum."""
        return await self.get(f"/f?kw={forum_name}&pn={page}")