# -*- coding: utf-8 -*-
"""
Douyin (抖音) Platform Crawler Core Implementation.
"""

import asyncio
import os
import random
from asyncio import Task
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

from services.mediacrawler.base_crawler import AbstractCrawler
from services.mediacrawler.config import CrawlerConfig, get_config
from services.mediacrawler.utils import convert_cookies, format_proxy_info, logger

from .client import DouYinClient
from .exception import DataFetchError
from .field import PublishTimeType
from .help import parse_video_info_from_url, parse_creator_info_from_url
from .login import DouYinLogin
from .models import VideoUrlInfo


class DouYinCrawler(AbstractCrawler):
    """Douyin crawler implementation."""

    context_page: Page
    dy_client: DouYinClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.douyin.com"
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        playwright_proxy_format, httpx_proxy_format = None, None
        if self._config.ENABLE_IP_PROXY:
            pass  # Proxy pool initialization

        async with async_playwright() as playwright:
            if self._config.ENABLE_CDP_MODE:
                logger.info("[DouYinCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    None,
                    headless=self._config.CDP_HEADLESS,
                )
            else:
                logger.info("[DouYinCrawler] Launching browser using standard mode")
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    user_agent=None,
                    headless=self._config.HEADLESS,
                )
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.dy_client = await self.create_douyin_client(httpx_proxy_format)
            if not await self.dy_client.pong(browser_context=self.browser_context):
                login_obj = DouYinLogin(
                    login_type=self._config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.dy_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_awemes()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_videos()

            logger.info("[DouYinCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for videos and retrieve their comment information."""
        logger.info("[DouYinCrawler.search] Begin search keywords")
        dy_limit_count = 10
        if self._config.CRAWLER_MAX_NOTES_COUNT < dy_limit_count:
            self._config.CRAWLER_MAX_NOTES_COUNT = dy_limit_count

        start_page = self._config.START_PAGE
        for keyword in self._config.KEYWORDS.split(","):
            logger.info(f"[DouYinCrawler.search] Current keyword: {keyword}")
            aweme_list: List[str] = []
            page = 0
            dy_search_id = ""
            while (page - start_page + 1) * dy_limit_count <= self._config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    logger.info(f"[DouYinCrawler.search] Skip {page}")
                    page += 1
                    continue
                try:
                    logger.info(f"[DouYinCrawler.search] Searching: {keyword}, page: {page}")
                    posts_res = await self.dy_client.search_info_by_keyword(
                        keyword=keyword,
                        offset=page * dy_limit_count - dy_limit_count,
                        publish_time=PublishTimeType(self._config.PUBLISH_TIME_TYPE) if hasattr(self._config, 'PUBLISH_TIME_TYPE') else PublishTimeType.UNLIMITED,
                        search_id=dy_search_id,
                    )
                    if posts_res.get("data") is None or posts_res.get("data") == []:
                        logger.info(f"[DouYinCrawler.search] Empty result for page {page}")
                        break
                except DataFetchError:
                    logger.error(f"[DouYinCrawler.search] Search failed for {keyword}")
                    break

                page += 1
                if "data" not in posts_res:
                    logger.error(f"[DouYinCrawler.search] No data in response")
                    break
                dy_search_id = posts_res.get("extra", {}).get("logid", "")
                page_aweme_list = []
                for post_item in posts_res.get("data", []):
                    try:
                        aweme_info: Dict = post_item.get("aweme_info") or post_item.get("aweme_mix_info", {}).get("mix_items", [{}])[0]
                    except (TypeError, IndexError):
                        continue
                    aweme_list.append(aweme_info.get("aweme_id", ""))
                    page_aweme_list.append(aweme_info.get("aweme_id", ""))
                    await self.store_aweme(aweme_info)
                    await self.get_aweme_media(aweme_info)

                await self.batch_get_note_comments(page_aweme_list)
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)

            logger.info(f"[DouYinCrawler.search] keyword:{keyword}, aweme_list:{aweme_list}")

    async def get_specified_awemes(self):
        """Get the information and comments of specified videos."""
        logger.info("[DouYinCrawler.get_specified_awemes] Parsing video URLs...")
        aweme_id_list = []
        specified_list = getattr(self._config, 'DY_SPECIFIED_ID_LIST', [])
        for video_url in specified_list:
            try:
                video_info = parse_video_info_from_url(video_url)

                if video_info.url_type == "short":
                    logger.info(f"[DouYinCrawler.get_specified_awemes] Resolving short link: {video_url}")
                    resolved_url = await self.dy_client.resolve_short_url(video_url)
                    if resolved_url:
                        video_info = parse_video_info_from_url(resolved_url)
                        logger.info(f"[DouYinCrawler.get_specified_awemes] Resolved to: {video_info.aweme_id}")
                    else:
                        logger.error(f"[DouYinCrawler.get_specified_awemes] Failed to resolve short link")
                        continue

                aweme_id_list.append(video_info.aweme_id)
                logger.info(f"[DouYinCrawler.get_specified_awemes] Parsed aweme ID: {video_info.aweme_id}")
            except ValueError as e:
                logger.error(f"[DouYinCrawler.get_specified_awemes] Failed to parse URL: {e}")
                continue

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_aweme_detail(aweme_id=aweme_id, semaphore=semaphore) for aweme_id in aweme_id_list]
        aweme_details = await asyncio.gather(*task_list)
        for aweme_detail in aweme_details:
            if aweme_detail is not None:
                await self.store_aweme(aweme_detail)
                await self.get_aweme_media(aweme_detail)
        await self.batch_get_note_comments(aweme_id_list)

    async def get_aweme_detail(self, aweme_id: str, semaphore: asyncio.Semaphore) -> Any:
        """Get video detail."""
        async with semaphore:
            try:
                result = await self.dy_client.get_video_by_id(aweme_id)
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                return result
            except DataFetchError as ex:
                logger.error(f"[DouYinCrawler.get_aweme_detail] Error: {ex}")
                return None
            except KeyError as ex:
                logger.error(f"[DouYinCrawler.get_aweme_detail] Key error for {aweme_id}: {ex}")
                return None

    async def batch_get_note_comments(self, aweme_list: List[str]) -> None:
        """Batch get video comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            logger.info("[DouYinCrawler.batch_get_note_comments] Comment crawling not enabled")
            return

        task_list: List[Task] = []
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        for aweme_id in aweme_list:
            task = asyncio.create_task(self.get_comments(aweme_id, semaphore), name=aweme_id)
            task_list.append(task)
        if task_list:
            await asyncio.wait(task_list)

    async def get_comments(self, aweme_id: str, semaphore: asyncio.Semaphore) -> None:
        """Get video comments."""
        async with semaphore:
            try:
                crawl_interval = self._config.CRAWLER_MAX_SLEEP_SEC
                await self.dy_client.get_aweme_all_comments(
                    aweme_id=aweme_id,
                    crawl_interval=crawl_interval,
                    is_fetch_sub_comments=self._config.ENABLE_GET_SUB_COMMENTS,
                    callback=self.store_comments,
                    max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
                await asyncio.sleep(crawl_interval)
                logger.info(f"[DouYinCrawler.get_comments] Comments retrieved for {aweme_id}")
            except DataFetchError as e:
                logger.error(f"[DouYinCrawler.get_comments] Failed for {aweme_id}: {e}")

    async def get_creators_and_videos(self) -> None:
        """Get creator information and their videos."""
        logger.info("[DouYinCrawler.get_creators_and_videos] Begin get creators")
        creator_list = getattr(self._config, 'DY_CREATOR_ID_LIST', [])
        for creator_url in creator_list:
            try:
                creator_info_parsed = parse_creator_info_from_url(creator_url)
                user_id = creator_info_parsed.sec_user_id
                logger.info(f"[DouYinCrawler.get_creators_and_videos] Parsed sec_user_id: {user_id}")
            except ValueError as e:
                logger.error(f"[DouYinCrawler.get_creators_and_videos] Failed to parse URL: {e}")
                continue

            creator_info: Dict = await self.dy_client.get_user_info(user_id)
            if creator_info:
                await self.store_creator(user_id, creator_info)

            all_video_list = await self.dy_client.get_all_user_aweme_posts(
                sec_user_id=user_id,
                callback=self.fetch_creator_video_detail
            )

            video_ids = [video_item.get("aweme_id") for video_item in all_video_list]
            await self.batch_get_note_comments(video_ids)

    async def fetch_creator_video_detail(self, video_list: List[Dict]):
        """Concurrently obtain video list and save data."""
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_aweme_detail(post_item.get("aweme_id"), semaphore) for post_item in video_list]
        aweme_details = await asyncio.gather(*task_list)
        for aweme_item in aweme_details:
            if aweme_item is not None:
                await self.store_aweme(aweme_item)
                await self.get_aweme_media(aweme_item)

    async def create_douyin_client(self, httpx_proxy: Optional[str]) -> DouYinClient:
        """Create Douyin API client."""
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        user_agent = await self.context_page.evaluate("() => navigator.userAgent")
        douyin_client = DouYinClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": user_agent,
                "Cookie": cookie_str,
                "Host": "www.douyin.com",
                "Origin": "https://www.douyin.com/",
                "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
        )
        return douyin_client

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context."""
        if self._config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "dy")
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)
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
            logger.error(f"[DouYinCrawler] CDP mode failed, falling back: {e}")
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self) -> None:
        """Close browser context."""
        await self.browser_context.close()
        logger.info("[DouYinCrawler.close] Browser context closed")

    # Storage methods
    async def store_aweme(self, aweme_item: Dict):
        """Store video data."""
        logger.info(f"[DouYinCrawler.store_aweme] Storing video: {aweme_item.get('aweme_id')}")

    async def store_comments(self, aweme_id: str, comments: List[Dict]):
        """Store comments data."""
        logger.info(f"[DouYinCrawler.store_comments] Storing {len(comments)} comments for video: {aweme_id}")

    async def store_creator(self, user_id: str, creator: Dict):
        """Store creator data."""
        logger.info(f"[DouYinCrawler.store_creator] Storing creator: {user_id}")

    async def get_aweme_media(self, aweme_item: Dict):
        """Download video/image media."""
        if not self._config.ENABLE_GET_MEDIAS:
            return

        aweme_id = aweme_item.get("aweme_id")
        # Check if it's image or video post
        images = aweme_item.get("images", [])
        if images:
            await self.get_aweme_images(aweme_item)
        else:
            await self.get_aweme_video(aweme_item)

    async def get_aweme_images(self, aweme_item: Dict):
        """Download post images."""
        if not self._config.ENABLE_GET_MEDIAS:
            return
        aweme_id = aweme_item.get("aweme_id")
        images = aweme_item.get("images", [])
        if not images:
            return

        for pic_num, img_info in enumerate(images):
            url_list = img_info.get("url_list", [])
            if not url_list:
                continue
            url = url_list[0]
            content = await self.dy_client.get_aweme_media(url)
            await asyncio.sleep(random.random())
            if content is None:
                continue
            logger.info(f"[DouYinCrawler.get_aweme_images] Downloaded image {pic_num} for video: {aweme_id}")

    async def get_aweme_video(self, aweme_item: Dict):
        """Download video."""
        if not self._config.ENABLE_GET_MEDIAS:
            return
        aweme_id = aweme_item.get("aweme_id")
        video_info = aweme_item.get("video", {})
        play_addr = video_info.get("play_addr", {})
        url_list = play_addr.get("url_list", [])

        if not url_list:
            return

        url = url_list[0]
        content = await self.dy_client.get_aweme_media(url)
        await asyncio.sleep(random.random())
        if content is None:
            return
        logger.info(f"[DouYinCrawler.get_aweme_video] Downloaded video: {aweme_id}")