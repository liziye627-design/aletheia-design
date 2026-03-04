import pytest

from core.config import settings
from services.evidence_linking import link_evidence_to_claims
from services.external.factcheck_client import GoogleFactCheckClient
from services.investigation_claims import analyze_claims, extract_claims
from services.verdict_gate import StrongVerdictGate


def test_verdict_gate_requires_two_high_tier_evidence():
    claims = [{"claim_id": "clm_001", "text": "OpenAI released a new model", "type": "product_release"}]
    claim_links = {
        "clm_001": [
            {
                "evidence_id": "ev_1",
                "source_name": "reuters",
                "source_tier": 2,
                "source_score": 0.82,
                "quality_score": 0.7,
                "confidence": 0.7,
                "stance": "support",
                "validation_status": "reachable",
            }
        ]
    }
    result = StrongVerdictGate().evaluate_all(claims=claims, claim_links=claim_links)
    row = result["claims"][0]
    assert row["gate_passed"] is False
    assert "INSUFFICIENT_HIGH_TIER_EVIDENCE" in row["gate_reasons"]
    assert row["verdict"] == "REVIEW_REQUIRED"


def test_claim_verdict_uncertain_on_conflicting_high_tier():
    claims = [{"claim_id": "clm_001", "text": "Policy was officially approved", "type": "policy_regulation"}]
    claim_links = {
        "clm_001": [
            {
                "evidence_id": "ev_1",
                "source_name": "bbc",
                "source_tier": 2,
                "source_score": 0.82,
                "quality_score": 0.72,
                "confidence": 0.8,
                "stance": "support",
                "validation_status": "reachable",
            },
            {
                "evidence_id": "ev_2",
                "source_name": "guardian",
                "source_tier": 2,
                "source_score": 0.82,
                "quality_score": 0.74,
                "confidence": 0.8,
                "stance": "refute",
                "validation_status": "reachable",
            },
            {
                "evidence_id": "ev_3",
                "source_name": "who",
                "source_tier": 1,
                "source_score": 1.0,
                "quality_score": 0.76,
                "confidence": 0.82,
                "stance": "support",
                "validation_status": "reachable",
            },
        ]
    }
    result = StrongVerdictGate().evaluate_all(claims=claims, claim_links=claim_links)
    row = result["claims"][0]
    assert row["gate_passed"] is False
    assert "CONFLICTING_HIGH_TIER_EVIDENCE" in row["gate_reasons"]
    assert row["verdict"] == "UNCERTAIN"
    assert row["score"] <= 0.59
    assert len(result["review_queue"]) == 1


def test_verdict_gate_allows_supported_when_support_is_dominant_with_limited_high_tier():
    claims = [{"claim_id": "clm_001", "text": "某事件已被确认", "type": "generic_claim"}]
    claim_links = {
        "clm_001": [
            {
                "evidence_id": f"ev_{idx}",
                "source_name": "douyin",
                "source_tier": 3,
                "source_score": 0.48,
                "quality_score": 0.72,
                "confidence": 0.84,
                "stance": "support",
                "validation_status": "reachable",
            }
            for idx in range(1, 9)
        ]
        + [
            {
                "evidence_id": "ev_t2",
                "source_name": "xinhua",
                "source_tier": 2,
                "source_score": 0.82,
                "quality_score": 0.74,
                "confidence": 0.86,
                "stance": "support",
                "validation_status": "reachable",
            }
        ]
    }
    result = StrongVerdictGate().evaluate_all(claims=claims, claim_links=claim_links)
    row = result["claims"][0]
    assert row["verdict"] == "SUPPORTED"
    assert row["gate_passed"] is True
    assert "LIMITED_HIGH_TIER_STRONG_SUPPORT" in row["gate_reasons"]


