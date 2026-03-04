# -*- coding: utf-8 -*-
"""
Zhihu (知乎) Platform Crawler Core Implementation.
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
from services.mediacrawler.utils import convert_cookies, logger

from .client import ZhiHuClient
from .exception import DataFetchError
from .help import judge_zhihu_url
from .login import ZhiHuLogin
from .models import ZhihuContent


class ZhihuCrawler(AbstractCrawler):
    """Zhihu crawler implementation."""

    context_page: Page
    zhihu_client: ZhiHuClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.zhihu.com"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        async with async_playwright() as playwright:
            logger.info("[ZhihuCrawler] Launching browser...")
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(chromium, None, self.user_agent, headless=self._config.HEADLESS)

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, wait_until="domcontentloaded")

            self.zhihu_client = await self.create_zhihu_client(None)
            if not await self.zhihu_client.pong():
                login_obj = ZhiHuLogin(
                    login_type=self._config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            # Navigate to search page to get proper cookies
            await self.context_page.goto(f"{self.index_url}/search?q=python&type=content")
            await asyncio.sleep(5)
            await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()

            logger.info("[ZhihuCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        logger.info("[ZhihuCrawler.search] Begin search keywords")

        for keyword in self._config.KEYWORDS.split(","):
            logger.info(f"[ZhihuCrawler.search] Current keyword: {keyword}")
            page = 1
            while page * 20 <= self._config.CRAWLER_MAX_NOTES_COUNT:
                try:
                    logger.info(f"[ZhihuCrawler.search] Searching: {keyword}, page: {page}")
                    content_list: List[ZhihuContent] = await self.zhihu_client.get_note_by_keyword(keyword=keyword, page=page)

                    if not content_list:
                        logger.info("[ZhihuCrawler.search] No more content")
                        break

                    await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                    page += 1

                    for content in content_list:
                        await self.store_content(content)

                    await self.batch_get_content_comments(content_list)
                except DataFetchError:
                    logger.error("[ZhihuCrawler.search] Search error")
                    return

    async def batch_get_content_comments(self, content_list: List[ZhihuContent]):
        """Batch get content comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            return

        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for content_item in content_list:
            task = asyncio.create_task(self.get_comments(content_item, semaphore), name=content_item.content_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, content_item: ZhihuContent, semaphore: asyncio.Semaphore):
        """Get content comments."""
        async with semaphore:
            logger.info(f"[ZhihuCrawler.get_comments] Getting comments for: {content_item.content_id}")
            await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
            await self.zhihu_client.get_note_all_comments(
                content=content_item,
                crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                callback=self.store_comments,
            )

    async def get_specified_notes(self):
        """Get specified notes info."""
        specified_list = getattr(self._config, 'ZHIHU_SPECIFIED_ID_LIST', [])
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = []
        for full_note_url in specified_list:
            full_note_url = full_note_url.split("?")[0]
            task_list.append(self.get_note_detail(full_note_url, semaphore))

        note_details = await asyncio.gather(*task_list)
        need_get_comment_notes: List[ZhihuContent] = [n for n in note_details if n]

        for note_detail in need_get_comment_notes:
            await self.store_content(note_detail)

        await self.batch_get_content_comments(need_get_comment_notes)

    async def get_note_detail(self, full_note_url: str, semaphore: asyncio.Semaphore) -> Optional[ZhihuContent]:
        """Get note detail."""
        async with semaphore:
            logger.info(f"[ZhihuCrawler.get_note_detail] Getting: {full_note_url}")
            note_type: str = judge_zhihu_url(full_note_url)

            if note_type == "answer":
                question_id = full_note_url.split("/")[-3]
                answer_id = full_note_url.split("/")[-1]
                result = await self.zhihu_client.get_answer_info(question_id, answer_id)
            elif note_type == "article":
                article_id = full_note_url.split("/")[-1]
                result = await self.zhihu_client.get_article_info(article_id)
            elif note_type == "video":
                video_id = full_note_url.split("/")[-1]
                result = await self.zhihu_client.get_video_info(video_id)
            else:
                return None

            await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
            return result

    async def get_creators_and_notes(self) -> None:
        """Get creator's information and their notes."""
        logger.info("[ZhihuCrawler.get_creators_and_notes] Begin get creators")
        creator_url_list = getattr(self._config, 'ZHIHU_CREATOR_URL_LIST', [])

        for user_link in creator_url_list:
            user_url_token = user_link.split("/")[-1]
            creator_info = await self.zhihu_client.get_creator_info(url_token=user_url_token)

            if not creator_info:
                logger.info(f"[ZhihuCrawler.get_creators_and_notes] Creator {user_url_token} not found")
                continue

            await self.store_creator(creator_info)

            all_content_list = await self.zhihu_client.get_all_anwser_by_creator(
                creator=creator_info,
                crawl_interval=self._config.CRAWLER_MAX_SLEEP_SEC,
                callback=self.batch_store_contents,
            )

            await self.batch_get_content_comments(all_content_list)

    async def create_zhihu_client(self, httpx_proxy: Optional[str]) -> ZhiHuClient:
        """Create Zhihu API client."""
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        return ZhiHuClient(
            proxy=httpx_proxy,
            headers={
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cookie": cookie_str,
                "user-agent": self.user_agent,
                "x-api-version": "3.0.91",
                "x-app-za": "OS=Web",
                "x-requested-with": "fetch",
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
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "zhihu")
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
    async def store_content(self, content: ZhihuContent):
        """Store content data."""
        logger.info(f"[ZhihuCrawler.store_content] Storing content: {content.content_id}")

    async def store_comments(self, content_id: str, comments: List[Dict]):
        """Store comments data."""
        logger.info(f"[ZhihuCrawler.store_comments] Storing {len(comments)} comments")

    async def store_creator(self, creator):
        """Store creator data."""
        logger.info(f"[ZhihuCrawler.store_creator] Storing creator: {creator.creator_id}")

    async def batch_store_contents(self, content_list: List[ZhihuContent]):
        """Batch store contents."""
        for content in content_list:
            await self.store_content(content)