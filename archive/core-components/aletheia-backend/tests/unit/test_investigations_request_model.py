from pydantic import ValidationError

from api.v1.endpoints.investigations import InvestigationRunRequest


def test_investigation_request_allows_lower_target_threshold():
    req = InvestigationRunRequest(claim="test claim", target_valid_evidence_min=20)
    assert req.target_valid_evidence_min == 20


def test_investigation_request_rejects_too_low_target_threshold():
    try:
        InvestigationRunRequest(claim="test claim", target_valid_evidence_min=9)
        assert False, "expected validation error"
    except ValidationError as exc:
        assert "target_valid_evidence_min" in str(exc)


def test_investigation_request_accepts_mediacrawler_fields():
    req = InvestigationRunRequest(
        claim="test claim",
        use_mediacrawler=True,
        mediacrawler_platforms=["weibo", "xiaohongshu"],
        mediacrawler_timeout_sec=120,
    )
    assert req.use_mediacrawler is True
    assert req.mediacrawler_platforms == ["weibo", "xiaohongshu"]
    assert req.mediacrawler_timeout_sec == 120


def test_investigation_request_accepts_confirmed_preview_fields():
    req = InvestigationRunRequest(
        claim="test claim",
        confirmed_preview_id="preview_123456",
        confirmed_claims=["claim a", "claim b"],
        confirmed_platforms=["xinhua", "reuters"],
    )
    assert req.confirmed_preview_id == "preview_123456"
    assert req.confirmed_claims == ["claim a", "claim b"]
    assert req.confirmed_platforms == ["xinhua", "reuters"]