def test_verdict_gate_allows_supported_when_multi_platform_support_dominates():
    claims = [{"claim_id": "clm_001", "text": "某事件已被确认", "type": "generic_claim"}]
    social_rows = []
    for idx in range(1, 6):
        social_rows.append(
            {
                "evidence_id": f"ev_dy_{idx}",
                "source_name": "douyin",
                "source_tier": 3,
                "source_score": 0.48,
                "quality_score": 0.7,
                "confidence": 0.84,
                "stance": "support",
                "validation_status": "reachable",
            }
        )
    for idx in range(1, 5):
        social_rows.append(
            {
                "evidence_id": f"ev_wb_{idx}",
                "source_name": "weibo",
                "source_tier": 3,
                "source_score": 0.48,
                "quality_score": 0.69,
                "confidence": 0.83,
                "stance": "support",
                "validation_status": "reachable",
            }
        )
    claim_links = {"clm_001": social_rows}
    result = StrongVerdictGate().evaluate_all(claims=claims, claim_links=claim_links)
    row = result["claims"][0]
    assert row["verdict"] == "SUPPORTED"
    assert row["gate_passed"] is True
    assert "LIMITED_HIGH_TIER_STRONG_SUPPORT" in row["gate_reasons"]


def test_uncertain_claim_is_always_enqueued_for_review():
    claims = [{"claim_id": "clm_001", "text": "WHO published new initiative", "type": "public_health"}]
    # gate_passed=True: tier1/2 >=2、平台>=2、且没有support/refute冲突
    claim_links = {
        "clm_001": [
            {
                "evidence_id": "ev_1",
                "source_name": "who",
                "source_tier": 1,
                "source_score": 1.0,
                "quality_score": 0.64,
                "confidence": 0.8,
                "stance": "unclear",
                "validation_status": "reachable",
            },
            {
                "evidence_id": "ev_2",
                "source_name": "reuters",
                "source_tier": 2,
                "source_score": 0.82,
                "quality_score": 0.63,
                "confidence": 0.79,
                "stance": "unclear",
                "validation_status": "reachable",
            },
        ]
    }
    result = StrongVerdictGate().evaluate_all(claims=claims, claim_links=claim_links)
    row = result["claims"][0]
    assert row["gate_passed"] is True
    assert row["verdict"] == "UNCERTAIN"
    assert row["score"] <= 0.59
    assert len(result["review_queue"]) == 1
    assert result["review_queue"][0]["claim_id"] == "clm_001"


@pytest.mark.asyncio
async def test_factcheck_client_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "FACTCHECK_ENABLE", True, raising=False)
    monkeypatch.setattr(settings, "GOOGLE_FACTCHECK_API_KEY", "", raising=False)
    client = GoogleFactCheckClient()
    payload = await client.search_claim("test claim")
    assert payload["available"] is False
    assert payload["reason"] in {"FACTCHECK_UNAVAILABLE", "FACTCHECK_DISABLED"}
    assert payload["items"] == []


def test_claim_evidence_linking_outputs_stance_summary():
    claim = "WHO officially announced new guidance"
    claims = extract_claims(claim, keyword="who guidance", max_claims=3)
    evidence_registry = [
        {
            "id": "ev_1",
            "source_name": "who",
            "url": "https://www.who.int/news/item/2026-01-01-test",
            "snippet": "WHO officially announced updated guidance for member states",
            "validation_status": "reachable",
            "confidence": 0.78,
        },
        {
            "id": "ev_2",
            "source_name": "bbc",
            "url": "https://www.bbc.com/news/world-123",
            "snippet": "Analysts said the claim is false and has been debunked",
            "validation_status": "reachable",
            "confidence": 0.73,
        },
    ]
    links, summary = link_evidence_to_claims(claims, evidence_registry)
    assert "clm_001" in links
    stances = {row["stance"] for row in links["clm_001"]}
    assert "support" in stances or "refute" in stances
    assert summary["tier1_count"] >= 1
    assert all("stage1_score" in row and "stage2_score" in row for row in links["clm_001"])


def test_evidence_linking_two_stage_rerank_filters_low_relevance_noise():
    claims = extract_claims("WHO global health initiative announced", keyword="WHO global health initiative", max_claims=3)
    evidence_registry = [
        {
            "id": "ev_relevant",
            "source_name": "who",
            "url": "https://www.who.int/news/item/2026-01-01-test",
            "snippet": "WHO announced a new global health initiative and policy package",
            "validation_status": "reachable",
            "confidence": 0.8,
        },
        {
            "id": "ev_noise",
            "source_name": "community_forum",
            "url": "https://example.org/post/abc",
            "snippet": "random local sports festival and ticket sale notice",
            "validation_status": "reachable",
            "confidence": 0.7,
        },
    ]
    links, _ = link_evidence_to_claims(claims, evidence_registry, min_relevance=0.2)
    rows = links["clm_001"]
    ids = [row["evidence_id"] for row in rows]
    assert "ev_relevant" in ids
    assert "ev_noise" not in ids


