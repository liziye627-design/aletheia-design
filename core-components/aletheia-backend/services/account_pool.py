"""
微博/知乎账号池：Cookie 轮转 + 失败熔断冷却。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from core.config import settings
from utils.logging import logger


def _unique_nonempty(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for row in values:
        value = str(row or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def parse_cookie_pool(raw: str) -> List[str]:
    """
    解析 Cookie 池配置，支持:
    - JSON 数组
    - 换行分隔
    - `||` 分隔

    注意：Cookie 本身通常包含 `;`，因此不使用分号/逗号作为分隔符。
    """
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _unique_nonempty([str(x or "") for x in parsed])
        except Exception:
            pass
    if "||" in text:
        return _unique_nonempty([x for x in text.split("||") if str(x or "").strip()])
    normalized = text.replace("\r", "\n")
    if "\n" in normalized:
        return _unique_nonempty([x for x in normalized.split("\n") if x.strip()])
    return _unique_nonempty([normalized])


@dataclass
class AccountState:
    cookie: str
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_used_at: float = 0.0
    success_count: int = 0
    failure_count: int = 0


class AccountPool:
    def __init__(
        self,
        *,
        platform: str,
        cookies: List[str],
        max_failures: int,
        cooldown_sec: int,
    ) -> None:
        self.platform = str(platform)
        self.max_failures = max(1, int(max_failures))
        self.cooldown_sec = max(1, int(cooldown_sec))
        self._items: List[AccountState] = [AccountState(cookie=c) for c in _unique_nonempty(cookies)]
        self._cursor = 0
        self._lock = threading.Lock()

    def size(self) -> int:
        return len(self._items)

    def acquire_cookie(self) -> str:
        if not self._items:
            return ""
        now = time.time()
        with self._lock:
            for _ in range(len(self._items)):
                idx = self._cursor % len(self._items)
                self._cursor = (self._cursor + 1) % len(self._items)
                state = self._items[idx]
                if state.cooldown_until > now:
                    continue
                state.last_used_at = now
                return state.cookie
            # 全部都在冷却：返回最早恢复的账号，避免全平台硬停。
            state = min(self._items, key=lambda x: x.cooldown_until)
            state.last_used_at = now
            return state.cookie

    def mark_success(self, cookie: str) -> None:
        if not cookie:
            return
        with self._lock:
            state = self._find_state(cookie)
            if state is None:
                return
            state.consecutive_failures = 0
            state.cooldown_until = 0.0
            state.last_error = ""
            state.success_count += 1

    def mark_failure(self, cookie: str, reason: str = "") -> None:
        if not cookie:
            return
        now = time.time()
        with self._lock:
            state = self._find_state(cookie)
            if state is None:
                return
            state.failure_count += 1
            state.consecutive_failures += 1
            state.last_error = str(reason or "")
            if state.consecutive_failures >= self.max_failures:
                state.cooldown_until = now + float(self.cooldown_sec)
                state.consecutive_failures = 0
                logger.warning(
                    f"account_pool cooldown platform={self.platform} "
                    f"cooldown_sec={self.cooldown_sec} reason={state.last_error or 'unknown'}"
                )

    def snapshot(self) -> Dict[str, object]:
        now = time.time()
        with self._lock:
            cooled_down = sum(1 for x in self._items if x.cooldown_until > now)
            return {
                "platform": self.platform,
                "total_accounts": len(self._items),
                "cooldown_accounts": cooled_down,
                "available_accounts": max(0, len(self._items) - cooled_down),
                "max_failures": self.max_failures,
                "cooldown_sec": self.cooldown_sec,
            }

    def _find_state(self, cookie: str) -> Optional[AccountState]:
        for row in self._items:
            if row.cookie == cookie:
                return row
        return None


class AccountPoolManager:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "ACCOUNT_POOL_ENABLED", True))
        self.max_failures = int(getattr(settings, "ACCOUNT_POOL_MAX_FAILURES", 3))
        self.cooldown_sec = int(getattr(settings, "ACCOUNT_POOL_COOLDOWN_SEC", 300))
        self._pools: Dict[str, AccountPool] = {}
        self._init_from_settings()

    def _init_from_settings(self) -> None:
        if not self.enabled:
            return
        self._register_pool(
            platform="weibo",
            pool_raw=str(getattr(settings, "WEIBO_COOKIES_POOL", "") or ""),
            single=str(getattr(settings, "WEIBO_COOKIES", "") or ""),
        )
        self._register_pool(
            platform="zhihu",
            pool_raw=str(getattr(settings, "ZHIHU_COOKIES_POOL", "") or ""),
            single=str(getattr(settings, "ZHIHU_COOKIES", "") or ""),
        )

    def _register_pool(self, *, platform: str, pool_raw: str, single: str) -> None:
        cookies = parse_cookie_pool(pool_raw)
        if not cookies and str(single or "").strip():
            cookies = [str(single).strip()]
        if not cookies:
            return
        self._pools[platform] = AccountPool(
            platform=platform,
            cookies=cookies,
            max_failures=self.max_failures,
            cooldown_sec=self.cooldown_sec,
        )
        logger.info(f"account_pool ready platform={platform} accounts={len(cookies)}")

    def get_pool(self, platform: str) -> Optional[AccountPool]:
        return self._pools.get(str(platform or "").strip().lower())

    def acquire_cookie(self, platform: str) -> str:
        pool = self.get_pool(platform)
        if not pool:
            return ""
        return pool.acquire_cookie()

    def mark_success(self, platform: str, cookie: str) -> None:
        pool = self.get_pool(platform)
        if pool:
            pool.mark_success(cookie)

    def mark_failure(self, platform: str, cookie: str, reason: str = "") -> None:
        pool = self.get_pool(platform)
        if pool:
            pool.mark_failure(cookie, reason=reason)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        return {name: pool.snapshot() for name, pool in self._pools.items()}


_POOL_MANAGER: Optional[AccountPoolManager] = None
_POOL_LOCK = threading.Lock()


def get_account_pool_manager() -> AccountPoolManager:
    global _POOL_MANAGER
    if _POOL_MANAGER is not None:
        return _POOL_MANAGER
    with _POOL_LOCK:
        if _POOL_MANAGER is None:
            _POOL_MANAGER = AccountPoolManager()
    return _POOL_MANAGER
