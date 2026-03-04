from services.search_sources_config import get_search_sources_registry


def test_search_sources_registry_loads_enabled_sources():
    registry = get_search_sources_registry()
    assert registry is not None
    rows = registry.get_enabled_sources()
    assert rows
    platforms = {str(r.get("platform") or "") for r in rows}
    assert "weibo" in platforms
    assert "xinhua" in platforms


def test_search_sources_registry_filters_platform_rows():
    registry = get_search_sources_registry()
    assert registry is not None
    weibo_rows = registry.get_sources_for_platform("weibo")
    assert weibo_rows
    assert all(str(r.get("platform") or "") == "weibo" for r in weibo_rows)
