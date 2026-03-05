"""RSS articles and comments endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from core.sqlite_database import get_sqlite_db
from models.schemas.rss import (
    RssArticle,
    RssArticleListResponse,
    RssCommentListResponse,
)

router = APIRouter()


@router.get("/articles", response_model=RssArticleListResponse)
async def list_rss_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_id: str | None = None,
    category: str | None = None,
):
    db = get_sqlite_db()
    data = db.list_rss_articles(
        page=page, page_size=page_size, source_id=source_id, category=category
    )
    return data


@router.get("/articles/search", response_model=RssArticleListResponse)
async def search_rss_articles(
    keyword: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(20, ge=1, le=200),
    source_id: str | None = None,
    days: int = Query(30, ge=1, le=365),
):
    db = get_sqlite_db()
    items = db.search_rss_articles(
        keyword=keyword,
        limit=limit,
        source_id=source_id,
        days=days,
    )
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": limit,
        "has_more": False,
    }


@router.get("/articles/{article_id}", response_model=RssArticle)
async def get_rss_article(article_id: str):
    db = get_sqlite_db()
    item = db.get_rss_article(article_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Article not found"
        )
    return item


@router.get("/articles/{article_id}/comments", response_model=RssCommentListResponse)
async def list_rss_comments(
    article_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = get_sqlite_db()
    data = db.list_rss_comments(article_id=article_id, page=page, page_size=page_size)
    return data