def test_evidence_linking_handles_chinese_question_claim_and_retirement_stance():
    claims = extract_claims("苏炳添退役了吗？", keyword="苏炳添 退役", max_claims=1)
    evidence_registry = [
        {
            "id": "ev_retire_support",
            "source_name": "xinhua",
            "url": "https://www.news.cn/sports/2026-02-25/retire.html",
            "snippet": "苏炳添宣布退役，并发布退役声明感谢支持者。",
            "validation_status": "reachable",
            "confidence": 0.86,
        },
        {
            "id": "ev_irrelevant",
            "source_name": "reuters",
            "url": "https://www.reuters.com/world/test",
            "snippet": "Global macro policy update unrelated to sports.",
            "validation_status": "reachable",
            "confidence": 0.72,
        },
    ]
    links, _ = link_evidence_to_claims(claims, evidence_registry, min_relevance=0.2)
    rows = links["clm_001"]
    ids = {row["evidence_id"] for row in rows}
    assert "ev_retire_support" in ids
    support = [row for row in rows if row["evidence_id"] == "ev_retire_support"]
    assert support
    assert support[0]["stance"] in {"support", "mixed"}
    assert "ev_irrelevant" not in ids


@pytest.mark.asyncio
async def test_claim_verdict_uses_primary_only(monkeypatch):
    monkeypatch.setattr(settings, "FACTCHECK_ENABLE", False, raising=False)
    monkeypatch.setattr(settings, "INVESTIGATION_CLAIM_REASONING_ENABLE_LLM", False, raising=False)
    monkeypatch.setattr(settings, "INVESTIGATION_CLAIM_MAX_CLAIMS", 1, raising=False)

    result = await analyze_claims(
        primary_claim="官方已经确认事件为真",
        keyword="官方 确认 事件",
        source_plan={"excluded_platforms": ["forum"]},
        evidence_registry=[
            {
                "id": "ev_primary",
                "source_name": "reuters",
                "source_tier": 2,
                "url": "https://reuters.com/a",
                "snippet": "official statement confirms the claim",
                "validation_status": "reachable",
                "relevance_score": 0.72,
                "keyword_match": True,
                "evidence_class": "primary",
                "confidence": 0.86,
            },
            {
                "id": "ev_background",
                "source_name": "forum",
                "source_tier": 3,
                "url": "https://forum.invalid/post",
                "snippet": "this claim is false and fabricated",
                "validation_status": "reachable",
                "relevance_score": 0.88,
                "keyword_match": True,
                "evidence_class": "background",
                "confidence": 0.4,
            },
        ],
    )

    claim = (result.get("claims") or [])[0]
    linked_ids = {row.get("evidence_id") for row in claim.get("linked_evidence") or []}
    assert "ev_primary" in linked_ids
    assert "ev_background" not in linked_ids


@pytest.mark.asyncio
async def test_claim_reasoning_always_returns_citations_or_review_queue(monkeypatch):
    monkeypatch.setattr(settings, "FACTCHECK_ENABLE", False, raising=False)
    monkeypatch.setattr(settings, "INVESTIGATION_CLAIM_REASONING_ENABLE_LLM", False, raising=False)
    monkeypatch.setattr(settings, "INVESTIGATION_CLAIM_MAX_CLAIMS", 1, raising=False)

    result = await analyze_claims(
        primary_claim="某主张成立",
        keyword="某主张",
        source_plan={},
        evidence_registry=[
            {
                "id": "ev_1",
                "source_name": "xinhua",
                "source_tier": 1,
                "url": "",
                "snippet": "相关内容存在，但无可追溯链接",
                "validation_status": "reachable",
                "relevance_score": 0.75,
                "keyword_match": True,
                "evidence_class": "primary",
                "confidence": 0.82,
            }
        ],
    )

    rows = result.get("claim_reasoning") or []
    assert rows
    citations = list(rows[0].get("citations") or [])
    if citations:
        assert any(str(c.get("url") or "").startswith("http") for c in citations)
    else:
        queue = result.get("review_queue") or []
        assert any("INSUFFICIENT_CITED_EVIDENCE" in (item.get("reasons") or []) for item in queue)
