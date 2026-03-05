# -*- coding: utf-8 -*-
"""
Tieba (贴吧) Platform Crawler Core Implementation.
"""

import asyncio
import os
from asyncio import Task
from typing import Dict, List, Optional

from playwright.async_api import BrowserContext, BrowserType, Page, Playwright, async_playwright

from services.mediacrawler.base_crawler import AbstractCrawler
from services.mediacrawler.config import CrawlerConfig, get_config
from services.mediacrawler.utils import convert_cookies, get_user_agent, logger

from .client import TieBaClient
from .exception import DataFetchError
from .help import parse_tiezi_info_from_url
from .login import TieBaLogin


class TieBaCrawler(AbstractCrawler):
    """Tieba crawler implementation."""

    context_page: Page
    tieba_client: TieBaClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://tieba.baidu.com"
        self.user_agent = get_user_agent()
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        async with async_playwright() as playwright:
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(chromium, None, self.user_agent, headless=self._config.HEADLESS)

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.tieba_client = await self.create_tieba_client(None)
            if not await self.tieba_client.pong():
                login_obj = TieBaLogin(
                    login_type=self._config.LOGIN_TYPE,
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.tieba_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_tiezis()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_forum_tiezis()

            logger.info("[TieBaCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for tiezis."""
        logger.info("[TieBaCrawler.search] Begin search")

        for keyword in self._config.KEYWORDS.split(","):
            page = 1
            while page * 20 <= self._config.CRAWLER_MAX_NOTES_COUNT:
                try:
                    response = await self.tieba_client.search_by_keyword(keyword, page)
                    tiezis = response.get("data", {}).get("post_list", [])
                    if not tiezis:
                        break

                    tiezi_ids = [t.get("tid") for t in tiezis]
                    for tiezi_id in tiezi_ids:
                        await self.store_tiezi({"tiezi_id": tiezi_id})

                    await self.batch_get_tiezi_comments(tiezi_ids)
                    page += 1
                    await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                except DataFetchError:
                    break

    async def get_specified_tiezis(self):
        """Get specified tiezis."""
        specified_list = getattr(self._config, 'TIEBA_SPECIFIED_ID_LIST', [])
        for tiezi_url in specified_list:
            tiezi_id = parse_tiezi_info_from_url(tiezi_url)
            tiezi_info = await self.tieba_client.get_tiezi_info(tiezi_id)
            if tiezi_info:
                await self.store_tiezi(tiezi_info)
        await self.batch_get_tiezi_comments(specified_list)

    async def batch_get_tiezi_comments(self, tiezi_id_list: List[str]):
        """Batch get tiezi comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            return

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [asyncio.create_task(self.get_comments(tid, semaphore)) for tid in tiezi_id_list]
        await asyncio.gather(*task_list)

    async def get_comments(self, tiezi_id: str, semaphore: asyncio.Semaphore):
        """Get tiezi comments."""
        async with semaphore:
            try:
                await self.tieba_client.get_tiezi_all_comments(
                    tiezi_id=tiezi_id,
                    crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                    callback=self.store_comments,
                    max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                logger.error(f"[TieBaCrawler.get_comments] Error: {ex}")

    async def get_forum_tiezis(self) -> None:
        """Get tiezis from specified forums."""
        forum_list = getattr(self._config, 'TIEBA_FORUM_LIST', [])
        for forum_name in forum_list:
            forum_info = await self.tieba_client.get_forum_info(forum_name)
            if forum_info:
                await self.store_forum(forum_info)

            page = 1
            while True:
                response = await self.tieba_client.get_forum_tiezis(forum_name, page)
                tiezis = response.get("tiezis", [])
                if not tiezis:
                    break
                for tiezi in tiezis:
                    await self.store_tiezi(tiezi)
                page += 1
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)

    async def create_tieba_client(self, httpx_proxy: Optional[str]) -> TieBaClient:
        """Create Tieba API client."""
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        return TieBaClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://tieba.baidu.com",
                "Referer": "https://tieba.baidu.com",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser."""
        if self._config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "tieba")
            return await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
            )
        else:
            browser = await chromium.launch(headless=headless)
            return await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)

    async def close(self) -> None:
        """Close browser."""
        await self.browser_context.close()

    async def store_tiezi(self, tiezi: Dict):
        """Store tiezi."""
        logger.info(f"[TieBaCrawler.store_tiezi] Storing tiezi: {tiezi.get('tiezi_id')}")

    async def store_comments(self, tiezi_id: str, comments: List[Dict]):
        """Store comments."""
        logger.info(f"[TieBaCrawler.store_comments] Storing {len(comments)} comments")

    async def store_forum(self, forum: Dict):
        """Store forum."""
        logger.info(f"[TieBaCrawler.store_forum] Storing forum")