# -*- coding: utf-8 -*-
"""
XiaoHongShu (小红书) Platform Crawler Core Implementation.

Migrated from MediaCrawler project with adaptations for the new service architecture.
"""

import asyncio
import os
import random
from asyncio import Task
from typing import Dict, List, Optional

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)
from tenacity import RetryError

from services.mediacrawler.base_crawler import AbstractCrawler
from services.mediacrawler.config import CrawlerConfig, get_config
from services.mediacrawler.utils import convert_cookies, format_proxy_info, logger

from .client import XiaoHongShuClient
from .exception import DataFetchError, NoteNotFoundError
from .field import SearchSortType
from .help import parse_note_info_from_note_url, parse_creator_info_from_url, get_search_id
from .login import XiaoHongShuLogin
from .models import NoteUrlInfo, CreatorUrlInfo


class XiaoHongShuCrawler(AbstractCrawler):
    """XiaoHongShu crawler implementation."""

    context_page: Page
    xhs_client: XiaoHongShuClient
    browser_context: BrowserContext

    def __init__(self, config: Optional[CrawlerConfig] = None) -> None:
        self._config = config or get_config()
        self.index_url = "https://www.xiaohongshu.com"
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self.ip_proxy_pool = None

    async def start(self) -> None:
        """Start the crawler."""
        playwright_proxy_format, httpx_proxy_format = None, None
        if self._config.ENABLE_IP_PROXY:
            # Proxy pool initialization would go here
            pass

        async with async_playwright() as playwright:
            if self._config.ENABLE_CDP_MODE:
                logger.info("[XiaoHongShuCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=self._config.CDP_HEADLESS,
                )
            else:
                logger.info("[XiaoHongShuCrawler] Launching browser using standard mode")
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=self._config.HEADLESS,
                )
                # Add stealth script
                await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            if not await self.xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type=self._config.LOGIN_TYPE,
                    login_phone="",
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=self._config.COOKIES,
                )
                await login_obj.begin()
                await self.xhs_client.update_cookies(browser_context=self.browser_context)

            if self._config.CRAWLER_TYPE == "search":
                await self.search()
            elif self._config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif self._config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                logger.warning(f"[XiaoHongShuCrawler.start] Unknown crawler type: {self._config.CRAWLER_TYPE}")

            logger.info("[XiaoHongShuCrawler.start] Crawler finished")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        logger.info("[XiaoHongShuCrawler.search] Begin search keywords")
        xhs_limit_count = 20
        if self._config.CRAWLER_MAX_NOTES_COUNT < xhs_limit_count:
            self._config.CRAWLER_MAX_NOTES_COUNT = xhs_limit_count

        start_page = self._config.START_PAGE
        for keyword in self._config.KEYWORDS.split(","):
            logger.info(f"[XiaoHongShuCrawler.search] Current keyword: {keyword}")
            page = 1
            search_id = get_search_id()
            while (page - start_page + 1) * xhs_limit_count <= self._config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    logger.info(f"[XiaoHongShuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    logger.info(f"[XiaoHongShuCrawler.search] Searching: {keyword}, page: {page}")
                    note_ids: List[str] = []
                    xsec_tokens: List[str] = []
                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,
                        search_id=search_id,
                        page=page,
                        sort=(SearchSortType(self._config.SORT_TYPE) if self._config.SORT_TYPE else SearchSortType.GENERAL),
                    )
                    logger.info(f"[XiaoHongShuCrawler.search] Response: {notes_res}")
                    if not notes_res or not notes_res.get("has_more", False):
                        logger.info("[XiaoHongShuCrawler.search] No more content")
                        break

                    semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self.get_note_detail_async_task(
                            note_id=post_item.get("id"),
                            xsec_source=post_item.get("xsec_source"),
                            xsec_token=post_item.get("xsec_token"),
                            semaphore=semaphore,
                        ) for post_item in notes_res.get("items", {}) if post_item.get("model_type") not in ("rec_query", "hot_query")
                    ]
                    note_details = await asyncio.gather(*task_list)
                    for note_detail in note_details:
                        if note_detail:
                            await self.store_note(note_detail)
                            await self.get_note_media(note_detail)
                            note_ids.append(note_detail.get("note_id"))
                            xsec_tokens.append(note_detail.get("xsec_token"))
                    page += 1
                    await self.batch_get_note_comments(note_ids, xsec_tokens)
                    await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                except DataFetchError:
                    logger.error("[XiaoHongShuCrawler.search] Get note detail error")
                    break

    async def get_creators_and_notes(self) -> None:
        """Get creator's notes and their comment information."""
        logger.info("[XiaoHongShuCrawler.get_creators_and_notes] Begin get creators")
        for creator_url in self._config.XHS_CREATOR_ID_LIST:
            try:
                creator_info: CreatorUrlInfo = parse_creator_info_from_url(creator_url)
                logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Creator info: {creator_info}")
                user_id = creator_info.user_id

                creator_data: Dict = await self.xhs_client.get_creator_info(
                    user_id=user_id,
                    xsec_token=creator_info.xsec_token,
                    xsec_source=creator_info.xsec_source
                )
                if creator_data:
                    await self.store_creator(user_id, creator_data)
            except ValueError as e:
                logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Failed to parse URL: {e}")
                continue

            crawl_interval = self._config.CRAWLER_MAX_SLEEP_SEC
            all_notes_list = await self.xhs_client.get_all_notes_by_creator(
                user_id=user_id,
                crawl_interval=crawl_interval,
                callback=self.fetch_creator_notes_detail,
                xsec_token=creator_info.xsec_token,
                xsec_source=creator_info.xsec_source,
            )

            note_ids = []
            xsec_tokens = []
            for note_item in all_notes_list:
                note_ids.append(note_item.get("note_id"))
                xsec_tokens.append(note_item.get("xsec_token"))
            await self.batch_get_note_comments(note_ids, xsec_tokens)

    async def fetch_creator_notes_detail(self, note_list: List[Dict]):
        """Concurrently obtain note list and save data."""
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_detail_async_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
                semaphore=semaphore,
            ) for post_item in note_list
        ]
        note_details = await asyncio.gather(*task_list)
        for note_detail in note_details:
            if note_detail:
                await self.store_note(note_detail)
                await self.get_note_media(note_detail)

    async def get_specified_notes(self):
        """Get information and comments of specified notes."""
        get_note_detail_task_list = []
        for full_note_url in self._config.XHS_SPECIFIED_NOTE_URL_LIST:
            note_url_info: NoteUrlInfo = parse_note_info_from_note_url(full_note_url)
            logger.info(f"[XiaoHongShuCrawler.get_specified_notes] Note URL info: {note_url_info}")
            crawler_task = self.get_note_detail_async_task(
                note_id=note_url_info.note_id,
                xsec_source=note_url_info.xsec_source,
                xsec_token=note_url_info.xsec_token,
                semaphore=asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_note_ids = []
        xsec_tokens = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for note_detail in note_details:
            if note_detail:
                need_get_comment_note_ids.append(note_detail.get("note_id", ""))
                xsec_tokens.append(note_detail.get("xsec_token", ""))
                await self.store_note(note_detail)
                await self.get_note_media(note_detail)
        await self.batch_get_note_comments(need_get_comment_note_ids, xsec_tokens)

    async def get_note_detail_async_task(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict]:
        """Get note detail asynchronously."""
        note_detail = None
        logger.info(f"[get_note_detail_async_task] Getting note: {note_id}")
        async with semaphore:
            try:
                try:
                    note_detail = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
                except RetryError:
                    pass

                if not note_detail:
                    note_detail = await self.xhs_client.get_note_by_id_from_html(
                        note_id, xsec_source, xsec_token, enable_cookie=True
                    )
                    if not note_detail:
                        raise Exception(f"Failed to get note detail: {note_id}")

                note_detail.update({"xsec_token": xsec_token, "xsec_source": xsec_source})
                await asyncio.sleep(self._config.CRAWLER_MAX_SLEEP_SEC)
                return note_detail

            except NoteNotFoundError as ex:
                logger.warning(f"[XiaoHongShuCrawler.get_note_detail_async_task] Note not found: {note_id}, {ex}")
                return None
            except DataFetchError as ex:
                logger.error(f"[XiaoHongShuCrawler.get_note_detail_async_task] Fetch error: {ex}")
                return None
            except KeyError as ex:
                logger.error(f"[XiaoHongShuCrawler.get_note_detail_async_task] Key error for {note_id}: {ex}")
                return None

    async def batch_get_note_comments(self, note_list: List[str], xsec_tokens: List[str]):
        """Batch get note comments."""
        if not self._config.ENABLE_GET_COMMENTS:
            logger.info("[XiaoHongShuCrawler.batch_get_note_comments] Comment crawling not enabled")
            return

        logger.info(f"[XiaoHongShuCrawler.batch_get_note_comments] Getting comments for notes: {note_list}")
        semaphore = asyncio.Semaphore(self._config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for index, note_id in enumerate(note_list):
            task = asyncio.create_task(
                self.get_comments(note_id=note_id, xsec_token=xsec_tokens[index], semaphore=semaphore),
                name=note_id,
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore):
        """Get note comments."""
        async with semaphore:
            logger.info(f"[XiaoHongShuCrawler.get_comments] Getting comments for note: {note_id}")
            crawl_interval = self._config.CRAWLER_MAX_SLEEP_SEC
            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=self.store_comments,
                max_count=self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
            )
            await asyncio.sleep(crawl_interval)

    async def create_xhs_client(self, httpx_proxy: Optional[str]) -> XiaoHongShuClient:
        """Create XiaoHongShu API client."""
        logger.info("[XiaoHongShuCrawler.create_xhs_client] Creating API client...")
        cookie_str, cookie_dict = convert_cookies(await self.browser_context.cookies())
        xhs_client_obj = XiaoHongShuClient(
            proxy=httpx_proxy,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://www.xiaohongshu.com",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://www.xiaohongshu.com/",
                "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": self.user_agent,
                "Cookie": cookie_str,
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,
        )
        return xhs_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context."""
        logger.info("[XiaoHongShuCrawler.launch_browser] Creating browser context...")
        if self._config.SAVE_LOGIN_STATE:
            user_data_dir = os.path.join(os.getcwd(), "browser_data", self._config.USER_DATA_DIR % "xhs")
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
            # CDP browser manager would be initialized here
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)
        except Exception as e:
            logger.error(f"[XiaoHongShuCrawler] CDP mode failed, falling back: {e}")
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self):
        """Close browser context."""
        await self.browser_context.close()
        logger.info("[XiaoHongShuCrawler.close] Browser context closed")

    # Storage methods - these would integrate with the store module
    async def store_note(self, note_detail: Dict):
        """Store note data."""
        # This would call the store module
        logger.info(f"[XiaoHongShuCrawler.store_note] Storing note: {note_detail.get('note_id')}")

    async def store_comments(self, note_id: str, comments: List[Dict]):
        """Store comments data."""
        logger.info(f"[XiaoHongShuCrawler.store_comments] Storing {len(comments)} comments for note: {note_id}")

    async def store_creator(self, user_id: str, creator: Dict):
        """Store creator data."""
        logger.info(f"[XiaoHongShuCrawler.store_creator] Storing creator: {user_id}")

    async def get_note_media(self, note_detail: Dict):
        """Download note media (images/videos)."""
        if not self._config.ENABLE_GET_MEDIAS:
            return
        await self.get_note_images(note_detail)
        await self.get_note_video(note_detail)

    async def get_note_images(self, note_item: Dict):
        """Download note images."""
        if not self._config.ENABLE_GET_MEDIAS:
            return
        note_id = note_item.get("note_id")
        image_list: List[Dict] = note_item.get("image_list", [])

        for img in image_list:
            if img.get("url_default") != "":
                img.update({"url": img.get("url_default")})

        if not image_list:
            return

        for pic_num, pic in enumerate(image_list):
            url = pic.get("url")
            if not url:
                continue
            content = await self.xhs_client.get_note_media(url)
            await asyncio.sleep(random.random())
            if content is None:
                continue
            # Store image content
            logger.info(f"[XiaoHongShuCrawler.get_note_images] Downloaded image {pic_num} for note: {note_id}")

    async def get_note_video(self, note_item: Dict):
        """Download note video."""
        if not self._config.ENABLE_GET_MEDIAS:
            return
        note_id = note_item.get("note_id")
        video_url = note_item.get("video", {}).get("url")

        if not video_url:
            return

        content = await self.xhs_client.get_note_media(video_url)
        await asyncio.sleep(random.random())
        if content is None:
            return
        logger.info(f"[XiaoHongShuCrawler.get_note_video] Downloaded video for note: {note_id}")