"""Comment discovery via DOM hints and optional Playwright network capture."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import httpx
from .comments_config import get_comments_config
from .provider_adapters import resolve_adapter


logger = logging.getLogger("comment_discovery")


@dataclass
class CommentDiscoveryResult:
    capability: str
    provider: str
    thread_id: Optional[str]
    endpoint: Optional[str]
    extra_params: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


def _contains_any(text: str, keywords: List[str]) -> bool:
    low = (text or "").lower()
    return any(str(k).lower() in low for k in keywords)


def _extract_thread_id(html: str, id_hints: List[str]) -> Optional[str]:
    if not html:
        return None
    for hint in id_hints:
        pattern = rf"{re.escape(hint)}\s*[:=]\s*[\"']?([a-zA-Z0-9_-]+)"
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _extract_endpoints(html: str) -> List[str]:
    if not html:
        return []
    return list({
        m.group(0)
        for m in re.finditer(r"https?://[^\"'\s]+", html)
        if "comment" in m.group(0).lower()
    })


def _infer_provider(html: str) -> str:
    if not html:
        return "unknown"
    low = html.lower()
    if "changyan" in low:
        return "changyan"
    if "disqus" in low:
        return "disqus"
    if "livere" in low:
        return "livere"
    if "giscus" in low:
        return "giscus"
    return "unknown"


def _json_has_fields(data: Any, fields: List[str]) -> bool:
    if isinstance(data, dict):
        for key in fields:
            if key in data:
                return True
        for value in data.values():
            if _json_has_fields(value, fields):
                return True
    if isinstance(data, list):
        return any(_json_has_fields(item, fields) for item in data)
    return False


async def _discover_with_playwright(url: str, cfg: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None, None

    network_cfg = cfg.get("network_capture") or {}
    max_wait_ms = int(network_cfg.get("max_wait_ms") or 6000)
    json_fields = list(network_cfg.get("json_fields_any") or [])

    captured: List[Tuple[str, Any]] = []
    tasks: List[asyncio.Task] = []

    async def handle_response(resp) -> None:
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            data = await resp.json()
            if _json_has_fields(data, json_fields):
                captured.append((resp.url, data))
        except Exception:
            return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            page.on("response", lambda resp: tasks.append(asyncio.create_task(handle_response(resp))))
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=max_wait_ms)
                await page.wait_for_timeout(max_wait_ms)
            finally:
                await page.close()
                await browser.close()
        except Exception as exc:
            logger.warning("comment_discovery: playwright failed %s", type(exc).__name__)
            return None, None

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    if not captured:
        return None, None

    endpoint, payload = captured[0]
    thread_id = None
    for key in ("thread_id", "object_id", "docId", "newsId", "articleId"):
        if isinstance(payload, dict) and key in payload:
            thread_id = str(payload.get(key) or "")
            if thread_id:
                break
    return endpoint, thread_id


async def discover_comments(url: str) -> CommentDiscoveryResult:
    cfg_obj = get_comments_config()
    cfg = cfg_obj.get() if cfg_obj else {}
    discovery_cfg = cfg.get("comment_discovery") or {}
    captcha_keywords = list(discovery_cfg.get("captcha_keywords_any") or [])

    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            html = resp.text or ""
        except Exception as exc:
            return CommentDiscoveryResult(
                capability="none",
                provider="unknown",
                thread_id=None,
                endpoint=None,
                reason=f"fetch_failed:{type(exc).__name__}",
            )

    if _contains_any(html, captcha_keywords):
        return CommentDiscoveryResult(
            capability="blocked",
            provider="unknown",
            thread_id=None,
            endpoint=None,
            reason="captcha_detected",
        )

    adapter_result = resolve_adapter(url, html)
    if adapter_result:
        return CommentDiscoveryResult(
            capability="public",
            provider=adapter_result.provider,
            thread_id=adapter_result.thread_id,
            endpoint=adapter_result.endpoint,
            extra_params=adapter_result.extra_params,
            reason="provider_adapter",
        )

    thread_id = _extract_thread_id(html, list(discovery_cfg.get("id_hints_any") or []))
    endpoints = _extract_endpoints(html)
    provider = _infer_provider(html)

    if thread_id or endpoints or _contains_any(html, list(discovery_cfg.get("dom_hints_any") or [])):
        endpoint = endpoints[0] if endpoints else None
        return CommentDiscoveryResult(
            capability="public",
            provider=provider,
            thread_id=thread_id,
            endpoint=endpoint,
            extra_params=None,
            reason="dom_hint",
        )

    network_cfg = cfg.get("network_capture") or {}
    if bool(network_cfg.get("enabled", True)):
        endpoint, thread_id = await _discover_with_playwright(url, cfg)
        if endpoint or thread_id:
            return CommentDiscoveryResult(
                capability="public",
                provider=provider,
                thread_id=thread_id,
                endpoint=endpoint,
                extra_params=None,
                reason="network_capture",
            )

    return CommentDiscoveryResult(
        capability="none",
        provider=provider,
        thread_id=None,
        endpoint=None,
        extra_params=None,
        reason="no_signal",
    )
