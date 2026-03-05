# -*- coding: utf-8 -*-
"""
Zhihu API Client.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import httpx
from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError
from .help import ZhihuExtractor
from .models import ZhihuContent, ZhihuCreator

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class ZhiHuClient(AbstractApiClient):
    """Zhihu API client for making authenticated requests."""

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
        self._host = "https://www.zhihu.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._proxy_ip_pool = proxy_ip_pool
        self._extractor = ZhihuExtractor()

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
        logger.info("[ZhiHuClient.pong] Checking login state...")
        return bool(self.cookie_dict.get("z_c0") or self.cookie_dict.get("_xsrf"))

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies from browser context."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        page: int = 1,
    ) -> List[ZhihuContent]:
        """Search content by keyword."""
        uri = "/api/v4/search_v3"
        params = {
            "t": "general",
            "q": keyword,
            "correction": 1,
            "offset": (page - 1) * 20,
            "limit": 20,
        }

        try:
            response = await self.get(uri, params)
            items = response.get("data", [])
            result = []
            for item in items:
                content = self._extractor.extract_content_from_search(item)
                if content:
                    result.append(content)
            return result
        except DataFetchError:
            return []

    async def get_answer_info(self, question_id: str, answer_id: str) -> Optional[ZhihuContent]:
        """Get answer detail."""
        uri = f"/api/v4/answers/{answer_id}"
        params = {"question_id": question_id}

        try:
            response = await self.get(uri, params)
            return ZhihuContent(
                content_id=answer_id,
                content_type="answer",
                title=response.get("question", {}).get("title", ""),
                text=response.get("excerpt", ""),
                author=response.get("author", {}),
            )
        except DataFetchError:
            return None

    async def get_article_info(self, article_id: str) -> Optional[ZhihuContent]:
        """Get article detail."""
        uri = f"/api/v4/articles/{article_id}"

        try:
            response = await self.get(uri)
            return ZhihuContent(
                content_id=article_id,
                content_type="article",
                title=response.get("title", ""),
                text=response.get("excerpt", ""),
                author=response.get("author", {}),
            )
        except DataFetchError:
            return None

    async def get_video_info(self, video_id: str) -> Optional[ZhihuContent]:
        """Get video detail."""
        uri = f"/api/v4/zvideos/{video_id}"

        try:
            response = await self.get(uri)
            return ZhihuContent(
                content_id=video_id,
                content_type="video",
                title=response.get("title", ""),
                text=response.get("description", ""),
                author=response.get("author", {}),
            )
        except DataFetchError:
            return None

    async def get_note_all_comments(
        self,
        content: ZhihuContent,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """Get all comments for content."""
        result = []
        offset = 0
        limit = 20

        if content.content_type == "answer":
            uri = f"/api/v4/answers/{content.content_id}/comments"
        elif content.content_type == "article":
            uri = f"/api/v4/articles/{content.content_id}/comments"
        else:
            return result

        while True:
            params = {"offset": offset, "limit": limit}
            try:
                response = await self.get(uri, params)
                comments = response.get("data", [])
                if not comments:
                    break

                if callback:
                    await callback(content.content_id, comments)

                result.extend(comments)
                offset += limit

                if not response.get("paging", {}).get("is_end", True):
                    break

                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break

        return result

    async def get_creator_info(self, url_token: str) -> Optional[ZhihuCreator]:
        """Get creator profile by URL token."""
        uri = f"/api/v4/members/{url_token}"

        try:
            response = await self.get(uri)
            return self._extractor.extract_creator_from_response(response)
        except DataFetchError:
            return None

    async def get_all_anwser_by_creator(
        self,
        creator: ZhihuCreator,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[ZhihuContent]:
        """Get all answers by creator."""
        result = []
        offset = 0
        limit = 20

        while True:
            uri = f"/api/v4/members/{creator.url_token}/answers"
            params = {"offset": offset, "limit": limit}

            try:
                response = await self.get(uri, params)
                items = response.get("data", [])
                if not items:
                    break

                contents = []
                for item in items:
                    content = ZhihuContent(
                        content_id=str(item.get("id", "")),
                        content_type="answer",
                        title=item.get("question", {}).get("title", ""),
                        text=item.get("excerpt", ""),
                        author=item.get("author", {}),
                    )
                    contents.append(content)

                if callback:
                    await callback(contents)

                result.extend(contents)
                offset += limit

                if not response.get("paging", {}).get("is_end", True):
                    break

                await asyncio.sleep(crawl_interval)
            except DataFetchError:
                break

        return result