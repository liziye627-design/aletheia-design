#!/usr/bin/env python3
"""
Runtime smoke checks for backend stability.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings
from core.sqlite_database import _resolve_sqlite_db_path, _can_open_sqlite_rw
from scripts.network_preflight import run_preflight, DEFAULT_ENDPOINTS
from services.llm.llm_failover import create_failover_manager_from_env
from services.llm.siliconflow_client import SiliconFlowClient
from services.layer1_perception.crawlers.rss_pool import RssPoolCrawler


async def _check_llm_semantic() -> Dict[str, Any]:
    client = SiliconFlowClient()
    result = await client.score_semantic_relevance(
        claim="OpenAI released a new model",
        keyword="OpenAI model release",
        evidence_text=(
            "At a developer event, OpenAI announced updates including "
            "enterprise controls and faster inference."
        ),
        source="smoke-test",
    )
    return {
        "ok": bool(
            isinstance(result, dict)
            and ("semantic_score" in result)
            and ("is_relevant" in result)
        ),
        "result": result,
    }


async def _check_rss_fetch() -> Dict[str, Any]:
    sources = [
        {
            "source_id": "bbc",
            "name": "BBC",
            "type": "rss",
            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "enabled": True,
            "priority": 1,
        },
        {
            "source_id": "google",
            "name": "Google News",
            "type": "rss",
            "url": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
            "enabled": True,
            "priority": 1,
        },
    ]
    crawler = RssPoolCrawler(sources)
    items = await crawler.fetch_hot_topics(limit=5)
    stats = crawler.last_fetch_stats
    return {
        "ok": bool(len(items) > 0),
        "items": len(items),
        "stats": stats,
    }


def _check_sqlite_writable() -> Dict[str, Any]:
    preferred = str(getattr(settings, "SQLITE_DB_PATH", "./aletheia.db"))
    resolved = _resolve_sqlite_db_path(preferred)
    return {
        "ok": bool(_can_open_sqlite_rw(resolved)),
        "preferred_path": preferred,
        "resolved_path": resolved,
        "resolved_exists": Path(resolved).exists(),
    }


def _check_llm_provider() -> Dict[str, Any]:
    manager = create_failover_manager_from_env()
    providers = manager.get_all_providers()
    available = manager.get_available_providers()
    return {
        "ok": bool(len(providers) > 0),
        "providers_total": len(providers),
        "providers_available": len(available),
        "providers": [
            {
                "name": p.name,
                "base_url": p.base_url,
                "model": p.model,
                "priority": p.priority,
                "status": p.get_status().value,
            }
            for p in providers
        ],
    }


async def main() -> int:
    report: Dict[str, Any] = {}
    report["network_preflight"] = run_preflight(list(DEFAULT_ENDPOINTS))
    report["sqlite_writable"] = _check_sqlite_writable()
    report["llm_provider"] = _check_llm_provider()
    report["llm_semantic"] = await _check_llm_semantic()
    report["rss_fetch"] = await _check_rss_fetch()
    report["ok"] = bool(
        report["network_preflight"].get("ok")
        and report["sqlite_writable"].get("ok")
        and report["llm_provider"].get("ok")
        and report["llm_semantic"].get("ok")
        and report["rss_fetch"].get("ok")
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
