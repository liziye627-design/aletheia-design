"""
Google News RSS based external search provider.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import feedparser
import httpx

from core.config import settings
from services.external.search_provider import SearchHit
from services.investigation_helpers import _HTTPX_TRUST_ENV
from utils.logging import logger


def _strip_html(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    return re.sub(r"<[^>]+>", "", raw).replace("&nbsp;", " ").strip()


def _parse_source(entry: Any) -> Tuple[str, str]:
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    source_href = str(source.get("href", "") or "").strip()
    source_name = str(source.get("title", "") or "").strip()
    source_domain = ""
    if source_href:
        try:
            source_domain = (urlparse(source_href).hostname or "").lower()
        except Exception:
            source_domain = ""
    return source_name, source_domain


class GoogleNewsSearchProvider:
    def __init__(self) -> None:
        self.timeout_sec = max(
            2.0,
            float(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_TIMEOUT_SEC", 6)),
        )
        self.max_results = max(
            1,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS", 20)),
        )
        self.max_domain_queries = max(
            2,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_DOMAIN_QUERIES", 8)),
        )
        self.concurrency = max(
            1,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_CONCURRENCY", 4)),
        )

    def _build_queries(self, query: str, allowed_domains: List[str]) -> List[str]:
        q = str(query or "").strip()
        if not q:
            return []
        out: List[str] = []
        if allowed_domains:
            for domain in allowed_domains[: self.max_domain_queries]:
                item = f"{q} site:{domain}"
                if item not in out:
                    out.append(item)
        if q not in out:
            out.append(q)
        return out[: max(2, self.max_domain_queries + 1)]

    def _query_to_url(self, query: str) -> str:
        encoded = quote(str(query or "").strip())
        return (
            "https://news.google.com/rss/search?"
            f"q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        )

    async def _fetch_feed(self, client: httpx.AsyncClient, query: str) -> List[SearchHit]:
        url = self._query_to_url(query)
        try:
            text = (await client.get(url)).text or ""
        except Exception as exc:
            logger.debug(f"google news feed fetch failed ({query}): {type(exc).__name__}")
            return []
        parsed = feedparser.parse(text)
        entries = list(getattr(parsed, "entries", []) or [])
        out: List[SearchHit] = []
        for entry in entries:
            link = str(entry.get("link", "") or "").strip()
            title = str(entry.get("title", "") or "").strip()
            summary = _strip_html(str(entry.get("summary", "") or ""))
            source_name, source_domain = _parse_source(entry)
            if not link or not title:
                continue
            out.append(
                {
                    "provider": "google_news_rss",
                    "query": query,
                    "url": link,
                    "title": title,
                    "summary": summary[:1200],
                    "source_name": source_name,
                    "source_domain": source_domain,
                    "published_at": str(entry.get("published", "") or ""),
                    "fetched_at": datetime.utcnow().isoformat(),
                    "reachable": True,
                }
            )
        return out

    async def search_news(
        self,
        *,
        query: str,
        limit: int,
        allowed_domains: Optional[List[str]] = None,
    ) -> List[SearchHit]:
        q = str(query or "").strip()
        if not q:
            return []
        max_results = max(1, min(int(limit or self.max_results), self.max_results))
        domains = [str(x).strip().lower() for x in (allowed_domains or []) if str(x).strip()]
        queries = self._build_queries(q, domains)
        if not queries:
            return []

        sem = asyncio.Semaphore(self.concurrency)
        timeout = httpx.Timeout(self.timeout_sec, connect=min(3.0, self.timeout_sec))

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            trust_env=_HTTPX_TRUST_ENV,
        ) as client:
            async def _worker(query_row: str) -> List[SearchHit]:
                async with sem:
                    return await self._fetch_feed(client, query_row)

            rows = await asyncio.gather(*[_worker(x) for x in queries], return_exceptions=True)

        dedup: Dict[str, SearchHit] = {}
        for row in rows:
            if isinstance(row, Exception):
                continue
            for item in row:
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                if url not in dedup:
                    dedup[url] = item
                if len(dedup) >= max_results:
                    break
            if len(dedup) >= max_results:
                break

        return list(dedup.values())[:max_results]

