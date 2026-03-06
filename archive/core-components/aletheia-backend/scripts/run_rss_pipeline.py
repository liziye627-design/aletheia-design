"""Run RSS pipeline: fetch RSS, apply rules, optionally discover comments and spam score."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict, List

from services.layer1_perception.crawlers.rss_pool import RssPoolCrawler
from services.rss_sources_config import get_rss_sources_registry
from services.comments.comment_discovery import discover_comments
from services.comments.comment_fetcher import CommentFetchRequest, fetch_comments
from services.comments.comments_config import get_comments_config
from services.comments.spam_scorer import score_comments
from core.sqlite_database import get_sqlite_db
from utils.logging import logger


async def run_pipeline(limit: int, with_comments: bool, output_path: str | None) -> List[Dict[str, Any]]:
    registry = get_rss_sources_registry()
    sources = registry.get_rss_sources() if registry else []
    crawler = RssPoolCrawler(sources)
    items = await crawler.fetch_hot_topics(limit=limit)
    if getattr(crawler, "last_fetch_stats", None):
        logger.info(f"rss_pipeline(cli): {crawler.last_fetch_stats}")
    db = get_sqlite_db()

    if with_comments:
        cfg_obj = get_comments_config()
        cfg = cfg_obj.get() if cfg_obj else {}
        policy = cfg.get("fetch_policy") or {}
        min_score = float(policy.get("min_score") or 70)
        require_summary_level = bool(policy.get("require_summary_level", False))

        for item in items:
            score = float(item.get("score") or 0)
            summary_level = item.get("summary_level")
            if score < min_score:
                continue
            if require_summary_level and summary_level != "deep":
                continue
            url = item.get("original_url") or item.get("metadata", {}).get("source_url")
            if not url:
                continue
            discovery = await discover_comments(url)
            item["comment_capability"] = discovery.capability
            item["comment_provider"] = discovery.provider
            item["comment_thread_id"] = discovery.thread_id
            item["comment_endpoint"] = discovery.endpoint
            if discovery.capability != "public" or not discovery.endpoint:
                continue
            fetch_cfg = cfg.get("fetch") or {}
            first_fetch = fetch_cfg.get("first_fetch") or {}
            page_size = int(first_fetch.get("page_size") or 20)
            max_pages = int(first_fetch.get("max_pages") or 1)
            comments: List[Dict[str, Any]] = []
            for page in range(1, max_pages + 1):
                req = CommentFetchRequest(
                    endpoint=discovery.endpoint,
                    thread_id=discovery.thread_id,
                    page=page,
                    page_size=page_size,
                    extra_params=discovery.extra_params,
                )
                batch = await fetch_comments(req)
                if not batch:
                    break
                comments.extend(batch)
                if len(batch) < page_size:
                    break
            if comments:
                comments = score_comments(comments)
                item["comments"] = comments
                spam_scores = [float(c.get("spam_score") or 0) for c in comments]
                suspected = [s for s in spam_scores if s >= 60]
                item["comment_stats"] = {
                    "total": len(comments),
                    "suspected": len(suspected),
                    "suspected_ratio": round(len(suspected) / max(1, len(comments)), 3),
                }
            if comments:
                article_id = db.save_rss_article(item)
                db.save_rss_comments(article_id, comments)
            else:
                db.save_rss_article(item)
    else:
        for item in items:
            db.save_rss_article(item)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--with-comments", action="store_true")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    output = args.output.strip() or None
    asyncio.run(run_pipeline(args.limit, args.with_comments, output))


if __name__ == "__main__":
    main()
