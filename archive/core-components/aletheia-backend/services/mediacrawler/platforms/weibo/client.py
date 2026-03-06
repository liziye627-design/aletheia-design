# -*- coding: utf-8 -*-
"""
Weibo API Client.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import httpx
from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError
from .field import SearchType

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class WeiboClient(AbstractApiClient):
    """Weibo API client for making authenticated requests."""

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
        self._host = "https://m.weibo.cn"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._proxy_ip_pool = proxy_ip_pool

    async def _refresh_proxy_if_expired(self):
        """Refresh proxy if expired."""
        if self._proxy_ip_pool:
            new_proxy = await self._proxy_ip_pool.get_proxy_if_expired()
            if new_proxy:
                self.proxy = new_proxy

    async def request(self, method: str, url: str, **kwargs) -> Any:
        """Make HTTP request."""
        await self._refresh_proxy_if_expired()

        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code != 200:
            raise DataFetchError(f"Request failed with status {response.status_code}")

        try:
            return response.json()
        except Exception:
            return response.text

    async def get(self, uri: str, params: Dict = None) -> Dict:
        """GET request."""
        return await self.request("GET", f"{self._host}{uri}", params=params, headers=self.headers)

    async def pong(self) -> bool:
        """Check if login state is still valid."""
        logger.info("[WeiboClient.pong] Checking login state...")
        try:
            response = await self.get("/api/config")
            if response.get("data", {}).get("login"):
                return True
        except Exception:
            pass
        return bool(self.cookie_dict.get("SUB"))

    async def update_cookies(self, browser_context: BrowserContext, urls: List[str] = None):
        """Update cookies from browser context."""
        cookies = await browser_context.cookies(urls=urls)
        cookie_str, cookie_dict = convert_cookies(cookies)
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        search_type: SearchType = SearchType.DEFAULT,
    ) -> Dict:
        """Search notes by keyword."""
        uri = "/api/container/getIndex"
        params = {
            "containerid": f"100103type={search_type.value}&q={keyword}",
            "page_type": "searchall",
            "page": page,
        }
        return await self.get(uri, params)

    async def get_note_info_by_id(self, note_id: str) -> Dict:
        """Get note detail by ID."""
        uri = f"/statuses/extend?id={note_id}"
        return await self.get(uri)

    async def get_note_all_comments(
        self,
        note_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all comments for a note."""
        result = []
        max_id = 0
        while len(result) < max_count:
            uri = "/comments/hotflow"
            params = {"id": note_id, "mid": note_id, "max_id_type": 0}
            if max_id:
                params["max_id"] = max_id

            try:
                response = await self.get(uri, params)
                comments = response.get("data", {}).get("data", [])
                if not comments:
                    break

                if len(result) + len(comments) > max_count:
                    comments = comments[:max_count - len(result)]

                result.extend(comments)
                if callback:
                    await callback(note_id, comments)

                max_id = response.get("data", {}).get("max_id", 0)
                if not max_id:
                    break

                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break

        return result

    async def get_note_image(self, url: str) -> Optional[bytes]:
        """Download note image."""
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            try:
                response = await client.get(url, timeout=self.timeout, headers=self.headers)
                if response.status_code == 200:
                    return response.content
            except Exception:
                pass
        return None

    async def get_creator_info_by_id(self, creator_id: str) -> Dict:
        """Get creator profile by ID."""
        uri = f"/api/container/getIndex?containerid=100505{creator_id}"
        return await self.get(uri)

    async def get_all_notes_by_creator_id(
        self,
        creator_id: str,
        container_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """Get all notes by creator."""
        result = []
        page = 1
        while True:
            uri = "/api/container/getIndex"
            params = {"containerid": container_id, "page": page}
            try:
                response = await self.get(uri, params)
                cards = response.get("data", {}).get("cards", [])
                if not cards:
                    break

                note_list = [card.get("mblog") for card in cards if card.get("card_type") == 9]
                if callback:
                    await callback([{"mblog": n} for n in note_list if n])

                result.extend([{"mblog": n} for n in note_list if n])
                page += 1
                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break
        return result