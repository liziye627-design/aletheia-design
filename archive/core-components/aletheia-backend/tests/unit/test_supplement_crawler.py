import pytest

from services.supplement_crawler import SupplementCrawlerService


class _FakeCrawlerManager:
    def __init__(self) -> None:
        self.crawlers = {"weibo": object(), "zhihu": object(), "xinhua": object()}
        self._calls = 0

    async def search_across_platforms_verbose(
        self,
        keyword: str,
        platforms=None,
        limit_per_platform=20,
        mediacrawler_options=None,
    ):
        self._calls += 1
        if self._calls == 1:
            return {
                "weibo": {
                    "platform": "weibo",
                    "status": "ok",
                    "reason_code": "OK",
                    "items_collected": 2,
                    "elapsed_ms": 120,
                    "items": [
                        {
                            "url": "https://weibo.com/1",
                            "title": "苏炳添 退役",
                            "content_text": "苏炳添 宣布退役",
                            "metadata": {
                                "retrieval_mode": "weibo_public_search",
                                "keyword_match": True,
                                "keyword_match_score": 1.0,
                            },
                        },
                        {
                            "url": "https://weibo.com/hot",
                            "title": "微博热榜",
                            "content_text": "与关键词无关",
                            "metadata": {"retrieval_mode": "hot_fallback"},
                        },
                    ],
                },
                "zhihu": {
                    "platform": "zhihu",
                    "status": "fallback",
                    "reason_code": "FALLBACK_EMPTY",
                    "items_collected": 0,
                    "elapsed_ms": 80,
                    "items": [],
                },
            }
        return {
            "xinhua": {
                "platform": "xinhua",
                "status": "ok",
                "reason_code": "OK",
                "items_collected": 1,
                "elapsed_ms": 95,
                "items": [
                    {
                        "url": "https://news.cn/1",
                        "title": "新华社：苏炳添退役",
                        "content_text": "苏炳添 退役 相关报道",
                        "metadata": {
                            "retrieval_mode": "search",
                            "keyword_match": True,
                            "keyword_match_score": 0.95,
                        },
                    }
                ],
            }
        }

    def get_platform_source_matrix(self):
        return {
            "weibo": {"account_pool": {"total_accounts": 3}},
            "zhihu": {"account_pool": {"total_accounts": 2}},
            "xinhua": {"account_pool": {}},
        }


@pytest.mark.asyncio
async def test_supplement_crawler_reaches_target_with_supplement_round():
    svc = SupplementCrawlerService(crawler_manager=_FakeCrawlerManager())
    report = await svc.run(
        keyword="苏炳添退役",
        target_evidence=2,
        rounds=3,
        limit_per_platform=10,
        primary_platforms=["weibo", "zhihu"],
        supplement_platforms=["xinhua"],
    )
    assert report["rounds_executed"] == 2
    assert report["promoted_items"] == 2
    assert report["coverage_reached"] is True
    attempts = list(report.get("platform_attempts") or [])
    assert any(row.get("platform") == "weibo" for row in attempts)
    assert any(row.get("platform") == "xinhua" for row in attempts)

