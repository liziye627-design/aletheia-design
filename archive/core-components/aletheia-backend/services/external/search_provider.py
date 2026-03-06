"""
External search provider interfaces.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol


SearchHit = Dict[str, Any]


class SearchProvider(Protocol):
    async def search_news(
        self,
        *,
        query: str,
        limit: int,
        allowed_domains: List[str] | None = None,
    ) -> List[SearchHit]:
        ...

