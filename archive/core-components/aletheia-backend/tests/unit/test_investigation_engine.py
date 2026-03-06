from core.config import settings
from services.investigation_engine import InvestigationOrchestrator, InvestigationRunManager


def test_dual_profile_score_clamped_on_insufficient_evidence():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    result = orchestrator._build_dual_profile_result(
        enhanced_score=0.9,
        cross_score=0.85,
        agent_score=0.88,
        score_breakdown={
            "platform_coverage_score": 0.95,
            "evidence_specificity_score": 0.9,
            "model_consensus_score": 0.86,
        },
        insufficient=True,
    )
    assert result["tob_result"]["score"] <= 0.45
    assert result["tog_result"]["score"] <= 0.45


def test_dual_profile_score_normal_mode():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    result = orchestrator._build_dual_profile_result(
        enhanced_score=0.65,
        cross_score=0.6,
        agent_score=0.7,
        score_breakdown={
            "platform_coverage_score": 0.7,
            "evidence_specificity_score": 0.5,
            "model_consensus_score": 0.6,
        },
        insufficient=False,
    )
    assert 0.0 <= result["tob_result"]["score"] <= 1.0
    assert 0.0 <= result["tog_result"]["score"] <= 1.0
    assert result["combined_result"]["level"] in {
        "VERIFIED",
        "LIKELY_TRUE",
        "UNCERTAIN",
        "LIKELY_FALSE",
        "FALSE",
    }


def test_quality_summary_contains_required_fields():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    quality = orchestrator._build_quality_summary(
        valid_cards=[
            {
                "url": "https://news.cn/politics/2026-01/01/c_111111.htm",
                "keyword_match": True,
                "validation_status": "reachable",
            },
            {
                "url": "https://www.reuters.com/world/test-article",
                "keyword_match": True,
                "validation_status": "reachable",
            },
        ],
        raw_collected_count=10,
        invalid_count=2,
    )
    assert set(quality.keys()) == {
        "keyword_match_ratio",
        "reachable_ratio",
        "specific_url_ratio",
        "domain_diversity",
        "invalid_evidence_ratio",
    }
    assert quality["keyword_match_ratio"] == 1.0
    assert quality["reachable_ratio"] == 1.0
    assert quality["domain_diversity"] >= 2


def test_validated_candidates_filters_bad_items():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    out = orchestrator._build_validated_candidates(
        keyword="gpt model",
        search_data={
            "news": [
                {
                    "url": "https://news.cn/politics/2026-01/01/c_111111.htm",
                    "title": "GPT model release note",
                    "content": "gpt model details",
                    "metadata": {"keyword_match": True},
                },
                {
                    "url": "https://news.cn/search?q=gpt",
                    "title": "search page",
                    "content": "gpt",
                    "metadata": {"keyword_match": True},
                },
            ]
        },
        allowed_domains={"news.cn"},
        quality_mode="strict",
        reachability_map={
            "https://news.cn/politics/2026-01/01/c_111111.htm": {
                "reachable": True,
                "reason": "OK",
            },
            "https://news.cn/search?q=gpt": {
                "reachable": True,
                "reason": "OK",
            },
        },
    )
    assert len(out["valid_items"]) == 1
    assert out["valid_items"][0]["url"] == "https://news.cn/politics/2026-01/01/c_111111.htm"
    assert out["reason_counter"]["NON_SPECIFIC_URL"] >= 1


def test_validated_candidates_extracts_url_from_original_and_metadata_source_url():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    out = orchestrator._build_validated_candidates(
        keyword="who update",
        search_data={
            "bbc": [
                {
                    "original_url": "https://www.bbc.com/news/world-123456",
                    "title": "WHO update bulletin",
                    "content": "who update",
                    "metadata": {"keyword_match": True},
                }
            ],
            "xinhua": [
                {
                    "title": "WHO update from xinhua",
                    "content": "who update",
                    "metadata": {
                        "keyword_match": True,
                        "source_url": "https://www.news.cn/world/2026-01/01/c_123456.htm",
                    },
                }
            ],
        },
        allowed_domains={"bbc.com", "news.cn"},
        quality_mode="balanced",
        reachability_map={},
    )
    urls = {row["url"] for row in out["valid_items"]}
    assert "https://www.bbc.com/news/world-123456" in urls
    assert "https://www.news.cn/world/2026-01/01/c_123456.htm" in urls
    assert len(out["valid_items"]) == 2


