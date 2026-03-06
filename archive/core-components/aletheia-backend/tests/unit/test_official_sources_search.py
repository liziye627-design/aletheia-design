import pytest

from services.layer1_perception.crawlers import official_sources as official_mod
from services.layer1_perception.crawlers.official_sources import OfficialSourceCrawler


class _StubDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.saved = []

    def search_rss_articles(self, **kwargs):
        return list(self.rows)

    def save_rss_article(self, article):
        self.saved.append(article)
        return article.get("id") or "ok"


@pytest.mark.asyncio
async def test_official_search_prefers_local_index_and_filters_source(monkeypatch):
    rows = [
        {
            "id": "a1",
            "source_id": "peoples_daily",
            "source_name": "人民日报",
            "title": "苏炳添宣布退役",
            "summary": "36岁苏炳添宣布退役",
            "link": "https://www.people.com.cn/n1/2025/1209/c1234-12345678.html",
            "published_at": "2025-12-09T00:00:00",
            "metadata": {"local_match_score": 4.0},
        },
        {
            "id": "a2",
            "source_id": "bbc",
            "source_name": "BBC",
            "title": "Irrelevant",
            "summary": "not about query",
            "link": "https://www.bbc.com/news/world-1",
            "published_at": "2025-12-09T00:00:00",
            "metadata": {"local_match_score": 1.0},
        },
    ]
    stub_db = _StubDB(rows=rows)
    monkeypatch.setattr(official_mod, "get_sqlite_db", lambda: stub_db)

    crawler = OfficialSourceCrawler(
        source_name="人民日报",
        source_url="https://www.people.com.cn/rss/politics.xml",
        source_type="state_media",
        access_method="web",
    )

    async def _empty_fetch(limit=50):
        return []

    monkeypatch.setattr(crawler, "fetch_hot_topics", _empty_fetch)

    out = await crawler.search(keyword="苏炳添 退役", limit=5)
    assert len(out) == 1
    meta = out[0].get("metadata") or {}
    assert meta.get("retrieval_mode") == "official_local_index"
    assert meta.get("keyword_match") is True
    assert "people.com.cn" in (out[0].get("original_url") or "")


@pytest.mark.asyncio
async def test_official_search_falls_back_to_live_fetch_and_writes_index(monkeypatch):
    stub_db = _StubDB(rows=[])
    monkeypatch.setattr(official_mod, "get_sqlite_db", lambda: stub_db)

    crawler = OfficialSourceCrawler(
        source_name="国家市场监督管理总局",
        source_url="https://www.samr.gov.cn/",
        source_type="regulator",
        access_method="web",
    )
    hit = crawler.standardize_item(
        {
            "url": "https://www.samr.gov.cn/xw/zj/202512/t20251209_12345.html",
            "text": "市场监管总局发布：苏炳添退役相关声明",
            "created_at": "2025-12-09T00:00:00",
            "author_name": crawler.source_name,
            "author_id": crawler.source_id,
            "followers": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "entities": [],
        }
    )
    hit["title"] = "市场监管总局发布：苏炳添退役相关声明"
    hit["description"] = "监管通报"
    hit["metadata"]["source_id"] = crawler.source_id
    hit["metadata"]["source_name"] = crawler.source_name

    miss = crawler.standardize_item(
        {
            "url": "https://www.samr.gov.cn/xw/zj/202512/t20251209_88888.html",
            "text": "与关键词无关的公告",
            "created_at": "2025-12-09T00:00:00",
            "author_name": crawler.source_name,
            "author_id": crawler.source_id,
            "followers": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "entities": [],
        }
    )
    miss["title"] = "与关键词无关的公告"
    miss["description"] = "无关"
    miss["metadata"]["source_id"] = crawler.source_id
    miss["metadata"]["source_name"] = crawler.source_name

    async def _fetch(limit=50):
        return [hit, miss]

    monkeypatch.setattr(crawler, "fetch_hot_topics", _fetch)

    out = await crawler.search(keyword="苏炳添 退役", limit=5)
    assert len(out) == 1
    assert "苏炳添" in (out[0].get("title") or "")
    assert len(stub_db.saved) >= 1
