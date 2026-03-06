"""
Rendered capture helpers for Playwright based agents.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import Page, Response


@dataclass
class NetworkTracker:
    inflight: int = 0
    last_activity: float = 0.0
    requests_seen: int = 0

    def touch(self) -> None:
        self.last_activity = time.monotonic()


def attach_network_activity_listeners(
    page: Page,
    tracker: NetworkTracker,
) -> Dict[str, Callable[..., Any]]:
    def on_request(_) -> None:
        tracker.requests_seen += 1
        tracker.inflight += 1
        tracker.touch()

    def on_request_done(_) -> None:
        tracker.inflight = max(0, tracker.inflight - 1)
        tracker.touch()

    page.on("request", on_request)
    page.on("requestfinished", on_request_done)
    page.on("requestfailed", on_request_done)

    return {
        "request": on_request,
        "requestfinished": on_request_done,
        "requestfailed": on_request_done,
    }


def attach_json_response_listener(
    page: Page,
    *,
    api_items: List[Dict[str, Any]],
    api_tasks: List[asyncio.Task[Any]],
    api_url_keyword: str,
    max_api_items: int,
) -> Dict[str, Callable[..., Any]]:
    async def collect_response(resp: Response) -> None:
        if len(api_items) >= max_api_items:
            return

        url_match = api_url_keyword.lower() in resp.url.lower() if api_url_keyword else True
        if not url_match or resp.status >= 400:
            return

        headers = resp.headers or {}
        ctype = str(headers.get("content-type", "")).lower()
        if "application/json" not in ctype and "text/json" not in ctype:
            return

        try:
            payload = await resp.json()
        except Exception:
            return

        api_items.append(
            {
                "url": resp.url,
                "status": resp.status,
                "payload": payload,
            }
        )

    def on_response(resp: Response) -> None:
        task: asyncio.Task[Any] = asyncio.create_task(collect_response(resp))
        api_tasks.append(task)

    page.on("response", on_response)
    return {"response": on_response}


def detach_page_listeners(page: Page, listeners: Dict[str, Callable[..., Any]]) -> None:
    for event_name, handler in listeners.items():
        removed = False
        off = getattr(page, "off", None)
        if callable(off):
            try:
                off(event_name, handler)
                removed = True
            except Exception:
                removed = False
        if removed:
            continue
        remove_listener = getattr(page, "remove_listener", None)
        if callable(remove_listener):
            try:
                remove_listener(event_name, handler)
            except Exception:
                pass


async def wait_for_network_quiet(
    tracker: NetworkTracker,
    *,
    quiet_ms: int = 900,
    timeout_ms: int = 12000,
) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    quiet_sec = quiet_ms / 1000.0
    while time.monotonic() < deadline:
        quiet_for = time.monotonic() - tracker.last_activity
        if tracker.inflight == 0 and quiet_for >= quiet_sec:
            return True
        await asyncio.sleep(0.08)
    return False


async def progressive_scroll(
    page: Page,
    *,
    max_scrolls: int = 10,
    pause_ms: int = 700,
) -> int:
    prev_height = -1
    done = 0
    for _ in range(max_scrolls):
        height = await page.evaluate("document.body ? document.body.scrollHeight : 0")
        if not isinstance(height, int):
            break
        if height == prev_height:
            break
        await page.mouse.wheel(0, 900)
        await asyncio.sleep(pause_ms / 1000.0)
        prev_height = height
        done += 1
    return done


async def wait_dom_stable(
    page: Page,
    *,
    stable_ms: int = 800,
    timeout_ms: int = 6000,
) -> bool:
    script = """
    ({ stableMs, timeoutMs }) => new Promise((resolve) => {
      const start = Date.now();
      let last = Date.now();
      const observer = new MutationObserver(() => {
        last = Date.now();
      });
      observer.observe(document.documentElement || document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true
      });
      const timer = setInterval(() => {
        const now = Date.now();
        const stableFor = now - last;
        const elapsed = now - start;
        if (stableFor >= stableMs) {
          clearInterval(timer);
          observer.disconnect();
          resolve(true);
        } else if (elapsed >= timeoutMs) {
          clearInterval(timer);
          observer.disconnect();
          resolve(false);
        }
      }, 100);
    })
    """
    return bool(
        await page.evaluate(
            script,
            {"stableMs": stable_ms, "timeoutMs": timeout_ms},
        )
    )


async def extract_schema_fields(page: Page, schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for field, rule in (schema or {}).items():
        selector = str(rule.get("selector", "")).strip()
        if not selector:
            output[field] = None
            continue

        mode = str(rule.get("mode", "text")).lower()  # text | attr | html
        many = bool(rule.get("many", False))
        attr = str(rule.get("attr", ""))

        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                output[field] = [] if many else None
                continue

            async def read_idx(i: int) -> Optional[str]:
                node = locator.nth(i)
                if mode == "html":
                    return await node.inner_html()
                if mode == "attr":
                    if not attr:
                        return None
                    return await node.get_attribute(attr)
                text = await node.inner_text()
                return text.strip() if text else text

            if many:
                values: List[Optional[str]] = []
                for i in range(count):
                    values.append(await read_idx(i))
                output[field] = values
            else:
                output[field] = await read_idx(0)
        except Exception as exc:
            output[field] = {"error": str(exc)}
    return output