def test_interleave_rows_by_platform_respects_relevance_desc_mode(monkeypatch):
    monkeypatch.setattr(settings, "INVESTIGATION_EVIDENCE_ORDER_MODE", "relevance_desc")
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    out = orchestrator._interleave_rows_by_platform(
        rows=[
            {"platform": "a", "relevance_score": 0.31},
            {"platform": "b", "relevance_score": 0.91},
            {"platform": "a", "relevance_score": 0.81},
            {"platform": "b", "relevance_score": 0.11},
        ]
    )
    scores = [float(row.get("relevance_score") or 0.0) for row in out]
    assert scores == sorted(scores, reverse=True)


def test_staged_validation_keeps_trusted_hot_fallback_as_provisional():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    out = orchestrator._build_staged_validated_candidates(
        keyword="gpt model",
        search_data={
            "xinhua": [
                {
                    "url": "https://news.cn/world/2026-01/01/c_123456.htm",
                    "title": "GPT model progress",
                    "content": "gpt model details",
                    "metadata": {
                        "keyword_match": True,
                        "retrieval_mode": "hot_fallback",
                    },
                }
            ]
        },
        allowed_domains={"news.cn"},
        candidate_top_n=20,
        final_top_m=10,
        reachability_map={},
    )
    assert len(out["valid_items"]) >= 1
    assert any(bool(row.get("provisional")) for row in out["valid_items"])


def test_staged_validation_respects_low_relevance_floor(monkeypatch):
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_THRESHOLD_STRICT", 0.15)
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_THRESHOLD_BALANCED", 0.08)
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_FLOOR", 0.0)
    monkeypatch.setattr(settings, "INVESTIGATION_ALLOW_LOW_RELEVANCE_RESCUE", True)
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    query = "苏炳添 甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
    rows = []
    for idx in range(8):
        rows.append(
            {
                "url": f"https://news.cn/world/2026-01/{idx+1:02d}/c_123456.htm",
                "title": f"苏炳添近况通稿 {idx}",
                "content": "苏炳添 赛后采访",
                "metadata": {
                    "keyword_match": False,
                    "retrieval_mode": "hot_fallback",
                },
            }
        )
    out = orchestrator._build_staged_validated_candidates(
        keyword=query,
        search_data={"xinhua": rows},
        allowed_domains={"news.cn"},
        candidate_top_n=20,
        final_top_m=50,
        reachability_map={},
        min_low_relevance_accept=5,
    )
    assert len(out["valid_items"]) >= 5
    assert any(row.get("low_relevance_fallback") for row in out["valid_items"])


