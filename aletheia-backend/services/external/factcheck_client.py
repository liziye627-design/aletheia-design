"""
Google Fact Check Tools 客户端（可降级）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import httpx

from core.config import settings
from utils.logging import logger


class GoogleFactCheckClient:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "FACTCHECK_ENABLE", True))
        self.api_key = str(getattr(settings, "GOOGLE_FACTCHECK_API_KEY", "") or "").strip()
        self.api_url = str(
            getattr(
                settings,
                "GOOGLE_FACTCHECK_API_URL",
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
            )
        )
        self.timeout_sec = float(getattr(settings, "FACTCHECK_TIMEOUT_SEC", 6))

    def _unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "available": False,
            "reason": reason,
            "items": [],
            "fetched_at": datetime.utcnow().isoformat(),
        }

    async def search_claim(self, claim_text: str, *, page_size: int = 5) -> Dict[str, Any]:
        if not self.enabled:
            return self._unavailable("FACTCHECK_DISABLED")
        if not self.api_key:
            return self._unavailable("FACTCHECK_UNAVAILABLE")
        query = str(claim_text or "").strip()
        if not query:
            return self._unavailable("EMPTY_CLAIM")

        params = {"query": query, "languageCode": "en", "pageSize": max(1, min(10, page_size)), "key": self.api_key}
        timeout = httpx.Timeout(self.timeout_sec, connect=min(3.0, self.timeout_sec))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.api_url, params=params)
                response.raise_for_status()
                payload = response.json() if response.content else {}
        except Exception as exc:
            logger.warning(f"factcheck query failed: {exc}")
            return {
                "available": False,
                "reason": "FACTCHECK_REQUEST_FAILED",
                "error": str(exc),
                "items": [],
                "fetched_at": datetime.utcnow().isoformat(),
            }

        items: List[Dict[str, Any]] = []
        for claim_row in payload.get("claims") or []:
            claim_text_out = str(claim_row.get("text") or claim_text)
            claim_date = claim_row.get("claimDate")
            for review in claim_row.get("claimReview") or []:
                publisher = review.get("publisher") or {}
                site = str(publisher.get("site") or "")
                url = str(review.get("url") or "")
                rating = str(review.get("textualRating") or review.get("title") or "")
                title = str(review.get("title") or "")
                language = str(review.get("languageCode") or "unknown")
                stance = self._stance_from_rating(rating)
                items.append(
                    {
                        "claim_text": claim_text_out,
                        "claim_date": claim_date,
                        "publisher_name": str(publisher.get("name") or "factcheck"),
                        "publisher_site": site,
                        "url": url,
                        "title": title,
                        "rating": rating,
                        "language": language,
                        "stance": stance,
                    }
                )

        return {
            "available": True,
            "reason": "OK",
            "items": items,
            "fetched_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _stance_from_rating(rating: str) -> str:
        low = str(rating or "").lower()
        if not low:
            return "unclear"
        refute_tokens = ["false", "misleading", "pants on fire", "incorrect", "wrong", "fake"]
        support_tokens = ["true", "correct", "accurate", "mostly true"]
        has_refute = any(token in low for token in refute_tokens)
        has_support = any(token in low for token in support_tokens)
        if has_refute and has_support:
            return "mixed"
        if has_refute:
            return "refute"
        if has_support:
            return "support"
        return "unclear"

