import pytest
from fastapi import HTTPException

from api.v1.endpoints.investigations import InvestigationRunRequest, run_investigation
from services import investigation_preview as preview_module


class _FakeCrawlerManager:
    def __init__(self):
        self.crawlers = {
            "xinhua": object(),
            "reuters": object(),
            "bbc": object(),
            "weibo": object(),
            "zhihu": object(),
            "who": object(),
        }

    def get_platform_health_snapshot(self):
        return {
            "xinhua": {"health_score": 0.95},
            "reuters": {"health_score": 0.9},
            "bbc": {"health_score": 0.88},
            "weibo": {"health_score": 0.82},
            "zhihu": {"health_score": 0.76},
            "who": {"health_score": 0.92},
        }

    def get_platform_source_matrix(self):
        return {}

    def get_source_profile_platforms(self, profile="stable_mixed_v1"):
        _ = profile
        return ["xinhua", "reuters", "bbc", "weibo"]


class _FakePreviewLLM:
    async def summarize_intent_preview(self, **kwargs):
        _ = kwargs
        return "本次预分析将围绕核心主张进行核验，优先官方与主流媒体，防止跨域噪声干扰。"


@pytest.mark.asyncio
async def test_preview_builds_claims_source_plan_without_crawler(monkeypatch):
    monkeypatch.setattr(preview_module, "get_crawler_manager", lambda: _FakeCrawlerManager())
    monkeypatch.setattr(preview_module, "get_siliconflow_client", lambda: _FakePreviewLLM())

    result = await preview_module.build_preview(
        {
            "claim": "苏炳添退役了，官方是否确认？",
            "keyword": "苏炳添 退役",
            "platforms": ["xinhua", "reuters", "bbc", "weibo", "zhihu"],
            "source_strategy": "auto",
        }
    )

    assert result["status"] == "ready"
    assert isinstance(result.get("claims_draft"), list)
    assert len(result["claims_draft"]) >= 1
    assert isinstance(result.get("source_plan"), dict)
    assert result["source_plan"]["plan_version"] == "auto_v2_precision"
    assert len(result["source_plan"].get("selected_platforms") or []) >= 1
    assert isinstance(result.get("intent_summary"), str) and result["intent_summary"].strip()
    assert len(result["intent_summary"]) >= 160
    assert len(result["intent_summary"]) <= 260


@pytest.mark.asyncio
async def test_preview_fallback_when_llm_timeout(monkeypatch):
    class _BrokenPreviewLLM:
        async def summarize_intent_preview(self, **kwargs):
            _ = kwargs
            raise TimeoutError("forced-timeout")

    monkeypatch.setattr(preview_module, "get_crawler_manager", lambda: _FakeCrawlerManager())
    monkeypatch.setattr(preview_module, "get_siliconflow_client", lambda: _BrokenPreviewLLM())

    result = await preview_module.build_preview(
        {
            "claim": "某公共卫生事件是否属实？",
            "keyword": "public health alert",
            "platforms": ["who", "reuters", "bbc"],
            "source_strategy": "auto",
        }
    )

    assert result["status"] == "degraded"
    assert str(result.get("fallback_reason") or "").startswith("PREVIEW_LLM_UNAVAILABLE")
    assert isinstance(result.get("intent_summary"), str) and result["intent_summary"].strip()
    assert len(result["intent_summary"]) >= 160
    assert len(result["intent_summary"]) <= 260


@pytest.mark.asyncio
async def test_preview_summary_is_trimmed_when_llm_output_too_long(monkeypatch):
    class _VerbosePreviewLLM:
        async def summarize_intent_preview(self, **kwargs):
            _ = kwargs
            return "这是一段超长预分析文本。" * 40

    monkeypatch.setattr(preview_module, "get_crawler_manager", lambda: _FakeCrawlerManager())
    monkeypatch.setattr(preview_module, "get_siliconflow_client", lambda: _VerbosePreviewLLM())

    result = await preview_module.build_preview(
        {
            "claim": "苏炳添退役是否有权威确认？",
            "keyword": "苏炳添 退役",
            "platforms": ["xinhua", "weibo", "zhihu"],
            "source_strategy": "auto",
        }
    )

    assert result["status"] == "ready"
    assert len(result["intent_summary"]) <= 260


@pytest.mark.asyncio
async def test_run_rejects_expired_preview_id(monkeypatch):
    class _FakeManager:
        def get_preview(self, preview_id):
            _ = preview_id
            return None

    class _FakeOrchestrator:
        async def execute(self, **kwargs):
            _ = kwargs
            return None

    monkeypatch.setattr(
        "api.v1.endpoints.investigations.get_investigation_manager",
        lambda: _FakeManager(),
    )
    monkeypatch.setattr(
        "api.v1.endpoints.investigations.get_investigation_orchestrator",
        lambda: _FakeOrchestrator(),
    )

    with pytest.raises(HTTPException) as exc:
        await run_investigation(
            InvestigationRunRequest(
                claim="test claim",
                confirmed_preview_id="preview_expired_1",
            )
        )
    assert exc.value.status_code == 422
    assert str(exc.value.detail) == "PREVIEW_EXPIRED"


@pytest.mark.asyncio
async def test_run_applies_confirmed_claims_and_platforms(monkeypatch):
    class _FakeManager:
        def __init__(self):
            self.preview_confirmed = []
            self.created_payload = None

        def get_preview(self, preview_id):
            return {
                "preview_id": preview_id,
                "created_at": "2026-02-25T10:00:00",
                "expires_at": "2026-02-25T10:30:00",
                "status": "ready",
            }

        def mark_preview_confirmed(self, preview_id):
            self.preview_confirmed.append(preview_id)

        async def create_run(self, payload):
            self.created_payload = payload
            return {
                "run_id": "run_test_preview_apply",
                "accepted_at": "2026-02-25T10:01:00",
                "status": "queued",
                "request": payload,
            }

    class _FakeOrchestrator:
        async def execute(self, **kwargs):
            _ = kwargs
            return None

    fake_manager = _FakeManager()
    monkeypatch.setattr(
        "api.v1.endpoints.investigations.get_investigation_manager",
        lambda: fake_manager,
    )
    monkeypatch.setattr(
        "api.v1.endpoints.investigations.get_investigation_orchestrator",
        lambda: _FakeOrchestrator(),
    )

    response = await run_investigation(
        InvestigationRunRequest(
            claim="old claim",
            platforms=["bbc"],
            confirmed_preview_id="preview_valid_1",
            confirmed_claims=["claim one", "claim two"],
            confirmed_platforms=["xinhua", "reuters"],
        )
    )

    assert response.run_id == "run_test_preview_apply"
    assert fake_manager.preview_confirmed == ["preview_valid_1"]
    assert fake_manager.created_payload["claim"] == "claim one\nclaim two"
    assert fake_manager.created_payload["platforms"] == ["xinhua", "reuters"]
    assert fake_manager.created_payload["preview_context"]["preview_id"] == "preview_valid_1"