def test_staged_validation_balances_low_relevance_fallback_across_platforms(monkeypatch):
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_THRESHOLD_STRICT", 0.15)
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_THRESHOLD_BALANCED", 0.08)
    monkeypatch.setattr(settings, "INVESTIGATION_RELEVANCE_FLOOR", 0.0)
    monkeypatch.setattr(settings, "INVESTIGATION_ALLOW_LOW_RELEVANCE_RESCUE", True)
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    query = "苏炳添 甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
    search_data = {
        "xinhua": [
            {
                "url": f"https://news.cn/world/2026-01/{idx+1:02d}/c_111111.htm",
                "title": f"苏炳添相关通稿 {idx}",
                "content": "苏炳添 训练",
                "metadata": {"keyword_match": False, "retrieval_mode": "hot_fallback"},
            }
            for idx in range(4)
        ],
        "who": [
            {
                "url": f"https://www.who.int/news/item/2026-01-{idx+1:02d}-sample",
                "title": f"WHO mention 苏炳添 {idx}",
                "content": "苏炳添 采访",
                "metadata": {
                    "keyword_match": False,
                    "retrieval_mode": "rss_emergency_fallback",
                },
            }
            for idx in range(4)
        ],
        "reuters": [
            {
                "url": f"https://www.reuters.com/world/sample-{idx+1}",
                "title": f"Reuters mention 苏炳添 {idx}",
                "content": "苏炳添 赛场",
                "metadata": {"keyword_match": False, "retrieval_mode": "hot_fallback"},
            }
            for idx in range(4)
        ],
    }
    out = orchestrator._build_staged_validated_candidates(
        keyword=query,
        search_data=search_data,
        allowed_domains={"news.cn", "who.int", "reuters.com"},
        candidate_top_n=50,
        final_top_m=12,
        reachability_map={},
        min_low_relevance_accept=6,
    )
    valid = out["valid_items"]
    selected_platforms = {str(row.get("platform") or "unknown") for row in valid}
    assert len(valid) >= 6
    assert len(selected_platforms) >= 2
    assert any(row.get("low_relevance_fallback") for row in valid)


def test_staged_validation_blocks_rows_without_entity_match():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    rows = [
        {
            "url": "https://news.cn/world/2026-01/01/c_999999.htm",
            "title": "generic bulletin",
            "content": "completely unrelated content",
            "metadata": {"keyword_match": False, "retrieval_mode": "hot_fallback"},
        }
    ]
    out = orchestrator._build_staged_validated_candidates(
        keyword="苏炳添退役了吗",
        search_data={"xinhua": rows},
        allowed_domains={"news.cn"},
        candidate_top_n=20,
        final_top_m=10,
        reachability_map={},
        min_low_relevance_accept=3,
    )
    assert len(out["valid_items"]) == 0
    assert int((out.get("reason_counter") or {}).get("ENTITY_GATE_MISS", 0)) >= 1


def test_result_status_partial_when_live_below_target():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    status = orchestrator._determine_result_status(
        multi_agent_status="complete",
        valid_evidence_count=60,
        target_valid_evidence_min=50,
        live_evidence_count=4,
        live_evidence_target=10,
        platforms_with_data=6,
        min_platforms_with_data=5,
        steps=[{"status": "success"}],
    )
    assert status == "partial"


def test_result_status_insufficient_when_platform_coverage_low():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    status = orchestrator._determine_result_status(
        multi_agent_status="complete",
        valid_evidence_count=60,
        target_valid_evidence_min=50,
        live_evidence_count=12,
        live_evidence_target=10,
        platforms_with_data=3,
        min_platforms_with_data=5,
        steps=[{"status": "success"}],
    )
    assert status == "insufficient_evidence"


def test_result_status_complete_when_all_thresholds_met():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    status = orchestrator._determine_result_status(
        multi_agent_status="complete",
        valid_evidence_count=60,
        target_valid_evidence_min=50,
        live_evidence_count=12,
        live_evidence_target=10,
        platforms_with_data=6,
        min_platforms_with_data=5,
        steps=[{"status": "success"}],
    )
    assert status == "complete"


