# -*- coding: utf-8 -*-
"""
XiaoHongShu API Client.
"""

import asyncio
import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

import httpx
from playwright.async_api import BrowserContext, Page
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

from services.mediacrawler.base_crawler import AbstractApiClient
from services.mediacrawler.config import get_config
from services.mediacrawler.utils import convert_cookies, logger

from .exception import DataFetchError, IPBlockError, NoteNotFoundError
from .field import SearchNoteType, SearchSortType
from .help import get_search_id
from .extractor import XiaoHongShuExtractor
from .playwright_sign import sign_with_playwright

if TYPE_CHECKING:
    from services.mediacrawler.proxy_pool import ProxyIpPool


class XiaoHongShuClient(AbstractApiClient):
    """XiaoHongShu API client for making authenticated requests."""

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
        self._host = "https://edith.xiaohongshu.com"
        self._domain = "https://www.xiaohongshu.com"
        self.IP_ERROR_STR = "Network connection error, please check network settings or restart"
        self.IP_ERROR_CODE = 300012
        self.NOTE_NOT_FOUND_CODE = -510000
        self.NOTE_ABNORMAL_STR = "Note status abnormal, please check later"
        self.NOTE_ABNORMAL_CODE = -510001
        self.playwright_page = playwright_page
        self.cookie_dict = cookie_dict
        self._extractor = XiaoHongShuExtractor()
        self._proxy_ip_pool = proxy_ip_pool
        self._config = get_config()

    async def _refresh_proxy_if_expired(self):
        """Refresh proxy if expired."""
        if self._proxy_ip_pool:
            new_proxy = await self._proxy_ip_pool.get_proxy_if_expired()
            if new_proxy:
                self.proxy = new_proxy

    async def _pre_headers(self, url: str, params: Optional[Dict] = None, payload: Optional[Dict] = None) -> Dict:
        """
        Request header parameter signing (using playwright injection method).

        Args:
            url: Request URL
            params: GET request parameters
            payload: POST request parameters

        Returns:
            Signed request header parameters
        """
        a1_value = self.cookie_dict.get("a1", "")

        if params is not None:
            data = params
            method = "GET"
        elif payload is not None:
            data = payload
            method = "POST"
        else:
            raise ValueError("params or payload is required")

        signs = await sign_with_playwright(
            page=self.playwright_page,
            uri=url,
            data=data,
            a1=a1_value,
            method=method,
        )

        headers = {
            "X-S": signs["x-s"],
            "X-T": signs["x-t"],
            "x-S-Common": signs["x-s-common"],
            "X-B3-Traceid": signs["x-b3-traceid"],
        }
        self.headers.update(headers)
        return self.headers

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), retry=retry_if_not_exception_type(NoteNotFoundError))
    async def request(self, method: str, url: str, **kwargs) -> Union[str, Any]:
        """
        Wrapper for httpx common request method.

        Args:
            method: Request method
            url: Request URL
            **kwargs: Other request parameters

        Returns:
            Response data
        """
        await self._refresh_proxy_if_expired()

        return_response = kwargs.pop("return_response", False)
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code == 471 or response.status_code == 461:
            verify_type = response.headers.get("Verifytype", "")
            verify_uuid = response.headers.get("Verifyuuid", "")
            msg = f"CAPTCHA appeared, request failed, Verifytype: {verify_type}, Verifyuuid: {verify_uuid}"
            logger.error(msg)
            raise Exception(msg)

        if return_response:
            return response.text
        data: Dict = response.json()
        if data.get("success"):
            return data.get("data", data.get("success", {}))
        elif data.get("code") == self.IP_ERROR_CODE:
            raise IPBlockError(self.IP_ERROR_STR)
        elif data.get("code") in (self.NOTE_NOT_FOUND_CODE, self.NOTE_ABNORMAL_CODE):
            raise NoteNotFoundError(f"Note not found or abnormal, code: {data.get('code')}")
        else:
            err_msg = data.get("msg", None) or f"{response.text}"
            raise DataFetchError(err_msg)

    async def get(self, uri: str, params: Optional[Dict] = None) -> Dict:
        """
        GET request with signed headers.

        Args:
            uri: Request route
            params: Request parameters

        Returns:
            Response data
        """
        headers = await self._pre_headers(uri, params)
        full_url = f"{self._host}{uri}"
        return await self.request(method="GET", url=full_url, headers=headers, params=params)

    async def post(self, uri: str, data: dict, **kwargs) -> Dict:
        """
        POST request with signed headers.

        Args:
            uri: Request route
            data: Request body parameters

        Returns:
            Response data
        """
        headers = await self._pre_headers(uri, payload=data)
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return await self.request(
            method="POST",
            url=f"{self._host}{uri}",
            data=json_str,
            headers=headers,
            **kwargs,
        )

    async def get_note_media(self, url: str) -> Optional[bytes]:
        """Download note media (image/video)."""
        await self._refresh_proxy_if_expired()

        async with httpx.AsyncClient(proxy=self.proxy) as client:
            try:
                response = await client.request("GET", url, timeout=self.timeout)
                response.raise_for_status()
                if not response.reason_phrase == "OK":
                    logger.error(f"[XiaoHongShuClient.get_note_media] request {url} err, res:{response.text}")
                    return None
                else:
                    return response.content
            except httpx.HTTPError as exc:
                logger.error(f"[XiaoHongShuClient.get_note_media] {exc.__class__.__name__} for {exc.request.url} - {exc}")
                return None

    async def query_self(self) -> Optional[Dict]:
        """Query self user info to check login state."""
        uri = "/api/sns/web/v1/user/selfinfo"
        headers = await self._pre_headers(uri, params={})
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            response = await client.get(f"{self._host}{uri}", headers=headers)
            if response.status_code == 200:
                return response.json()
        return None

    async def pong(self) -> bool:
        """Check if login state is still valid."""
        logger.info("[XiaoHongShuClient.pong] Begin to check login state...")
        ping_flag = False
        try:
            self_info: Dict = await self.query_self()
            if self_info and self_info.get("data", {}).get("result", {}).get("success"):
                ping_flag = True
        except Exception as e:
            logger.error(f"[XiaoHongShuClient.pong] Check login state failed: {e}")
            ping_flag = False
        logger.info(f"[XiaoHongShuClient.pong] Login state result: {ping_flag}")
        return ping_flag

    async def update_cookies(self, browser_context: BrowserContext):
        """Update cookies from browser context."""
        cookie_str, cookie_dict = convert_cookies(await browser_context.cookies())
        self.headers["Cookie"] = cookie_str
        self.cookie_dict = cookie_dict

    async def get_note_by_keyword(
        self,
        keyword: str,
        search_id: str = get_search_id(),
        page: int = 1,
        page_size: int = 20,
        sort: SearchSortType = SearchSortType.GENERAL,
        note_type: SearchNoteType = SearchNoteType.ALL,
    ) -> Dict:
        """
        Search notes by keyword.

        Args:
            keyword: Keyword parameter
            page: Page number
            page_size: Page data length
            sort: Search result sorting
            note_type: Type of note to search

        Returns:
            Search results
        """
        uri = "/api/sns/web/v1/search/notes"
        data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": search_id,
            "sort": sort.value,
            "note_type": note_type.value,
        }
        return await self.post(uri, data)

    async def get_note_by_id(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
    ) -> Dict:
        """
        Get note detail by ID.

        Args:
            note_id: Note ID
            xsec_source: Channel source
            xsec_token: Token from search result

        Returns:
            Note details
        """
        if xsec_source == "":
            xsec_source = "pc_search"

        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        uri = "/api/sns/web/v1/feed"
        res = await self.post(uri, data)
        if res and res.get("items"):
            res_dict: Dict = res["items"][0]["note_card"]
            return res_dict
        logger.error(f"[XiaoHongShuClient.get_note_by_id] get note id:{note_id} empty and res:{res}")
        return dict()

    async def get_note_comments(
        self,
        note_id: str,
        xsec_token: str,
        cursor: str = "",
    ) -> Dict:
        """Get first-level comments."""
        uri = "/api/sns/web/v2/comment/page"
        params = {
            "note_id": note_id,
            "cursor": cursor,
            "top_comment_id": "",
            "image_formats": "jpg,webp,avif",
            "xsec_token": xsec_token,
        }
        return await self.get(uri, params)

    async def get_note_sub_comments(
        self,
        note_id: str,
        root_comment_id: str,
        xsec_token: str,
        num: int = 10,
        cursor: str = "",
    ) -> Dict:
        """Get sub-comments under parent comment."""
        uri = "/api/sns/web/v2/comment/sub/page"
        params = {
            "note_id": note_id,
            "root_comment_id": root_comment_id,
            "num": str(num),
            "cursor": cursor,
            "image_formats": "jpg,webp,avif",
            "top_comment_id": "",
            "xsec_token": xsec_token,
        }
        return await self.get(uri, params)

    async def get_note_all_comments(
        self,
        note_id: str,
        xsec_token: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        max_count: int = 10,
    ) -> List[Dict]:
        """Get all first-level comments under note."""
        result = []
        comments_has_more = True
        comments_cursor = ""
        while comments_has_more and len(result) < max_count:
            comments_res = await self.get_note_comments(
                note_id=note_id, xsec_token=xsec_token, cursor=comments_cursor
            )
            comments_has_more = comments_res.get("has_more", False)
            comments_cursor = comments_res.get("cursor", "")
            if "comments" not in comments_res:
                logger.info(f"[XiaoHongShuClient.get_note_all_comments] No 'comments' key in response: {comments_res}")
                break
            comments = comments_res["comments"]
            if len(result) + len(comments) > max_count:
                comments = comments[: max_count - len(result)]
            if callback:
                await callback(note_id, comments)
            await asyncio.sleep(crawl_interval)
            result.extend(comments)
            sub_comments = await self.get_comments_all_sub_comments(
                comments=comments,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=callback,
            )
            result.extend(sub_comments)
        return result

    async def get_comments_all_sub_comments(
        self,
        comments: List[Dict],
        xsec_token: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
    ) -> List[Dict]:
        """Get all sub-comments under first-level comments."""
        config = self._config
        if not config.ENABLE_GET_SUB_COMMENTS:
            logger.info("[XiaoHongShuClient.get_comments_all_sub_comments] Sub-comment crawling not enabled")
            return []

        result = []
        for comment in comments:
            try:
                note_id = comment.get("note_id")
                sub_comments = comment.get("sub_comments")
                if sub_comments and callback:
                    await callback(note_id, sub_comments)

                sub_comment_has_more = comment.get("sub_comment_has_more")
                if not sub_comment_has_more:
                    continue

                root_comment_id = comment.get("id")
                sub_comment_cursor = comment.get("sub_comment_cursor")

                while sub_comment_has_more:
                    try:
                        comments_res = await self.get_note_sub_comments(
                            note_id=note_id,
                            root_comment_id=root_comment_id,
                            xsec_token=xsec_token,
                            num=10,
                            cursor=sub_comment_cursor,
                        )
                        if comments_res is None:
                            break
                        sub_comment_has_more = comments_res.get("has_more", False)
                        sub_comment_cursor = comments_res.get("cursor", "")
                        if "comments" not in comments_res:
                            break
                        comments = comments_res["comments"]
                        if callback:
                            await callback(note_id, comments)
                        await asyncio.sleep(crawl_interval)
                        result.extend(comments)
                    except DataFetchError as e:
                        logger.warning(f"[XiaoHongShuClient.get_comments_all_sub_comments] Failed: {e}")
                        break
                    except Exception as e:
                        logger.error(f"[XiaoHongShuClient.get_comments_all_sub_comments] Unexpected error: {e}")
                        break
            except Exception as e:
                logger.error(f"[XiaoHongShuClient.get_comments_all_sub_comments] Error processing comment: {e}")
                continue
        return result

    async def get_creator_info(
        self, user_id: str, xsec_token: str = "", xsec_source: str = ""
    ) -> Dict:
        """
        Get user profile by parsing user homepage HTML.
        """
        uri = f"/user/profile/{user_id}"
        if xsec_token and xsec_source:
            uri = f"{uri}?xsec_token={xsec_token}&xsec_source={xsec_source}"

        html_content = await self.request(
            "GET", self._domain + uri, return_response=True, headers=self.headers
        )
        return self._extractor.extract_creator_info_from_html(html_content)

    async def get_notes_by_creator(
        self,
        creator: str,
        cursor: str,
        page_size: int = 30,
        xsec_token: str = "",
        xsec_source: str = "pc_feed",
    ) -> Dict:
        """Get creator's notes."""
        uri = f"/api/sns/web/v1/user_posted"
        params = {
            "num": page_size,
            "cursor": cursor,
            "user_id": creator,
            "xsec_token": xsec_token,
            "xsec_source": xsec_source,
        }
        return await self.get(uri, params)

    async def get_all_notes_by_creator(
        self,
        user_id: str,
        crawl_interval: float = 1.0,
        callback: Optional[Callable] = None,
        xsec_token: str = "",
        xsec_source: str = "pc_feed",
    ) -> List[Dict]:
        """Get all notes by creator."""
        result = []
        notes_has_more = True
        notes_cursor = ""
        max_notes = self._config.CRAWLER_MAX_NOTES_COUNT
        while notes_has_more and len(result) < max_notes:
            notes_res = await self.get_notes_by_creator(
                user_id, notes_cursor, xsec_token=xsec_token, xsec_source=xsec_source
            )
            if not notes_res:
                logger.error("[XiaoHongShuClient.get_all_notes_by_creator] Creator may be banned")
                break

            notes_has_more = notes_res.get("has_more", False)
            notes_cursor = notes_res.get("cursor", "")
            if "notes" not in notes_res:
                break

            notes = notes_res["notes"]
            logger.info(f"[XiaoHongShuClient.get_all_notes_by_creator] got user_id:{user_id} notes len: {len(notes)}")

            remaining = max_notes - len(result)
            if remaining <= 0:
                break

            notes_to_add = notes[:remaining]
            if callback:
                await callback(notes_to_add)

            result.extend(notes_to_add)
            await asyncio.sleep(crawl_interval)

        logger.info(f"[XiaoHongShuClient.get_all_notes_by_creator] Finished for user {user_id}, total: {len(result)}")
        return result

    async def get_note_short_url(self, note_id: str) -> Dict:
        """Get note short URL."""
        uri = f"/api/sns/web/short_url"
        data = {"original_url": f"{self._domain}/discovery/item/{note_id}"}
        return await self.post(uri, data=data, return_response=True)

    async def get_note_by_id_from_html(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        enable_cookie: bool = False,
    ) -> Optional[Dict]:
        """Get note details by parsing note detail page HTML."""
        url = (
            "https://www.xiaohongshu.com/explore/"
            + note_id
            + f"?xsec_token={xsec_token}&xsec_source={xsec_source}"
        )
        copy_headers = self.headers.copy()
        if not enable_cookie:
            del copy_headers["Cookie"]

        html = await self.request(
            method="GET", url=url, return_response=True, headers=copy_headers
        )
        return self._extractor.extract_note_detail_from_html(note_id, html)