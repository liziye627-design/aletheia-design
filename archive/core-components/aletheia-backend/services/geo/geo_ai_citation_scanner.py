"""
GEO scan: collect content + simulate AI citation preference signals.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from services.layer1_perception.crawler_manager import get_crawler_manager

    _crawler_import_error = None
except Exception as import_error:
    get_crawler_manager = None
    _crawler_import_error = import_error


DEFAULT_AI_PLATFORMS = ["ChatGPT", "Gemini", "Doubao", "BaiduAI"]


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _require_crawler_manager():
    if get_crawler_manager is None:
        raise RuntimeError(f"crawler_manager unavailable: {_crawler_import_error}")
    return get_crawler_manager()


async def run_geo_scan(
    *,
    topic: str,
    platforms: Optional[List[str]] = None,
    limit_per_platform: int = 20,
) -> Dict[str, Any]:
    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("topic required")

    crawlers = _require_crawler_manager()
    platforms = platforms or [
        "news",
        "xinhua",
        "reuters",
        "ap_news",
        "guardian",
        "bbc",
    ]
    verbose = await crawlers.search_across_platforms_verbose(
        keyword=topic,
        platforms=platforms,
        limit_per_platform=limit_per_platform,
        max_concurrency=6,
        mediacrawler_options=None,
    )
    content_items: List[Dict[str, Any]] = []
    domain_counter: Counter[str] = Counter()
    for platform, row in (verbose or {}).items():
        items = row.get("items") if isinstance(row, dict) else []
        if not isinstance(items, list):
            items = []
        for item in items[:limit_per_platform]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "")
            domain = _extract_domain(url)
            if domain:
                domain_counter[domain] += 1
            content_items.append(
                {
                    "platform": platform,
                    "title": str(item.get("title") or item.get("content") or item.get("text") or "")[:180],
                    "url": url,
                    "snippet": str(item.get("summary") or item.get("content") or "")[:200],
                    "domain": domain,
                }
            )

    source_rankings = [
        {"domain": domain, "count": int(count)}
        for domain, count in domain_counter.most_common(20)
    ]
    ai_citation_samples = []
    for idx, item in enumerate(source_rankings[:6]):
        ai_citation_samples.append(
            {
                "ai_platform": DEFAULT_AI_PLATFORMS[idx % len(DEFAULT_AI_PLATFORMS)],
                "domain": item["domain"],
                "citation_count": item["count"],
            }
        )

    return {
        "topic": topic,
        "platforms": platforms,
        "content_items": content_items,
        "source_rankings": source_rankings,
        "ai_citation_samples": ai_citation_samples,
        "generated_at": datetime.utcnow().isoformat(),
    }