def test_step_summaries_include_links_and_codes_for_core_steps():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    result = {
        "steps": [
            {"id": "multiplatform_search", "status": "partial"},
            {"id": "claim_analysis", "status": "success"},
            {"id": "report_template_render", "status": "success"},
        ],
        "status": "partial",
        "acquisition_report": {
            "valid_evidence_count": 11,
            "raw_collected_count": 46,
            "live_evidence_count": 8,
            "cached_evidence_count": 3,
            "platforms_with_data": 4,
            "platform_reason_stats": {
                "by_reason": {"CRAWLER_TIMEOUT": 2, "LOW_RELEVANCE": 6}
            },
        },
        "quality_summary": {"keyword_match_ratio": 0.76, "reachable_ratio": 0.88},
        "evidence_registry": [
            {
                "id": "ev_1",
                "source_name": "reuters",
                "url": "https://www.reuters.com/world/test-story",
                "snippet": "Reuters test snippet",
                "retrieval_mode": "live",
            }
        ],
        "claim_analysis": {
            "claims": [
                {
                    "claim_id": "clm_001",
                    "text": "test claim",
                    "gate_reasons": ["INSUFFICIENT_HIGH_TIER_EVIDENCE"],
                    "linked_evidence": [
                        {
                            "source_name": "who",
                            "url": "https://www.who.int/news-room/test",
                            "snippet": "WHO bulletin",
                            "source_tier": 1,
                            "stance": "support",
                        }
                    ],
                }
            ],
            "review_queue": [{"claim_id": "clm_001", "priority": "high"}],
            "run_verdict": "REVIEW_REQUIRED",
            "factcheck": {"status": "FACTCHECK_UNAVAILABLE"},
        },
        "source_trace": {
            "timeline_count": 1,
            "timeline": [
                {
                    "source_name": "reuters",
                    "url": "https://www.reuters.com/world/test-story",
                    "snippet": "Reuters timeline",
                }
            ],
        },
        "report_template": {"template_id": "deep-research-report"},
        "report_sections": [{"title": "summary", "content_markdown": "x"}],
        "data_quality_flags": ["TARGET_EVIDENCE_NOT_REACHED", "CLAIM_REVIEW_QUEUE_NON_EMPTY"],
    }
    summaries = orchestrator._build_step_summaries(result)
    assert len(summaries) == 3
    by_id = {row["step_id"]: row for row in summaries}

    search_summary = by_id["multiplatform_search"]
    assert search_summary["summary_text"]
    assert search_summary["links"]
    assert "TARGET_EVIDENCE_NOT_REACHED" in search_summary["codes"]

    claim_summary = by_id["claim_analysis"]
    assert claim_summary["summary_text"]
    assert any(str(link.get("url") or "").startswith("https://") for link in claim_summary["links"])
    assert "INSUFFICIENT_HIGH_TIER_EVIDENCE" in claim_summary["codes"]

    template_summary = by_id["report_template_render"]
    assert template_summary["summary_text"]
    assert template_summary["links"]
    assert template_summary["codes"]


def test_step_summaries_fallback_to_next_queries_as_links():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    result = {
        "steps": [{"id": "network_precheck", "status": "partial"}],
        "no_data_explainer": {"next_queries": ["who outbreak notice", "example domain official"]},
        "data_quality_flags": ["NETWORK_PRECHECK_FAILED"],
    }
    summaries = orchestrator._build_step_summaries(result)
    assert len(summaries) == 1
    links = summaries[0]["links"]
    assert links
    assert str(links[0].get("url") or "").startswith("https://www.google.com/search?q=")
    assert "NETWORK_PRECHECK_FAILED" in summaries[0]["codes"]


def test_evidence_classification_primary_background_noise():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    source_plan = {
        "must_have_platforms": ["reuters", "bbc"],
        "excluded_platforms": ["sec"],
    }

    primary = orchestrator._infer_evidence_class(
        card={
            "source_name": "reuters",
            "source_tier": 2,
            "relevance_score": 0.62,
            "keyword_match": True,
            "retrieval_mode": "search",
            "validation_status": "reachable",
        },
        source_plan=source_plan,
        keyword="who global health initiative",
    )
    assert primary["evidence_class"] == "primary"

    background = orchestrator._infer_evidence_class(
        card={
            "source_name": "bbc",
            "source_tier": 2,
            "relevance_score": 0.2,
            "keyword_match": False,
            "retrieval_mode": "hot_fallback",
            "validation_status": "provisional",
        },
        source_plan=source_plan,
        keyword="who global health initiative",
    )
    assert background["evidence_class"] in {"background", "noise"}

    noise = orchestrator._infer_evidence_class(
        card={
            "source_name": "sec",
            "source_tier": 1,
            "relevance_score": 0.05,
            "keyword_match": False,
            "retrieval_mode": "hot_fallback",
            "validation_status": "provisional_low_relevance",
        },
        source_plan=source_plan,
        keyword="who global health initiative",
    )
    assert noise["evidence_class"] == "noise"


