# -*- coding: utf-8 -*-
"""
Kuaishou (快手) Platform Crawler Core Implementation.
"""

import asyncio
import os
from asyncio import Task
from typing import Dict, List, Optional

from playwright.async_api import BrowserContext, BrowserType, Page, Playwright, async_playwright

from services.mediacrawler.base_crawler import AbstractCrawler
from services.mediacrawler.config import CrawlerConfig, get_config
from services.mediacrawler.utils import convert_cookies, get_user_agent, logger

from .client import KuaishouClient
from .exception import DataFetchError
from .login import KuaishouLogin


class KuaishouCrawler(AbstractCrawler):
    """Kuaishou crawler implementation."""

    context_page: Page
    ks_client: KuaishouClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.kuaishou.com"
        self.user_agent = get_user_agent()
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        async with async_playwright() as playwright:
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(chromium, None, self.user_agent, headless=self._config.HEADLESS)

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.ks_client = await self.create_kuaishou_client(None)
            if not await self.ks_client.pong():
                login_obj = KuaishouLogin(
                    login_type=self._config.LOGIN_TYPE,
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.ks_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_videos()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_videos()

            logger.info("[KuaishouCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for videos."""
        logger.info("[KuaishouCrawler.search] Begin search")

        for keyword in self._config.KEYWORDS.split(","):
            page = 1
            while page * 20 <= self._config.CRAWLER_MAX_NOTES_COUNT:
                try:
                    response = await self.ks_client.search_video_by_keyword(keyword, page)
                    videos = response.get("videos", [])
                    if not videos:
                        break

                    video_ids = [v.get("id") for v in videos]
                    for video_id in video_ids:
                        await self.store_video({"video_id": video_id})

                    await self.batch_get_video_comments(video_ids)
                    page += 1
                    await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                except DataFetchError:
                    break

    async def get_specified_videos(self):
        """Get specified videos."""
        specified_list = getattr(self._config, 'KS_SPECIFIED_ID_LIST', [])
        for video_id in specified_list:
            video_info = await self.ks_client.get_video_info(video_id)
            if video_info:
                await self.store_video(video_info)
        await self.batch_get_video_comments(specified_list)

    async def batch_get_video_comments(self, video_id_list: List[str]):
        """Batch get video comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            return

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [asyncio.create_task(self.get_comments(vid, semaphore)) for vid in video_id_list]
        await asyncio.gather(*task_list)

    async def get_comments(self, video_id: str, semaphore: asyncio.Semaphore):
        """Get video comments."""
        async with semaphore:
            try:
                await self.ks_client.get_video_all_comments(
                    video_id=video_id,
                    crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                    callback=self.store_comments,
                    max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
                )
            except DataFetchError as ex:
                logger.error(f"[KuaishouCrawler.get_comments] Error: {ex}")

    async def get_creators_and_videos(self) -> None:
        """Get creator's videos."""
        creator_list = getattr(self._config, 'KS_CREATOR_ID_LIST', [])
        for creator_id in creator_list:
            creator_info = await self.ks_client.get_creator_info(creator_id)
            if creator_info:
                await self.store_creator(creator_info)

            page = 1
            while True:
                response = await self.ks_client.get_creator_videos(creator_id, page)
                videos = response.get("videos", [])
                if not videos:
                    break
                for video in videos:
                    await self.store_video(video)
                page += 1
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)

    async def create_kuaishou_client(self, httpx_proxy: Optional[str]) -> KuaishouClient:
        """Create Kuaishou API client."""
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        return KuaishouClient(
            proxy=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://www.kuaishou.com",
                "Referer": "https://www.kuaishou.com",
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
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "ks")
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

    async def store_video(self, video: Dict):
        """Store video."""
        logger.info(f"[KuaishouCrawler.store_video] Storing video: {video.get('video_id')}")

    async def store_comments(self, video_id: str, comments: List[Dict]):
        """Store comments."""
        logger.info(f"[KuaishouCrawler.store_comments] Storing {len(comments)} comments")

    async def store_creator(self, creator: Dict):
        """Store creator."""
        logger.info(f"[KuaishouCrawler.store_creator] Storing creator")