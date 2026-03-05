# -*- coding: utf-8 -*-
"""
Bilibili (B站) Platform Crawler Core Implementation.
"""

import asyncio
import os
from asyncio import Task
from typing import Dict, List, Optional, Union

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

from services.mediacrawler.base_crawler import AbstractCrawler
from services.mediacrawler.config import CrawlerConfig, get_config
from services.mediacrawler.utils import convert_cookies, get_user_agent, logger

from .client import BilibiliClient
from .exception import DataFetchError
from .field import SearchOrderType
from .help import parse_video_info_from_url, parse_creator_info_from_url
from .login import BilibiliLogin


class BilibiliCrawler(AbstractCrawler):
    """Bilibili crawler implementation."""

    context_page: Page
    bili_client: BilibiliClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.bilibili.com"
        self.user_agent = get_user_agent()
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        playwright_proxy_format, httpx_proxy_format = None, None
        if self._config.ENABLE_IP_PROXY:
            pass  # Proxy pool initialization

        async with async_playwright() as playwright:
            if self._config.ENABLE_CDP_MODE:
                logger.info("[BilibiliCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=self._config.CDP_HEADLESS,
                )
            else:
                logger.info("[BilibiliCrawler] Launching browser using standard mode")
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=self._config.HEADLESS
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.bili_client = await self.create_bilibili_client(httpx_proxy_format)
            if not await self.bili_client.pong():
                login_obj = BilibiliLogin(
                    login_type=self._config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.bili_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                specified_list = getattr(self._config, 'BILI_SPECIFIED_ID_LIST', [])
                await self.get_specified_videos(specified_list)
            elif self._config.CRAWLER_TYPE == "creator":
                creator_list = getattr(self._config, 'BILI_CREATOR_ID_LIST', [])
                creator_mode = getattr(self._config, 'CREATOR_MODE', False)
                if creator_mode:
                    for creator_url in creator_list:
                        try:
                            creator_info = parse_creator_info_from_url(creator_url)
                            logger.info(f"[BilibiliCrawler] Parsed creator ID: {creator_info.creator_id}")
                            await self.get_creator_videos(int(creator_info.creator_id))
                        except ValueError as e:
                            logger.error(f"[BilibiliCrawler] Failed to parse creator URL: {e}")
                            continue
                else:
                    await self.get_all_creator_details(creator_list)

            logger.info("[BilibiliCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for videos and retrieve their comment information."""
        logger.info("[BilibiliCrawler.search] Begin search keywords")
        bili_limit_count = 20
        if self._config.CRAWLER_MAX_NOTES_COUNT < bili_limit_count:
            self._config.CRAWLER_MAX_NOTES_COUNT = bili_limit_count

        start_page = self._config.START_PAGE
        for keyword in self._config.KEYWORDS.split(","):
            logger.info(f"[BilibiliCrawler.search] Current keyword: {keyword}")
            page = 1
            while (page - start_page + 1) * bili_limit_count <= self._config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    logger.info(f"[BilibiliCrawler.search] Skip page: {page}")
                    page += 1
                    continue

                logger.info(f"[BilibiliCrawler.search] Searching: {keyword}, page: {page}")
                video_id_list: List[str] = []
                videos_res = await self.bili_client.search_video_by_keyword(
                    keyword=keyword,
                    page=page,
                    page_size=bili_limit_count,
                    order=SearchOrderType.DEFAULT,
                    pubtime_begin_s=0,
                    pubtime_end_s=0,
                )
                video_list: List[Dict] = videos_res.get("result", [])

                if not video_list:
                    logger.info(f"[BilibiliCrawler.search] No more videos for '{keyword}'")
                    break

                semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
                task_list = [
                    self.get_video_info_task(aid=video_item.get("aid"), bvid="", semaphore=semaphore)
                    for video_item in video_list
                ]
                video_items = await asyncio.gather(*task_list)

                for video_item in video_items:
                    if video_item:
                        video_id_list.append(video_item.get("View", {}).get("aid"))
                        await self.store_video(video_item)
                        await self.get_bilibili_video(video_item, semaphore)

                page += 1
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                await self.batch_get_video_comments(video_id_list)

    async def batch_get_video_comments(self, video_id_list: List[str]) -> None:
        """Batch get video comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            logger.info("[BilibiliCrawler.batch_get_video_comments] Comment crawling not enabled")
            return

        logger.info(f"[BilibiliCrawler.batch_get_video_comments] video ids: {video_id_list}")
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for video_id in video_id_list:
            task = asyncio.create_task(self.get_comments(video_id, semaphore), name=str(video_id))
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, video_id: str, semaphore: asyncio.Semaphore) -> None:
        """Get video comments."""
        async with semaphore:
            try:
                logger.info(f"[BilibiliCrawler.get_comments] Getting comments for video: {video_id}")
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                await self.bili_client.get_video_all_comments(
                    video_id=video_id,
                    crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                    is_fetch_sub_comments=self._config.ENABLE_GET_SUB_COMMENTS,
                    callback=self.store_comments,
                    max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                logger.error(f"[BilibiliCrawler.get_comments] Error: {ex}")

    async def get_creator_videos(self, creator_id: int) -> None:
        """Get all videos for a creator."""
        ps = 30
        pn = 1
        while True:
            result = await self.bili_client.get_creator_videos(creator_id, pn, ps)
            video_bvids_list = [video["bvid"] for video in result.get("list", {}).get("vlist", [])]
            await self.get_specified_videos(video_bvids_list)
            page_info = result.get("page", {})
            if page_info.get("count", 0) <= pn * ps:
                break
            await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
            pn += 1

    async def get_specified_videos(self, video_url_list: List[str]) -> None:
        """Get specified videos info from URLs or BV IDs."""
        logger.info("[BilibiliCrawler.get_specified_videos] Parsing video URLs...")
        bvids_list = []
        for video_url in video_url_list:
            try:
                video_info = parse_video_info_from_url(video_url)
                bvids_list.append(video_info.video_id)
                logger.info(f"[BilibiliCrawler.get_specified_videos] Parsed video ID: {video_info.video_id}")
            except ValueError as e:
                logger.error(f"[BilibiliCrawler.get_specified_videos] Failed to parse URL: {e}")
                continue

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_video_info_task(aid=0, bvid=video_id, semaphore=semaphore)
            for video_id in bvids_list
        ]
        video_details = await asyncio.gather(*task_list)
        video_aids_list = []
        for video_detail in video_details:
            if video_detail is not None:
                video_item_view: Dict = video_detail.get("View", {})
                video_aid: str = video_item_view.get("aid")
                if video_aid:
                    video_aids_list.append(video_aid)
                await self.store_video(video_detail)
                await self.get_bilibili_video(video_detail, semaphore)
        await self.batch_get_video_comments(video_aids_list)

    async def get_video_info_task(
        self,
        aid: int,
        bvid: str,
        semaphore: asyncio.Semaphore
    ) -> Optional[Dict]:
        """Get video detail task."""
        async with semaphore:
            try:
                result = await self.bili_client.get_video_info(aid=aid, bvid=bvid)
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                return result
            except DataFetchError as ex:
                logger.error(f"[BilibiliCrawler.get_video_info_task] Error: {ex}")
                return None
            except KeyError as ex:
                logger.error(f"[BilibiliCrawler.get_video_info_task] Key error: {ex}")
                return None

    async def get_video_play_url_task(
        self,
        aid: int,
        cid: int,
        semaphore: asyncio.Semaphore
    ) -> Optional[Dict]:
        """Get video play URL task."""
        async with semaphore:
            try:
                result = await self.bili_client.get_video_play_url(aid=aid, cid=cid)
                return result
            except DataFetchError as ex:
                logger.error(f"[BilibiliCrawler.get_video_play_url_task] Error: {ex}")
                return None

    async def create_bilibili_client(self, httpx_proxy: Optional[str]) -> BilibiliClient:
        """Create Bilibili API client."""
        logger.info("[BilibiliCrawler.create_bilibili_client] Creating API client...")
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        bilibili_client_obj = BilibiliClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://www.bilibili.com",
                "Referer": "https://www.bilibili.com",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
        )
        return bilibili_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context."""
        logger.info("[BilibiliCrawler.launch_browser] Creating browser context...")
        if self._config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "bili")
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                channel="chrome",
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy, channel="chrome")
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser using CDP mode."""
        try:
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)
        except Exception as e:
            logger.error(f"[BilibiliCrawler] CDP mode failed, falling back: {e}")
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self) -> None:
        """Close browser context."""
        await self.browser_context.close()
        logger.info("[BilibiliCrawler.close] Browser context closed")

    async def get_bilibili_video(self, video_item: Dict, semaphore: asyncio.Semaphore) -> None:
        """Download Bilibili video."""
        if not self._config.ENABLE_GET_MEDIAS:
            return

        video_item_view: Dict = video_item.get("View", {})
        aid = video_item_view.get("aid")
        cid = video_item_view.get("cid")
        result = await self.get_video_play_url_task(aid, cid, semaphore)
        if result is None:
            logger.info("[BilibiliCrawler.get_bilibili_video] Failed to get play URL")
            return

        durl_list = result.get("durl", [])
        max_size = -1
        video_url = ""
        for durl in durl_list:
            size = durl.get("size", 0)
            if size > max_size:
                max_size = size
                video_url = durl.get("url", "")

        if not video_url:
            logger.info("[BilibiliCrawler.get_bilibili_video] Failed to get video URL")
            return

        content = await self.bili_client.get_video_media(video_url)
        await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
        if content is None:
            return
        logger.info(f"[BilibiliCrawler.get_bilibili_video] Downloaded video: {aid}")

    async def get_all_creator_details(self, creator_url_list: List[str]) -> None:
        """Get details for creators from URL list."""
        logger.info("[BilibiliCrawler.get_all_creator_details] Parsing creator URLs...")

        creator_id_list = []
        for creator_url in creator_url_list:
            try:
                creator_info = parse_creator_info_from_url(creator_url)
                creator_id_list.append(int(creator_info.creator_id))
                logger.info(f"[BilibiliCrawler] Parsed creator ID: {creator_info.creator_id}")
            except ValueError as e:
                logger.error(f"[BilibiliCrawler] Failed to parse creator URL: {e}")
                continue

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [
            asyncio.create_task(self.get_creator_details(creator_id, semaphore), name=str(creator_id))
            for creator_id in creator_id_list
        ]
        await asyncio.gather(*task_list)

    async def get_creator_details(self, creator_id: int, semaphore: asyncio.Semaphore) -> None:
        """Get details for a creator."""
        async with semaphore:
            creator_unhandled_info: Dict = await self.bili_client.get_creator_info(creator_id)
            creator_info: Dict = {
                "id": creator_id,
                "name": creator_unhandled_info.get("name"),
                "sign": creator_unhandled_info.get("sign"),
                "avatar": creator_unhandled_info.get("face"),
            }
            await self.store_creator(creator_info)

    # Storage methods
    async def store_video(self, video_item: Dict):
        """Store video data."""
        logger.info(f"[BilibiliCrawler.store_video] Storing video")

    async def store_comments(self, video_id: str, comments: List[Dict]):
        """Store comments data."""
        logger.info(f"[BilibiliCrawler.store_comments] Storing {len(comments)} comments")

    async def store_creator(self, creator: Dict):
        """Store creator data."""
        logger.info(f"[BilibiliCrawler.store_creator] Storing creator: {creator.get('id')}")