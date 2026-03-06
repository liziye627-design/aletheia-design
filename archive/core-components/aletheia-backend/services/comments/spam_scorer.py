"""Rule-based spam scorer for comment batches."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from core.config import settings

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:
    from dateutil import parser as date_parser
except Exception:  # pragma: no cover
    date_parser = None


logger = logging.getLogger("spam_scorer")


_DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "spam_scoring": {"base": 0, "cap": 100},
    "rules": [],
    "cluster_rules": [],
    "output": {"flags_field": "spam_flags", "score_field": "spam_score"},
}


class SpamRulesConfig:
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
            logger.warning("spam_scorer: PyYAML not available, skip load")
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                return None
            return data
        except Exception as exc:
            logger.warning("spam_scorer: failed to load %s: %s", path, exc)
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
        merged = dict(_DEFAULT_CONFIG)
        merged.update(data)
        self._data = merged
        self._last_mtime = mtime

    def get(self) -> Dict[str, Any]:
        with self._lock:
            self._maybe_reload()
            return dict(self._data)


_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "spam_rules.yaml",
)


def get_spam_rules_config() -> Optional[SpamRulesConfig]:
    enabled = bool(getattr(settings, "SPAM_RULES_CONFIG_ENABLED", True))
    if not enabled:
        return None
    path = str(getattr(settings, "SPAM_RULES_CONFIG_PATH", _DEFAULT_CONFIG_PATH))
    refresh_sec = float(getattr(settings, "SPAM_RULES_CONFIG_REFRESH_SEC", 5.0))
    return SpamRulesConfig(config_path=path, refresh_sec=refresh_sec)


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    out = re.sub(r"\s+", " ", text.strip())
    return out


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"\w+", text.lower())
    if tokens:
        return tokens
    return list(text)


def _simhash(text: str) -> int:
    tokens = _tokenize(text)
    if not tokens:
        return 0
    vector = [0] * 64
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(64):
            bit = (h >> i) & 1
            vector[i] += 1 if bit else -1
    fingerprint = 0
    for i, value in enumerate(vector):
        if value > 0:
            fingerprint |= 1 << i
    return fingerprint


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _parse_datetime(value: Any) -> Optional[float]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if date_parser is None:
        return None
    try:
        dt = date_parser.parse(str(value))
        return dt.timestamp()
    except Exception:
        return None


def _apply_burst_rule(comments: List[Dict[str, Any]], rule: Dict[str, Any]) -> List[int]:
    window_minutes = int(rule.get("burst", {}).get("window_minutes") or 5)
    min_count = int(rule.get("burst", {}).get("min_comments_in_window") or 30)
    timestamps: List[Tuple[int, float]] = []
    for idx, comment in enumerate(comments):
        ts = _parse_datetime(comment.get("created_at"))
        if ts is not None:
            timestamps.append((idx, ts))
    if len(timestamps) < min_count:
        return []
    timestamps.sort(key=lambda x: x[1])
    hit_indices: List[int] = []
    window_sec = window_minutes * 60
    left = 0
    for right in range(len(timestamps)):
        while timestamps[right][1] - timestamps[left][1] > window_sec:
            left += 1
        if right - left + 1 >= min_count:
            hit_indices.extend([idx for idx, _ in timestamps[left : right + 1]])
    return list(set(hit_indices))


def _cluster_by_simhash(hashes: List[int], max_dist: int) -> List[int]:
    cluster_ids = [-1] * len(hashes)
    cluster = 0
    for i, h in enumerate(hashes):
        if cluster_ids[i] >= 0:
            continue
        cluster_ids[i] = cluster
        for j in range(i + 1, len(hashes)):
            if cluster_ids[j] >= 0:
                continue
            if _hamming(h, hashes[j]) <= max_dist:
                cluster_ids[j] = cluster
        cluster += 1
    return cluster_ids


def score_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cfg_obj = get_spam_rules_config()
    cfg = cfg_obj.get() if cfg_obj else dict(_DEFAULT_CONFIG)

    rules = list(cfg.get("rules") or [])
    cluster_rules = list(cfg.get("cluster_rules") or [])
    flags_field = (cfg.get("output") or {}).get("flags_field") or "spam_flags"
    score_field = (cfg.get("output") or {}).get("score_field") or "spam_score"
    base_score = float((cfg.get("spam_scoring") or {}).get("base") or 0)
    cap_score = float((cfg.get("spam_scoring") or {}).get("cap") or 100)

    for comment in comments:
        comment[flags_field] = []
        comment[score_field] = base_score

    # Per-comment rules
    for rule in rules:
        rule_id = str(rule.get("id") or "")
        score = float(rule.get("score") or 0)
        regex_any = rule.get("regex_any") or []
        keywords_any = rule.get("keywords_any") or []
        min_len = rule.get("min_len")
        max_len = rule.get("max_len")

        for comment in comments:
            text = _normalize_text(str(comment.get("content_text") or ""))
            matched = False
            if regex_any:
                for pattern in regex_any:
                    if re.search(pattern, text):
                        matched = True
                        break
            if keywords_any and not matched:
                matched = any(k in text for k in keywords_any)
            if min_len is not None or max_len is not None:
                length = len(text)
                if min_len is not None and length < int(min_len):
                    matched = False
                if max_len is not None and length > int(max_len):
                    matched = False
                if min_len is not None or max_len is not None:
                    if (min_len is None or length >= int(min_len)) and (
                        max_len is None or length <= int(max_len)
                    ):
                        matched = True
            if matched:
                comment[score_field] = min(cap_score, comment[score_field] + score)
                comment[flags_field].append(rule_id)

    # Similarity clustering
    simhash_rule = next((r for r in rules if r.get("similarity")), None)
    cluster_counts: Dict[int, int] = {}
    if simhash_rule:
        max_dist = int(simhash_rule.get("similarity", {}).get("hamming_max") or 3)
        hashes = [_simhash(_normalize_text(str(c.get("content_text") or ""))) for c in comments]
        cluster_ids = _cluster_by_simhash(hashes, max_dist)
        for idx, cluster_id in enumerate(cluster_ids):
            comments[idx]["cluster_id"] = cluster_id
            cluster_counts[int(cluster_id)] = cluster_counts.get(int(cluster_id), 0) + 1
        # Apply dup_high to comments that have near-duplicates
        rule_id = str(simhash_rule.get("id") or "dup_high")
        score = float(simhash_rule.get("score") or 0)
        if score:
            for idx, comment in enumerate(comments):
                cluster_id = comment.get("cluster_id")
                if cluster_id is None:
                    continue
                if cluster_counts.get(int(cluster_id), 0) <= 1:
                    continue
                comment[score_field] = min(cap_score, comment[score_field] + score)
                comment[flags_field].append(rule_id)

    # Burst window
    burst_rule = next((r for r in rules if r.get("burst")), None)
    if burst_rule:
        hit_indices = _apply_burst_rule(comments, burst_rule)
        rule_id = str(burst_rule.get("id") or "burst_window")
        score = float(burst_rule.get("score") or 0)
        for idx in hit_indices:
            comments[idx][score_field] = min(cap_score, comments[idx][score_field] + score)
            comments[idx][flags_field].append(rule_id)

    # Cluster dominant
    if cluster_rules and cluster_counts:
        total = len(comments) or 1
        for rule in cluster_rules:
            ratio = float(rule.get("dominant_ratio") or 0)
            rule_id = str(rule.get("id") or "cluster_dominant")
            score = float(rule.get("score") or 0)
            for cluster_id, count in cluster_counts.items():
                if count / total >= ratio:
                    for comment in comments:
                        if comment.get("cluster_id") == cluster_id:
                            comment[score_field] = min(cap_score, comment[score_field] + score)
                            comment[flags_field].append(rule_id)

    return comments
