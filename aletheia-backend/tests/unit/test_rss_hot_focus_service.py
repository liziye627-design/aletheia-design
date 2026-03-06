from services.rss_hot_focus_service import RssHotFocusService


def _item(
    item_id: str,
    *,
    title: str,
    published_at: str,
    source_id: str,
    source_name: str,
    category: str,
    url: str,
) -> dict:
    return {
        "id": item_id,
        "title": title,
        "description": f"{title} summary",
        "original_url": url,
        "published_at": published_at,
        "metadata": {
            "source_id": source_id,
            "source_name": source_name,
            "group_name": "测试分组",
            "category": category,
            "priority": 2,
        },
    }


def test_build_payload_prefers_fresh_diverse_items():
    service = RssHotFocusService()
    payload = service._build_payload(
        [
            _item(
                "a1",
                title="国际突发更新",
                published_at="2026-03-06T10:00:00+00:00",
                source_id="reuters",
                source_name="Reuters",
                category="国际",
                url="https://example.com/reuters-1",
            ),
            _item(
                "a2",
                title="政策发布更新",
                published_at="2026-03-06T09:00:00+00:00",
                source_id="gov",
                source_name="Gov",
                category="政策",
                url="https://example.com/gov-1",
            ),
            _item(
                "a3",
                title="科技产业观察",
                published_at="2026-03-06T08:00:00+00:00",
                source_id="36kr",
                source_name="36Kr",
                category="科技",
                url="https://example.com/36kr-1",
            ),
            _item(
                "stale",
                title="过旧政策",
                published_at="2024-01-01T00:00:00+00:00",
                source_id="old-gov",
                source_name="Old Gov",
                category="政策",
                url="https://example.com/old",
            ),
        ]
    )

    assert len(payload["summary_items"]) == 3
    titles = {item["title"] for item in payload["summary_items"]}
    assert "过旧政策" not in titles
    assert len({item["source_id"] for item in payload["summary_items"]}) == 3
    assert payload["source_count"] >= 3
    assert payload["candidate_count"] == 3


def test_build_payload_deduplicates_same_url():
    service = RssHotFocusService()
    payload = service._build_payload(
        [
            _item(
                "dup-1",
                title="重复条目A",
                published_at="2026-03-06T10:00:00+00:00",
                source_id="src-a",
                source_name="A",
                category="国际",
                url="https://example.com/same",
            ),
            _item(
                "dup-2",
                title="重复条目B",
                published_at="2026-03-06T09:59:00+00:00",
                source_id="src-b",
                source_name="B",
                category="国际",
                url="https://example.com/same",
            ),
        ]
    )

    assert payload["candidate_count"] == 1
    assert len(payload["detail_items"]) == 1
