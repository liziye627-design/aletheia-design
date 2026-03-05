import pytest

import services.opinion_monitoring as opinion_monitoring
from services.opinion_monitoring import analyze_opinion_monitoring


class DummyCrawlerManager:
    def __init__(self, comments_by_platform, sidecar_diag=None):
        self._comments_by_platform = comments_by_platform
        self._sidecar_diag = sidecar_diag or {
            "fetched_at": "",
            "hit_count": 0,
            "enabled": False,
            "failures": [],
        }

    async def fetch_comments_multi_platform(
        self,
        post_ids,
        limit_per_platform=50,
        mediacrawler_options=None,
    ):
        del mediacrawler_options
        return {
            platform: list(self._comments_by_platform.get(platform) or [])[:limit_per_platform]
            for platform in post_ids.keys()
        }

    def get_last_comment_sidecar_diag(self):
        return dict(self._sidecar_diag)


class DummyCrawlerManagerWithVerbose(DummyCrawlerManager):
    def __init__(self, comments_by_platform, verbose_search, sidecar_diag=None):
        super().__init__(comments_by_platform=comments_by_platform, sidecar_diag=sidecar_diag)
        self.crawlers = {"weibo": object(), "xiaohongshu": object(), "douyin": object(), "zhihu": object()}
        self._verbose_search = verbose_search

    async def search_across_platforms_verbose(
        self,
        keyword,
        platforms=None,
        limit_per_platform=20,
        mediacrawler_options=None,
        max_concurrency=None,
    ):
        del keyword, platforms, limit_per_platform, mediacrawler_options, max_concurrency
        return self._verbose_search

    async def search_across_platforms(
        self,
        keyword,
        platforms=None,
        limit_per_platform=20,
        mediacrawler_options=None,
        max_concurrency=None,
    ):
        del keyword, platforms, limit_per_platform, mediacrawler_options, max_concurrency
        return {
            str(p): list((row or {}).get("items") or [])
            for p, row in (self._verbose_search or {}).items()
        }


@pytest.mark.asyncio
async def test_opinion_monitoring_no_comment_candidates_fallback_to_synthetic_samples():
    manager = DummyCrawlerManager(comments_by_platform={})
    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={
            "bbc": [
                {
                    "url": "https://www.bbc.com/news/world-1",
                    "metadata": {},
                    "title": "Su Bingtian retirement rumor check",
                    "content_text": "Su Bingtian retirement rumor is spreading online.",
                }
            ]
        },
        source_plan={"selected_platforms": ["bbc"]},
        crawler_manager=manager,
        comment_target=120,
        comment_limit_per_post=40,
        max_posts_per_platform=2,
        max_platforms=6,
        allow_synthetic_comments=True,
    )
    assert result["status"] in {"partial", "ok"}
    assert result["total_comments"] > 0
    assert result["synthetic_comment_mode"] is True
    assert result["comment_target_reached"] is False
    assert result["real_comment_count"] == 0
    assert result["real_comment_ratio"] == 0.0
    assert "INSUFFICIENT_COMMENT_COVERAGE" in result["risk_flags"]
    assert "NO_COMMENT_POST_CANDIDATES" in result["risk_flags"]
    assert "COMMENT_SOURCE_FALLBACK_POSTS" in result["risk_flags"]


@pytest.mark.asyncio
async def test_opinion_monitoring_no_comment_candidates_without_any_samples():
    manager = DummyCrawlerManager(comments_by_platform={})
    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={},
        source_plan={"selected_platforms": ["bbc"]},
        crawler_manager=manager,
        comment_target=120,
        comment_limit_per_post=40,
        max_posts_per_platform=2,
        max_platforms=6,
    )
    assert result["status"] == "no_comment_post_candidates"
    assert result["comment_target_reached"] is False
    assert "INSUFFICIENT_COMMENT_COVERAGE" in result["risk_flags"]
    assert "SYNTHETIC_COMMENTS_DISABLED" in result["risk_flags"]


