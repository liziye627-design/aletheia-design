"""
Bocha Web Search API based external search provider.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from core.config import settings
from services.external.search_provider import SearchHit
from services.investigation_helpers import _HTTPX_TRUST_ENV
from utils.logging import logger


def _extract_domain(url_value: str) -> str:
    url = str(url_value or "").strip()
    if not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


class BochaSearchProvider:
    def __init__(self) -> None:
        self.base_url = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_BASE_URL", "")
            or "https://api.bocha.cn/v1"
        ).strip()
        self.api_key = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_API_KEY", "") or ""
        ).strip()
        self.enabled = bool(self.base_url and self.api_key)
        self.timeout_sec = max(
            2.0,
            float(
                getattr(
                    settings,
                    "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_TIMEOUT_SEC",
                    getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_TIMEOUT_SEC", 8.0),
                )
            ),
        )
        self.max_results = max(
            1,
            int(
                getattr(
                    settings,
                    "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_MAX_RESULTS",
                    getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS", 50),
                )
            ),
        )
        self.max_domain_queries = max(
            2,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_DOMAIN_QUERIES", 8)),
        )
        self.concurrency = max(
            1,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_CONCURRENCY", 4)),
        )
        self.summary = bool(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_SUMMARY", True)
        )
        self.freshness = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_FRESHNESS", "noLimit")
            or "noLimit"
        ).strip()
        self.enable_site_scoped_queries = bool(
            getattr(
                settings,
                "INVESTIGATION_EXTERNAL_SEARCH_BOCHA_ENABLE_SITE_SCOPED_QUERIES",
                False,
            )
        )

    def _build_queries(self, query: str, allowed_domains: List[str]) -> List[str]:
        q = str(query or "").strip()
        if not q:
            return []
        out: List[str] = [q]
        if allowed_domains and self.enable_site_scoped_queries:
            for domain in allowed_domains[: self.max_domain_queries]:
                row = str(domain or "").strip().lower()
                if not row:
                    continue
                scoped = f"{q} site:{row}"
                if scoped not in out:
                    out.append(scoped)
        return out[: max(2, self.max_domain_queries + 1)]

    async def _search_single(
        self,
        *,
        client: httpx.AsyncClient,
        query: str,
        limit: int,
    ) -> List[SearchHit]:
        payload: Dict[str, Any] = {
            "query": str(query or "").strip(),
            "summary": self.summary,
            "freshness": self.freshness,
            "count": max(1, min(int(limit or 10), self.max_results)),
        }
        url = f"{self.base_url.rstrip('/')}/web-search"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(url, headers=headers, json=payload)
        except Exception as exc:
            logger.warning(f"bocha request failed ({query}): {type(exc).__name__}")
            return []
        if int(resp.status_code) >= 400:
            logger.warning(f"bocha search failed status={resp.status_code} query={query}")
            return []
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            logger.warning("bocha response json decode failed")
            return []
        if int(body.get("code") or 0) != 200:
            logger.warning(f"bocha api code={body.get('code')} msg={body.get('msg')}")
            return []
        values = (
            ((body.get("data") or {}).get("webPages") or {}).get("value") or []
        )
        out: List[SearchHit] = []
        for row in values:
            if not isinstance(row, dict):
                continue
            link = str(row.get("url") or "").strip()
            title = str(row.get("name") or "").strip()
            if not link or not title:
                continue
            summary = str(row.get("summary") or row.get("snippet") or "").strip()
            source_name = str(row.get("siteName") or "bocha").strip()
            out.append(
                {
                    "provider": "bocha_web",
                    "query": str(query or "").strip(),
                    "url": link,
                    "title": title,
                    "summary": summary[:1200],
                    "source_name": source_name,
                    "source_domain": _extract_domain(link),
                    "published_at": str(
                        row.get("datePublished") or row.get("dateLastCrawled") or ""
                    ),
                    "fetched_at": datetime.utcnow().isoformat(),
                    "reachable": True,
                }
            )
            if len(out) >= limit:
                break
        return out

    async def search_news(
        self,
        *,
        query: str,
        limit: int,
        allowed_domains: Optional[List[str]] = None,
    ) -> List[SearchHit]:
        if not self.enabled:
            return []
        q = str(query or "").strip()
        if not q:
            return []
        max_results = max(1, min(int(limit or self.max_results), self.max_results))
        domains = [str(x).strip().lower() for x in (allowed_domains or []) if str(x).strip()]
        queries = self._build_queries(q, domains)
        if not queries:
            return []
        timeout = httpx.Timeout(self.timeout_sec, connect=min(4.0, self.timeout_sec))
        sem = asyncio.Semaphore(self.concurrency)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            trust_env=_HTTPX_TRUST_ENV,
        ) as client:
            async def _worker(query_row: str) -> List[SearchHit]:
                async with sem:
                    return await self._search_single(
                        client=client,
                        query=query_row,
                        limit=max_results,
                    )

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
