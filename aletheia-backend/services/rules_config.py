"""
Rules configuration loader.
Loads rules.yaml and exposes structured dict with hot reload.
"""

from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any, Dict, Optional

from core.config import settings

logger = logging.getLogger("rules_config")

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency check
    yaml = None


_DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "pipeline": {},
    "scoring": {},
    "deep_fetch": {},
    "anti_blocking": {},
    "output": {},
}


class RulesConfig:
    def __init__(self, *, config_path: str, refresh_sec: float = 5.0):
        self._config_path = config_path
        self._refresh_sec = max(1.0, float(refresh_sec))
        self._lock = Lock()
        self._last_checked_at = 0.0
        self._last_mtime: Optional[float] = None
        self._data: Dict[str, Any] = dict(_DEFAULT_CONFIG)

    def _read_file(self, path: str) -> Optional[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return None
        if yaml is None:
            logger.warning("rules_config: PyYAML not available, skip load")
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                return None
            return data
        except Exception as exc:
            logger.warning(f"rules_config: failed to load {path}: {exc}")
            return None

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_checked_at) < self._refresh_sec:
            return
        self._last_checked_at = now

        path = self._config_path
        if not path:
            return
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            return
        if self._last_mtime is not None and mtime <= self._last_mtime:
            return
        data = self._read_file(path)
        if not data:
            return
        self._data = data
        self._last_mtime = mtime

    def get_rules(self) -> Dict[str, Any]:
        with self._lock:
            self._maybe_reload()
            return dict(self._data or {})


_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "rules.yaml"
)

_RULES_REGISTRY: Optional[RulesConfig] = None


def get_rules_registry() -> Optional[RulesConfig]:
    global _RULES_REGISTRY
    enabled = bool(getattr(settings, "RULES_CONFIG_ENABLED", True))
    if not enabled:
        return None
    if _RULES_REGISTRY is None:
        path = str(getattr(settings, "RULES_CONFIG_PATH", _DEFAULT_CONFIG_PATH))
        refresh_sec = float(getattr(settings, "RULES_CONFIG_REFRESH_SEC", 5.0))
        _RULES_REGISTRY = RulesConfig(config_path=path, refresh_sec=refresh_sec)
    return _RULES_REGISTRY
