import pytest

from core.config import settings
from services.external.mediacrawler_client import MediaCrawlerClient
from services.layer1_perception.crawler_manager import CrawlerManager
from services.layer1_perception.crawlers.mediacrawler_normalizer import (
    normalize_mediacrawler_posts,
)


@pytest.mark.asyncio
async def test_mediacrawler_client_health_respects_enable_ack(monkeypatch):
    monkeypatch.setattr(settings, "MEDIACRAWLER_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False, raising=False)
    client = MediaCrawlerClient()
    row = await client.health_check()
    assert row["ok"] is False
    assert row["reason"] == "MEDIACRAWLER_DISABLED"

    monkeypatch.setattr(settings, "MEDIACRAWLER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False, raising=False)
    row2 = await client.health_check()
    assert row2["ok"] is False
    assert row2["reason"] == "MEDIACRAWLER_ACK_REQUIRED"


def test_mediacrawler_normalizer_outputs_standard_fields():
    rows = [
        {
            "id": "raw_1",
            "mblogid": "M123456",
            "url": "https://weibo.com/123456/M123456",
            "content": "苏炳添退役？官方尚未确认。",
            "created_at": "2026-02-24T10:00:00",
            "author_id": "u_1",
            "author_name": "用户A",
            "likes": 12,
            "comments": 3,
            "shares": 2,
        }
    ]
    out = normalize_mediacrawler_posts(
        platform="weibo",
        rows=rows,
        keyword="苏炳添退役",
        sidecar_task_id="mc_task_1",
    )
    assert len(out) == 1
    row = out[0]
    assert row["source_platform"] == "weibo"
    assert row["original_url"].startswith("https://weibo.com")
    assert row["content_text"] != ""
    meta = row["metadata"]
    assert meta["provider"] == "mediacrawler"
    assert meta["retrieval_mode"] == "mediacrawler_api"
    assert meta["post_id"] == "M123456"
    assert meta["sidecar_task_id"] == "mc_task_1"


def test_crawler_manager_merges_native_and_mediacrawler_without_dup():
    manager = CrawlerManager()
    native = [
        {
            "url": "https://weibo.com/123456/M123456",
            "content_text": "unrelated hot topic",
            "metadata": {
                "provider": "native",
                "keyword_match": False,
                "keyword_match_score": 0.02,
            },
        }
    ]
    sidecar = [
        {
            "url": "https://weibo.com/123456/M123456",
            "content_text": "苏炳添退役相关动态",
            "metadata": {
                "provider": "mediacrawler",
                "keyword_match": True,
                "keyword_match_score": 0.98,
                "post_id": "M123456",
            },
        }
    ]
    merged = manager._merge_native_with_mediacrawler(
        native_items=native,
        mediacrawler_items=sidecar,
        limit=10,
    )
    assert len(merged) == 1
    assert merged[0]["metadata"]["provider"] == "mediacrawler"
    assert merged[0]["metadata"]["keyword_match"] is True


@pytest.mark.asyncio
async def test_hot_fallback_trigger_calls_mediacrawler_for_social_platforms(monkeypatch):
    manager = CrawlerManager()
    monkeypatch.setattr(settings, "MEDIACRAWLER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", True, raising=False)

    async def _fake_native(*args, **kwargs):
        del args, kwargs
        return [
            {
                "url": "https://weibo.com/xxx",
                "content_text": "unrelated hot item",
                "metadata": {
                    "keyword_match": False,
                    "keyword_match_score": 0.01,
                    "retrieval_mode": "hot_fallback",
                    "provider": "native",
                },
            }
        ]

    async def _fake_sidecar(*args, **kwargs):
        del args, kwargs
        return {
            "ok": True,
            "reason": "OK",
            "task_id": "mc_task_x",
            "items": [
                {
                    "url": "https://weibo.com/123456/M123456",
                    "content_text": "苏炳添退役传闻核验",
                    "metadata": {
                        "provider": "mediacrawler",
                        "retrieval_mode": "mediacrawler_api",
                        "keyword_match": True,
                        "keyword_match_score": 0.9,
                        "post_id": "M123456",
                    },
                }
            ],
        }

    async def _fake_web_fallback(*args, **kwargs):
        del args, kwargs
        return []

    monkeypatch.setattr(manager, "_call_first_available_search", _fake_native)
    monkeypatch.setattr(manager, "_collect_mediacrawler_posts", _fake_sidecar)
    monkeypatch.setattr(manager, "_public_web_search_fallback", _fake_web_fallback)

    row = await manager._search_platform(
        platform="weibo",
        keyword="苏炳添退役",
        limit=10,
        mediacrawler_options={"use_mediacrawler": True, "mediacrawler_platforms": ["weibo"]},
        return_diagnostics=True,
    )
    assert isinstance(row, dict)
    assert len(row.get("items") or []) >= 1
    sidecar = row.get("mediacrawler") or {}
    assert sidecar.get("triggered") is True
    assert int(sidecar.get("mediacrawler_count") or 0) > 0
    assert int(sidecar.get("merged_count") or 0) > 0


@pytest.mark.asyncio
async def test_sidecar_failure_soft_degrade_and_flag_set(monkeypatch):
    manager = CrawlerManager()
    monkeypatch.setattr(settings, "MEDIACRAWLER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", True, raising=False)

    async def _fake_native(*args, **kwargs):
        del args, kwargs
        return [
            {
                "url": "https://weibo.com/xxx",
                "content_text": "fallback row",
                "metadata": {
                    "keyword_match": False,
                    "keyword_match_score": 0.01,
                    "retrieval_mode": "hot_fallback",
                    "provider": "native",
                },
            }
        ]

    async def _fake_sidecar_fail(*args, **kwargs):
        del args, kwargs
        return {"ok": False, "reason": "MEDIACRAWLER_UNAVAILABLE"}

    monkeypatch.setattr(manager, "_call_first_available_search", _fake_native)
    monkeypatch.setattr(manager, "_collect_mediacrawler_posts", _fake_sidecar_fail)

    row = await manager._search_platform(
        platform="weibo",
        keyword="苏炳添退役",
        limit=10,
        mediacrawler_options={"use_mediacrawler": True, "mediacrawler_platforms": ["weibo"]},
        return_diagnostics=True,
    )
    assert len(row.get("items") or []) >= 1
    sidecar = row.get("mediacrawler") or {}
    assert sidecar.get("triggered") is True
    assert sidecar.get("degraded") is True
    assert "MEDIACRAWLER" in str(sidecar.get("error") or "")

