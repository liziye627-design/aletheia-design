# -*- coding: utf-8 -*-
"""
Zhihu Login Handler.
"""

import asyncio
import functools
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from tenacity import RetryError, retry, retry_if_result, stop_after_attempt, wait_fixed

from services.mediacrawler.base_crawler import AbstractLogin
from services.mediacrawler.config import get_config
from services.mediacrawler.utils import convert_cookies, convert_str_cookie_to_dict, logger, show_qrcode, find_login_qrcode


class ZhiHuLogin(AbstractLogin):
    """Zhihu login handler."""

    def __init__(
        self,
        login_type: str,
        browser_context: BrowserContext,
        context_page: Page,
        login_phone: Optional[str] = "",
        cookie_str: str = ""
    ):
        self._config = get_config()
        self._config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.cookie_str = cookie_str

    async def begin(self):
        """Start login process."""
        logger.info("[ZhiHuLogin.begin] Begin login Zhihu...")
        if self._config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif self._config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif self._config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[ZhiHuLogin.begin] Invalid Login Type")

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self) -> bool:
        """Check if login was successful."""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = convert_cookies(current_cookie)
        return bool(cookie_dict.get("z_c0"))

    async def login_by_qrcode(self):
        """Login by QR code scanning."""
        logger.info("[ZhiHuLogin.login_by_qrcode] Begin QR code login...")
        qrcode_img_selector = "xpath=//img[@class='qrcode-sign'"
        base64_qrcode_img = await find_login_qrcode(self.context_page, selector=qrcode_img_selector)
        if base64_qrcode_img:
            partial_show_qrcode = functools.partial(show_qrcode, base64_qrcode_img)
            asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)

        try:
            await self.check_login_state()
        except RetryError:
            logger.info("[ZhiHuLogin.login_by_qrcode] Login failed")
            sys.exit()

        logger.info("[ZhiHuLogin.login_by_qrcode] Login successful")
        await asyncio.sleep(5)

    async def login_by_mobile(self):
        """Login by mobile phone number."""
        logger.info("[ZhiHuLogin.login_by_mobile] Mobile login not fully implemented")

    async def login_by_cookies(self):
        """Login using saved cookies."""
        logger.info("[ZhiHuLogin.login_by_cookies] Begin cookie login...")
        for key, value in convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".zhihu.com",
                'path': "/"
            }])