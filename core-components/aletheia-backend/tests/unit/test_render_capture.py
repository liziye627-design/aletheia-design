import time
import pytest

from services.layer1_perception.agents.render_capture import (
    NetworkTracker,
    wait_for_network_quiet,
    extract_schema_fields,
)


class FakeNode:
    def __init__(self, text: str = "", html: str = "", attrs=None):
        self._text = text
        self._html = html
        self._attrs = attrs or {}

    async def inner_text(self):
        return self._text

    async def inner_html(self):
        return self._html

    async def get_attribute(self, name: str):
        return self._attrs.get(name)


class FakeLocator:
    def __init__(self, nodes):
        self._nodes = nodes

    async def count(self):
        return len(self._nodes)

    def nth(self, idx: int):
        return self._nodes[idx]


class FakePage:
    def __init__(self, by_selector):
        self._by_selector = by_selector

    def locator(self, selector: str):
        return FakeLocator(self._by_selector.get(selector, []))


@pytest.mark.asyncio
async def test_wait_for_network_quiet_true_when_idle_and_quiet_enough():
    tracker = NetworkTracker(inflight=0, last_activity=time.monotonic() - 1.0, requests_seen=4)
    ok = await wait_for_network_quiet(tracker, quiet_ms=100, timeout_ms=300)
    assert ok is True


@pytest.mark.asyncio
async def test_wait_for_network_quiet_false_on_timeout():
    tracker = NetworkTracker(inflight=1, last_activity=time.monotonic(), requests_seen=2)
    ok = await wait_for_network_quiet(tracker, quiet_ms=50, timeout_ms=150)
    assert ok is False


@pytest.mark.asyncio
async def test_extract_schema_fields_supports_text_attr_html_and_many():
    page = FakePage(
        {
            "h1": [FakeNode(text="  Title A  ")],
            "a.link": [
                FakeNode(attrs={"href": "https://a.example"}),
                FakeNode(attrs={"href": "https://b.example"}),
            ],
            "div.rich": [FakeNode(html="<b>Hello</b>")],
        }
    )
    schema = {
        "title": {"selector": "h1", "mode": "text"},
        "links": {"selector": "a.link", "mode": "attr", "attr": "href", "many": True},
        "rich": {"selector": "div.rich", "mode": "html"},
        "missing": {"selector": "span.none", "mode": "text"},
        "bad": {"selector": "", "mode": "text"},
    }

    out = await extract_schema_fields(page, schema)

    assert out["title"] == "Title A"
    assert out["links"] == ["https://a.example", "https://b.example"]
    assert out["rich"] == "<b>Hello</b>"
    assert out["missing"] is None
    assert out["bad"] is None
