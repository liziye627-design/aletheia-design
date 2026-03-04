from services.investigation_reporting import build_report_sections


def test_build_report_sections_prioritizes_primary_evidence_lines():
    template = {
        "sections": [
            {"id": "summary", "title": "摘要", "markdown": ""},
            {"id": "evidence", "title": "证据清单", "markdown": ""},
        ]
    }
    evidence_registry = [
        {
            "id": "bg_1",
            "source_name": "weibo",
            "source_tier": 3,
            "relevance_score": 0.9,
            "credibility_score": 0.4,
            "evidence_origin": "external",
            "evidence_class": "background",
            "snippet": "背景信息",
            "published_at": "2026-03-01T10:00:00",
            "retrieval_mode": "weibo_public_search",
        },
        {
            "id": "ev_1",
            "source_name": "xinhua",
            "source_tier": 1,
            "relevance_score": 0.6,
            "credibility_score": 0.9,
            "evidence_origin": "external",
            "evidence_class": "primary",
            "snippet": "核心证据",
            "published_at": "2026-03-01T11:00:00",
            "retrieval_mode": "external_search",
        },
    ]
    sections = build_report_sections(
        template=template,
        keyword="苏炳添退役",
        enhanced={"reasoning_chain": {"final_score": 0.7, "final_level": "LIKELY_TRUE"}},
        credibility={"credibility_score": 0.8},
        multi_agent={"recommendation": "ok"},
        evidence_registry=evidence_registry,
        steps=[],
        source_trace={},
        opinion_monitoring={},
    )
    evidence_section = next(s for s in sections if s.get("id") == "evidence")
    lines = [x for x in str(evidence_section.get("content_markdown") or "").splitlines() if x.startswith("- [")]
    assert lines
    assert lines[0].startswith("- [EVIDENCE]")
    assert "xinhua" in lines[0].lower()