@pytest.mark.asyncio
async def test_opinion_monitoring_high_suspicious_ratio_sets_risk_flag(monkeypatch):
    manager = DummyCrawlerManager(
        comments_by_platform={
            "weibo": [
                {
                    "content_text": "同一条可疑评论模板",
                    "url": "https://weibo.com/comment/1",
                    "metadata": {
                        "author_id": "u1",
                        "author_name": "u1",
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                    },
                },
                {
                    "content_text": "同一条可疑评论模板",
                    "url": "https://weibo.com/comment/2",
                    "metadata": {
                        "author_id": "u2",
                        "author_name": "u2",
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                    },
                },
                {
                    "content_text": "同一条可疑评论模板",
                    "url": "https://weibo.com/comment/3",
                    "metadata": {
                        "author_id": "u3",
                        "author_name": "u3",
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                    },
                },
            ]
        }
    )

    def fake_run_bot_detection(_comments_by_platform):
        return [
            {
                "platform": "weibo",
                "user_id": "u1",
                "nickname": "u1",
                "comment_count": 1,
                "risk_score": 0.91,
                "risk_level": "high",
                "is_suspicious": True,
                "detected_features": ["HIGH_POSTING_FREQUENCY"],
                "sample_comments": ["同一条可疑评论模板"],
            },
            {
                "platform": "weibo",
                "user_id": "u2",
                "nickname": "u2",
                "comment_count": 1,
                "risk_score": 0.82,
                "risk_level": "high",
                "is_suspicious": True,
                "detected_features": ["LOW_PROFILE_COMPLETENESS"],
                "sample_comments": ["同一条可疑评论模板"],
            },
            {
                "platform": "weibo",
                "user_id": "u3",
                "nickname": "u3",
                "comment_count": 1,
                "risk_score": 0.21,
                "risk_level": "low",
                "is_suspicious": False,
                "detected_features": [],
                "sample_comments": ["同一条可疑评论模板"],
            },
        ]

    monkeypatch.setattr(opinion_monitoring, "_run_bot_detection", fake_run_bot_detection)

    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={
            "weibo": [
                {
                    "url": "https://weibo.com/athlete/1234567890",
                    "metadata": {"post_id": "1234567890", "keyword_match": True},
                    "content_text": "苏炳添退役传闻",
                }
            ]
        },
        source_plan={"selected_platforms": ["weibo"]},
        crawler_manager=manager,
        comment_target=2,
        comment_limit_per_post=40,
        max_posts_per_platform=2,
        max_platforms=6,
    )

    assert result["total_comments"] == 3
    assert result["comment_target_reached"] is True
    assert result["suspicious_accounts_count"] == 2
    assert result["suspicious_ratio"] >= 0.66
    assert result["risk_level"] in {"medium", "high"}
    assert any(flag.startswith("BOT_SWARM_RISK_") for flag in result["risk_flags"])


@pytest.mark.asyncio
async def test_opinion_monitoring_prefers_real_post_id_from_mediacrawler():
    manager = DummyCrawlerManager(comments_by_platform={})
    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={
            "weibo": [
                {
                    "url": "https://weibo.com/anonymous/no_post_id",
                    "metadata": {"keyword_match": True, "provider": "native"},
                    "content_text": "疑似传闻帖子",
                },
                {
                    "url": "https://weibo.com/123456/M123456",
                    "metadata": {
                        "keyword_match": True,
                        "provider": "mediacrawler",
                        "post_id": "M123456",
                        "keyword_match_score": 0.95,
                    },
                    "content_text": "带真实 post_id 的帖子",
                },
            ]
        },
        source_plan={"selected_platforms": ["weibo"]},
        crawler_manager=manager,
        mediacrawler_options={"use_mediacrawler": True, "mediacrawler_platforms": ["weibo"]},
        comment_target=20,
        comment_limit_per_post=20,
        max_posts_per_platform=2,
        max_platforms=2,
    )
    assert result["post_targets"].get("weibo") == "M123456"


@pytest.mark.asyncio
async def test_opinion_monitoring_surfaces_sidecar_comment_failures():
    manager = DummyCrawlerManager(
        comments_by_platform={"weibo": []},
        sidecar_diag={
            "fetched_at": "2026-02-24T00:00:00",
            "hit_count": 0,
            "enabled": True,
            "failures": [
                {
                    "platform": "weibo",
                    "post_id": "M123456",
                    "reason": "MEDIACRAWLER_LOGIN_REQUIRED",
                }
            ],
        },
    )
    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={
            "weibo": [
                {
                    "url": "https://weibo.com/123456/M123456",
                    "metadata": {
                        "keyword_match": True,
                        "provider": "mediacrawler",
                        "post_id": "M123456",
                    },
                    "content_text": "带真实 post_id 的帖子",
                },
            ],
        },
        source_plan={"selected_platforms": ["weibo"]},
        crawler_manager=manager,
        comment_target=20,
        comment_limit_per_post=20,
        max_posts_per_platform=1,
        max_platforms=1,
    )
    assert isinstance(result.get("sidecar_failures"), list)
    assert any(str(row.get("reason") or "").startswith("MEDIACRAWLER_") for row in result["sidecar_failures"])
    assert "MEDIACRAWLER_COMMENT_DEGRADED" in (result.get("risk_flags") or [])


@pytest.mark.asyncio
async def test_opinion_monitoring_collects_sidecar_failures_from_quick_social_search():
    manager = DummyCrawlerManagerWithVerbose(
        comments_by_platform={},
        verbose_search={
            "weibo": {
                "items": [],
                "mediacrawler": {"degraded": True, "error": "MEDIACRAWLER_LOGIN_REQUIRED"},
            }
        },
        sidecar_diag={"fetched_at": "", "hit_count": 0, "enabled": True, "failures": []},
    )
    result = await analyze_opinion_monitoring(
        keyword="苏炳添退役",
        search_data={},
        source_plan={"selected_platforms": ["weibo"]},
        crawler_manager=manager,
        mediacrawler_options={"use_mediacrawler": True, "mediacrawler_platforms": ["weibo"]},
        comment_target=30,
        comment_limit_per_post=20,
        max_posts_per_platform=1,
        max_platforms=1,
        allow_synthetic_comments=False,
    )
    failures = result.get("sidecar_failures") or []
    assert any(str(row.get("reason") or "") == "MEDIACRAWLER_LOGIN_REQUIRED" for row in failures)
