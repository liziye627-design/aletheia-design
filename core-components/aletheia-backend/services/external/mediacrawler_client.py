"""
MediaCrawler sidecar API 客户端（软降级）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from core.config import settings
from utils.logging import logger

PLATFORM_CODE_MAP: Dict[str, str] = {
    "xiaohongshu": "xhs",
    "douyin": "dy",
    "weibo": "wb",
    "zhihu": "zhihu",
}

DEFAULT_SUPPORTED_PLATFORMS = ("xiaohongshu", "douyin", "weibo", "zhihu")
LOGIN_HINT_KEYWORDS = (
    "login",
    "qrcode",
    "scan",
    "cookie may be invalid",
    "again login",
    "captcha",
)


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


class MediaCrawlerClient:
    def __init__(self) -> None:
        self.base_url = str(
            getattr(settings, "MEDIACRAWLER_BASE_URL", "http://127.0.0.1:8080")
        ).rstrip("/")
        self.request_timeout_sec = float(
            getattr(settings, "MEDIACRAWLER_REQUEST_TIMEOUT_SEC", 15)
        )
        self.task_timeout_sec = float(
            getattr(settings, "MEDIACRAWLER_TASK_TIMEOUT_SEC", 120)
        )
        platforms_raw = str(
            getattr(
                settings,
                "MEDIACRAWLER_PLATFORMS",
                "xiaohongshu,douyin,weibo,zhihu",
            )
        )
        self.supported_platforms: List[str] = [
            str(x).strip().lower()
            for x in platforms_raw.split(",")
            if str(x).strip()
        ]
        if not self.supported_platforms:
            self.supported_platforms = list(DEFAULT_SUPPORTED_PLATFORMS)

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "MEDIACRAWLER_ENABLED", False))

    @property
    def acked(self) -> bool:
        return bool(getattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False))

    @property
    def active(self) -> bool:
        return self.enabled and self.acked

    def _unavailable(self, reason: str, **extra: Any) -> Dict[str, Any]:
        return {
            "ok": False,
            "reason": reason,
            "fetched_at": _utc_now(),
            **extra,
        }

    def _platform_code(self, platform: str) -> str:
        return PLATFORM_CODE_MAP.get(str(platform or "").strip().lower(), "")

    def supports_platform(self, platform: str) -> bool:
        normalized = str(platform or "").strip().lower()
        return normalized in set(self.supported_platforms)

    def _looks_like_login_required(self, logs: List[Dict[str, Any]]) -> bool:
        for row in logs:
            msg = str(row.get("message") or "").lower()
            if any(key in msg for key in LOGIN_HINT_KEYWORDS):
                return True
        return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        timeout = httpx.Timeout(
            max(1.0, float(timeout_sec or self.request_timeout_sec)),
            connect=min(5.0, max(1.0, float(timeout_sec or self.request_timeout_sec))),
        )
        url = f"{self.base_url}{path}"
        try:
            # Always bypass env proxy for local sidecar calls (127.0.0.1),
            # otherwise corporate/dev proxy may return 502 and mark sidecar unhealthy.
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=False,
            ) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                )
                data = resp.json() if resp.content else {}
                if resp.status_code >= 400:
                    return self._unavailable(
                        "MEDIACRAWLER_REQUEST_FAILED",
                        status_code=int(resp.status_code),
                        detail=str(data or resp.text or ""),
                    )
                return {"ok": True, "data": data, "status_code": int(resp.status_code)}
        except httpx.TimeoutException:
            return self._unavailable("MEDIACRAWLER_TIMEOUT")
        except Exception as exc:
            return self._unavailable("MEDIACRAWLER_UNAVAILABLE", error=str(exc))

    async def health_check(self) -> Dict[str, Any]:
        if not self.active:
            reason = "MEDIACRAWLER_DISABLED"
            if self.enabled and not self.acked:
                reason = "MEDIACRAWLER_ACK_REQUIRED"
            return self._unavailable(reason)

        # Prefer `/api/health`; fallback to crawler status endpoint.
        health = await self._request("GET", "/api/health")
        if health.get("ok"):
            return {"ok": True, "reason": "OK", "healthy": True, "payload": health.get("data") or {}}

        status = await self._request("GET", "/api/crawler/status")
        if status.get("ok"):
            payload = status.get("data") or {}
            return {
                "ok": True,
                "reason": "OK",
                "healthy": True,
                "payload": payload,
                "crawler_status": str(payload.get("status") or "unknown"),
            }
        return self._unavailable(
            str(status.get("reason") or "MEDIACRAWLER_UNAVAILABLE"),
            error=status.get("error") or status.get("detail"),
        )

    async def stop_task(self) -> Dict[str, Any]:
        if not self.active:
            return self._unavailable("MEDIACRAWLER_DISABLED")
        response = await self._request(
            "POST",
            "/api/crawler/stop",
            timeout_sec=self.request_timeout_sec,
        )
        if response.get("ok"):
            return {"ok": True, "reason": "STOPPED"}
        # stop endpoint may return 400 when already stopped; treat as non-fatal
        detail = str(response.get("detail") or "").lower()
        if "no crawler is running" in detail:
            return {"ok": True, "reason": "ALREADY_STOPPED"}
        return response

    async def get_recent_logs(self, *, limit: int = 80) -> Dict[str, Any]:
        if not self.active:
            return self._unavailable("MEDIACRAWLER_DISABLED")
        response = await self._request(
            "GET",
            "/api/crawler/logs",
            params={"limit": max(10, int(limit))},
        )
        if not response.get("ok"):
            return response
        logs = list((response.get("data") or {}).get("logs") or [])
        return {"ok": True, "reason": "OK", "logs": logs}

    async def start_task(
        self,
        *,
        platform: str,
        crawler_type: str,
        keyword: str = "",
        spec_ids: str = "",
        enable_comments: bool = True,
        timeout_sec: Optional[float] = None,
        max_count: int = 80,
    ) -> Dict[str, Any]:
        if not self.active:
            return self._unavailable("MEDIACRAWLER_DISABLED")
        normalized = str(platform or "").strip().lower()
        if not self.supports_platform(normalized):
            return self._unavailable("MEDIACRAWLER_PLATFORM_UNSUPPORTED", platform=normalized)
        platform_code = self._platform_code(normalized)
        if not platform_code:
            return self._unavailable("MEDIACRAWLER_PLATFORM_CODE_MISSING", platform=normalized)

        body = {
            "platform": platform_code,
            "crawler_type": str(crawler_type or "search"),
            "keywords": str(keyword or ""),
            "specified_ids": str(spec_ids or ""),
            "start_page": 1,
            "enable_comments": bool(enable_comments),
            "enable_sub_comments": False,
            "save_option": "json",
            "headless": bool(getattr(settings, "MEDIACRAWLER_HEADLESS", False)),
        }
        response = await self._request(
            "POST",
            "/api/crawler/start",
            json_body=body,
            timeout_sec=timeout_sec or self.request_timeout_sec,
        )
        if not response.get("ok"):
            reason = str(response.get("reason") or "MEDIACRAWLER_REQUEST_FAILED")
            if "already running" in str(response.get("detail") or "").lower():
                reason = "MEDIACRAWLER_BUSY"
            return self._unavailable(reason, detail=response.get("detail"))
        task_id = f"mc_{normalized}_{int(datetime.utcnow().timestamp() * 1000)}"
        return {
            "ok": True,
            "reason": "STARTED",
            "task_id": task_id,
            "platform": normalized,
            "crawler_type": str(crawler_type or "search"),
            "max_count": int(max_count),
            "started_at": _utc_now(),
        }

    async def poll_status(
        self,
        *,
        timeout_sec: Optional[float] = None,
        poll_interval_sec: float = 1.5,
    ) -> Dict[str, Any]:
        if not self.active:
            return self._unavailable("MEDIACRAWLER_DISABLED")
        deadline = asyncio.get_event_loop().time() + float(timeout_sec or self.task_timeout_sec)
        last_status: Dict[str, Any] = {}
        probe_idx = 0
        while asyncio.get_event_loop().time() < deadline:
            row = await self._request("GET", "/api/crawler/status")
            if not row.get("ok"):
                return self._unavailable(
                    str(row.get("reason") or "MEDIACRAWLER_UNAVAILABLE"),
                    detail=row.get("detail"),
                )
            payload = row.get("data") if isinstance(row.get("data"), dict) else {}
            status = str(payload.get("status") or "unknown").lower()
            last_status = payload
            if status in {"idle"}:
                return {"ok": True, "reason": "DONE", "status": status, "payload": payload}
            if status in {"error"}:
                return self._unavailable(
                    "MEDIACRAWLER_TASK_FAILED",
                    status=status,
                    payload=payload,
                )
            probe_idx += 1
            if probe_idx % 3 == 0:
                logs = await self.get_recent_logs(limit=60)
                if logs.get("ok") and self._looks_like_login_required(list(logs.get("logs") or [])):
                    return self._unavailable(
                        "MEDIACRAWLER_LOGIN_REQUIRED",
                        status=status,
                        payload=payload,
                    )
            await asyncio.sleep(max(0.5, float(poll_interval_sec)))
        return self._unavailable("MEDIACRAWLER_TIMEOUT", payload=last_status)

    async def list_data_files(
        self,
        *,
        platform: str,
        file_type: str = "json",
    ) -> Dict[str, Any]:
        normalized = str(platform or "").strip().lower()
        platform_code = self._platform_code(normalized)
        if not platform_code:
            return self._unavailable("MEDIACRAWLER_PLATFORM_CODE_MISSING", platform=normalized)
        return await self._request(
            "GET",
            "/api/data/files",
            params={"platform": platform_code, "file_type": str(file_type or "json")},
        )

    async def get_file_preview(self, path: str, *, limit: int = 120) -> Dict[str, Any]:
        safe_path = str(path or "").strip().lstrip("/")
        if not safe_path:
            return self._unavailable("MEDIACRAWLER_FILE_EMPTY_PATH")
        return await self._request(
            "GET",
            f"/api/data/files/{safe_path}",
            params={"preview": "true", "limit": max(1, int(limit))},
        )

    async def collect_search_items(
        self,
        *,
        platform: str,
        keyword: str,
        max_items: int = 80,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        start = await self.start_task(
            platform=platform,
            crawler_type="search",
            keyword=keyword,
            enable_comments=True,
            timeout_sec=timeout_sec,
            max_count=max_items,
        )
        if not start.get("ok"):
            if str(start.get("reason") or "") == "MEDIACRAWLER_BUSY":
                status_busy = await self.poll_status(timeout_sec=timeout_sec or self.task_timeout_sec)
                if not status_busy.get("ok"):
                    return status_busy
            else:
                return start
        status = await self.poll_status(timeout_sec=timeout_sec or self.task_timeout_sec)
        if not status.get("ok"):
            return {
                **status,
                "task_id": start.get("task_id"),
            }
        files = await self.list_data_files(platform=platform, file_type="json")
        if not files.get("ok"):
            return {
                **files,
                "task_id": start.get("task_id"),
            }
        file_rows = list((files.get("data") or {}).get("files") or [])
        if not file_rows:
            logs = await self.get_recent_logs(limit=80)
            if logs.get("ok") and self._looks_like_login_required(list(logs.get("logs") or [])):
                return self._unavailable(
                    "MEDIACRAWLER_LOGIN_REQUIRED",
                    task_id=start.get("task_id"),
                )
            return self._unavailable("MEDIACRAWLER_NO_DATA_FILES", task_id=start.get("task_id"))

        # 优先最新文件
        best = file_rows[0]
        path = str(best.get("path") or "")
        preview = await self.get_file_preview(path, limit=max(20, int(max_items)))
        if not preview.get("ok"):
            return {
                **preview,
                "task_id": start.get("task_id"),
                "file_path": path,
            }
        data = (preview.get("data") or {}).get("data")
        if not isinstance(data, list):
            data = []
        return {
            "ok": True,
            "reason": "OK",
            "task_id": start.get("task_id"),
            "file_path": path,
            "items": data[: max(1, int(max_items))],
            "fetched_at": _utc_now(),
        }

    async def collect_detail_with_comments(
        self,
        *,
        platform: str,
        post_id: str,
        max_items: int = 120,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        start = await self.start_task(
            platform=platform,
            crawler_type="detail",
            spec_ids=str(post_id or ""),
            enable_comments=True,
            timeout_sec=timeout_sec,
            max_count=max_items,
        )
        if not start.get("ok"):
            if str(start.get("reason") or "") == "MEDIACRAWLER_BUSY":
                status_busy = await self.poll_status(timeout_sec=timeout_sec or self.task_timeout_sec)
                if not status_busy.get("ok"):
                    return status_busy
            else:
                return start
        status = await self.poll_status(timeout_sec=timeout_sec or self.task_timeout_sec)
        if not status.get("ok"):
            return {
                **status,
                "task_id": start.get("task_id"),
            }
        files = await self.list_data_files(platform=platform, file_type="json")
        if not files.get("ok"):
            return {
                **files,
                "task_id": start.get("task_id"),
            }
        file_rows = list((files.get("data") or {}).get("files") or [])
        if not file_rows:
            logs = await self.get_recent_logs(limit=80)
            if logs.get("ok") and self._looks_like_login_required(list(logs.get("logs") or [])):
                return self._unavailable(
                    "MEDIACRAWLER_LOGIN_REQUIRED",
                    task_id=start.get("task_id"),
                )
            return self._unavailable("MEDIACRAWLER_NO_DATA_FILES", task_id=start.get("task_id"))
        best = file_rows[0]
        path = str(best.get("path") or "")
        preview = await self.get_file_preview(path, limit=max(20, int(max_items)))
        if not preview.get("ok"):
            return {
                **preview,
                "task_id": start.get("task_id"),
                "file_path": path,
            }
        data = (preview.get("data") or {}).get("data")
        if not isinstance(data, list):
            data = []
        return {
            "ok": True,
            "reason": "OK",
            "task_id": start.get("task_id"),
            "file_path": path,
            "items": data[: max(1, int(max_items))],
            "fetched_at": _utc_now(),
        }


_mediacrawler_client_singleton: Optional[MediaCrawlerClient] = None


def get_mediacrawler_client() -> MediaCrawlerClient:
    global _mediacrawler_client_singleton
    if _mediacrawler_client_singleton is None:
        _mediacrawler_client_singleton = MediaCrawlerClient()
    return _mediacrawler_client_singleton
