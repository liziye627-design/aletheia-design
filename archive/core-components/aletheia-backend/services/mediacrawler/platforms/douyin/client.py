# -*- coding: utf-8 -*-
"""
Douyin API Client.
"""

import asyncio
import copy
import json
import urllib.parse
from typing import TYPE_CHECKING, Any, Callable, Dict, Union, Optional, List

import httpx
from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError
from .field import SearchChannelType, SearchSortType, PublishTimeType
from .help import get_web_id, get_a_bogus

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class DouYinClient(AbstractApiClient):
    """Douyin API client for making authenticated requests."""

    def __init__(
        self,
        timeout: int = 60,
        proxy: Optional[str] = None,
        *,
        headers: Dict[str, str],
        playwright_page: Optional[Page] = None,
        cookie_dict: Dict[str, str] = None,
        proxy_ip_pool: Optional["ProxyIpPool"] = None,
    ):
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers
        self._host = "https://www.douyin.com"
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict or {}
        self._proxy_ip_pool = proxy_ip_pool

    async def _refresh_proxy_if_expired(self):
        """Refresh proxy if expired."""
        if self._proxy_ip_pool:
            new_proxy = await self._proxy_ip_pool.get_proxy_if_expired()
            if new_proxy:
                self.proxy = new_proxy

    async def __process_req_params(
        self,
        uri: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        request_method: str = "GET",
    ):
        """Process request parameters with common params and signature."""
        if not params:
            return
        headers = headers or self.headers
        local_storage: Dict = {}
        if self.playwright_page:
            local_storage = await self.playwright_page.evaluate("() => window.localStorage")

        common_params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "version_code": "190600",
            "version_name": "19.6.0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "MacIntel",
            "browser_name": "Chrome",
            "browser_version": "125.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "os_name": "Mac OS",
            "os_version": "10.15.7",
            "cpu_core_num": "8",
            "device_memory": "8",
            "engine_version": "109.0",
            "platform": "PC",
            "screen_width": "2560",
            "screen_height": "1440",
            'effective_type': '4g',
            "round_trip_time": "50",
            "webid": get_web_id(),
            "msToken": local_storage.get("xmst", ""),
        }
        params.update(common_params)
        query_string = urllib.parse.urlencode(params)

        post_data = {}
        if request_method == "POST":
            post_data = params

        if "/v1/web/general/search" not in uri:
            a_bogus = await get_a_bogus(uri, query_string, post_data, headers.get("User-Agent", ""), self.playwright_page)
            params["a_bogus"] = a_bogus

    async def request(self, method: str, url: str, **kwargs) -> Dict:
        """Make HTTP request."""
        await self._refresh_proxy_if_expired()

        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)
        try:
            if response.text == "" or response.text == "blocked":
                logger.error(f"request params error, response.text: {response.text}")
                raise Exception("account blocked")
            return response.json()
        except Exception as e:
            raise DataFetchError(f"{e}, {response.text}")

    async def get(self, uri: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Dict:
        """GET request."""
        await self.__process_req_params(uri, params, headers)
        headers = headers or self.headers
        return await self.request(method="GET", url=f"{self._host}{uri}", params=params, headers=headers)

    async def post(self, uri: str, data: dict, headers: Optional[Dict] = None) -> Dict:
        """POST request."""
        await self.__process_req_params(uri, data, headers)
        headers = headers or self.headers
        return await self.request(method="POST", url=f"{self._host}{uri}", data=data, headers=headers)

    async def pong(self, browser_context: BrowserContext) -> bool:
        """Check if login state is still valid."""
        if self.playwright_page:
            local_storage = await self.playwright_page.evaluate("() => window.localStorage")
            if local_storage.get("HasUserLogin", "") == "1":
                return True

        _, cookie_dict = convert_cookies(await browser_context.cookies())
        return cookie_dict.get("LOGIN_STATUS") == "1"

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies from browser context."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_info_by_keyword(
        self,
        keyword: str,
        offset: int = 0,
        search_channel: SearchChannelType = SearchChannelType.GENERAL,
        sort_type: SearchSortType = SearchSortType.GENERAL,
        publish_time: PublishTimeType = PublishTimeType.UNLIMITED,
        search_id: str = "",
    ) -> Dict:
        """Search videos by keyword."""
        query_params = {
            'search_channel': search_channel.value,
            'enable_history': '1',
            'keyword': keyword,
            'search_source': 'tab_search',
            'query_correct_type': '1',
            'is_filter_search': '0',
            'from_group_id': '7378810571505847586',
            'offset': offset,
            'count': '15',
            'need_filter_settings': '1',
            'list_type': 'multi',
            'search_id': search_id,
        }
        if sort_type.value != SearchSortType.GENERAL.value or publish_time.value != PublishTimeType.UNLIMITED.value:
            query_params["filter_selected"] = json.dumps({
                "sort_type": str(sort_type.value),
                "publish_time": str(publish_time.value)
            })
            query_params["is_filter_search"] = 1
            query_params["search_source"] = "tab_search"
        referer_url = f"https://www.douyin.com/search/{keyword}?aid=f594bbd9-a0e2-4651-9319-ebe3cb6298c1&type=general"
        headers = copy.copy(self.headers)
        headers["Referer"] = urllib.parse.quote(referer_url, safe=':/')
        return await self.get("/aweme/v1/web/general/search/single/", query_params, headers=headers)

    async def get_video_by_id(self, aweme_id: str) -> Dict:
        """Get video detail by ID."""
        params = {"aweme_id": aweme_id}
        headers = copy.copy(self.headers)
        del headers["Origin"]
        res = await self.get("/aweme/v1/web/aweme/detail/", params, headers)
        return res.get("aweme_detail", {})

    async def get_aweme_comments(self, aweme_id: str, cursor: int = 0) -> Dict:
        """Get video comments."""
        uri = "/aweme/v1/web/comment/list/"
        params = {"aweme_id": aweme_id, "cursor": cursor, "count": 20, "item_type": 0}
        return await self.get(uri, params)

    async def get_sub_comments(self, aweme_id: str, comment_id: str, cursor: int = 0) -> Dict:
        """Get sub-comments under parent comment."""
        uri = "/aweme/v1/web/comment/list/reply/"
        params = {
            'comment_id': comment_id,
            "cursor": cursor,
            "count": 20,
            "item_type": 0,
            "item_id": aweme_id,
        }
        return await self.get(uri, params)

    async def get_aweme_all_comments(
        self,
        aweme_id: str,
        crawl_interval: float = 1.0,
        is_fetch_sub_comments: bool = False,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all comments including sub-comments."""
        result = []
        comments_has_more = 1
        comments_cursor = 0
        while comments_has_more and len(result) < max_count:
            comments_res = await self.get_aweme_comments(aweme_id, comments_cursor)
            comments_has_more = comments_res.get("has_more", 0)
            comments_cursor = comments_res.get("cursor", 0)
            comments = comments_res.get("comments", [])
            if not comments:
                continue
            if len(result) + len(comments) > max_count:
                comments = comments[:max_count - len(result)]
            result.extend(comments)
            if callback:
                await callback(aweme_id, comments)

            await asyncio.sleep(crawl_interval)
            if not is_fetch_sub_comments:
                continue
            # Get sub-comments
            for comment in comments:
                reply_comment_total = comment.get("reply_comment_total", 0)
                if reply_comment_total > 0:
                    comment_id = comment.get("cid")
                    sub_comments_has_more = 1
                    sub_comments_cursor = 0

                    while sub_comments_has_more:
                        sub_comments_res = await self.get_sub_comments(aweme_id, comment_id, sub_comments_cursor)
                        sub_comments_has_more = sub_comments_res.get("has_more", 0)
                        sub_comments_cursor = sub_comments_res.get("cursor", 0)
                        sub_comments = sub_comments_res.get("comments", [])

                        if not sub_comments:
                            continue
                        result.extend(sub_comments)
                        if callback:
                            await callback(aweme_id, sub_comments)
                        await asyncio.sleep(crawl_interval)
        return result

    async def get_user_info(self, sec_user_id: str) -> Dict:
        """Get user profile info."""
        uri = "/aweme/v1/web/user/profile/other/"
        params = {
            "sec_user_id": sec_user_id,
            "publish_video_strategy_type": 2,
            "personal_center_strategy": 1,
        }
        return await self.get(uri, params)

    async def get_user_aweme_posts(self, sec_user_id: str, max_cursor: str = "") -> Dict:
        """Get user's video posts."""
        uri = "/aweme/v1/web/aweme/post/"
        params = {
            "sec_user_id": sec_user_id,
            "count": 18,
            "max_cursor": max_cursor,
            "locate_query": "false",
            "publish_video_strategy_type": 2,
        }
        return await self.get(uri, params)

    async def get_all_user_aweme_posts(
        self,
        sec_user_id: str,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """Get all user's video posts."""
        posts_has_more = 1
        max_cursor = ""
        result = []
        while posts_has_more == 1:
            aweme_post_res = await self.get_user_aweme_posts(sec_user_id, max_cursor)
            posts_has_more = aweme_post_res.get("has_more", 0)
            max_cursor = aweme_post_res.get("max_cursor")
            aweme_list = aweme_post_res.get("aweme_list") or []
            logger.info(f"[DouYinClient.get_all_user_aweme_posts] got sec_user_id:{sec_user_id} video len: {len(aweme_list)}")
            if callback:
                await callback(aweme_list)
            result.extend(aweme_list)
        return result

    async def get_aweme_media(self, url: str) -> Optional[bytes]:
        """Download video/image media."""
        async with httpx.AsyncClient(proxy=self.proxy, follow_redirects=True) as client:
            try:
                response = await client.request("GET", url, timeout=self.timeout)
                response.raise_for_status()
                if response.reason_phrase != "OK":
                    logger.error(f"[DouYinClient.get_aweme_media] request {url} error, res:{response.text}")
                    return None
                return response.content
            except httpx.HTTPError as exc:
                logger.error(f"[DouYinClient.get_aweme_media] {exc.__class__.__name__} for {exc.request.url} - {exc}")
                return None

    async def resolve_short_url(self, short_url: str) -> str:
        """Resolve short URL to get the real redirect URL."""
        async with httpx.AsyncClient(proxy=self.proxy, follow_redirects=False) as client:
            try:
                logger.info(f"[DouYinClient.resolve_short_url] Resolving: {short_url}")
                response = await client.get(short_url, timeout=10)
                if response.status_code in [301, 302, 303, 307, 308]:
                    redirect_url = response.headers.get("Location", "")
                    logger.info(f"[DouYinClient.resolve_short_url] Resolved to: {redirect_url}")
                    return redirect_url
                else:
                    logger.warning(f"[DouYinClient.resolve_short_url] Unexpected status: {response.status_code}")
                    return ""
            except Exception as e:
                logger.error(f"[DouYinClient.resolve_short_url] Failed: {e}")
                return ""