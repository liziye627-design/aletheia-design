import pytest

from services import investigation_reporting as reporting_mod


class _StubProvider:
    def __init__(self, rows):
        self.rows = list(rows or [])

    async def search_news(self, *, query, limit, allowed_domains=None):
        _ = (query, allowed_domains)
        return list(self.rows)[: max(1, int(limit))]


def test_provider_chain_from_settings(monkeypatch):
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_PROVIDER_CHAIN",
        "google_news_rss, bocha_web, searxng, google_news_rss",
        raising=False,
    )
    chain = reporting_mod._provider_chain_from_settings()
    assert chain == ["google_news_rss", "bocha_web", "searxng"]


def test_build_search_providers_supports_bocha(monkeypatch):
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_PROVIDER_CHAIN",
        "bocha_web,google_news_rss",
        raising=False,
    )

    class _EnabledBocha:
        enabled = True

    monkeypatch.setattr(reporting_mod, "BochaSearchProvider", lambda: _EnabledBocha())
    providers = reporting_mod._build_search_providers()
    assert [name for name, _ in providers] == ["bocha_web", "google_news_rss"]


@pytest.mark.asyncio
async def test_check_external_sources_uses_provider_chain_and_whitelist(monkeypatch):
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_ALLOWED_DOMAINS",
        "news.cn,people.com.cn",
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_PER_PROVIDER_LIMIT",
        10,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS",
        10,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_MIN_RELEVANCE",
        0.1,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_ENTITY_HIT",
        True,
        raising=False,
    )
    p1_rows = [
        {
            "provider": "google_news_rss",
            "url": "https://www.news.cn/sports/2025-12/09/c_123.htm",
            "title": "苏炳添：将在十五运会后退役",
            "summary": "新华社报道",
            "source_name": "新华网",
            "source_domain": "news.cn",
        },
        # duplicate url across providers, should dedupe
        {
            "provider": "google_news_rss",
            "url": "https://www.news.cn/sports/2025-12/09/c_123.htm",
            "title": "苏炳添：将在十五运会后退役",
            "summary": "duplicate",
            "source_name": "新华网",
            "source_domain": "news.cn",
        },
    ]
    p2_rows = [
        {
            "provider": "searxng",
            "url": "https://www.people.com.cn/n1/2025/1209/c1234-12345678.html",
            "title": "苏炳添退役专访",
            "summary": "人民网报道",
            "source_name": "人民网",
            "source_domain": "people.com.cn",
        },
        # out-of-whitelist domain should be filtered when whitelist_only=True
        {
            "provider": "searxng",
            "url": "https://example.com/irrelevant",
            "title": "无关条目",
            "summary": "无关",
            "source_name": "Example",
            "source_domain": "example.com",
        },
    ]
    monkeypatch.setattr(
        reporting_mod,
        "_build_search_providers",
        lambda: [("google_news_rss", _StubProvider(p1_rows)), ("searxng", _StubProvider(p2_rows))],
    )

    rows = await reporting_mod.check_external_sources(
        "苏炳添退役了吗",
        whitelist_only=True,
        limit=10,
    )
    assert len(rows) == 2
    domains = sorted([str(r.get("source_domain") or "") for r in rows])
    assert domains == ["news.cn", "people.com.cn"]
    assert all(bool(r.get("domain_allowed")) for r in rows)
    assert all(float(r.get("relevance_score") or 0.0) > 0.0 for r in rows)


@pytest.mark.asyncio
async def test_check_external_sources_entity_gate_filters_irrelevant(monkeypatch):
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_ENABLED",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_MIN_RELEVANCE",
        0.1,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_ENTITY_HIT",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_PER_PROVIDER_LIMIT",
        20,
        raising=False,
    )
    monkeypatch.setattr(
        reporting_mod.settings,
        "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS",
        20,
        raising=False,
    )
    rows = [
        {
            "provider": "bocha_web",
            "url": "https://news.example.com/a",
            "title": "苏炳添宣布退役",
            "summary": "相关",
            "source_name": "example",
            "source_domain": "news.example.com",
        },
        {
            "provider": "bocha_web",
            "url": "https://news.example.com/b",
            "title": "某球队退役球衣",
            "summary": "不含人名实体",
            "source_name": "example",
            "source_domain": "news.example.com",
        },
    ]
    monkeypatch.setattr(
        reporting_mod,
        "_build_search_providers",
        lambda: [("bocha_web", _StubProvider(rows))],
    )
    out = await reporting_mod.check_external_sources(
        "苏炳添退役了吗",
        whitelist_only=False,
        limit=20,
    )
    assert len(out) == 1
    assert "苏炳添" in str(out[0].get("title") or "")
