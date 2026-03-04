"""Generic comment fetcher for discovered endpoints."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx

logger = logging.getLogger("comment_fetcher")


@dataclass
class CommentFetchRequest:
    endpoint: str
    thread_id: Optional[str] = None
    page: int = 1
    page_size: int = 20
    extra_params: Optional[Dict[str, Any]] = None


def _extract_comments(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("comments", "list", "items", "data", "hot", "replies"):
            if key in data:
                return _extract_comments(data.get(key))
    return []


def _normalize_comment(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "comment_id": raw.get("id") or raw.get("comment_id") or raw.get("cid"),
        "author": raw.get("author") or raw.get("user") or raw.get("nickname"),
        "created_at": raw.get("created_at") or raw.get("time") or raw.get("date"),
        "like_count": raw.get("like") or raw.get("likes") or raw.get("like_count"),
        "reply_count": raw.get("reply") or raw.get("replies") or raw.get("reply_count"),
        "content_text": raw.get("content") or raw.get("text") or raw.get("message"),
        "raw_payload": raw,
    }


async def fetch_comments(req: CommentFetchRequest) -> List[Dict[str, Any]]:
    if not req.endpoint:
        return []
    params: Dict[str, Any] = {
        "page": req.page,
        "page_size": req.page_size,
        "pageSize": req.page_size,
        "limit": req.page_size,
    }
    if req.thread_id:
        params.update(
            {
                "thread_id": req.thread_id,
                "object_id": req.thread_id,
                "docId": req.thread_id,
                "newsId": req.thread_id,
                "articleId": req.thread_id,
            }
        )
    if req.extra_params:
        params.update(req.extra_params)

    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(req.endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("comment_fetcher: fetch failed %s: %s", req.endpoint, type(exc).__name__)
            return []

    comments = _extract_comments(data)
    return [_normalize_comment(row) for row in comments if isinstance(row, dict)]
