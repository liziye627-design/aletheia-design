import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.v1.endpoints import multiplatform


class FakeBrowserAgent:
    init_calls = []
    capture_calls = []
    fail = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeBrowserAgent.init_calls.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def capture_rendered_page(self, **kwargs):
        FakeBrowserAgent.capture_calls.append(kwargs)
        if FakeBrowserAgent.fail:
            raise RuntimeError("boom")
        return {
            "success": True,
            "url": kwargs["url"],
            "diagnostics": {"dom_stable": True},
            "fields": {"title": "ok"},
            "visible_text": "txt",
            "visible_text_truncated": False,
            "html": "<html></html>",
            "html_truncated": False,
            "api_responses": [],
            "captured_at": "2026-02-23T00:00:00+00:00",
        }


@pytest.mark.asyncio
async def test_playwright_rendered_extract_success(monkeypatch):
    FakeBrowserAgent.fail = False
    FakeBrowserAgent.init_calls.clear()
    FakeBrowserAgent.capture_calls.clear()
    monkeypatch.setattr(multiplatform, "BrowserAgent", FakeBrowserAgent)

    req = multiplatform.PlaywrightRenderedExtractRequest(
        url="https://example.com",
        critical_selector="h1",
        schema={"title": {"selector": "h1", "mode": "text"}},
        api_url_keyword="api",
        headless=True,
        storage_state_path="/tmp/state.json",
    )

    payload = await multiplatform.playwright_rendered_extract(req)

    assert payload["success"] is True
    assert payload["url"] == "https://example.com"
    assert FakeBrowserAgent.init_calls[-1]["headless"] is True
    assert FakeBrowserAgent.init_calls[-1]["storage_state_path"] == "/tmp/state.json"
    assert FakeBrowserAgent.capture_calls[-1]["critical_selector"] == "h1"
    assert FakeBrowserAgent.capture_calls[-1]["schema"]["title"]["selector"] == "h1"


@pytest.mark.asyncio
async def test_playwright_rendered_extract_failure_returns_http_500(monkeypatch):
    FakeBrowserAgent.fail = True
    FakeBrowserAgent.init_calls.clear()
    FakeBrowserAgent.capture_calls.clear()
    monkeypatch.setattr(multiplatform, "BrowserAgent", FakeBrowserAgent)

    req = multiplatform.PlaywrightRenderedExtractRequest(url="https://example.com")

    with pytest.raises(HTTPException) as exc_info:
        await multiplatform.playwright_rendered_extract(req)

    assert exc_info.value.status_code == 500
    assert "Playwright rendered extract failed" in str(exc_info.value.detail)


def test_playwright_rendered_extract_request_rejects_non_http_url():
    with pytest.raises(ValidationError):
        multiplatform.PlaywrightRenderedExtractRequest(url="ftp://example.com")


def test_playwright_rendered_extract_request_rejects_bad_schema_shape():
    with pytest.raises(ValidationError):
        multiplatform.PlaywrightRenderedExtractRequest(
            url="https://example.com",
            schema={"title": "not-object"},
        )
