import pytest

from services.layer1_perception import crawler_manager as crawler_manager_module
from services.layer1_perception.crawler_manager import CrawlerManager


def test_platform_domains_include_official_sources():
    manager = CrawlerManager()
    samr_domains = manager.get_platform_domains("samr")
    assert any("samr.gov.cn" in d for d in samr_domains)
    sec_domains = manager.get_platform_domains("sec")
    assert any("sec.gov" in d for d in sec_domains)


def test_platform_domains_do_not_keep_full_urls():
    manager = CrawlerManager()
    people_domains = manager.get_platform_domains("peoples_daily")
    assert any(d == "people.com.cn" for d in people_domains)
    assert all(not d.startswith("http") for d in people_domains)


def test_append_platform_domain_normalizes_url_to_hostname():
    manager = CrawlerManager()
    manager._platform_domains["__tmp"] = []
    manager._append_platform_domain(
        "__tmp",
        "https://www.people.com.cn/rss/politics.xml?x=1",
    )
    manager._append_platform_domain("__tmp", "www.people.com.cn")
    out = manager.get_platform_domains("__tmp")
    # 应只保留归一后的 host，不保留 URL 形式。
    assert out == ["people.com.cn"]


def test_keyword_filter_includes_content_text():
    manager = CrawlerManager()
    out = manager._filter_items_by_keyword_with_fallback(
        platform="news",
        items=[
            {"title": "x", "content_text": "this is about GPT-5 release", "metadata": {}},
            {"title": "y", "content": "nothing related", "metadata": {}},
        ],
        keyword="gpt-5",
        limit=10,
    )
    assert len(out) == 1
    assert "GPT-5" in out[0].get("content_text", "")


def test_keyword_filter_fallback_is_limited_and_marked():
    manager = CrawlerManager()
    rows = [
        {"title": f"row-{idx}", "content_text": "unrelated hot topic", "metadata": {}}
        for idx in range(9)
    ]
    out = manager._filter_items_by_keyword_with_fallback(
        platform="xiaohongshu",
        items=rows,
        keyword="rare-keyword-not-found",
        limit=20,
    )
    assert len(out) == 5
    for row in out:
        meta = row.get("metadata") or {}
        assert meta.get("keyword_match") is False
        assert meta.get("retrieval_mode") == "hot_fallback"
        assert meta.get("low_relevance_fallback") is True


def test_keyword_filter_weibo_prefers_web_fallback_over_hot_pool():
    manager = CrawlerManager()
    rows = [
        {"title": f"row-{idx}", "content_text": "unrelated hot topic", "metadata": {}}
        for idx in range(12)
    ]
    out = manager._filter_items_by_keyword_with_fallback(
        platform="weibo",
        items=rows,
        keyword="rare-keyword-not-found",
        limit=20,
    )
    assert out == []


def test_keyword_filter_official_news_prefers_web_fallback_over_hot_pool():
    manager = CrawlerManager()
    rows = [
        {"title": f"row-{idx}", "content_text": "unrelated hot topic", "metadata": {}}
        for idx in range(32)
    ]
    out = manager._filter_items_by_keyword_with_fallback(
        platform="news",
        items=rows,
        keyword="rare-keyword-not-found",
        limit=80,
    )
    # 0 命中时不应直接回热点，交给 _search_platform 的 web fallback 分支处理。
    assert out == []


def test_keyword_query_variants_expand_cjk_event_phrase():
    manager = CrawlerManager()
    out = manager._keyword_query_variants("苏炳添退役了")
    assert out
    # 保留原始查询 + 关键实体词，避免整句匹配失败时全量退化为热点。
    assert "苏炳添退役了" in out
    assert any("苏炳添" == x for x in out)


def test_keyword_query_variants_trim_question_tail_for_cjk_claim():
    manager = CrawlerManager()
    out = manager._keyword_query_variants("苏炳添退役了吗？")
    assert out
    assert any("苏炳添退役" == x for x in out)
    assert any("苏炳添" == x for x in out)


def test_reason_code_normalization_network_and_proxy():
    manager = CrawlerManager()
    assert (
        manager._normalize_reason_code("Temporary failure in name resolution")
        == "DNS_ERROR"
    )
    assert (
        manager._normalize_reason_code("proxy connect failed 127.0.0.1:7897")
        == "PROXY_UNREACHABLE"
    )
    assert manager._normalize_reason_code("request timed out") == "CRAWLER_TIMEOUT"
    assert manager._normalize_reason_code("fallback empty result") == "FALLBACK_EMPTY"


def test_academic_crawlers_are_initialized():
    manager = CrawlerManager()
    assert "gdelt" in manager.crawlers
    assert "common_crawl" in manager.crawlers
    assert "openalex" in manager.crawlers


def test_split_platform_pools_stable_profile():
    manager = CrawlerManager()
    pools = manager.split_platform_pools(
        requested_platforms=["bbc", "guardian", "samr", "weibo", "zhihu", "news"],
        profile="stable_mixed_v1",
    )
    stable_pool = pools["stable_pool"]
    experimental_pool = pools["experimental_pool"]
    assert "bbc" in stable_pool
    assert "guardian" in stable_pool
    assert "samr" in stable_pool
    assert "news" in experimental_pool
    assert "weibo" in experimental_pool


