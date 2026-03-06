# -*- coding: utf-8 -*-
"""
Bilibili API Client.
"""

import asyncio
import json
import random
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

import httpx
from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError
from .field import CommentOrderType, SearchOrderType
from .help import BilibiliSign

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class BilibiliClient(AbstractApiClient):
    """Bilibili API client for making authenticated requests."""

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
        self._host = "https://api.bilibili.com"
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
        try:
            data: Dict = response.json()
        except json.JSONDecodeError:
            logger.error(f"[BilibiliClient.request] Failed to decode JSON. status: {response.status_code}")
            raise DataFetchError(f"Failed to decode JSON, content: {response.text}")
        if data.get("code") != 0:
            raise DataFetchError(data.get("message", "unknown error"))
        return data.get("data", {})

    async def pre_request_data(self, req_data: Dict) -> Dict:
        """Sign request parameters with WBI signature."""
        if not req_data:
            return {}
        img_key, sub_key = await self.get_wbi_keys()
        return BilibiliSign(img_key, sub_key).sign(req_data)

    async def get_wbi_keys(self) -> Tuple[str, str]:
        """Get the latest img_key and sub_key for WBI signature."""
        local_storage = await self.playwright_page.evaluate("() => window.localStorage")
        wbi_img_urls = local_storage.get("wbi_img_urls", "")
        if not wbi_img_urls:
            img_url_from_storage = local_storage.get("wbi_img_url")
            sub_url_from_storage = local_storage.get("wbi_sub_url")
            if img_url_from_storage and sub_url_from_storage:
                wbi_img_urls = f"{img_url_from_storage}-{sub_url_from_storage}"
        if wbi_img_urls and "-" in wbi_img_urls:
            img_url, sub_url = wbi_img_urls.split("-")
        else:
            resp = await self.request(method="GET", url=self._host + "/x/web-interface/nav")
            img_url: str = resp['wbi_img']['img_url']
            sub_url: str = resp['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return img_key, sub_key

    async def get(self, uri: str, params: Dict = None, enable_params_sign: bool = True) -> Dict:
        """GET request with optional parameter signing."""
        final_uri = uri
        if enable_params_sign:
            params = await self.pre_request_data(params)
        if isinstance(params, dict):
            final_uri = f"{uri}?{urlencode(params)}"
        return await self.request(method="GET", url=f"{self._host}{final_uri}", headers=self.headers)

    async def post(self, uri: str, data: dict) -> Dict:
        """POST request with parameter signing."""
        data = await self.pre_request_data(data)
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        return await self.request(method="POST", url=f"{self._host}{uri}", data=json_str, headers=self.headers)

    async def pong(self) -> bool:
        """Check if login state is still valid."""
        logger.info("[BilibiliClient.pong] Checking login state...")
        ping_flag = False
        try:
            check_login_uri = "/x/web-interface/nav"
            response = await self.get(check_login_uri)
            if response.get("isLogin"):
                logger.info("[BilibiliClient.pong] Login state valid")
                ping_flag = True
        except Exception as e:
            logger.error(f"[BilibiliClient.pong] Check failed: {e}")
            ping_flag = False
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies from browser context."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def search_video_by_keyword(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        order: SearchOrderType = SearchOrderType.DEFAULT,
        pubtime_begin_s: int = 0,
        pubtime_end_s: int = 0,
    ) -> Dict:
        """Search videos by keyword."""
        uri = "/x/web-interface/wbi/search/type"
        post_data = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": order.value,
            "pubtime_begin_s": pubtime_begin_s,
            "pubtime_end_s": pubtime_end_s
        }
        return await self.get(uri, post_data)

    async def get_video_info(self, aid: Union[int, None] = None, bvid: Union[str, None] = None) -> Dict:
        """Get video detail by aid or bvid."""
        if not aid and not bvid:
            raise ValueError("Please provide at least one parameter: aid or bvid")

        uri = "/x/web-interface/view/detail"
        params = {}
        if aid:
            params.update({"aid": aid})
        else:
            params.update({"bvid": bvid})
        return await self.get(uri, params, enable_params_sign=False)

    async def get_video_play_url(self, aid: int, cid: int, qn: int = 80) -> Dict:
        """Get video play URL."""
        if not aid or not cid or aid <= 0 or cid <= 0:
            raise ValueError("aid and cid must exist")
        uri = "/x/player/wbi/playurl"
        params = {
            "avid": aid,
            "cid": cid,
            "qn": qn,
            "fourk": 1,
            "fnval": 1,
            "platform": "pc",
        }
        return await self.get(uri, params, enable_params_sign=True)

    async def get_video_media(self, url: str) -> Optional[bytes]:
        """Download video media."""
        async with httpx.AsyncClient(proxy=self.proxy, follow_redirects=True) as client:
            try:
                response = await client.request("GET", url, timeout=self.timeout, headers=self.headers)
                response.raise_for_status()
                if 200 <= response.status_code < 300:
                    return response.content
                logger.error(f"[BilibiliClient.get_video_media] Unexpected status {response.status_code}")
                return None
            except httpx.HTTPError as exc:
                logger.error(f"[BilibiliClient.get_video_media] {exc.__class__.__name__} for {exc.request.url}")
                return None

    async def get_video_comments(
        self,
        video_id: str,
        order_mode: CommentOrderType = CommentOrderType.DEFAULT,
        next_page: int = 0,
    ) -> Dict:
        """Get video comments."""
        uri = "/x/v2/reply/wbi/main"
        post_data = {"oid": video_id, "mode": order_mode.value, "type": 1, "ps": 20, "next": next_page}
        return await self.get(uri, post_data)

    async def get_video_all_comments(
        self,
        video_id: str,
        crawl_interval: float = 1.0,
        is_fetch_sub_comments: bool = False,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all video comments including sub-comments."""
        result = []
        is_end = False
        next_page = 0
        max_retries = 3

        while not is_end and len(result) < max_count:
            comments_res = None
            for attempt in range(max_retries):
                try:
                    comments_res = await self.get_video_comments(video_id, CommentOrderType.DEFAULT, next_page)
                    break
                except DataFetchError as e:
                    if attempt < max_retries - 1:
                        delay = 5 * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"[BilibiliClient] Retrying in {delay:.2f}s...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[BilibiliClient] Max retries reached for video: {video_id}")
                        is_end = True
                        break

            if not comments_res:
                break

            cursor_info: Dict = comments_res.get("cursor", {})
            if not cursor_info:
                break

            comment_list: List[Dict] = comments_res.get("replies", [])

            if "is_end" in cursor_info and "next" in cursor_info:
                is_end = cursor_info.get("is_end")
                next_page = cursor_info.get("next")
            else:
                is_end = True

            if is_fetch_sub_comments:
                for comment in comment_list:
                    comment_id = comment.get('rpid')
                    if comment.get("rcount", 0) > 0:
                        await self.get_video_all_level_two_comments(
                            video_id, comment_id, CommentOrderType.DEFAULT, 10, crawl_interval, callback
                        )

            if len(result) + len(comment_list) > max_count:
                comment_list = comment_list[:max_count - len(result)]

            if callback:
                await callback(video_id, comment_list)

            await asyncio.sleep(crawl_interval)
            if not is_fetch_sub_comments:
                result.extend(comment_list)

        return result

    async def get_video_all_level_two_comments(
        self,
        video_id: str,
        level_one_comment_id: int,
        order_mode: CommentOrderType,
        ps: int = 10,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ):
        """Get all level-two comments for a level-one comment."""
        pn = 1
        while True:
            result = await self.get_video_level_two_comments(video_id, level_one_comment_id, pn, ps, order_mode)
            comment_list: List[Dict] = result.get("replies", [])
            if callback:
                await callback(video_id, comment_list)
            await asyncio.sleep(crawl_interval)
            if int(result["page"]["count"]) <= pn * ps:
                break
            pn += 1

    async def get_video_level_two_comments(
        self,
        video_id: str,
        level_one_comment_id: int,
        pn: int,
        ps: int,
        order_mode: CommentOrderType,
    ) -> Dict:
        """Get level-two comments."""
        uri = "/x/v2/reply/reply"
        post_data = {
            "oid": video_id,
            "mode": order_mode.value,
            "type": 1,
            "ps": ps,
            "pn": pn,
            "root": level_one_comment_id,
        }
        return await self.get(uri, post_data)

    async def get_creator_videos(
        self,
        creator_id: str,
        pn: int,
        ps: int = 30,
        order_mode: SearchOrderType = SearchOrderType.LAST_PUBLISH
    ) -> Dict:
        """Get creator's videos."""
        uri = "/x/space/wbi/arc/search"
        post_data = {
            "mid": creator_id,
            "pn": pn,
            "ps": ps,
            "order": order_mode,
        }
        return await self.get(uri, post_data)

    async def get_creator_info(self, creator_id: int) -> Dict:
        """Get creator profile info."""
        uri = "/x/space/wbi/acc/info"
        post_data = {"mid": creator_id}
        return await self.get(uri, post_data)

    async def get_creator_fans(self, creator_id: int, pn: int, ps: int = 24) -> Dict:
        """Get creator's fans."""
        uri = "/x/relation/fans"
        post_data = {
            'vmid': creator_id,
            "pn": pn,
            "ps": ps,
            "gaia_source": "main_web",
        }
        return await self.get(uri, post_data)

    async def get_creator_followings(self, creator_id: int, pn: int, ps: int = 24) -> Dict:
        """Get creator's followings."""
        uri = "/x/relation/followings"
        post_data = {
            "vmid": creator_id,
            "pn": pn,
            "ps": ps,
            "gaia_source": "main_web",
        }
        return await self.get(uri, post_data)

    async def get_creator_dynamics(self, creator_id: int, offset: str = "") -> Dict:
        """Get creator's dynamics."""
        uri = "/x/polymer/web-dynamic/v1/feed/space"
        post_data = {
            "offset": offset,
            "host_mid": creator_id,
            "platform": "web",
        }
        return await self.get(uri, post_data)