def test_hot_fallback_items_never_promoted_to_primary_without_relevance():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    source_plan = {
        "must_have_platforms": ["bbc"],
        "excluded_platforms": [],
    }
    out = orchestrator._infer_evidence_class(
        card={
            "source_name": "bbc",
            "source_tier": 2,
            "relevance_score": 0.21,
            "keyword_match": False,
            "retrieval_mode": "hot_fallback",
            "validation_status": "provisional",
        },
        source_plan=source_plan,
        keyword="某事件",
    )
    assert out["evidence_class"] != "primary"


def test_hot_fallback_items_can_be_promoted_when_high_tier_and_high_signal():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    source_plan = {
        "must_have_platforms": ["xinhua"],
        "excluded_platforms": [],
    }
    out = orchestrator._infer_evidence_class(
        card={
            "source_name": "xinhua",
            "source_tier": 1,
            "relevance_score": 0.72,
            "keyword_match": True,
            "retrieval_mode": "web_search_fallback",
            "validation_status": "reachable",
        },
        source_plan=source_plan,
        keyword="苏炳添退役",
    )
    assert out["evidence_class"] == "primary"
    assert out["selection_reason"] == "high_tier_fallback_promoted"


def test_to_evidence_card_infers_official_attribution_from_social_snippet():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    row = {
        "platform": "weibo",
        "url": "https://www.weibo.com/2286908003/QhzE02WEe",
        "item": {
            "title": "来自新华社 - 微博",
            "content_text": "苏炳添宣布退役，新华社发布相关报道",
            "metadata": {},
        },
        "reachable": True,
        "keyword_match": True,
        "relevance_score": 0.88,
    }
    card = orchestrator._to_evidence_card(
        keyword="苏炳添退役",
        row=row,
        idx=1,
        source_plan={"must_have_platforms": ["xinhua"], "excluded_platforms": []},
    )
    assert card["source_platform"] == "weibo"
    assert card["source_name"] == "xinhua"
    assert card["source_tier"] == 2
    assert card["source_attribution"] == "xinhua"


def test_external_vs_derived_evidence_origin_split():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    cards = [
        {
            "id": "ev_ext_1",
            "source_name": "reuters",
            "source_tier": 2,
            "relevance_score": 0.58,
            "keyword_match": True,
            "retrieval_mode": "search",
            "validation_status": "reachable",
        },
        {
            "id": "ev_der_1",
            "source_name": "reasoning_chain",
            "source_tier": 2,
            "relevance_score": 0.2,
            "keyword_match": False,
            "retrieval_mode": "reasoning",
            "validation_status": "derived",
        },
    ]
    orchestrator._apply_evidence_stratification(
        evidence_cards=cards,
        source_plan={"must_have_platforms": ["reuters"], "excluded_platforms": []},
        keyword="测试主张",
    )
    assert cards[0]["evidence_origin"] == "external"
    assert cards[1]["evidence_origin"] == "derived_reasoning"


class _DummyCrawlersForPoolTest:
    def split_platform_pools(self, requested_platforms, profile):
        return {
            "stable_pool": ["xinhua", "reuters", "bbc"],
            "experimental_pool": ["weibo", "douyin"],
        }


def test_split_platform_pools_promotes_must_have_into_stable_pool():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    pools = orchestrator._split_platform_pools(
        crawlers=_DummyCrawlersForPoolTest(),
        source_profile="stable_mixed_v1",
        available_platforms=["xinhua", "reuters", "bbc", "weibo", "douyin"],
        must_have_platforms=["weibo", "xinhua"],
    )
    assert pools["stable_pool"][0] == "weibo"
    assert "weibo" not in pools["experimental_pool"]


