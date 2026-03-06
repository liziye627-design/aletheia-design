# -*- coding: utf-8 -*-
"""
Weibo (微博) Platform Crawler Core Implementation.
"""

import asyncio
import os
from asyncio import Task
from typing import Dict, List, Optional

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

from .client import WeiboClient
from .exception import DataFetchError
from .field import SearchType
from .help import filter_search_result_card
from .login import WeiboLogin


class WeiboCrawler(AbstractCrawler):
    """Weibo crawler implementation."""

    context_page: Page
    wb_client: WeiboClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.weibo.com"
        self.mobile_index_url = "https://m.weibo.cn"
        self.user_agent = get_user_agent()
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        playwright_proxy_format, httpx_proxy_format = None, None

        async with async_playwright() as playwright:
            logger.info("[WeiboCrawler] Launching browser...")
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(chromium, None, self.user_agent, headless=self._config.HEADLESS)

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)
            await asyncio.sleep(2)

            self.wb_client = await self.create_weibo_client(httpx_proxy_format)
            if not await self.wb_client.pong():
                login_obj = WeiboLogin(
                    login_type=self._config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.context_page.goto(self.mobile_index_url)
                await asyncio.sleep(3)
                await self.wb_client.update_cookies(browser_context=self.browser_context, urls=[self.mobile_index_url])

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()

            logger.info("[WeiboCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        logger.info("[WeiboCrawler.search] Begin search keywords")
        weibo_limit_count = 10

        search_type_map = {
            "default": SearchType.DEFAULT,
            "real_time": SearchType.REAL_TIME,
            "popular": SearchType.POPULAR,
            "video": SearchType.VIDEO,
        }
        search_type = search_type_map.get(getattr(self._config, 'WEIBO_SEARCH_TYPE', 'default'), SearchType.DEFAULT)

        for keyword in self._config.KEYWORDS.split(","):
            logger.info(f"[WeiboCrawler.search] Current keyword: {keyword}")
            page = 1
            while page * weibo_limit_count <= self._config.CRAWLER_MAX_NOTES_COUNT:
                logger.info(f"[WeiboCrawler.search] Searching: {keyword}, page: {page}")
                search_res = await self.wb_client.get_note_by_keyword(keyword=keyword, page=page, search_type=search_type)
                note_id_list: List[str] = []
                note_list = filter_search_result_card(search_res.get("cards", []))

                for note_item in note_list:
                    if note_item:
                        mblog: Dict = note_item.get("mblog", {})
                        if mblog:
                            note_id_list.append(mblog.get("id"))
                            await self.store_note(note_item)
                            await self.get_note_images(mblog)

                page += 1
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                await self.batch_get_notes_comments(note_id_list)

    async def get_specified_notes(self):
        """Get specified notes info."""
        specified_list = getattr(self._config, 'WEIBO_SPECIFIED_ID_LIST', [])
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [self.get_note_info_task(note_id=note_id, semaphore=semaphore) for note_id in specified_list]
        note_details = await asyncio.gather(*task_list)
        for note_item in note_details:
            if note_item:
                await self.store_note(note_item)
        await self.batch_get_notes_comments(specified_list)

    async def get_note_info_task(self, note_id: str, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        """Get note detail task."""
        async with semaphore:
            try:
                result = await self.wb_client.get_note_info_by_id(note_id)
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                return result
            except DataFetchError as ex:
                logger.error(f"[WeiboCrawler.get_note_info_task] Error: {ex}")
                return None

    async def batch_get_notes_comments(self, note_id_list: List[str]):
        """Batch get notes comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            return

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for note_id in note_id_list:
            task = asyncio.create_task(self.get_note_comments(note_id, semaphore), name=note_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_note_comments(self, note_id: str, semaphore: asyncio.Semaphore):
        """Get note comments."""
        async with semaphore:
            try:
                await self.wb_client.get_note_all_comments(
                    note_id=note_id,
                    crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                    callback=self.store_comments,
                    max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                logger.error(f"[WeiboCrawler.get_note_comments] Error: {ex}")

    async def get_note_images(self, mblog: Dict):
        """Download note images."""
        if not self._config.ENABLE_GET_MEDIAS:
            return

        pics: List = mblog.get("pics", [])
        if not pics:
            return

        for pic in pics:
            url = pic.get("url") if isinstance(pic, dict) else pic
            if not url:
                continue
            content = await self.wb_client.get_note_image(url)
            if content:
                logger.info(f"[WeiboCrawler.get_note_images] Downloaded image")

    async def get_creators_and_notes(self) -> None:
        """Get creator's information and their notes."""
        logger.info("[WeiboCrawler.get_creators_and_notes] Begin get creators")
        creator_list = getattr(self._config, 'WEIBO_CREATOR_ID_LIST', [])
        for user_id in creator_list:
            creator_info_res: Dict = await self.wb_client.get_creator_info_by_id(creator_id=user_id)
            if creator_info_res:
                creator_info: Dict = creator_info_res.get("userInfo", {})
                if creator_info:
                    await self.store_creator(creator_info)

                all_notes_list = await self.wb_client.get_all_notes_by_creator_id(
                    creator_id=user_id,
                    container_id=f"107603{user_id}",
                    crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                    callback=self.batch_store_notes,
                )

                note_ids = [note_item.get("mblog", {}).get("id") for note_item in all_notes_list if note_item.get("mblog", {}).get("id")]
                await self.batch_get_notes_comments(note_ids)

    async def create_weibo_client(self, httpx_proxy: Optional[str]) -> WeiboClient:
        """Create Weibo API client."""
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies(urls=[self.mobile_index_url]))
        return WeiboClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": get_user_agent(),
                "Cookie": cookie_str,
                "Origin": "https://m.weibo.cn",
                "Referer": "https://m.weibo.cn",
                "Content-Type": "application/json;charset=UTF-8",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
        )

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context."""
        if self._config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "wb")
            return await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)
            return await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)

    async def close(self) -> None:
        """Close browser context."""
        await self.browser_context.close()

    # Storage methods
    async def store_note(self, note_item: Dict):
        """Store note data."""
        logger.info(f"[WeiboCrawler.store_note] Storing note")

    async def store_comments(self, note_id: str, comments: List[Dict]):
        """Store comments data."""
        logger.info(f"[WeiboCrawler.store_comments] Storing {len(comments)} comments")

    async def store_creator(self, creator: Dict):
        """Store creator data."""
        logger.info(f"[WeiboCrawler.store_creator] Storing creator")

    async def batch_store_notes(self, note_list: List[Dict]):
        """Batch store notes."""
        for note in note_list:
            await self.store_note(note)