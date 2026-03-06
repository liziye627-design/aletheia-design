"""Background runner for RSS pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from core.config import settings
from core.sqlite_database import get_sqlite_db
from utils.logging import logger
from services.layer1_perception.crawlers.rss_pool import RssPoolCrawler
from services.rss_sources_config import get_rss_sources_registry
from services.comments.comment_discovery import discover_comments
from services.comments.comment_fetcher import CommentFetchRequest, fetch_comments
from services.comments.comments_config import get_comments_config
from services.comments.spam_scorer import score_comments


async def _run_pipeline_once(limit: int, with_comments: bool) -> List[Dict[str, Any]]:
    registry = get_rss_sources_registry()
    sources = registry.get_rss_sources() if registry else []
    crawler = RssPoolCrawler(sources)
    items = await crawler.fetch_hot_topics(limit=limit)
    if getattr(crawler, "last_fetch_stats", None):
        logger.info(f"rss_pipeline(loop): {crawler.last_fetch_stats}")
    db = get_sqlite_db()
    item_concurrency = max(1, int(getattr(settings, "RSS_PIPELINE_ITEM_CONCURRENCY", 6)))

    if with_comments:
        cfg_obj = get_comments_config()
        cfg = cfg_obj.get() if cfg_obj else {}
        policy = cfg.get("fetch_policy") or {}
        min_score = float(policy.get("min_score") or 70)
        require_summary_level = bool(policy.get("require_summary_level", False))
        fetch_cfg = cfg.get("fetch") or {}
        first_fetch = fetch_cfg.get("first_fetch") or {}
        page_size = int(first_fetch.get("page_size") or 20)
        max_pages = int(first_fetch.get("max_pages") or 1)

        sem = asyncio.Semaphore(item_concurrency)

        async def _process_item(item: Dict[str, Any]) -> None:
            async with sem:
                try:
                    score = float(item.get("score") or 0)
                    summary_level = item.get("summary_level")
                    if score < min_score:
                        await asyncio.to_thread(db.save_rss_article, item)
                        return
                    if require_summary_level and summary_level != "deep":
                        await asyncio.to_thread(db.save_rss_article, item)
                        return
                    url = item.get("original_url") or item.get("metadata", {}).get("source_url")
                    if not url:
                        await asyncio.to_thread(db.save_rss_article, item)
                        return
                    discovery = await discover_comments(url)
                    item["comment_capability"] = discovery.capability
                    item["comment_provider"] = discovery.provider
                    item["comment_thread_id"] = discovery.thread_id
                    item["comment_endpoint"] = discovery.endpoint
                    comments: List[Dict[str, Any]] = []
                    if discovery.capability == "public" and discovery.endpoint:
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
                    article_id = await asyncio.to_thread(db.save_rss_article, item)
                    if comments:
                        await asyncio.to_thread(db.save_rss_comments, article_id, comments)
                except Exception as exc:
                    logger.warning("rss_pipeline(item): failed %s", type(exc).__name__)

        await asyncio.gather(*[_process_item(item) for item in items], return_exceptions=True)
    else:
        await asyncio.gather(
            *[asyncio.to_thread(db.save_rss_article, item) for item in items],
            return_exceptions=True,
        )

    return items


async def run_rss_pipeline_loop(stop_event: asyncio.Event) -> None:
    interval = int(getattr(settings, "RSS_PIPELINE_INTERVAL_SECONDS", 600))
    limit = int(getattr(settings, "RSS_PIPELINE_LIMIT", 50))
    with_comments = bool(getattr(settings, "RSS_PIPELINE_WITH_COMMENTS", False))
    lock = asyncio.Lock()

    while not stop_event.is_set():
        try:
            async with lock:
                await _run_pipeline_once(limit, with_comments)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("rss_pipeline: run failed %s", type(exc).__name__)
        await asyncio.sleep(max(5, interval))


def start_rss_pipeline_task(app) -> None:
    if not bool(getattr(settings, "RSS_PIPELINE_ENABLED", False)):
        return
    stop_event = asyncio.Event()
    task = asyncio.create_task(run_rss_pipeline_loop(stop_event))
    app.state.rss_pipeline_stop_event = stop_event
    app.state.rss_pipeline_task = task
    logger.info("ℹ️ RSS pipeline background task scheduled")


async def stop_rss_pipeline_task(app) -> None:
    stop_event = getattr(app.state, "rss_pipeline_stop_event", None)
    task = getattr(app.state, "rss_pipeline_task", None)
    if stop_event:
        stop_event.set()
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
