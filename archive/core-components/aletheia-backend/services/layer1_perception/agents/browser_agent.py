"""
BrowserAgent - 浏览器Agent基础类

提供浏览器自动化的基础能力:
- 浏览器启动/关闭
- 页面导航
- 截图功能
- 人类行为模拟
- 反检测
"""

import asyncio
import random
import base64
import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from utils.logging import logger
from .render_capture import (
    NetworkTracker,
    attach_network_activity_listeners,
    attach_json_response_listener,
    detach_page_listeners,
    wait_for_network_quiet,
    progressive_scroll,
    wait_dom_stable,
    extract_schema_fields,
)


class BrowserAgent:
    """
    浏览器Agent基础类

    核心能力:
    1. 浏览器控制
    2. 人类行为模拟
    3. 反检测
    """

    def __init__(
        self,
        headless: bool = False,
        user_agent: Optional[str] = None,
        viewport_size: Optional[Dict[str, int]] = None,
        storage_state_path: Optional[str] = None,
        manual_takeover: Optional[bool] = None,
        manual_takeover_timeout_sec: Optional[int] = None,
        blocked_screenshot_dir: Optional[str] = None,
    ):
        """
        初始化Browser Agent

        Args:
            headless: 是否无头模式
            user_agent: 自定义User-Agent
            viewport_size: 视口大小 {"width": 1920, "height": 1080}
        """
        self.headless = headless
        self.user_agent = user_agent or self._get_random_user_agent()
        self.viewport_size = viewport_size or {"width": 1920, "height": 1080}
        self.storage_state_path = storage_state_path or os.getenv(
            "PLAYWRIGHT_STORAGE_STATE"
        )
        env_manual_takeover = (
            str(os.getenv("PLAYWRIGHT_ENABLE_MANUAL_TAKEOVER", "false")).lower()
            in {"1", "true", "yes", "on"}
        )
        self.enable_manual_takeover = (
            env_manual_takeover if manual_takeover is None else bool(manual_takeover)
        )
        env_manual_timeout = int(os.getenv("PLAYWRIGHT_MANUAL_TAKEOVER_TIMEOUT_SEC", "90"))
        self.manual_takeover_timeout_sec = int(
            env_manual_timeout
            if manual_takeover_timeout_sec is None
            else manual_takeover_timeout_sec
        )
        self.blocked_screenshot_dir = (
            blocked_screenshot_dir or os.getenv("PLAYWRIGHT_BLOCKED_SCREENSHOT_DIR")
        )
        self.logger = logger

        # Playwright实例
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        # 统计
        self.stats = {
            "pages_visited": 0,
            "screenshots_taken": 0,
            "actions_performed": 0,
            "errors": 0,
        }
        self.last_diagnostics: Dict[str, Any] = {
            "blocked": False,
            "selector_miss": False,
            "empty_result": False,
            "reason": "",
        }

    async def start(self):
        """启动浏览器"""
        self.playwright = await async_playwright().start()

        # 启动Chromium（反检测配置）
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
            ],
        )

        # 创建上下文（反检测）
        context_kwargs = dict(
            user_agent=self.user_agent,
            viewport=self.viewport_size,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            # 伪装权限
            permissions=["geolocation", "notifications"],
            # 伪装设备
            device_scale_factor=1,
            is_mobile=False,
        )

        if self.storage_state_path and os.path.exists(self.storage_state_path):
            context_kwargs["storage_state"] = self.storage_state_path
            self.logger.info(f"🔐 Using storage_state: {self.storage_state_path}")

        self.context = await self.browser.new_context(**context_kwargs)

        # 注入反检测脚本
        await self.context.add_init_script("""
            // 隐藏webdriver标志
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 伪装Chrome属性
            window.chrome = {
                runtime: {}
            };
            
            // 伪装权限
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

        # 创建页面
        self.page = await self.context.new_page()

        print(f"✅ BrowserAgent已启动 (headless={self.headless})")
        self.logger.info(f"✅ BrowserAgent started (headless={self.headless})")

    async def close(self):
        """关闭浏览器"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

        print(f"🛑 BrowserAgent已关闭")
        print(f"📊 统计: {self.stats}")
        self.logger.info(f"🛑 BrowserAgent closed: {self.stats}")

    async def navigate(self, url: str, wait_until: str = "networkidle"):
        """
        导航到URL

        Args:
            url: 目标URL
            wait_until: 等待条件 (load, domcontentloaded, networkidle)
        """
        print(f"🌐 导航到: {url}")

        await self.page.goto(url, wait_until=wait_until)
        await self.random_delay(0.5, 1.5)  # 模拟人类阅读

        self.stats["pages_visited"] += 1

    async def screenshot(
        self, full_page: bool = False, element_selector: Optional[str] = None
    ) -> bytes:
        """
        截图

        Args:
            full_page: 是否全页截图
            element_selector: 元素选择器（截取特定元素）

        Returns:
            PNG图像字节
        """
        if element_selector:
            element = await self.page.query_selector(element_selector)
            screenshot = await element.screenshot()
        else:
            screenshot = await self.page.screenshot(full_page=full_page)

        self.stats["screenshots_taken"] += 1
        return screenshot

    async def screenshot_base64(self, **kwargs) -> str:
        """截图并返回base64编码"""
        screenshot = await self.screenshot(**kwargs)
        return base64.b64encode(screenshot).decode("utf-8")

    # ==================== 人类行为模拟 ====================

    async def random_delay(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """随机延迟（模拟人类）"""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def human_type(self, selector: str, text: str, delay_per_char: float = 0.1):
        """
        模拟人类打字

        Args:
            selector: 输入框选择器
            text: 要输入的文本
            delay_per_char: 每个字符之间的延迟
        """
        element = await self.page.query_selector(selector)

        for char in text:
            await element.type(char)
            await self.random_delay(delay_per_char * 0.5, delay_per_char * 1.5)

        self.stats["actions_performed"] += 1

    async def human_click(self, selector: str):
        """模拟人类点击（带随机偏移）"""
        element = await self.page.query_selector(selector)

        # 获取元素位置
        box = await element.bounding_box()

        # 随机点击位置（避免总是点击中心）
        x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

        # 鼠标移动到位置
        await self.page.mouse.move(x, y)
        await self.random_delay(0.1, 0.3)

        # 点击
        await self.page.mouse.click(x, y)
        await self.random_delay(0.3, 0.8)

        self.stats["actions_performed"] += 1

    async def human_scroll(self, distance: int = None, direction: str = "down"):
        """
        模拟人类滚动

        Args:
            distance: 滚动距离（像素）。None表示滚动一屏
            direction: 方向 (down/up)
        """
        if distance is None:
            # 滚动一屏
            distance = self.viewport_size["height"] - 100

        if direction == "up":
            distance = -distance

        # 分段滚动（模拟阅读）
        segments = self._split_scroll(distance, num_segments=3)

        for segment in segments:
            await self.page.mouse.wheel(0, segment)
            await self.random_delay(0.3, 1.0)  # 阅读停顿

        self.stats["actions_performed"] += 1

    async def scroll_to_bottom(self, max_scrolls: int = 10):
        """滚动到页面底部（处理无限滚动）"""
        prev_height = 0
        scrolls = 0

        while scrolls < max_scrolls:
            # 获取当前页面高度
            current_height = await self.page.evaluate("document.body.scrollHeight")

            # 如果高度没有变化，说明到底了
            if current_height == prev_height:
                break

            # 滚动一屏
            await self.human_scroll()

            prev_height = current_height
            scrolls += 1

            # 等待内容加载
            await self.random_delay(1.0, 2.0)

        print(f"📜 滚动完成 (共{scrolls}次)")

    async def scroll_page(self, distance: int = None, direction: str = "down"):
        """兼容方法：供子Agent调用"""
        await self.human_scroll(distance=distance, direction=direction)

    # ==================== 辅助方法 ====================

    def _split_scroll(self, distance: int, num_segments: int = 3) -> List[int]:
        """
        将滚动距离分成多段（模拟人类阅读）

        Args:
            distance: 总距离
            num_segments: 分段数

        Returns:
            每段的距离列表
        """
        segments = []
        remaining = distance

        for i in range(num_segments - 1):
            segment = int(remaining * random.uniform(0.2, 0.4))
            segments.append(segment)
            remaining -= segment

        segments.append(remaining)
        return segments

    def _get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        return random.choice(user_agents)

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000, state: str = "visible"
    ):
        """
        等待元素出现

        Args:
            selector: 选择器
            timeout: 超时时间（毫秒）
            state: 状态 (attached, detached, visible, hidden)
        """
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception as e:
            print(f"⚠️ 等待元素失败: {selector} - {e}")
            self.stats["errors"] += 1
            return False

    async def wait_render_ready(
        self,
        *,
        tracker: Optional[NetworkTracker] = None,
        critical_selector: Optional[str] = None,
        networkidle_timeout_ms: int = 9000,
        quiet_ms: int = 900,
        quiet_timeout_ms: int = 12000,
        max_scrolls: int = 8,
        scroll_pause_ms: int = 700,
        dom_stable_ms: int = 800,
        dom_timeout_ms: int = 5000,
    ) -> Dict[str, Any]:
        """
        等待页面达到“可稳定抽取”的状态。
        返回诊断信息，不抛出等待失败异常。
        """
        local_tracker = tracker or NetworkTracker(last_activity=time.monotonic())
        network_listeners: Dict[str, Any] = {}
        if tracker is None:
            network_listeners = attach_network_activity_listeners(self.page, local_tracker)
        diagnostics: Dict[str, Any] = {
            "critical_selector_found": False,
            "playwright_networkidle_reached": False,
            "custom_network_quiet_reached": False,
            "dom_stable": False,
            "scroll_count": 0,
            "requests_seen": 0,
        }
        try:
            try:
                await self.page.wait_for_load_state(
                    "networkidle",
                    timeout=max(1000, int(networkidle_timeout_ms)),
                )
                diagnostics["playwright_networkidle_reached"] = True
            except Exception:
                diagnostics["playwright_networkidle_reached"] = False

            if critical_selector:
                try:
                    await self.page.wait_for_selector(
                        critical_selector,
                        timeout=12000,
                        state="visible",
                    )
                    diagnostics["critical_selector_found"] = True
                except Exception:
                    diagnostics["critical_selector_found"] = False

            diagnostics["scroll_count"] = await progressive_scroll(
                self.page,
                max_scrolls=max(0, int(max_scrolls)),
                pause_ms=max(50, int(scroll_pause_ms)),
            )
            diagnostics["custom_network_quiet_reached"] = await wait_for_network_quiet(
                local_tracker,
                quiet_ms=max(50, int(quiet_ms)),
                timeout_ms=max(500, int(quiet_timeout_ms)),
            )
            diagnostics["dom_stable"] = await wait_dom_stable(
                self.page,
                stable_ms=max(100, int(dom_stable_ms)),
                timeout_ms=max(500, int(dom_timeout_ms)),
            )
            diagnostics["requests_seen"] = local_tracker.requests_seen
            return diagnostics
        finally:
            if network_listeners:
                detach_page_listeners(self.page, network_listeners)

    async def capture_rendered_page(
        self,
        *,
        url: str,
        critical_selector: Optional[str] = None,
        schema: Optional[Dict[str, Dict[str, Any]]] = None,
        api_url_keyword: str = "",
        max_api_items: int = 30,
        visible_text_limit: int = 18000,
        html_limit: int = 250000,
        max_scrolls: int = 8,
        scroll_pause_ms: int = 700,
        wait_until: str = "domcontentloaded",
        navigation_timeout_ms: int = 45000,
    ) -> Dict[str, Any]:
        """
        打开页面并抓取渲染后信息:
        - diagnostics
        - fields (schema抽取)
        - visible_text/html (截断)
        - api_responses (JSON响应)
        """
        tracker = NetworkTracker(last_activity=time.monotonic())
        activity_listeners = attach_network_activity_listeners(self.page, tracker)
        api_items: List[Dict[str, Any]] = []
        api_tasks: List[asyncio.Task[Any]] = []
        response_listeners = attach_json_response_listener(
            self.page,
            api_items=api_items,
            api_tasks=api_tasks,
            api_url_keyword=api_url_keyword,
            max_api_items=max(1, int(max_api_items)),
        )
        try:
            await self.page.goto(
                url,
                wait_until=wait_until,
                timeout=max(1000, int(navigation_timeout_ms)),
            )
            diagnostics = await self.wait_render_ready(
                tracker=tracker,
                critical_selector=critical_selector,
                max_scrolls=max_scrolls,
                scroll_pause_ms=scroll_pause_ms,
            )
            fields = await extract_schema_fields(self.page, schema or {})
            visible_text = await self.page.evaluate(
                "() => (document.body ? document.body.innerText : '')"
            )
            html = await self.page.content()

            if api_tasks:
                await asyncio.gather(*api_tasks, return_exceptions=True)

            payload = {
                "success": True,
                "url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "diagnostics": diagnostics,
                "fields": fields,
                "visible_text": (visible_text or "")[: max(1000, int(visible_text_limit))],
                "visible_text_truncated": bool(
                    visible_text and len(visible_text) > max(1000, int(visible_text_limit))
                ),
                "html": (html or "")[: max(10000, int(html_limit))],
                "html_truncated": bool(html and len(html) > max(10000, int(html_limit))),
                "api_responses": api_items,
            }
            self.last_diagnostics["render"] = diagnostics
            return payload
        finally:
            detach_page_listeners(self.page, response_listeners)
            detach_page_listeners(self.page, activity_listeners)

    async def detect_blocked_page(self) -> bool:
        """检测是否触发登录墙/风控页。"""
        try:
            text = await self.get_page_text()
        except Exception:
            return False

        blocked_markers = [
            "请先登录",
            "登录后查看更多",
            "登录后继续",
            "验证",
            "安全验证",
            "访问受限",
            "异常访问",
            "请输入验证码",
            "请完成验证",
            "请拖动滑块",
            "账号登录",
            "login",
            "sign in",
            "captcha",
            "verify you are human",
            "are you human",
            "access denied",
        ]
        lowered = text.lower() if text else ""
        for marker in blocked_markers:
            if marker.lower() in lowered:
                self.last_diagnostics.update(
                    {"blocked": True, "reason": f"blocked_by:{marker}"}
                )
                await self._dump_blocked_snapshot(marker)
                if self.enable_manual_takeover and not self.headless:
                    resolved = await self._wait_manual_unblock(marker)
                    if resolved:
                        self.last_diagnostics.update(
                            {"blocked": False, "reason": "manual_takeover_resolved"}
                        )
                        return False
                return True
        return False

    async def _dump_blocked_snapshot(self, marker: str) -> None:
        if not self.blocked_screenshot_dir:
            return
        try:
            os.makedirs(self.blocked_screenshot_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"blocked_{marker[:24].replace(' ', '_')}_{ts}.png"
            path = os.path.join(self.blocked_screenshot_dir, file_name)
            await self.page.screenshot(path=path, full_page=False)
            self.logger.warning(f"🧱 blocked snapshot saved: {path}")
        except Exception as exc:
            self.logger.warning(f"save blocked snapshot failed: {exc}")

    async def _wait_manual_unblock(self, marker: str) -> bool:
        self.logger.warning(
            f"🧱 blocked marker detected: {marker}. waiting manual takeover "
            f"(timeout={self.manual_takeover_timeout_sec}s)"
        )
        deadline = datetime.now().timestamp() + max(5, self.manual_takeover_timeout_sec)
        while datetime.now().timestamp() < deadline:
            await asyncio.sleep(2.0)
            try:
                txt = (await self.get_page_text()).lower()
            except Exception:
                continue
            if not txt:
                continue
            if not any(
                m in txt
                for m in [
                    "请先登录",
                    "登录后查看更多",
                    "验证",
                    "安全验证",
                    "captcha",
                    "verify you are human",
                    "access denied",
                ]
            ):
                self.logger.info("✅ manual takeover resolved blocked page")
                return True
        self.logger.warning("manual takeover timeout, keep blocked status")
        return False

    async def get_page_text(self) -> str:
        """获取页面所有文本内容"""
        return await self.page.inner_text("body")

    async def execute_script(self, script: str) -> Any:
        """执行JavaScript脚本"""
        return await self.page.evaluate(script)

    # ==================== 上下文管理器 ====================

    async def __aenter__(self):
        """异步上下文管理器进入"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()


# 导出
__all__ = ["BrowserAgent"]
