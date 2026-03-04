"""
Source tier configuration loader and resolver.
Hot-reloadable, non-invasive, and safe fallback to Tier3.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("source_tier_config")


_DEFAULT_CONFIG = {
    "version": 1,
    "updated_at": None,
    "tiers": {
        "1": {"name": "Tier1", "trust_score": 0.95, "rules": ["official_or_regulatory"]},
        "2": {"name": "Tier2", "trust_score": 0.75, "rules": ["professional_or_mainstream"]},
        "3": {"name": "Tier3", "trust_score": 0.35, "rules": ["ugc_or_social"]},
    },
    "entries": [],
}


@dataclass(frozen=True)
class SourceTierResult:
    tier: int
    trust_score: float
    match_type: str
    matched_pattern: str
    rules: List[str]
    domain: str
    config_version: int
    config_updated_at: Optional[str]
    config_path: str


class SourceTierConfig:
    def __init__(self, *, config_path: str, refresh_sec: float = 2.0):
        self._config_path = config_path
        self._refresh_sec = max(0.5, float(refresh_sec))
        self._lock = Lock()
        self._last_checked_at = 0.0
        self._last_mtime: Optional[float] = None
        self._data: Dict[str, Any] = dict(_DEFAULT_CONFIG)

    def _read_file(self, path: str) -> Optional[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning(f"source_tier_config: failed to load {path}: {exc}")
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

    def _normalize_domain(self, value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        if "://" in raw:
            parsed = urlparse(raw)
            host = parsed.netloc or parsed.path.split("/")[0]
        else:
            host = raw.split("/")[0]
        if "@" in host:
            host = host.split("@", 1)[-1]
        if ":" in host:
            host = host.split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        return host

    def _match_entry(self, domain: str, entry: Dict[str, Any]) -> bool:
        pattern = str(entry.get("pattern") or "").strip().lower()
        if not pattern:
            return False
        match_type = str(entry.get("match") or "suffix").strip().lower()
        if match_type == "exact":
            return domain == pattern
        if match_type == "contains":
            return pattern in domain
        # suffix (default)
        return domain == pattern or domain.endswith("." + pattern) or domain.endswith(pattern)

    def resolve(self, url_or_domain: str) -> SourceTierResult:
        with self._lock:
            self._maybe_reload()
            data = self._data or {}

        domain = self._normalize_domain(url_or_domain)
        entries = list(data.get("entries") or [])
        tiers = dict(data.get("tiers") or {})
        config_version = int(data.get("version") or 1)
        config_updated_at = data.get("updated_at")

        matched: List[Tuple[int, float, Dict[str, Any]]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not self._match_entry(domain, entry):
                continue
            tier = int(entry.get("tier") or 3)
            tier_meta = tiers.get(str(tier), {})
            trust = float(entry.get("trust_score") or tier_meta.get("trust_score") or 0.35)
            matched.append((tier, trust, entry))

        if matched:
            matched.sort(key=lambda x: (x[0], -x[1]))
            tier, trust, entry = matched[0]
            rules = list(entry.get("rules") or []) or list(tiers.get(str(tier), {}).get("rules") or [])
            return SourceTierResult(
                tier=tier,
                trust_score=round(trust, 4),
                match_type=str(entry.get("match") or "suffix"),
                matched_pattern=str(entry.get("pattern") or ""),
                rules=[str(r) for r in rules],
                domain=domain,
                config_version=config_version,
                config_updated_at=config_updated_at,
                config_path=self._config_path,
            )

        tier_meta = tiers.get("3", {})
        return SourceTierResult(
            tier=3,
            trust_score=round(float(tier_meta.get("trust_score") or 0.35), 4),
            match_type="fallback",
            matched_pattern="",
            rules=[str(r) for r in list(tier_meta.get("rules") or ["ugc_or_social"])],
            domain=domain,
            config_version=config_version,
            config_updated_at=config_updated_at,
            config_path=self._config_path,
        )


_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "source_tier_config.json"
)


def get_source_tier_resolver() -> SourceTierConfig:
    path = os.getenv("SOURCE_TIER_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
    try:
        refresh_sec = float(os.getenv("SOURCE_TIER_CONFIG_REFRESH_SEC", "2.0"))
    except Exception:
        refresh_sec = 2.0
    return SourceTierConfig(config_path=path, refresh_sec=refresh_sec)


_RESOLVER = get_source_tier_resolver()


def resolve_source_tier(url_or_domain: str) -> SourceTierResult:
    return _RESOLVER.resolve(url_or_domain)
