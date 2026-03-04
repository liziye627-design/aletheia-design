"""
Rules engine for RSS pool enrichment (fast/deep summary + scoring).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env
from services.rules_config import get_rules_registry


_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ rules_engine disable httpx trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            if ts <= 0:
                return None
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        from dateutil import parser

        dt = parser.parse(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).hostname or "").lower().strip()
    except Exception:
        return ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _build_fast_summary(title: str, description: str, max_chars: int) -> str:
    blob = " ".join([str(title or "").strip(), str(description or "").strip()]).strip()
    if not blob:
        return ""
    return blob[: max(120, int(max_chars))]


def _heuristic_summary(text: str, max_chars: int) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    max_chars = max(120, int(max_chars))
    if len(content) <= max_chars:
        return content
    # Split by common sentence delimiters (CN + EN)
    parts = re.split(r"[。！？!?]\s*", content)
    summary = ""
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        if summary:
            candidate = f"{summary}。{chunk}"
        else:
            candidate = chunk
        if len(candidate) > max_chars:
            break
        summary = candidate
        if len(summary) >= max_chars * 0.6:
            break
    if summary:
        return summary[:max_chars]
    return content[:max_chars]


class RulesEngine:
    def __init__(self, registry):
        self._registry = registry
        self._lock = asyncio.Lock()
        self._dedupe_cache: Dict[str, float] = {}
        self._domain_fetch_times: Dict[str, List[float]] = {}
        self._global_fetch_times: List[float] = []
        self._paused_domains: Dict[str, float] = {}
        self._regex_cache: Dict[Tuple[str, ...], List[re.Pattern[str]]] = {}

    def _get_rules(self) -> Dict[str, Any]:
        return self._registry.get_rules() if self._registry else {}

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern[str]]:
        key = tuple(patterns or [])
        if key in self._regex_cache:
            return self._regex_cache[key]
        compiled: List[re.Pattern[str]] = []
        for pat in patterns or []:
            try:
                compiled.append(re.compile(pat))
            except re.error:
                continue
        self._regex_cache[key] = compiled
        return compiled

    def _extract_fields(self, item: Dict[str, Any]) -> Tuple[str, str, str]:
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        title = str(item.get("title") or meta.get("title") or "").strip()
        description = str(
            item.get("description")
            or meta.get("description")
            or item.get("summary")
            or ""
        ).strip()
        content_text = str(
            item.get("content_text")
            or item.get("content")
            or item.get("text")
            or ""
        ).strip()
        if not title and content_text:
            title = content_text.splitlines()[0][:120]
        return title, description, content_text

    def _match_keywords(self, text: str, keywords: List[str]) -> bool:
        lowered = text.lower()
        for kw in keywords or []:
            if not kw:
                continue
            if str(kw).lower() in lowered:
                return True
        return False

    def _score_source_priority(self, priority: int, config: Dict[str, Any]) -> int:
        points = config.get("source_priority_points") or {}
        if priority <= 2:
            return _safe_int(points.get("priority_1_2"), 0)
        if priority <= 4:
            return _safe_int(points.get("priority_3_4"), 0)
        if priority <= 6:
            return _safe_int(points.get("priority_5_6"), 0)
        if priority <= 8:
            return _safe_int(points.get("priority_7_8"), 0)
        return _safe_int(points.get("priority_9_10"), 0)

    def _score_recency(self, published_at: Optional[str], config: Dict[str, Any]) -> int:
        if not published_at:
            return 0
        recency = config.get("recency_points") or {}
        dt = _parse_datetime(published_at)
        if not dt:
            return 0
        delta = (_utc_now() - dt).total_seconds()
        if delta <= 15 * 60:
            return _safe_int(recency.get("within_15_min"), 0)
        if delta <= 60 * 60:
            return _safe_int(recency.get("within_1_hour"), 0)
        if delta <= 6 * 60 * 60:
            return _safe_int(recency.get("within_6_hours"), 0)
        if delta <= 24 * 60 * 60:
            return _safe_int(recency.get("within_24_hours"), 0)
        return _safe_int(recency.get("older"), 0)

    async def _dedupe_penalty(self, url: str, window_hours: float, penalty: int) -> int:
        if not url:
            return 0
        now = time.time()
        window_sec = max(1.0, float(window_hours)) * 3600.0
        async with self._lock:
            # prune cache
            expired = [k for k, ts in self._dedupe_cache.items() if now - ts > window_sec]
            for key in expired:
                self._dedupe_cache.pop(key, None)
            last = self._dedupe_cache.get(url)
            self._dedupe_cache[url] = now
        if last and (now - last) <= window_sec:
            return int(penalty)
        return 0

    def _is_domain_paused(self, domain: str) -> bool:
        if not domain:
            return False
        now = time.time()
        paused_until = self._paused_domains.get(domain)
        if paused_until and paused_until > now:
            return True
        if paused_until and paused_until <= now:
            self._paused_domains.pop(domain, None)
        return False

    async def _register_pause(self, domain: str, pause_hours: float) -> None:
        if not domain:
            return
        until = time.time() + max(0.1, float(pause_hours)) * 3600.0
        async with self._lock:
            existing = self._paused_domains.get(domain, 0.0)
            self._paused_domains[domain] = max(existing, until)

    async def _can_deep_fetch(self, domain: str, rules: Dict[str, Any]) -> bool:
        if not domain:
            return False
        if self._is_domain_paused(domain):
            return False

        limits = rules.get("deep_fetch") or {}
        max_domain = _safe_int(limits.get("max_article_fetches_per_domain_per_hour"), 0)
        max_total = _safe_int(limits.get("max_article_fetches_total_per_hour"), 0)
        now = time.time()
        window_sec = 3600.0

        async with self._lock:
            if max_total > 0:
                self._global_fetch_times = [
                    ts for ts in self._global_fetch_times if now - ts <= window_sec
                ]
                if len(self._global_fetch_times) >= max_total:
                    return False

            if max_domain > 0:
                domain_times = self._domain_fetch_times.get(domain, [])
                domain_times = [ts for ts in domain_times if now - ts <= window_sec]
                if len(domain_times) >= max_domain:
                    self._domain_fetch_times[domain] = domain_times
                    return False
                self._domain_fetch_times[domain] = domain_times
        return True

    async def _mark_deep_fetch(self, domain: str) -> None:
        if not domain:
            return
        now = time.time()
        async with self._lock:
            self._global_fetch_times.append(now)
            domain_times = self._domain_fetch_times.get(domain, [])
            domain_times.append(now)
            self._domain_fetch_times[domain] = domain_times

    async def _fetch_article_text(self, url: str, rules: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        trace: Dict[str, Any] = {"fetch_method": "http", "url": url}
        if not url:
            return "", trace

        extract_url = f"https://r.jina.ai/http://{url.replace('https://', '').replace('http://', '')}"
        timeout_sec = float(getattr(settings, "RULES_DEEP_FETCH_TIMEOUT_SECONDS", 10.0))
        timeout = httpx.Timeout(timeout_sec, connect=min(3.0, timeout_sec))
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=_HTTPX_TRUST_ENV,
            ) as client:
                resp = await client.get(extract_url)
                trace["status_code"] = resp.status_code
                text = resp.text or ""
        except Exception as exc:
            trace["error"] = f"{type(exc).__name__}"
            return "", trace

        if resp.status_code >= 400:
            status_policies = (rules.get("anti_blocking") or {}).get("status_policies") or {}
            policy = status_policies.get(str(resp.status_code)) or {}
            trace["status_policy"] = policy
            action = str(policy.get("action") or "")
            multiplier = _safe_float(
                policy.get("backoff_multiplier")
                or policy.get("reduce_fetch_interval_factor")
                or 1.0,
                1.0,
            )
            if action in {"backoff_and_degrade", "degrade_and_reduce_frequency", "backoff"}:
                pause_hours = min(24.0, max(0.1, multiplier))
                await self._register_pause(_extract_domain(url), pause_hours)
            return "", trace

        # strip jina headers
        marker = "Markdown Content:"
        body = text.split(marker, 1)[1] if marker in text else text
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        filtered = [
            line
            for line in lines
            if not line.startswith("URL Source:")
            and not line.startswith("Title:")
            and not line.startswith("Published Time:")
        ]
        content = "\n".join(filtered)

        # captcha detection
        captcha = (rules.get("anti_blocking") or {}).get("captcha_detection") or {}
        keywords = captcha.get("keywords_any") or []
        lowered = content.lower() if content else ""
        for kw in keywords:
            if kw and str(kw).lower() in lowered:
                trace["captcha_detected"] = kw
                pause_hours = _safe_float(captcha.get("pause_hours"), 24.0)
                await self._register_pause(_extract_domain(url), pause_hours)
                return "", trace

        return content.strip(), trace

    async def process_item(
        self,
        item: Dict[str, Any],
        *,
        allow_deep_fetch: bool = True,
    ) -> Dict[str, Any]:
        if not item or not isinstance(item, dict):
            return item
        rules = self._get_rules()
        if not rules:
            return item

        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        title, description, content_text = self._extract_fields(item)
        combined_text = " ".join([title, description, content_text]).strip()

        scoring = rules.get("scoring") or {}
        threshold = _safe_int(scoring.get("threshold"), 60)

        source_priority = _safe_int(meta.get("priority"), _safe_int(item.get("priority"), 5))
        category = str(meta.get("category") or item.get("category") or "").strip()
        published_at = (
            item.get("published_at")
            or meta.get("published_at")
            or meta.get("timestamp")
            or item.get("created_at")
        )
        source_id = str(meta.get("source_id") or item.get("source_id") or "").strip()
        url = str(
            item.get("original_url")
            or item.get("url")
            or item.get("source_url")
            or meta.get("canonical_url")
            or meta.get("rss_url")
            or ""
        ).strip()

        # score parts
        score_breakdown: Dict[str, Any] = {}
        source_points = self._score_source_priority(source_priority, scoring)
        score_breakdown["source_priority"] = source_points

        category_points = _safe_int((scoring.get("category_points") or {}).get(category), 0)
        score_breakdown["category"] = category_points

        keyword_sets = scoring.get("keyword_sets") or {}
        keyword_points = 0
        keyword_matches: Dict[str, bool] = {}
        for key, block in keyword_sets.items():
            block_points = _safe_int(block.get("points"), 0)
            keywords = block.get("any") or []
            matched = self._match_keywords(combined_text, keywords)
            keyword_matches[key] = matched
            if matched:
                keyword_points += block_points
        score_breakdown["keyword_match"] = keyword_points
        score_breakdown["keyword_matches"] = keyword_matches

        breaking = scoring.get("breaking_patterns") or {}
        breaking_points = 0
        if breaking:
            regexes = self._compile_patterns(breaking.get("regex_any") or [])
            for rx in regexes:
                if rx.search(title or combined_text):
                    breaking_points = _safe_int(breaking.get("points"), 0)
                    break
        score_breakdown["breaking"] = breaking_points

        recency_points = self._score_recency(published_at, scoring)
        score_breakdown["recency"] = recency_points

        length_signal = scoring.get("length_signal") or {}
        desc_len = len(description)
        if desc_len < 120:
            length_points = _safe_int(length_signal.get("description_chars_lt_120"), 0)
        elif desc_len < 400:
            length_points = _safe_int(length_signal.get("description_chars_120_400"), 0)
        else:
            length_points = _safe_int(length_signal.get("description_chars_gt_400"), 0)
        score_breakdown["length_signal"] = length_points

        duplication = scoring.get("duplication") or {}
        dup_penalty = await self._dedupe_penalty(
            url=url,
            window_hours=_safe_float(duplication.get("window_hours"), 24.0),
            penalty=_safe_int(duplication.get("penalty"), -20),
        )
        score_breakdown["duplication_penalty"] = dup_penalty

        score = (
            source_points
            + category_points
            + keyword_points
            + breaking_points
            + recency_points
            + length_points
            + dup_penalty
        )
        score_breakdown["final_score"] = score

        high_value = score >= threshold

        # deep fetch rules
        deep_fetch_cfg = rules.get("deep_fetch") or {}
        force_fetch_cfg = deep_fetch_cfg.get("force_fetch_if") or {}
        never_fetch_cfg = deep_fetch_cfg.get("never_fetch_if") or {}
        force_fetch = False
        never_fetch = False

        if category and category in (force_fetch_cfg.get("any_category_in") or []):
            force_fetch = True
        if source_id and source_id in (force_fetch_cfg.get("any_source_id_in") or []):
            force_fetch = True
        title_regexes = self._compile_patterns(force_fetch_cfg.get("title_regex_any") or [])
        for rx in title_regexes:
            if rx.search(title or ""):
                force_fetch = True
                break

        if category and category in (never_fetch_cfg.get("any_category_in") or []):
            never_fetch = True
        never_title_regexes = self._compile_patterns(
            never_fetch_cfg.get("title_regex_any") or []
        )
        for rx in never_title_regexes:
            if rx.search(title or ""):
                never_fetch = True
                break

        pipeline = rules.get("pipeline") or {}
        stage_b = pipeline.get("stage_b_deep_summary") or {}
        stage_b_enabled = bool(stage_b.get("enabled", True))
        require_high_value = bool(stage_b.get("require_high_value", True))
        min_age_seconds = _safe_float(stage_b.get("min_age_seconds"), 0)
        fallback_to_fast = bool(stage_b.get("fallback_to_fast_summary", True))

        deep_fetch_required = False
        if stage_b_enabled and not never_fetch:
            if force_fetch:
                deep_fetch_required = True
            elif require_high_value and high_value:
                deep_fetch_required = True
            elif not require_high_value:
                deep_fetch_required = True
        score_breakdown["force_fetch"] = force_fetch
        score_breakdown["never_fetch"] = never_fetch

        # min age gate
        if deep_fetch_required and min_age_seconds > 0:
            dt = _parse_datetime(published_at)
            if dt:
                age = (_utc_now() - dt).total_seconds()
                if age < min_age_seconds:
                    deep_fetch_required = False
                    score_breakdown["deep_fetch_blocked_reason"] = "min_age"

        fast_summary_max = _safe_int(
            (pipeline.get("stage_a_fast_summary") or {}).get("max_chars"), 1200
        )
        fast_summary = _build_fast_summary(title, description, fast_summary_max)

        summary_level = "fast"
        summary_text = fast_summary
        deep_summary = ""
        fetch_trace: Dict[str, Any] = {}

        if deep_fetch_required and allow_deep_fetch:
            domain = _extract_domain(url)
            if await self._can_deep_fetch(domain, rules):
                await self._mark_deep_fetch(domain)
                fetch_order = (deep_fetch_cfg.get("fetch_order") or ["http"])
                extracted = ""
                for method in fetch_order:
                    if method == "http":
                        extracted, fetch_trace = await self._fetch_article_text(url, rules)
                        if extracted:
                            break
                    elif method == "playwright":
                        fetch_trace["playwright_skipped"] = True
                    # Playwright fallback is intentionally skipped unless explicitly enabled.
                if extracted:
                    deep_summary = await self._summarize_with_llm_or_heuristic(
                        extracted,
                        max_chars=fast_summary_max,
                    )
                    if deep_summary:
                        summary_level = "deep"
                        summary_text = deep_summary
                elif fallback_to_fast:
                    summary_level = "fast"
                    summary_text = fast_summary
            else:
                score_breakdown["deep_fetch_blocked_reason"] = "rate_limit_or_pause"
        elif deep_fetch_required and not allow_deep_fetch:
            score_breakdown["deep_fetch_blocked_reason"] = "disabled"

        # attach fields
        item["summary"] = summary_text
        item["summary_level"] = summary_level
        item["published_at"] = (
            item.get("published_at")
            or meta.get("published_at")
            or meta.get("timestamp")
            or published_at
        )
        item["retrieved_at"] = datetime.utcnow().isoformat()
        item["score"] = score
        item["score_breakdown"] = score_breakdown

        meta.update(
            {
                "summary_level": summary_level,
                "fast_summary": fast_summary,
                "deep_summary": deep_summary,
                "score": score,
                "high_value": high_value,
                "deep_fetch_required": deep_fetch_required,
                "score_breakdown": score_breakdown,
                "fetch_trace": fetch_trace,
            }
        )
        item["metadata"] = meta
        return item

    async def _summarize_with_llm_or_heuristic(
        self,
        text: str,
        *,
        max_chars: int = 200,
    ) -> str:
        use_llm = bool(getattr(settings, "RULES_DEEP_SUMMARY_USE_LLM", False))
        if use_llm:
            try:
                from services.llm.llm_provider import LLMClient

                client = LLMClient()
                max_len = int(getattr(settings, "RULES_DEEP_SUMMARY_MAX_LENGTH", 200))
                return (await client.generate_summary([text], max_length=max_len)).strip()
            except Exception as exc:
                logger.warning(f"rules_engine: deep summary llm failed: {exc}")
        return _heuristic_summary(text, max_chars=max_chars)


_RULES_ENGINE: Optional[RulesEngine] = None


def get_rules_engine() -> Optional[RulesEngine]:
    global _RULES_ENGINE
    registry = get_rules_registry()
    if not registry:
        return None
    if _RULES_ENGINE is None:
        _RULES_ENGINE = RulesEngine(registry)
    return _RULES_ENGINE