def test_platform_source_matrix_contains_primary_and_pool():
    manager = CrawlerManager()
    matrix = manager.get_platform_source_matrix()
    assert "bbc" in matrix
    assert matrix["bbc"]["profile_pool"] in {"stable", "experimental"}
    assert matrix["bbc"]["quality_tier"] in {1, 2, 3}
    assert isinstance(matrix["bbc"]["backup_urls"], list)


def test_primary_url_falls_back_to_backup_list():
    manager = CrawlerManager()
    primary = manager.get_platform_primary_url("news")
    assert primary.startswith("http")


def test_search_sources_snapshot_loaded():
    manager = CrawlerManager()
    rows = manager.get_search_sources_snapshot()
    assert rows
    platforms = {str(r.get("platform") or "") for r in rows if isinstance(r, dict)}
    assert "weibo" in platforms
    assert "xinhua" in platforms


def test_search_source_routing_filters_en_background_for_zh_query():
    manager = CrawlerManager()
    selected = manager._filter_platforms_by_search_registry(
        keyword="苏炳添退役了吗",
        platforms=["weibo", "xinhua", "reuters", "bbc"],
    )
    assert "weibo" in selected
    assert "xinhua" in selected
    assert "reuters" not in selected
    assert "bbc" not in selected


def test_annotate_items_with_search_source_adds_metadata():
    manager = CrawlerManager()
    out = manager._annotate_items_with_search_source(
        platform="weibo",
        keyword="苏炳添退役了吗",
        items=[{"title": "苏炳添退役", "content": "测试", "metadata": {}}],
    )
    assert len(out) == 1
    meta = out[0]["metadata"]
    assert meta.get("search_source_platform") == "weibo"
    assert meta.get("search_source_mode") in {"search", "hot", "topic", "feed"}


def test_bocha_fallback_allowlist_defaults_loaded():
    manager = CrawlerManager()
    assert manager.enable_bocha_fallback is True
    assert "weibo" in manager._bocha_fallback_allowlist
    assert "zhihu" in manager._bocha_fallback_allowlist


@pytest.mark.asyncio
async def test_bocha_fallback_uses_cache_for_same_query(monkeypatch):
    calls = {"count": 0}

    class FakeProvider:
        enabled = True
        enable_site_scoped_queries = False

        async def search_news(self, *, query, limit, allowed_domains=None):
            calls["count"] += 1
            return [
                {
                    "url": "https://weibo.com/123456/abc",
                    "title": "苏炳添宣布退役",
                    "summary": "测试摘要",
                }
            ]

    monkeypatch.setattr(crawler_manager_module, "BochaSearchProvider", lambda: FakeProvider())
    manager = CrawlerManager()
    manager._bocha_fallback_cache_ttl_sec = 300
    manager._bocha_fallback_max_query_variants = 1

    rows1 = await manager._bocha_web_search_fallback(
        platform="weibo",
        keyword="苏炳添退役了吗",
        limit=5,
        require_keyword_match=False,
    )
    rows2 = await manager._bocha_web_search_fallback(
        platform="weibo",
        keyword="苏炳添退役了吗",
        limit=5,
        require_keyword_match=False,
    )

    assert calls["count"] == 1
    assert len(rows1) == 1
    assert len(rows2) == 1


@pytest.mark.asyncio
async def test_bocha_fallback_allows_cross_domain_for_social_platform(monkeypatch):
    class FakeProvider:
        enabled = True
        enable_site_scoped_queries = False

        async def search_news(self, *, query, limit, allowed_domains=None):
            return [
                {
                    "url": "https://news.cn/sports/20251209/abc.html",
                    "title": "苏炳添宣布退役",
                    "summary": "新华社报道",
                }
            ]

    monkeypatch.setattr(crawler_manager_module, "BochaSearchProvider", lambda: FakeProvider())
    manager = CrawlerManager()
    manager._bocha_allow_cross_domain_social = True
    manager._bocha_social_platforms = {"zhihu"}
    rows = await manager._bocha_web_search_fallback(
        platform="zhihu",
        keyword="苏炳添退役了吗",
        limit=5,
        require_keyword_match=False,
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_bocha_fallback_rejects_cross_domain_for_non_social(monkeypatch):
    class FakeProvider:
        enabled = True
        enable_site_scoped_queries = False

        async def search_news(self, *, query, limit, allowed_domains=None):
            return [
                {
                    "url": "https://news.cn/sports/20251209/abc.html",
                    "title": "苏炳添宣布退役",
                    "summary": "新华社报道",
                }
            ]

    monkeypatch.setattr(crawler_manager_module, "BochaSearchProvider", lambda: FakeProvider())
    manager = CrawlerManager()
    manager._bocha_allow_cross_domain_social = True
    manager._bocha_social_platforms = {"weibo", "zhihu"}
    rows = await manager._bocha_web_search_fallback(
        platform="csrc",
        keyword="苏炳添退役了吗",
        limit=5,
        require_keyword_match=False,
    )
    assert rows == []
