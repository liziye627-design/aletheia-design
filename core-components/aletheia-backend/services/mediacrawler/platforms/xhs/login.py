# -*- coding: utf-8 -*-
"""
XiaoHongShu Login Handler.
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


class XiaoHongShuLogin(AbstractLogin):
    """XiaoHongShu login handler."""

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

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self, no_logged_in_session: str) -> bool:
        """
        Verify login status using dual-check: UI elements and Cookies.
        """
        # 1. Check if "Me" (Profile) node appears in sidebar
        try:
            user_profile_selector = "xpath=//a[contains(@href, '/user/profile/')]//span[text()='我']"
            is_visible = await self.context_page.is_visible(user_profile_selector, timeout=500)
            if is_visible:
                logger.info("[XiaoHongShuLogin.check_login_state] Login confirmed by UI element.")
                return True
        except Exception:
            pass

        # 2. Check for CAPTCHA prompt
        if "请通过验证" in await self.context_page.content():
            logger.info("[XiaoHongShuLogin.check_login_state] CAPTCHA appeared, please verify manually.")

        # 3. Cookie-based change detection fallback
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = convert_cookies(current_cookie)
        current_web_session = cookie_dict.get("web_session")

        if current_web_session and current_web_session != no_logged_in_session:
            logger.info("[XiaoHongShuLogin.check_login_state] Login confirmed by Cookie change.")
            return True

        return False

    async def begin(self):
        """Start login process."""
        logger.info("[XiaoHongShuLogin.begin] Begin login xiaohongshu ...")
        if self._config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif self._config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif self._config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[XiaoHongShuLogin.begin] Invalid Login Type. Supported: qrcode, phone, cookie")

    async def login_by_mobile(self):
        """Login by mobile phone number."""
        logger.info("[XiaoHongShuLogin.login_by_mobile] Begin login by mobile ...")
        await asyncio.sleep(1)
        try:
            login_button_ele = await self.context_page.wait_for_selector(
                selector="xpath=//*[@id='app']/div[1]/div[2]/div[1]/ul/div[1]/button",
                timeout=5000
            )
            await login_button_ele.click()
            element = await self.context_page.wait_for_selector(
                selector='xpath=//div[@class="login-container"]//div[@class="other-method"]/div[1]',
                timeout=5000
            )
            await element.click()
        except Exception as e:
            logger.info(f"[XiaoHongShuLogin.login_by_mobile] Mobile button not found, continuing: {e}")

        await asyncio.sleep(1)
        login_container_ele = await self.context_page.wait_for_selector("div.login-container")
        input_ele = await login_container_ele.query_selector("label.phone > input")
        await input_ele.fill(self.login_phone)
        await asyncio.sleep(0.5)

        send_btn_ele = await login_container_ele.query_selector("label.auth-code > span")
        await send_btn_ele.click()
        sms_code_input_ele = await login_container_ele.query_selector("label.auth-code > input")
        submit_btn_ele = await login_container_ele.query_selector("div.input-container > button")

        # TODO: Implement SMS code retrieval from cache
        no_logged_in_session = ""
        max_get_sms_code_time = 60 * 2
        while max_get_sms_code_time > 0:
            logger.info(f"[XiaoHongShuLogin.login_by_mobile] Waiting for SMS code, remaining: {max_get_sms_code_time}s")
            await asyncio.sleep(1)
            max_get_sms_code_time -= 1
            # SMS code retrieval logic would go here

            current_cookie = await self.browser_context.cookies()
            _, cookie_dict = convert_cookies(current_cookie)
            no_logged_in_session = cookie_dict.get("web_session")

        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            logger.info("[XiaoHongShuLogin.login_by_mobile] Login failed by mobile")
            sys.exit()

        logger.info("[XiaoHongShuLogin.login_by_mobile] Login successful")
        await asyncio.sleep(5)

    async def login_by_qrcode(self):
        """Login by QR code scanning."""
        logger.info("[XiaoHongShuLogin.login_by_qrcode] Begin login by QR code ...")
        qrcode_img_selector = "xpath=//img[@class='qrcode-img']"
        base64_qrcode_img = await find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            logger.info("[XiaoHongShuLogin.login_by_qrcode] QR code not found, clicking login button...")
            await asyncio.sleep(0.5)
            login_button_ele = self.context_page.locator("xpath=//*[@id='app']/div[1]/div[2]/div[1]/ul/div[1]/button")
            await login_button_ele.click()
            base64_qrcode_img = await find_login_qrcode(
                self.context_page,
                selector=qrcode_img_selector
            )
            if not base64_qrcode_img:
                sys.exit()

        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = convert_cookies(current_cookie)
        no_logged_in_session = cookie_dict.get("web_session")

        # Show QR code in terminal
        partial_show_qrcode = functools.partial(show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)

        logger.info("[XiaoHongShuLogin.login_by_qrcode] Waiting for QR code scan (120s timeout)")
        try:
            await self.check_login_state(no_logged_in_session)
        except RetryError:
            logger.info("[XiaoHongShuLogin.login_by_qrcode] Login failed by QR code")
            sys.exit()

        logger.info("[XiaoHongShuLogin.login_by_qrcode] Login successful")
        await asyncio.sleep(5)

    async def login_by_cookies(self):
        """Login using saved cookies."""
        logger.info("[XiaoHongShuLogin.login_by_cookies] Begin login by cookie ...")
        for key, value in convert_str_cookie_to_dict(self.cookie_str).items():
            if key != "web_session":
                continue
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".xiaohongshu.com",
                'path': "/"
            }])