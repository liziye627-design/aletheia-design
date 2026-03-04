"""Pydantic schemas for RSS articles and comments."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RssArticle(BaseModel):
    id: str
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    category: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    description: Optional[str] = None
    fast_summary: Optional[str] = None
    deep_summary: Optional[str] = None
    summary: Optional[str] = None
    summary_level: Optional[str] = None
    score: Optional[float] = None
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)
    comment_capability: Optional[str] = None
    comment_provider: Optional[str] = None
    comment_thread_id: Optional[str] = None
    comment_stats: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RssArticleListResponse(BaseModel):
    items: List[RssArticle]
    total: int
    page: int
    page_size: int
    has_more: bool


class RssComment(BaseModel):
    id: str
    article_id: str
    parent_id: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    created_at: Optional[str] = None
    like_count: Optional[int] = None
    reply_count: Optional[int] = None
    content_text: Optional[str] = None
    normalized_text: Optional[str] = None
    spam_score: Optional[float] = None
    spam_flags: List[str] = Field(default_factory=list)
    cluster_id: Optional[int] = None
    ingested_at: Optional[str] = None
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class RssCommentListResponse(BaseModel):
    items: List[RssComment]
    total: int
    page: int
    page_size: int
    has_more: bool
