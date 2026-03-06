from services.source_planner import plan_sources


def test_source_planner_sports_claim_selects_sports_sources():
    plan = plan_sources(
        claim="苏炳添退役了",
        keyword="苏炳添 退役",
        available_platforms=[
            "xinhua",
            "bbc",
            "guardian",
            "reuters",
            "ap_news",
            "weibo",
            "zhihu",
            "who",
            "sec",
        ],
        platform_health_snapshot={},
    )
    assert plan["domain"] == "sports_person"
    assert plan["event_type"] == "sports_person_status"
    assert "xinhua" in plan["must_have_platforms"]
    assert "weibo" in plan["must_have_platforms"]
    assert "xinhua" in plan["selected_platforms"]
    assert "who" in plan["excluded_platforms"]
    assert "sec" in plan["excluded_platforms"]
    assert "who" not in plan["selected_platforms"]
    assert "sec" not in plan["selected_platforms"]
    assert len(plan["selected_platforms"]) <= 8
    assert plan["plan_version"] == "auto_v2_precision"
    assert 0.0 <= float(plan["selection_confidence"]) <= 1.0
    assert isinstance(plan["domain_keywords"], list)


def test_source_planner_excludes_low_domain_sources():
    plan = plan_sources(
        claim="WHO发布了新的全球卫生倡议",
        keyword="WHO global health initiative",
        available_platforms=["who", "reuters", "bbc", "guardian", "ap_news", "sec", "xinhua"],
        platform_health_snapshot={},
    )
    assert plan["domain"] == "public_health"
    assert plan["event_type"] == "public_health_alert"
    assert "sec" in plan["excluded_platforms"]
    assert "sec" not in plan["selected_platforms"]
    assert any(p in plan["selected_platforms"] for p in ["who", "reuters", "bbc", "guardian"])
    assert len(plan["must_have_platforms"]) <= 6


def test_source_planner_skips_unhealthy_platform_and_replaces():
    plan = plan_sources(
        claim="苏炳添退役了",
        keyword="苏炳添 退役",
        available_platforms=[
            "xinhua",
            "bbc",
            "reuters",
            "guardian",
            "weibo",
            "zhihu",
        ],
        platform_health_snapshot={
            "xinhua": {"health_score": 0.92},
            "bbc": {"health_score": 0.91},
            "reuters": {"health_score": 0.88},
            "guardian": {"health_score": 0.86},
            "weibo": {"health_score": 0.2},
            "zhihu": {"health_score": 0.15},
        },
    )
    assert "weibo" not in plan["selected_platforms"]
    assert "zhihu" not in plan["selected_platforms"]
    assert any(p in plan["selected_platforms"] for p in ["xinhua", "bbc", "reuters", "guardian"])


def test_source_planner_enforces_official_floor_when_available():
    plan = plan_sources(
        claim="某公众人物退役消息",
        keyword="退役 官方 声明",
        available_platforms=[
            "xinhua",
            "news",
            "samr",
            "reuters",
            "bbc",
            "weibo",
            "zhihu",
        ],
        platform_health_snapshot={},
    )
    official_set = {"xinhua", "news", "who", "un_news", "sec", "samr", "csrc", "nhc", "cdc", "mps", "mem"}
    official_selected = [p for p in plan["selected_platforms"] if p in official_set]
    assert len(official_selected) >= 2
    assert "xinhua" in official_selected
