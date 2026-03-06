"""
Generic RSS pool crawler that pulls from sources.yaml.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from core.config import settings
from core.sqlite_database import get_sqlite_db
from utils.logging import logger
from utils.network_env import evaluate_trust_env
from utils.query_intent import extract_keyword_terms, score_keyword_relevance
from services.rules_engine import get_rules_engine
from .base import BaseCrawler

_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", True)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        "⚠️ rss_pool disable httpx trust_env due unreachable local proxy: "
        + ",".join(_BROKEN_LOCAL_PROXY)
    )


class RssPoolCrawler(BaseCrawler):
    def __init__(self, sources: List[Dict[str, Any]]):
        super().__init__(platform_name="rss_pool", rate_limit=5)
        self.sources = [s for s in (sources or []) if isinstance(s, dict)]
        self.max_sources_per_fetch = max(
            2, int(getattr(settings, "RSS_POOL_MAX_SOURCES_PER_FETCH", 8))
        )
        self.fetch_timeout_seconds = max(
            3.0, float(getattr(settings, "RSS_POOL_FETCH_TIMEOUT_SECONDS", 8.0))
        )
        self.fetch_retries = max(
            0, int(getattr(settings, "RSS_POOL_FETCH_RETRIES", 2))
        )
        self.retry_backoff_base = max(
            0.1, float(getattr(settings, "RSS_POOL_RETRY_BACKOFF_BASE", 0.6))
        )
        self.fetch_concurrency = max(
            1, int(getattr(settings, "RSS_POOL_FETCH_CONCURRENCY", 6))
        )
        self.per_source_limit = max(
            3, int(getattr(settings, "RSS_POOL_ITEMS_PER_SOURCE", 12))
        )
        self.hot_max_age_hours = max(
            1, int(getattr(settings, "RSS_POOL_HOT_MAX_AGE_HOURS", 168))
        )
        self.hot_per_source_cap = max(
            1, int(getattr(settings, "RSS_POOL_HOT_PER_SOURCE_CAP", 2))
        )
        self._trust_env_candidates: List[bool] = []
        trust_env_only = bool(getattr(settings, "HTTPX_TRUST_ENV_ONLY", True))
        candidate_order = (
            (_HTTPX_TRUST_ENV,)
            if trust_env_only
            else (_HTTPX_TRUST_ENV, not _HTTPX_TRUST_ENV)
        )
        for v in candidate_order:
            if v not in self._trust_env_candidates:
                self._trust_env_candidates.append(v)
        self.last_fetch_stats: Dict[str, Any] = {}

    def _keyword_tokens(self, keyword: str) -> List[str]:
        return extract_keyword_terms(keyword, max_terms=24)

    def _keyword_score(self, keyword: str, text: str) -> float:
        return score_keyword_relevance(keyword, text)

    def _looks_like_feed_url(self, url: str) -> bool:
        raw = str(url or "").strip().lower()
        if not raw:
            return False
        feed_hints = (
            "/rss",
            "rss.",
            "/feed",
            "feed-",
            ".xml",
            "atom",
            "news.google.com/rss/",
        )
        return any(h in raw for h in feed_hints)

    async def _fetch_feed_text(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str, str]:
        """
        Fetch feed text with retries + jitter backoff.
        Returns (response_text, reason_code)
        """
        attempts = self.fetch_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.get(url)
                if int(resp.status_code) >= 400:
                    return "", f"HTTP_{int(resp.status_code)}"
                return str(resp.text or ""), "OK"
            except (httpx.ConnectError, httpx.ConnectTimeout):
                reason = "CONNECT_ERROR"
            except httpx.ReadTimeout:
                reason = "READ_TIMEOUT"
            except httpx.TimeoutException:
                reason = "TIMEOUT"
            except Exception:
                reason = "FETCH_ERROR"
            if attempt < attempts:
                sleep_sec = self.retry_backoff_base * (2 ** (attempt - 1))
                sleep_sec += random.uniform(0.0, 0.2)
                await asyncio.sleep(sleep_sec)
                continue
            return "", reason
        return "", "UNKNOWN_ERROR"

    def _parse_date(self, value: str) -> str:
        try:
            from dateutil import parser

            dt = parser.parse(value)
            return dt.isoformat()
        except Exception:
            return datetime.utcnow().isoformat()

    def _to_datetime(self, value: str | None) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            return datetime.now(timezone.utc)
        try:
            from dateutil import parser

            dt = parser.parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _rank_hot_items(self, items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        if not items or limit <= 0:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.hot_max_age_hours)
        fresh: List[Dict[str, Any]] = []
        stale: List[Dict[str, Any]] = []
        for item in items:
            published_at = self._to_datetime(
                str(
                    item.get("published_at")
                    or ((item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}).get("timestamp")
                    or item.get("created_at")
                    or ""
                )
            )
            bucket = fresh if published_at >= cutoff else stale
            cloned = dict(item)
            cloned["_published_dt"] = published_at
            bucket.append(cloned)

        def _sort_key(row: Dict[str, Any]) -> tuple[datetime, float]:
            meta = row.get("metadata") or {}
            priority = int((meta.get("priority") if isinstance(meta, dict) else 5) or 5)
            priority_boost = float(max(0, 10 - priority))
            return (row.get("_published_dt") or datetime.min.replace(tzinfo=timezone.utc), priority_boost)

        ordered = sorted(fresh, key=_sort_key, reverse=True)
        if not ordered:
            ordered = sorted(stale, key=_sort_key, reverse=True)
        elif len(ordered) < limit:
            ordered.extend(sorted(stale, key=_sort_key, reverse=True))

        picked: List[Dict[str, Any]] = []
        per_source_seen: Dict[str, int] = {}
        overflow: List[Dict[str, Any]] = []
        for row in ordered:
            meta = row.get("metadata") or {}
            source_id = str((meta.get("source_id") if isinstance(meta, dict) else "") or "rss_pool")
            if per_source_seen.get(source_id, 0) < self.hot_per_source_cap:
                per_source_seen[source_id] = per_source_seen.get(source_id, 0) + 1
                picked.append(row)
            else:
                overflow.append(row)
            if len(picked) >= limit:
                break
        if len(picked) < limit:
            for row in overflow:
                picked.append(row)
                if len(picked) >= limit:
                    break
        for row in picked:
            row.pop("_published_dt", None)
        return picked[:limit]

    def _select_sources(self) -> List[Dict[str, Any]]:
        sources = [
            s
            for s in self.sources
            if bool(s.get("enabled", True))
            and str(s.get("type") or "rss").strip().lower() in {"rss", "atom"}
            and str(s.get("url") or "").strip()
        ]
        sources.sort(key=lambda x: (int(x.get("priority") or 5), str(x.get("source_id") or "")))
        return sources[: self.max_sources_per_fetch]

    def _select_sources_for_query(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Query-aware source selection:
        - keep low-priority number semantics
        - boost sources whose name/category/source_id hints match query tokens
        """
        candidates = [
            s
            for s in self.sources
            if bool(s.get("enabled", True))
            and str(s.get("type") or "rss").strip().lower() in {"rss", "atom"}
            and str(s.get("url") or "").strip()
        ]
        # 搜索模式优先保留“像 RSS 的 URL”，避免目录页/入口页在查询时拉低命中率。
        feed_like = [
            s for s in candidates if self._looks_like_feed_url(str(s.get("url") or ""))
        ]
        if feed_like:
            candidates = feed_like
        if not candidates:
            return []
        tokens = self._keyword_tokens(keyword)
        search_cap = max(
            self.max_sources_per_fetch,
            int(getattr(settings, "RSS_POOL_MAX_SOURCES_PER_SEARCH_FETCH", 24)),
        )
        if not tokens:
            candidates.sort(
                key=lambda x: (int(x.get("priority") or 5), str(x.get("source_id") or ""))
            )
            return candidates[:search_cap]

        def _score(src: Dict[str, Any]) -> float:
            base = float(10 - int(src.get("priority") or 5))
            blob = " ".join(
                [
                    str(src.get("name") or ""),
                    str(src.get("category") or ""),
                    str(src.get("source_id") or ""),
                    str(src.get("group_name") or ""),
                ]
            ).lower()
            hit = sum(1 for t in tokens if t in blob)
            return base + hit * 4.0

        candidates.sort(key=lambda s: (_score(s), -int(s.get("priority") or 5)), reverse=True)
        return candidates[:search_cap]

    async def _fetch_source_entries(
        self,
        src: Dict[str, Any],
        timeout: httpx.Timeout,
    ) -> tuple[List[Dict[str, Any]], str, bool, str]:
        await self.rate_limit_wait()
        url = str(src.get("url") or "").strip()
        if not url:
            return [], "INVALID_URL", self._trust_env_candidates[0], ""
        feed_text = ""
        reason_code = "FETCH_ERROR"
        used_trust_env = self._trust_env_candidates[0]
        for trust_env in self._trust_env_candidates:
            used_trust_env = trust_env
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=trust_env,
            ) as client:
                feed_text, reason_code = await self._fetch_feed_text(client, url)
            if reason_code == "OK":
                break
            if reason_code in {"CONNECT_ERROR", "READ_TIMEOUT", "TIMEOUT"}:
                continue
            break
        if reason_code != "OK":
            return [], reason_code, used_trust_env, url
        feed = feedparser.parse(feed_text or "")
        entries = list(getattr(feed, "entries", []) or [])
        if not entries:
            return [], "EMPTY_FEED", used_trust_env, url
        return entries, "OK", used_trust_env, url

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        selected = self._select_sources()
        if not selected:
            return []

        items: List[Dict[str, Any]] = []
        reason_stats: Dict[str, int] = {}
        trust_env_stats: Dict[str, int] = {"trust_env_0": 0, "trust_env_1": 0}
        timeout = httpx.Timeout(
            self.fetch_timeout_seconds, connect=min(3.0, self.fetch_timeout_seconds)
        )
        rules_engine = get_rules_engine()
        sem = asyncio.Semaphore(self.fetch_concurrency)

        async def _worker(src: Dict[str, Any]):
            async with sem:
                return src, await self._fetch_source_entries(src, timeout)

        results = await asyncio.gather(*[_worker(src) for src in selected], return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                reason_stats[type(result).__name__] = int(reason_stats.get(type(result).__name__, 0)) + 1
                continue
            src, (entries, reason_code, used_trust_env, url) = result
            trust_env_stats[f"trust_env_{int(bool(used_trust_env))}"] = int(
                trust_env_stats.get(f"trust_env_{int(bool(used_trust_env))}", 0)
            ) + 1
            reason_stats[reason_code] = int(reason_stats.get(reason_code, 0)) + 1
            if reason_code != "OK":
                logger.warning(f"rss_pool: fetch failed {url}: {reason_code}")
                continue
            for entry in entries[: self.per_source_limit]:
                title = str(entry.get("title", "") or "").strip()
                summary = str(entry.get("summary", "") or "").strip()
                link = str(entry.get("link", "") or "").strip()
                if not link:
                    continue
                raw = {
                    "url": link,
                    "text": f"{title}\n{summary}".strip(),
                    "created_at": self._parse_date(str(entry.get("published", "") or "")),
                    "author_name": str(src.get("name") or "rss_pool"),
                    "author_id": str(src.get("source_id") or "rss_pool"),
                    "followers": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [],
                }
                standardized = self.standardize_item(raw)
                meta = (
                    standardized.get("metadata")
                    if isinstance(standardized.get("metadata"), dict)
                    else {}
                )
                meta.update(
                    {
                        "source_id": src.get("source_id"),
                        "source_name": src.get("name"),
                        "group_id": src.get("group_id"),
                        "group_name": src.get("group_name"),
                        "category": src.get("category"),
                        "rss_url": url,
                        "source_type": "rss_pool",
                        "priority": src.get("priority"),
                        "title": title,
                        "description": summary,
                    }
                )
                standardized["title"] = title
                standardized["description"] = summary
                standardized["published_at"] = raw.get("created_at")
                standardized["metadata"] = meta
                if rules_engine is not None:
                    standardized = await rules_engine.process_item(
                        standardized, allow_deep_fetch=True
                    )
                items.append(standardized)
        self.last_fetch_stats = {
            "selected_sources": len(selected),
            "items_collected": len(items),
            "reason_stats": reason_stats,
            "trust_env_stats": trust_env_stats,
            "concurrency": self.fetch_concurrency,
        }
        if reason_stats:
            logger.info(
                f"rss_pool: summary selected={len(selected)} items={len(items)} "
                f"reasons={reason_stats} trust_env={trust_env_stats}"
            )
        ranked = self._rank_hot_items(items, limit)
        return ranked[:limit]

    async def search(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        RSS has no native search API; emulate search by fetching recent items
        and filtering by keyword score.
        """
        kw = str(keyword or "").strip()
        if not kw:
            return await self.fetch_hot_topics(limit=limit)
        fetch_limit = max(limit * 6, 80)
        selected = self._select_sources_for_query(kw)
        if not selected:
            return []
        selected_source_ids = {
            str(src.get("source_id") or "").strip()
            for src in selected
            if str(src.get("source_id") or "").strip()
        }
        enable_local = bool(getattr(settings, "RSS_POOL_ENABLE_LOCAL_INDEX_SEARCH", True))
        local_first = bool(getattr(settings, "RSS_POOL_SEARCH_LOCAL_FIRST", True))
        local_min_results = max(
            1, int(getattr(settings, "RSS_POOL_SEARCH_LOCAL_MIN_RESULTS", max(3, limit // 2)))
        )
        skip_network_if_local_enough = bool(
            getattr(settings, "RSS_POOL_SEARCH_SKIP_NETWORK_IF_LOCAL_ENOUGH", True)
        )
        pre_local_scored: List[tuple[float, Dict[str, Any]]] = []
        if enable_local and local_first:
            pre_local_scored = await self._search_local_index(
                kw=kw,
                limit=limit,
                threshold=max(
                    0.25, float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2))
                ),
                selected_source_ids=selected_source_ids,
            )
            if skip_network_if_local_enough and len(pre_local_scored) >= local_min_results:
                return [row for _, row in pre_local_scored[:limit]]
        items: List[Dict[str, Any]] = []
        reason_stats: Dict[str, int] = {}
        trust_env_stats: Dict[str, int] = {"trust_env_0": 0, "trust_env_1": 0}
        timeout = httpx.Timeout(
            self.fetch_timeout_seconds, connect=min(3.0, self.fetch_timeout_seconds)
        )
        rules_engine = get_rules_engine()
        sem = asyncio.Semaphore(self.fetch_concurrency)

        async def _worker(src: Dict[str, Any]):
            async with sem:
                return src, await self._fetch_source_entries(src, timeout)

        results = await asyncio.gather(*[_worker(src) for src in selected], return_exceptions=True)
        for result in results:
            if len(items) >= fetch_limit:
                break
            if isinstance(result, Exception):
                reason_stats[type(result).__name__] = int(reason_stats.get(type(result).__name__, 0)) + 1
                continue
            src, (entries, reason_code, used_trust_env, url) = result
            trust_env_stats[f"trust_env_{int(bool(used_trust_env))}"] = int(
                trust_env_stats.get(f"trust_env_{int(bool(used_trust_env))}", 0)
            ) + 1
            reason_stats[reason_code] = int(reason_stats.get(reason_code, 0)) + 1
            if reason_code != "OK":
                continue
            for entry in entries[: self.per_source_limit]:
                if len(items) >= fetch_limit:
                    break
                title = str(entry.get("title", "") or "").strip()
                summary = str(entry.get("summary", "") or "").strip()
                link = str(entry.get("link", "") or "").strip()
                if not link:
                    continue
                raw = {
                    "url": link,
                    "text": f"{title}\n{summary}".strip(),
                    "created_at": self._parse_date(str(entry.get("published", "") or "")),
                    "author_name": str(src.get("name") or "rss_pool"),
                    "author_id": str(src.get("source_id") or "rss_pool"),
                    "followers": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [],
                }
                standardized = self.standardize_item(raw)
                meta = (
                    standardized.get("metadata")
                    if isinstance(standardized.get("metadata"), dict)
                    else {}
                )
                meta.update(
                    {
                        "source_id": src.get("source_id"),
                        "source_name": src.get("name"),
                        "group_id": src.get("group_id"),
                        "group_name": src.get("group_name"),
                        "category": src.get("category"),
                        "rss_url": url,
                        "source_type": "rss_pool",
                        "priority": src.get("priority"),
                        "title": title,
                        "description": summary,
                    }
                )
                standardized["title"] = title
                standardized["description"] = summary
                standardized["published_at"] = raw.get("created_at")
                standardized["metadata"] = meta
                if rules_engine is not None:
                    standardized = await rules_engine.process_item(
                        standardized, allow_deep_fetch=True
                    )
                items.append(standardized)
        self.last_fetch_stats = {
            "selected_sources": len(selected),
            "items_collected": len(items),
            "reason_stats": reason_stats,
            "trust_env_stats": trust_env_stats,
            "mode": "search",
            "concurrency": self.fetch_concurrency,
        }
        scored: List[tuple[float, Dict[str, Any]]] = []
        threshold = max(0.25, float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2)))
        dedup_urls = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            blob = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("description") or ""),
                    str(item.get("content") or ""),
                    str(item.get("text") or ""),
                ]
            )
            score = self._keyword_score(kw, blob)
            is_hit = bool(score >= threshold)
            meta["search_keyword"] = kw
            meta["keyword_match"] = is_hit
            meta["keyword_match_score"] = round(float(score), 4)
            meta["retrieval_mode"] = "rss_search_emulated"
            item["metadata"] = meta
            if is_hit:
                dedup_urls.add(str(item.get("url") or "").strip())
                scored.append((score, item))

        if enable_local and len(scored) < limit:
            local_scored = await self._search_local_index(
                kw=kw,
                limit=limit,
                threshold=threshold,
                selected_source_ids=selected_source_ids,
            )
            for score, standard in local_scored:
                link = str(standard.get("url") or "").strip()
                if not link or link in dedup_urls:
                    continue
                dedup_urls.add(link)
                scored.append((score, standard))
                if len(scored) >= limit * 2:
                    break
        if pre_local_scored:
            for score, standard in pre_local_scored:
                link = str(standard.get("url") or "").strip()
                if not link or link in dedup_urls:
                    continue
                dedup_urls.add(link)
                scored.append((score, standard))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[:limit]]

    async def _search_local_index(
        self,
        *,
        kw: str,
        limit: int,
        threshold: float,
        selected_source_ids: set[str],
    ) -> List[tuple[float, Dict[str, Any]]]:
        lookback_days = int(getattr(settings, "RSS_POOL_LOCAL_INDEX_LOOKBACK_DAYS", 30))
        max_candidates = int(getattr(settings, "RSS_POOL_LOCAL_INDEX_MAX_CANDIDATES", 120))
        local_limit = max(limit * 4, max_candidates)
        out: List[tuple[float, Dict[str, Any]]] = []
        try:
            local_rows = await asyncio.to_thread(
                get_sqlite_db().search_rss_articles,
                keyword=kw,
                limit=local_limit,
                days=lookback_days,
            )
            for row in list(local_rows or []):
                row_source = str(row.get("source_id") or "").strip()
                if selected_source_ids and row_source and row_source not in selected_source_ids:
                    continue
                link = str(row.get("link") or row.get("canonical_url") or "").strip()
                if not link:
                    continue
                title = str(row.get("title") or "").strip()
                summary = str(
                    row.get("summary")
                    or row.get("deep_summary")
                    or row.get("description")
                    or ""
                ).strip()
                raw = {
                    "url": link,
                    "text": f"{title}\n{summary}".strip(),
                    "created_at": str(row.get("published_at") or row.get("retrieved_at") or ""),
                    "author_name": str(row.get("source_name") or "rss_pool"),
                    "author_id": str(row.get("source_id") or "rss_pool"),
                    "followers": 0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [],
                }
                standard = self.standardize_item(raw)
                meta = standard.get("metadata") if isinstance(standard.get("metadata"), dict) else {}
                meta.update(
                    {
                        "source_id": row.get("source_id"),
                        "source_name": row.get("source_name"),
                        "category": row.get("category"),
                        "source_type": "rss_pool",
                        "retrieval_mode": "rss_local_index",
                        "title": title,
                        "description": summary,
                        "local_match_score": (
                            (row.get("metadata") or {}).get("local_match_score")
                            if isinstance(row.get("metadata"), dict)
                            else 0.0
                        ),
                    }
                )
                standard["title"] = title
                standard["description"] = summary
                standard["published_at"] = raw.get("created_at")
                standard["metadata"] = meta
                blob = "\n".join(
                    [
                        str(standard.get("title") or ""),
                        str(standard.get("description") or ""),
                        str(standard.get("content") or ""),
                        str(standard.get("text") or ""),
                    ]
                )
                score = self._keyword_score(kw, blob)
                if score < threshold:
                    continue
                out.append((score, standard))
                if len(out) >= local_limit:
                    break
        except Exception as exc:
            logger.warning(f"rss_pool local index search failed: {type(exc).__name__}")
        out.sort(key=lambda x: x[0], reverse=True)
        return out

    async def fetch_user_posts(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return []

    async def fetch_comments(self, post_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return []
