from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from core.config import settings
from services.layer1_perception.crawlers.rss_pool import RssPoolCrawler
from services.rss_sources_config import get_rss_sources_registry


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return _now_utc()
    try:
        from dateutil import parser

        dt = parser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return _now_utc()


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def _normalize_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return raw


def _normalized_title(value: Any) -> str:
    raw = _clean_text(value).lower()
    return "".join(ch for ch in raw if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _classify_item(item: Dict[str, Any]) -> str:
    meta = item.get("metadata") or {}
    blob = " ".join(
        [
            str(item.get("title") or ""),
            str(meta.get("category") if isinstance(meta, dict) else ""),
            str(meta.get("group_name") if isinstance(meta, dict) else ""),
            str(meta.get("source_name") if isinstance(meta, dict) else ""),
        ]
    ).lower()
    rules: List[Tuple[str, Tuple[str, ...]]] = [
        ("政策监管", ("政策", "监管", "gov", "gov.cn", "统计", "sec", "法院", "检察", "国务院")),
        ("国际资讯", ("国际", "world", "reuters", "bbc", "guardian", "un ", "who", "ap news")),
        ("科技产业", ("科技", "36氪", "爱范儿", "tech", "开发者", "产业", "界面")),
        ("公共民生", ("社会", "医疗", "健康", "education", "民生", "法治", "住房")),
        ("财经商业", ("财经", "business", "finance", "market", "证券", "资本")),
        ("突发快讯", ("快讯", "即时", "scroll", "breaking")),
    ]
    for label, keywords in rules:
        if any(keyword in blob for keyword in keywords):
            return label
    return "综合观察"


def _summary_text(item: Dict[str, Any]) -> str:
    meta = item.get("metadata") or {}
    text = _clean_text(
        item.get("description")
        or item.get("summary")
        or (meta.get("fast_summary") if isinstance(meta, dict) else "")
        or (meta.get("deep_summary") if isinstance(meta, dict) else "")
        or item.get("content_text")
    )
    if not text:
        return "该条目需要进一步打开原文核查上下文与时间线。"
    return text[:220]


def _rank_item(item: Dict[str, Any], *, now: datetime) -> float:
    meta = item.get("metadata") or {}
    published_dt = _parse_dt(item.get("published_at") or item.get("created_at"))
    age_hours = max(0.0, (now - published_dt).total_seconds() / 3600.0)
    freshness = max(0.0, 120.0 - min(age_hours, 120.0))
    priority = int((meta.get("priority") if isinstance(meta, dict) else 5) or 5)
    source_score = max(0.0, 18.0 - priority * 2.0)
    summary_score = 10.0 if _summary_text(item) else 0.0
    category_score = {
        "突发快讯": 9.0,
        "国际资讯": 7.5,
        "政策监管": 7.0,
        "科技产业": 6.5,
        "公共民生": 6.0,
        "财经商业": 5.5,
        "综合观察": 4.0,
    }.get(_classify_item(item), 4.0)
    return freshness + source_score + summary_score + category_score


class RssHotFocusService:
    def __init__(self):
        self._cache_payload: Optional[Dict[str, Any]] = None
        self._cache_at: Optional[datetime] = None

    async def build_snapshot(self, *, refresh: bool = False) -> Dict[str, Any]:
        ttl_sec = max(60, int(getattr(settings, "RSS_HOT_FOCUS_CACHE_TTL_SEC", 3600)))
        if (
            not refresh
            and self._cache_payload is not None
            and self._cache_at is not None
            and (_now_utc() - self._cache_at).total_seconds() < ttl_sec
        ):
            return self._cache_payload

        registry = get_rss_sources_registry()
        sources = registry.get_rss_sources() if registry else []
        crawler = RssPoolCrawler(sources=sources)
        crawler.max_sources_per_fetch = min(
            len(sources),
            max(1, int(getattr(settings, "RSS_HOT_FOCUS_SOURCE_LIMIT", 24))),
        )
        crawler.per_source_limit = max(
            1, int(getattr(settings, "RSS_HOT_FOCUS_PER_SOURCE_LIMIT", 4))
        )

        candidate_limit = max(20, crawler.max_sources_per_fetch * crawler.per_source_limit)
        candidates = await crawler.fetch_hot_topics(limit=candidate_limit)
        payload = self._build_payload(candidates)
        self._cache_payload = payload
        self._cache_at = _now_utc()
        return payload

    def _build_payload(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        now = _now_utc()
        max_age_hours = max(1, int(getattr(settings, "RSS_HOT_FOCUS_MAX_AGE_HOURS", 72)))
        cutoff = now - timedelta(hours=max_age_hours)

        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            published_dt = _parse_dt(item.get("published_at") or item.get("created_at"))
            if published_dt < cutoff:
                continue
            dedupe_key = _normalize_url(item.get("original_url")) or _normalized_title(item.get("title"))
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cloned = dict(item)
            cloned["_published_dt"] = published_dt
            cloned["_category"] = _classify_item(item)
            cloned["_score"] = _rank_item(item, now=now)
            deduped.append(cloned)

        deduped.sort(key=lambda row: (row["_score"], row["_published_dt"]), reverse=True)

        summary_limit = max(1, int(getattr(settings, "RSS_HOT_FOCUS_SUMMARY_LIMIT", 3)))
        detail_limit = max(summary_limit, int(getattr(settings, "RSS_HOT_FOCUS_DETAIL_LIMIT", 12)))
        summary_items = self._diversified_pick(deduped, summary_limit, per_source_cap=1)
        detail_items = self._diversified_pick(deduped, detail_limit, per_source_cap=2)

        sections_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in detail_items:
            sections_map[row["_category"]].append(self._serialize_item(row))

        sections = [
            {"category": category, "items": items}
            for category, items in sorted(
                sections_map.items(),
                key=lambda pair: max(
                    (_parse_dt(item.get("published_at")).timestamp() for item in pair[1]),
                    default=0,
                ),
                reverse=True,
            )
        ]

        return {
            "updated_at": now.isoformat(),
            "source_count": len({str((row.get("metadata") or {}).get("source_id") or "") for row in deduped}),
            "candidate_count": len(deduped),
            "summary_items": [self._serialize_item(row) for row in summary_items],
            "detail_items": [self._serialize_item(row) for row in detail_items],
            "sections": sections,
        }

    def _diversified_pick(
        self, rows: List[Dict[str, Any]], limit: int, *, per_source_cap: int
    ) -> List[Dict[str, Any]]:
        picked: List[Dict[str, Any]] = []
        overflow: List[Dict[str, Any]] = []
        source_counts: Dict[str, int] = defaultdict(int)
        for row in rows:
            meta = row.get("metadata") or {}
            source_id = str((meta.get("source_id") if isinstance(meta, dict) else "") or "rss_pool")
            if source_counts[source_id] < per_source_cap:
                source_counts[source_id] += 1
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
        return picked[:limit]

    def _serialize_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        meta = row.get("metadata") or {}
        return {
            "id": str(row.get("id") or ""),
            "title": _clean_text(row.get("title") or row.get("content_text")),
            "summary": _summary_text(row),
            "url": str(row.get("original_url") or ""),
            "published_at": _parse_dt(row.get("published_at") or row.get("created_at")).isoformat(),
            "category": str(row.get("_category") or _classify_item(row)),
            "source_name": str((meta.get("source_name") if isinstance(meta, dict) else "") or row.get("source_platform") or "rss_pool"),
            "source_id": str((meta.get("source_id") if isinstance(meta, dict) else "") or "rss_pool"),
            "group_name": str((meta.get("group_name") if isinstance(meta, dict) else "") or ""),
            "score": round(float(row.get("_score") or 0.0), 2),
        }


_service: Optional[RssHotFocusService] = None
_service_lock = asyncio.Lock()


async def get_rss_hot_focus_service() -> RssHotFocusService:
    global _service
    if _service is None:
        async with _service_lock:
            if _service is None:
                _service = RssHotFocusService()
    return _service
