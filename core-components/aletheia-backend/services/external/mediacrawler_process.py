"""
MediaCrawler sidecar 进程管理。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import settings
from services.external.mediacrawler_client import get_mediacrawler_client
from utils.logging import logger


class MediaCrawlerProcessManager:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._last_error: str = ""
        self._auto_started: bool = False

    @property
    def active(self) -> bool:
        return bool(
            getattr(settings, "MEDIACRAWLER_ENABLED", False)
            and getattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False)
        )

    @property
    def auto_start(self) -> bool:
        return bool(getattr(settings, "MEDIACRAWLER_AUTO_START", True))

    @property
    def base_url(self) -> str:
        return str(getattr(settings, "MEDIACRAWLER_BASE_URL", "http://127.0.0.1:8080"))

    @property
    def process(self) -> Optional[subprocess.Popen]:
        return self._process

    @property
    def pid(self) -> Optional[int]:
        if self._process and self._process.poll() is None:
            return int(self._process.pid)
        return None

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def auto_started(self) -> bool:
        return self._auto_started

    def _resolve_home(self) -> Path:
        home = str(
            getattr(settings, "MEDIACRAWLER_HOME", "third_party/MediaCrawler")
            or "third_party/MediaCrawler"
        )
        home_path = Path(home)
        if home_path.is_absolute():
            return home_path

        # Prefer CWD-relative path first for CLI/dev usage.
        cwd_candidate = (Path(os.getcwd()) / home_path).resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        # Fallback to backend-root relative path for service/runtime usage.
        backend_root = Path(__file__).resolve().parents[2]
        backend_candidate = (backend_root / home_path).resolve()
        return backend_candidate

    async def wait_until_healthy(self, timeout_sec: Optional[float] = None) -> bool:
        timeout = float(timeout_sec or getattr(settings, "MEDIACRAWLER_STARTUP_TIMEOUT_SEC", 45))
        client = get_mediacrawler_client()
        deadline = asyncio.get_event_loop().time() + max(3.0, timeout)
        while asyncio.get_event_loop().time() < deadline:
            health = await client.health_check()
            if health.get("ok") and bool(health.get("healthy")):
                return True
            await asyncio.sleep(1.2)
        return False

    async def ensure_started(self) -> Dict[str, Any]:
        if not self.active:
            reason = "MEDIACRAWLER_DISABLED"
            if bool(getattr(settings, "MEDIACRAWLER_ENABLED", False)) and not bool(
                getattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False)
            ):
                reason = "MEDIACRAWLER_ACK_REQUIRED"
            self._last_error = reason
            return {
                "ok": False,
                "reason": reason,
                "healthy": False,
                "auto_started": False,
                "pid": None,
            }

        client = get_mediacrawler_client()
        healthy = await client.health_check()
        if healthy.get("ok") and bool(healthy.get("healthy")):
            self._last_error = ""
            return {
                "ok": True,
                "reason": "ALREADY_HEALTHY",
                "healthy": True,
                "auto_started": False,
                "pid": self.pid,
            }

        if not self.auto_start:
            self._last_error = "MEDIACRAWLER_UNAVAILABLE_AUTO_START_DISABLED"
            return {
                "ok": False,
                "reason": "MEDIACRAWLER_UNAVAILABLE_AUTO_START_DISABLED",
                "healthy": False,
                "auto_started": False,
                "pid": self.pid,
            }

        home = self._resolve_home()
        if not home.exists():
            self._last_error = f"MEDIACRAWLER_HOME_NOT_FOUND:{home}"
            return {
                "ok": False,
                "reason": "MEDIACRAWLER_HOME_NOT_FOUND",
                "healthy": False,
                "auto_started": False,
                "pid": None,
                "home": str(home),
            }

        if self._process and self._process.poll() is None:
            # 进程已在运行，直接等待健康。
            ready = await self.wait_until_healthy()
            if ready:
                self._last_error = ""
                return {
                    "ok": True,
                    "reason": "STARTED_AND_HEALTHY",
                    "healthy": True,
                    "auto_started": self._auto_started,
                    "pid": self.pid,
                }
            self._last_error = "MEDIACRAWLER_STARTUP_TIMEOUT"
            return {
                "ok": False,
                "reason": "MEDIACRAWLER_STARTUP_TIMEOUT",
                "healthy": False,
                "auto_started": self._auto_started,
                "pid": self.pid,
            }

        cmd = str(
            getattr(
                settings,
                "MEDIACRAWLER_START_COMMAND",
                "uv run uvicorn api.main:app --host 127.0.0.1 --port 8080",
            )
        ).strip()
        try:
            self._process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(home),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._auto_started = True
            ready = await self.wait_until_healthy()
            if ready:
                self._last_error = ""
                return {
                    "ok": True,
                    "reason": "STARTED_AND_HEALTHY",
                    "healthy": True,
                    "auto_started": True,
                    "pid": self.pid,
                }
            self._last_error = "MEDIACRAWLER_STARTUP_TIMEOUT"
            return {
                "ok": False,
                "reason": "MEDIACRAWLER_STARTUP_TIMEOUT",
                "healthy": False,
                "auto_started": True,
                "pid": self.pid,
            }
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(f"mediacrawler auto start failed: {exc}")
            return {
                "ok": False,
                "reason": "MEDIACRAWLER_START_FAILED",
                "healthy": False,
                "auto_started": False,
                "pid": None,
                "error": str(exc),
            }

    async def stop(self) -> Dict[str, Any]:
        process = self._process
        if process is None:
            return {"ok": True, "reason": "NOT_RUNNING", "stopped": False}
        if process.poll() is not None:
            self._process = None
            return {"ok": True, "reason": "ALREADY_EXITED", "stopped": False}
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            self._process = None
            return {"ok": True, "reason": "STOPPED", "stopped": True}
        except Exception as exc:
            self._last_error = str(exc)
            return {"ok": False, "reason": "STOP_FAILED", "error": str(exc), "stopped": False}

    async def diagnostics(self) -> Dict[str, Any]:
        client = get_mediacrawler_client()
        health = await client.health_check()
        return {
            "enabled": bool(getattr(settings, "MEDIACRAWLER_ENABLED", False)),
            "ack": bool(getattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False)),
            "active": self.active,
            "base_url": self.base_url,
            "healthy": bool(health.get("ok") and health.get("healthy")),
            "health_reason": str(health.get("reason") or ""),
            "auto_start": self.auto_start,
            "auto_started": self._auto_started,
            "pid": self.pid,
            "last_error": self._last_error,
            "supported_platforms": list(getattr(client, "supported_platforms", []) or []),
        }


_mediacrawler_process_manager_singleton: Optional[MediaCrawlerProcessManager] = None


def get_mediacrawler_process_manager() -> MediaCrawlerProcessManager:
    global _mediacrawler_process_manager_singleton
    if _mediacrawler_process_manager_singleton is None:
        _mediacrawler_process_manager_singleton = MediaCrawlerProcessManager()
    return _mediacrawler_process_manager_singleton
