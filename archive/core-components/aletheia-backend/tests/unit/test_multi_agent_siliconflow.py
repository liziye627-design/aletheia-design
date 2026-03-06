import pytest

from services.multi_agent_siliconflow import MultiAgentSiliconFlowProcessor


def test_no_data_reason_code_network_unreachable():
    processor = MultiAgentSiliconFlowProcessor()
    reason = processor._infer_no_data_reason_code(
        {
            "bbc": ["Temporary failure in name resolution"],
            "guardian": ["request timeout"],
            "reuters": ["proxy connect failed 127.0.0.1:7897"],
        }
    )
    assert reason == "NETWORK_UNREACHABLE"


def test_no_data_reason_code_insufficient_evidence():
    processor = MultiAgentSiliconFlowProcessor()
    reason = processor._infer_no_data_reason_code(
        {"bbc": ["crawler_empty"], "guardian": ["non_specific_url"]}
    )
    assert reason == "INSUFFICIENT_EVIDENCE"

@pytest.mark.asyncio
async def test_claim_reasoning_schema_contains_citations():
    processor = MultiAgentSiliconFlowProcessor()

    async def _fake_reasoning(**kwargs):
        claim_row = kwargs.get("claim_row") or {}
        return {
            "claim_id": claim_row.get("claim_id"),
            "conclusion_text": "结论：UNCERTAIN。",
            "risk_text": "风险：INSUFFICIENT_SIGNAL_SEPARATION。",
            "reasoning_steps": ["step1", "step2"],
            "citations": [
                {
                    "evidence_id": "ev_1",
                    "url": "https://example.com/a",
                    "source_name": "bbc",
                    "source_tier": 2,
                    "stance": "unclear",
                    "snippet_quote": "example quote",
                }
            ],
            "fallback": False,
        }

    processor.llm.summarize_claim_reasoning = _fake_reasoning  # type: ignore[assignment]
    rows = await processor.build_claim_reasoning_with_citations(
        keyword="test",
        claims=[
            {
                "claim_id": "clm_001",
                "verdict": "UNCERTAIN",
                "linked_evidence": [{"evidence_id": "ev_1", "url": "https://example.com/a"}],
            }
        ],
    )
    assert len(rows) == 1
    assert rows[0]["claim_id"] == "clm_001"
    assert isinstance(rows[0].get("citations"), list) and rows[0]["citations"]
    assert rows[0]["citations"][0]["url"].startswith("https://")


@pytest.mark.asyncio
async def test_claim_reasoning_fallback_when_llm_timeout():
    processor = MultiAgentSiliconFlowProcessor()

    async def _raise_reasoning(**kwargs):
        raise TimeoutError("timeout")

    processor.llm.summarize_claim_reasoning = _raise_reasoning  # type: ignore[assignment]
    rows = await processor.build_claim_reasoning_with_citations(
        keyword="test",
        claims=[
            {
                "claim_id": "clm_001",
                "verdict": "REVIEW_REQUIRED",
                "gate_reasons": ["INSUFFICIENT_HIGH_TIER_EVIDENCE"],
                "linked_evidence": [
                    {
                        "evidence_id": "ev_1",
                        "url": "https://example.com/a",
                        "source_name": "reuters",
                        "source_tier": 2,
                        "stance": "unclear",
                        "snippet": "fallback snippet",
                    }
                ],
            }
        ],
    )
    assert len(rows) == 1
    assert rows[0]["fallback"] is True
    assert rows[0]["citations"][0]["evidence_id"] == "ev_1"
