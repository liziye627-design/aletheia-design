# -*- coding: utf-8 -*-
"""
Kuaishou Login Handler.
"""

import asyncio
from typing import Optional

from playwright.async_api import BrowserContext, Page

from services.mediacrawler.base_crawler import AbstractLogin
from services.mediacrawler.config import get_config
from services.mediacrawler.utils import convert_cookies, convert_str_cookie_to_dict, logger


class KuaishouLogin(AbstractLogin):
    """Kuaishou login handler."""

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
        logger.info("[KuaishouLogin.begin] Begin login...")
        if self._config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif self._config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()

    async def check_login_state(self) -> bool:
        """Check login state."""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = convert_cookies(current_cookie)
        return bool(cookie_dict.get("kuaishou.cp.token"))

    async def login_by_qrcode(self):
        """Login by QR code."""
        logger.info("[KuaishouLogin.login_by_qrcode] Waiting for QR scan...")

    async def login_by_cookies(self):
        """Login by cookies."""
        logger.info("[KuaishouLogin.login_by_cookies] Setting cookies...")
        for key, value in convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".kuaishou.com",
                'path': "/"
            }])