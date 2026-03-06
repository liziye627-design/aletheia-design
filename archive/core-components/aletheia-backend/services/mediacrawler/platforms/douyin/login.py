# -*- coding: utf-8 -*-
"""
Douyin Login Handler.
"""

import asyncio
import functools
import sys
from typing import Optional

from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import RetryError, retry, retry_if_result, stop_after_attempt, wait_fixed

from services.mediacrawler.base_crawler import AbstractLogin
from services.mediacrawler.config import get_config
from services.mediacrawler.utils import convert_cookies, convert_str_cookie_to_dict, logger, show_qrcode, find_login_qrcode


class DouYinLogin(AbstractLogin):
    """Douyin login handler."""

    def __init__(
        self,
        login_type: str,
        browser_context: BrowserContext,
        context_page: Page,
        login_phone: Optional[str] = "",
        cookie_str: Optional[str] = ""
    ):
        self._config = get_config()
        self._config.LOGIN_TYPE = login_type
        self.browser_context = browser_context
        self.context_page = context_page
        self.login_phone = login_phone
        self.scan_qrcode_time = 60
        self.cookie_str = cookie_str

    async def begin(self):
        """Start login process."""
        await self.popup_login_dialog()

        if self._config.LOGIN_TYPE == "qrcode":
            await self.login_by_qrcode()
        elif self._config.LOGIN_TYPE == "phone":
            await self.login_by_mobile()
        elif self._config.LOGIN_TYPE == "cookie":
            await self.login_by_cookies()
        else:
            raise ValueError("[DouYinLogin.begin] Invalid Login Type. Supported: qrcode, phone, cookie")

        await asyncio.sleep(6)
        current_page_title = await self.context_page.title()
        if "验证码中间页" in current_page_title:
            await self.check_page_display_slider(move_step=3, slider_level="hard")

        logger.info("[DouYinLogin.begin] Checking login state...")
        try:
            await self.check_login_state()
        except RetryError:
            logger.info("[DouYinLogin.begin] Login failed")
            sys.exit()

        logger.info("[DouYinLogin.begin] Login successful")
        await asyncio.sleep(5)

    @retry(stop=stop_after_attempt(600), wait=wait_fixed(1), retry=retry_if_result(lambda value: value is False))
    async def check_login_state(self) -> bool:
        """Check if login was successful."""
        current_cookie = await self.browser_context.cookies()
        _, cookie_dict = convert_cookies(current_cookie)

        for page in self.browser_context.pages:
            try:
                local_storage = await page.evaluate("() => window.localStorage")
                if local_storage.get("HasUserLogin", "") == "1":
                    return True
            except Exception:
                await asyncio.sleep(0.1)

        if cookie_dict.get("LOGIN_STATUS") == "1":
            return True

        return False

    async def popup_login_dialog(self):
        """Manually click login button if dialog doesn't auto-popup."""
        dialog_selector = "xpath=//div[@id='login-panel-new']"
        try:
            await self.context_page.wait_for_selector(dialog_selector, timeout=1000 * 10)
        except Exception as e:
            logger.error(f"[DouYinLogin.popup_login_dialog] Dialog not auto-popup: {e}")
            login_button_ele = self.context_page.locator("xpath=//p[text() = '登录']")
            await login_button_ele.click()
            await asyncio.sleep(0.5)

    async def login_by_qrcode(self):
        """Login by QR code scanning."""
        logger.info("[DouYinLogin.login_by_qrcode] Begin QR code login...")
        qrcode_img_selector = "xpath=//div[@id='animate_qrcode_container']//img"
        base64_qrcode_img = await find_login_qrcode(
            self.context_page,
            selector=qrcode_img_selector
        )
        if not base64_qrcode_img:
            logger.info("[DouYinLogin.login_by_qrcode] QR code not found")
            sys.exit()

        partial_show_qrcode = functools.partial(show_qrcode, base64_qrcode_img)
        asyncio.get_running_loop().run_in_executor(executor=None, func=partial_show_qrcode)
        await asyncio.sleep(2)

    async def login_by_mobile(self):
        """Login by mobile phone number."""
        logger.info("[DouYinLogin.login_by_mobile] Begin mobile login...")
        mobile_tap_ele = self.context_page.locator("xpath=//li[text() = '验证码登录']")
        await mobile_tap_ele.click()
        await self.context_page.wait_for_selector("xpath=//article[@class='web-login-mobile-code']")
        mobile_input_ele = self.context_page.locator("xpath=//input[@placeholder='手机号']")
        await mobile_input_ele.fill(self.login_phone)
        await asyncio.sleep(0.5)
        send_sms_code_btn = self.context_page.locator("xpath=//span[text() = '获取验证码']")
        await send_sms_code_btn.click()

        await self.check_page_display_slider(move_step=10, slider_level="easy")

        # Wait for SMS code input
        max_get_sms_code_time = 60 * 2
        while max_get_sms_code_time > 0:
            logger.info(f"[DouYinLogin.login_by_mobile] Waiting for SMS code, remaining: {max_get_sms_code_time}s")
            await asyncio.sleep(1)
            max_get_sms_code_time -= 1

    async def check_page_display_slider(self, move_step: int = 10, slider_level: str = "easy"):
        """Check if slider verification is displayed."""
        back_selector = "#captcha-verify-image"
        try:
            await self.context_page.wait_for_selector(selector=back_selector, state="visible", timeout=30 * 1000)
        except PlaywrightTimeoutError:
            return

        max_slider_try_times = 20
        slider_verify_success = False
        while not slider_verify_success:
            if max_slider_try_times <= 0:
                logger.error("[DouYinLogin.check_page_display_slider] Slider verify failed")
                sys.exit()
            try:
                # Slider verification would need additional implementation
                await asyncio.sleep(1)
                page_content = await self.context_page.content()
                if "操作过慢" in page_content or "提示重新操作" in page_content:
                    logger.info("[DouYinLogin.check_page_display_slider] Slider verify failed, retry...")
                    await self.context_page.click(selector="//a[contains(@class, 'secsdk_captcha_refresh')]")
                    continue

                await self.context_page.wait_for_selector(selector=back_selector, state="hidden", timeout=1000)
                logger.info("[DouYinLogin.check_page_display_slider] Slider verify success")
                slider_verify_success = True
            except Exception as e:
                logger.error(f"[DouYinLogin.check_page_display_slider] Error: {e}")
                await asyncio.sleep(1)
                max_slider_try_times -= 1

    async def login_by_cookies(self):
        """Login using saved cookies."""
        logger.info("[DouYinLogin.login_by_cookies] Begin cookie login...")
        for key, value in convert_str_cookie_to_dict(self.cookie_str).items():
            await self.browser_context.add_cookies([{
                'name': key,
                'value': value,
                'domain': ".douyin.com",
                'path': "/"
            }])