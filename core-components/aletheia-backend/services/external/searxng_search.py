"""
SearXNG JSON search provider for external evidence supplements.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from core.config import settings
from services.external.search_provider import SearchHit
from services.investigation_helpers import _HTTPX_TRUST_ENV
from utils.logging import logger


class SearxngSearchProvider:
    def __init__(self) -> None:
        self.base_url = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_SEARXNG_BASE_URL", "")
            or ""
        ).strip()
        self.enabled = bool(self.base_url)
        self.timeout_sec = max(
            2.0,
            float(
                getattr(
                    settings,
                    "INVESTIGATION_EXTERNAL_SEARCH_SEARXNG_TIMEOUT_SEC",
                    getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_TIMEOUT_SEC", 6.0),
                )
            ),
        )
        self.max_domain_queries = max(
            2,
            int(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_DOMAIN_QUERIES", 8)),
        )

    def _build_query(self, query: str, allowed_domains: List[str]) -> str:
        q = str(query or "").strip()
        if not q:
            return ""
        domains = [str(x).strip().lower() for x in (allowed_domains or []) if str(x).strip()]
        if not domains:
            return q
        scope = " OR ".join([f"site:{d}" for d in domains[: self.max_domain_queries]])
        return f"{q} ({scope})"

    async def search_news(
        self,
        *,
        query: str,
        limit: int,
        allowed_domains: Optional[List[str]] = None,
    ) -> List[SearchHit]:
        if not self.enabled:
            return []
        q = self._build_query(query, allowed_domains or [])
        if not q:
            return []

        encoded_q = quote(q)
        url = f"{self.base_url.rstrip('/')}/search?q={encoded_q}&format=json"
        timeout = httpx.Timeout(self.timeout_sec, connect=min(3.0, self.timeout_sec))
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=_HTTPX_TRUST_ENV,
            ) as client:
                resp = await client.get(url)
                if int(resp.status_code) >= 400:
                    logger.warning(
                        f"searxng search failed status={resp.status_code} url={self.base_url}"
                    )
                    return []
                payload = resp.json() if resp.content else {}
        except Exception as exc:
            logger.warning(f"searxng request failed: {type(exc).__name__}")
            return []

        rows = list((payload or {}).get("results") or [])
        out: List[SearchHit] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            link = str(row.get("url") or "").strip()
            title = str(row.get("title") or "").strip()
            if not link or not title:
                continue
            content = str(row.get("content") or "").strip()
            source_domain = str(row.get("parsed_url", [None, None, None, ""])[2] or "").strip().lower()
            out.append(
                {
                    "provider": "searxng",
                    "query": query,
                    "url": link,
                    "title": title,
                    "summary": content[:1200],
                    "source_name": str(row.get("engine") or "searxng"),
                    "source_domain": source_domain,
                    "published_at": str(row.get("publishedDate") or ""),
                    "fetched_at": datetime.utcnow().isoformat(),
                    "reachable": True,
                }
            )
            if len(out) >= max(1, int(limit or 10)):
                break
        return out

