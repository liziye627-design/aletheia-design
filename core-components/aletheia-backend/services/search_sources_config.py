"""
Search sources configuration loader.
Loads search_sources.yaml and exposes flattened, merged entries.
"""

from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

from core.config import settings

logger = logging.getLogger("search_sources_config")

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency check
    yaml = None


_DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "defaults": {},
    "groups": [],
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out.get(key) or {}, value)
        else:
            out[key] = value
    return out


class SearchSourcesConfig:
    def __init__(
        self,
        *,
        config_path: str,
        refresh_sec: float = 5.0,
        extra_paths: Optional[Iterable[str]] = None,
    ):
        self._config_path = config_path
        self._extra_paths = [
            str(p).strip()
            for p in (extra_paths or [])
            if str(p or "").strip()
        ]
        self._refresh_sec = max(1.0, float(refresh_sec))
        self._lock = Lock()
        self._last_checked_at = 0.0
        self._last_mtime: Optional[float] = None
        self._extra_mtimes: Dict[str, Optional[float]] = {
            path: None for path in self._extra_paths
        }
        self._flat_cache: List[Dict[str, Any]] = []

    def _read_file(self, path: str) -> Optional[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return None
        if yaml is None:
            logger.warning("search_sources_config: PyYAML not available, skip load")
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                return None
            return data
        except Exception as exc:
            logger.warning(f"search_sources_config: failed to load {path}: {exc}")
            return None

    def _flatten_sources(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        defaults = data.get("defaults") if isinstance(data, dict) else None
        defaults = defaults if isinstance(defaults, dict) else {}
        groups = data.get("groups") if isinstance(data, dict) else None
        groups = groups if isinstance(groups, list) else []

        out: List[Dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            group_defaults = _deep_merge(defaults, group.get("defaults_override") or {})
            group_id = str(group.get("group_id") or "").strip()
            group_name = str(group.get("name") or group_id or "").strip()
            for source in group.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                merged = _deep_merge(group_defaults, source)
                merged["group_id"] = group_id
                merged["group_name"] = group_name
                merged["source_id"] = str(
                    merged.get("source_id") or source.get("source_id") or ""
                ).strip()
                merged["platform"] = str(merged.get("platform") or "").strip()
                merged["lang"] = str(merged.get("lang") or "zh").strip().lower()
                merged["tier"] = str(merged.get("tier") or "B").strip().upper()
                merged["pool"] = str(merged.get("pool") or "evidence").strip().lower()
                merged["discovery_mode"] = str(
                    merged.get("discovery_mode") or "search"
                ).strip().lower()
                out.append(merged)
        return out

    def _maybe_reload(self) -> None:
        now = time.time()
        if (now - self._last_checked_at) < self._refresh_sec:
            return
        self._last_checked_at = now

        paths = [self._config_path] + list(self._extra_paths)
        mtimes: Dict[str, float] = {}
        changed = False
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                continue
            mtimes[path] = mtime
            if path == self._config_path:
                if self._last_mtime is None or mtime > self._last_mtime:
                    changed = True
            else:
                last = self._extra_mtimes.get(path)
                if last is None or mtime > last:
                    changed = True
        if not changed and self._flat_cache:
            return

        data_list: List[Dict[str, Any]] = []
        for path in paths:
            data = self._read_file(path)
            if data:
                data_list.append(data)
        if not data_list:
            return

        flat: List[Dict[str, Any]] = []
        for data in data_list:
            flat.extend(self._flatten_sources(data))
        self._flat_cache = flat
        if self._config_path in mtimes:
            self._last_mtime = mtimes.get(self._config_path)
        for path in self._extra_paths:
            if path in mtimes:
                self._extra_mtimes[path] = mtimes.get(path)

    def get_sources(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._maybe_reload()
            return list(self._flat_cache)

    def get_enabled_sources(self) -> List[Dict[str, Any]]:
        return [
            row
            for row in self.get_sources()
            if bool(row.get("enabled", True))
            and str(row.get("platform") or "").strip()
        ]

    def get_sources_for_platform(self, platform: str) -> List[Dict[str, Any]]:
        target = str(platform or "").strip().lower()
        if not target:
            return []
        return [
            row
            for row in self.get_enabled_sources()
            if str(row.get("platform") or "").strip().lower() == target
        ]

    def get_enabled_platforms(self, *, lang: Optional[str] = None) -> List[str]:
        out: List[str] = []
        lang_filter = str(lang or "").strip().lower()
        for row in self.get_enabled_sources():
            if lang_filter and str(row.get("lang") or "").strip().lower() != lang_filter:
                continue
            platform = str(row.get("platform") or "").strip()
            if platform and platform not in out:
                out.append(platform)
        return out


_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "search_sources.yaml"
)


def get_search_sources_registry() -> Optional[SearchSourcesConfig]:
    enabled = bool(getattr(settings, "SEARCH_SOURCES_CONFIG_ENABLED", True))
    if not enabled:
        return None
    path = str(
        getattr(settings, "SEARCH_SOURCES_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
    ).strip()
    refresh_sec = float(getattr(settings, "SEARCH_SOURCES_CONFIG_REFRESH_SEC", 5.0))
    extra_paths_raw = str(
        getattr(settings, "SEARCH_SOURCES_CONFIG_EXTRA_PATHS", "") or ""
    )
    extra_paths = [
        p.strip()
        for p in extra_paths_raw.replace(";", ",").replace("\n", ",").split(",")
        if p.strip()
    ]
    return SearchSourcesConfig(
        config_path=path,
        refresh_sec=refresh_sec,
        extra_paths=extra_paths,
    )