def test_apply_evidence_stratification_recomputes_preexisting_class():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    cards = [
        {
            "source_name": "weibo",
            "source_tier": 3,
            "relevance_score": 1.0,
            "keyword_match": True,
            "retrieval_mode": "weibo_public_search",
            "validation_status": "context_fallback",
            "evidence_class": "background",
            "selection_reason": "context_fill_to_target",
        }
    ]
    orchestrator._apply_evidence_stratification(
        evidence_cards=cards,
        source_plan={"must_have_platforms": ["weibo"], "excluded_platforms": []},
        keyword="苏炳添退役了",
    )
    assert cards[0]["evidence_class"] == "primary"
    assert cards[0]["selection_reason"] == "primary_signal_passed"


def test_partition_external_evidence_cards_splits_three_pools():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    cards = [
        {
            "id": "ev_1",
            "evidence_origin": "external",
            "evidence_class": "primary",
        },
        {
            "id": "ev_2",
            "evidence_origin": "external",
            "evidence_class": "background",
        },
        {
            "id": "ev_3",
            "evidence_origin": "external",
            "evidence_class": "noise",
        },
        {
            "id": "ev_4",
            "evidence_origin": "derived_reasoning",
            "evidence_class": "primary",
        },
    ]
    out = orchestrator._partition_external_evidence_cards(cards)
    assert [x["id"] for x in out["evidence_pool"]] == ["ev_1"]
    assert [x["id"] for x in out["context_pool"]] == ["ev_2"]
    assert [x["id"] for x in out["noise_pool"]] == ["ev_3"]


def test_collect_search_hits_and_apply_promotion():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    hits = orchestrator._collect_search_hits(
        keyword="苏炳添退役了吗",
        search_data={
            "weibo": [
                {
                    "title": "苏炳添退役",
                    "content": "微博热议",
                    "url": "https://weibo.com/123",
                    "metadata": {"search_source_mode": "search"},
                },
                {
                    "title": "无关热点",
                    "content": "其他新闻",
                    "url": "https://weibo.com/999",
                    "metadata": {"search_source_mode": "hot"},
                },
            ]
        },
    )
    assert len(hits) == 2
    normalized = orchestrator._apply_search_hit_promotions(
        hits=hits,
        invalid_items=[{"platform": "weibo", "url": "https://weibo.com/999", "reason": "LOW_RELEVANCE"}],
        valid_rows=[
            {
                "platform": "weibo",
                "url": "https://weibo.com/123",
                "relevance_score": 0.91,
                "keyword_match": True,
                "item": {"metadata": {"provider": "native", "retrieval_mode": "weibo_public_search"}},
            }
        ],
    )
    promoted = [x for x in normalized if x.get("is_promoted")]
    dropped = [x for x in normalized if not x.get("is_promoted")]
    assert len(promoted) == 1
    assert promoted[0]["drop_reason"] == ""
    assert promoted[0]["relevance_score"] > 0.9
    assert len(dropped) == 1
    assert dropped[0]["drop_reason"] == "LOW_RELEVANCE"


def test_build_evidence_docs_from_cards():
    orchestrator = InvestigationOrchestrator(InvestigationRunManager())
    docs = orchestrator._build_evidence_docs(
        [
            {
                "id": "ev_1",
                "source_name": "xinhua",
                "source_platform": "xinhua",
                "source_domain": "news.cn",
                "url": "https://news.cn/sports/2025-12/09/c_123.htm",
                "snippet": "苏炳添宣布退役",
                "source_tier": 1,
                "confidence": 0.9,
                "relevance_score": 0.88,
                "keyword_match": True,
                "entity_pass": True,
                "validation_status": "reachable",
                "retrieval_mode": "rss_pool",
                "evidence_class": "primary",
            }
        ]
    )
    assert len(docs) == 1
    assert docs[0]["id"] == "ev_1"
    assert docs[0]["source_tier"] == 1
    assert docs[0]["keyword_match"] is True
