"""
爬虫管理器 - 统一管理多个数据源爬虫
"""

import asyncio
import os
import re
import time
from collections import defaultdict
from typing import Optional, List, Dict, Any, Literal, Tuple
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs, unquote
import httpx
import feedparser
from core.config import settings
from services.external.bocha_search import BochaSearchProvider
from services.external.mediacrawler_client import get_mediacrawler_client
from services.layer1_perception.crawlers.mediacrawler_normalizer import (
    normalize_mediacrawler_comments,
    normalize_mediacrawler_posts,
)
from .crawlers.weibo import WeiboCrawler
from .crawlers.twitter import TwitterCrawler
from .crawlers.xiaohongshu import XiaohongshuCrawler
from .crawlers.douyin import DouyinCrawler
from .crawlers.zhihu import ZhihuCrawler
from .crawlers.bilibili import BilibiliCrawler
from .crawlers.news_aggregator import NewsAggregator
from .crawlers.kuaishou import KuaishouCrawler
from .crawlers.douban import DoubanCrawler
from .crawlers.reddit import RedditCrawler
from .crawlers.rss_pool import RssPoolCrawler
from services.rss_sources_config import get_rss_sources_registry
from services.search_sources_config import get_search_sources_registry
from services.account_pool import get_account_pool_manager

# 官方信源（统一管理器）
from .crawlers.official_sources import OfficialSourcesManager
from .crawlers.news_media import InternationalNewsManager
from .crawlers.community import (
    GitHubEventsCrawler,
    StackOverflowCrawler,
    QuoraCrawler,
)
from .crawlers.academic_datasets import (
    GDELTCrawler,
    CommonCrawlCrawler,
    OpenAlexCrawler,
)

from utils.logging import logger
from utils.metrics import (
    crawler_platform_success_total,
    crawler_platform_timeout_total,
)
from utils.network_env import evaluate_trust_env


_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ CrawlerManager disable httpx trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


PlatformType = Literal[
    "weibo",
    "twitter",
    "xiaohongshu",
    "douyin",
    "zhihu",
    "bilibili",
    "news",
    "kuaishou",
    "douban",
    "reddit",
    # 官方信源 - 中国
    "china_gov",
    "samr",
    "csrc",
    "nhc",
    "mem",
    "mps",
    "supreme_court",
    "supreme_procuratorate",
    "xinhua",
    "peoples_daily",
    # 官方信源 - 全球
    "who",
    "cdc",
    "un_news",
    "world_bank",
    "sec",
    "fca_uk",
    "eu_open_data",
    # 新闻媒体
    "reuters",
    "ap_news",
    "bbc",
    "guardian",
    "caixin",
    "the_paper",
    # 社区论坛
    "github",
    "stackoverflow",
    "quora",
    # 学术数据集
    "gdelt",
    "common_crawl",
    "openalex",
    "rss_pool",
    "all",
]


class CrawlerManager:
    """爬虫管理器 - 协调多个平台爬虫"""

    def __init__(
        self,
        # 原有社交媒体平台
        weibo_cookies: Optional[str] = None,
        twitter_bearer_token: Optional[str] = None,
        xhs_cookies: Optional[str] = None,
        douyin_cookies: Optional[str] = None,
        zhihu_cookies: Optional[str] = None,
        bilibili_cookies: Optional[str] = None,
        kuaishou_cookies: Optional[str] = None,
        douban_cookies: Optional[str] = None,
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
        # 社区论坛平台
        github_token: Optional[str] = None,
        stackoverflow_api_key: Optional[str] = None,
        # 学术数据集
        openalex_email: Optional[str] = None,  # OpenAlex建议提供邮箱以获得更高速率限制
    ):
        """
        初始化爬虫管理器

        Args:
            # 社交媒体平台 (可通过MCP工具获取cookies)
            weibo_cookies: 微博登录Cookies
            twitter_bearer_token: Twitter API Bearer Token
            xhs_cookies: 小红书登录Cookies
            douyin_cookies: 抖音登录Cookies
            zhihu_cookies: 知乎登录Cookies
            bilibili_cookies: B站登录Cookies
            kuaishou_cookies: 快手登录Cookies
            douban_cookies: 豆瓣登录Cookies
            reddit_client_id: Reddit API Client ID
            reddit_client_secret: Reddit API Client Secret

            # 社区论坛
            github_token: GitHub Personal Access Token (可选，提高速率限制)
            stackoverflow_api_key: Stack Overflow API Key (可选)

            # 学术数据集
            openalex_email: OpenAlex联系邮箱 (可选，建议提供以获得100req/s速率)
        """
        self.crawlers = {}
        self._platform_metrics: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {
                "calls": 0.0,
                "success": 0.0,
                "timeout": 0.0,
                "total_latency_ms": 0.0,
            }
        )
        self._platform_reason_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._platform_domains: Dict[str, List[str]] = self._default_platform_domains()
        self._platform_backup_urls: Dict[str, List[str]] = self._default_platform_backup_urls()
        self._rss_sources_registry = get_rss_sources_registry()
        self._rss_sources_snapshot: List[Dict[str, Any]] = []
        self._search_sources_registry = get_search_sources_registry()
        self._search_sources_snapshot: List[Dict[str, Any]] = []
        self._source_profiles: Dict[str, List[str]] = {
            "stable_mixed_v1": [
                "xinhua",
                "peoples_daily",
                "china_gov",
                "who",
                "un_news",
                "sec",
                "samr",
                "csrc",
                "nhc",
                "cdc",
                "bbc",
                "guardian",
                "reuters",
                "ap_news",
            ]
        }
        self.platform_search_timeout_seconds = max(
            3.0,
            float(
                getattr(
                    settings,
                    "CRAWLER_PLATFORM_SEARCH_TIMEOUT_SECONDS",
                    12.0,
                )
            ),
        )
        self.platform_search_timeout_max_seconds = max(
            self.platform_search_timeout_seconds,
            float(
                getattr(
                    settings,
                    "CRAWLER_PLATFORM_SEARCH_TIMEOUT_MAX_SECONDS",
                    18.0,
                )
            ),
        )
        self.web_fallback_timeout_seconds = max(
            3.0,
            float(
                getattr(
                    settings,
                    "CRAWLER_WEB_FALLBACK_TIMEOUT_SECONDS",
                    6.0,
                )
            ),
        )
        self.hot_fallback_multiplier = max(
            1,
            int(getattr(settings, "CRAWLER_HOT_FALLBACK_MULTIPLIER", 2)),
        )
        self.news_search_fetch_limit_cap = max(
            20,
            int(getattr(settings, "CRAWLER_NEWS_SEARCH_FETCH_LIMIT_CAP", 80)),
        )
        self.enable_web_fallback = bool(
            getattr(settings, "CRAWLER_ENABLE_WEB_FALLBACK", True)
        )
        self.web_fallback_concurrency = max(
            1,
            int(getattr(settings, "CRAWLER_WEB_FALLBACK_CONCURRENCY", 3)),
        )
        self._web_fallback_semaphore = asyncio.Semaphore(self.web_fallback_concurrency)
        self._fallback_trust_env_hint: Optional[bool] = None
        self.enable_bocha_fallback = bool(
            getattr(settings, "CRAWLER_BOCHA_FALLBACK_ENABLED", True)
        )
        bocha_allowlist_raw = str(
            getattr(
                settings,
                "CRAWLER_BOCHA_FALLBACK_PLATFORM_ALLOWLIST",
                "rss_pool,news,weibo,zhihu,xinhua,peoples_daily",
            )
            or ""
        )
        self._bocha_fallback_allowlist: set[str] = {
            row.strip().lower()
            for row in bocha_allowlist_raw.split(",")
            if row.strip()
        }
        self._bocha_fallback_max_query_variants = max(
            1,
            int(getattr(settings, "CRAWLER_BOCHA_FALLBACK_MAX_QUERY_VARIANTS", 1)),
        )
        self._bocha_fallback_fetch_multiplier = max(
            1,
            int(getattr(settings, "CRAWLER_BOCHA_FALLBACK_FETCH_MULTIPLIER", 2)),
        )
        self._bocha_fallback_cache_ttl_sec = max(
            5,
            int(getattr(settings, "CRAWLER_BOCHA_FALLBACK_CACHE_TTL_SEC", 120)),
        )
        self._bocha_allow_cross_domain_social = bool(
            getattr(
                settings,
                "CRAWLER_BOCHA_FALLBACK_ALLOW_CROSS_DOMAIN_FOR_SOCIAL",
                True,
            )
        )
        bocha_social_raw = str(
            getattr(
                settings,
                "CRAWLER_BOCHA_FALLBACK_SOCIAL_PLATFORMS",
                "weibo,zhihu,xiaohongshu,douyin,bilibili,kuaishou,douban",
            )
            or ""
        )
        self._bocha_social_platforms: set[str] = {
            row.strip().lower()
            for row in bocha_social_raw.split(",")
            if row.strip()
        }
        self._bocha_fallback_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._fallback_first_platforms: set[str] = {
            "twitter",
            "xiaohongshu",
            "douyin",
            "zhihu",
            "bilibili",
            "kuaishou",
            "douban",
            "reddit",
            "quora",
            "gdelt",
            "common_crawl",
            "openalex",
        }
        self._web_fallback_budget_sec_default = max(
            4.0,
            float(getattr(settings, "CRAWLER_WEB_FALLBACK_BUDGET_SECONDS", 14.0)),
        )
        self._web_fallback_budget_overrides: Dict[str, float] = {
            "twitter": 10.0,
            "xiaohongshu": 12.0,
            "douyin": 12.0,
            "zhihu": 14.0,
            "weibo": 14.0,
            "bilibili": 10.0,
            "kuaishou": 10.0,
            "douban": 10.0,
            "reddit": 10.0,
            "quora": 10.0,
            "news": 10.0,
            "rss_pool": 16.0,
            "gdelt": 12.0,
            "common_crawl": 12.0,
            "openalex": 12.0,
            "who": 10.0,
            "cdc": 10.0,
            "xinhua": 14.0,
            "peoples_daily": 14.0,
            "china_gov": 14.0,
            "nhc": 14.0,
            "mps": 12.0,
            "mem": 12.0,
            "samr": 14.0,
            "csrc": 14.0,
            "sec": 10.0,
            "un_news": 10.0,
        }
        self._platform_timeout_overrides: Dict[str, float] = {
            "twitter": 6.0,
            "xiaohongshu": 8.0,
            "douyin": 8.0,
            "zhihu": 12.0,
            "weibo": 12.0,
            "bilibili": 7.0,
            "kuaishou": 7.0,
            "douban": 7.0,
            "reddit": 6.0,
            "quora": 7.0,
            "gdelt": 8.0,
            "common_crawl": 8.0,
            "openalex": 8.0,
            "rss_pool": 12.0,
            "xinhua": 14.0,
            "news": 12.0,
            "bbc": 12.0,
            "guardian": 12.0,
            "reuters": 12.0,
            "ap_news": 12.0,
            "caixin": 12.0,
            "the_paper": 12.0,
            "who": 12.0,
            "cdc": 12.0,
            "un_news": 12.0,
            "sec": 12.0,
            "fca_uk": 12.0,
            "peoples_daily": 14.0,
            "china_gov": 14.0,
            "mps": 12.0,
            "mem": 12.0,
            "samr": 14.0,
            "csrc": 14.0,
            "nhc": 14.0,
        }
        self._mediacrawler_supported_platforms: set[str] = {
            "weibo",
            "xiaohongshu",
            "douyin",
            "zhihu",
        }
        self._trusted_hot_fallback_platforms: set[str] = {
            "xinhua",
            "news",
            "bbc",
            "guardian",
            "reuters",
            "ap_news",
            "caixin",
            "the_paper",
            "who",
            "cdc",
            "un_news",
            "sec",
            "samr",
            "csrc",
            "nhc",
            "mem",
            "mps",
            "china_gov",
            "peoples_daily",
            "supreme_court",
            "supreme_procuratorate",
            "fca_uk",
        }
        self._mediacrawler_max_items_per_platform = max(
            10,
            int(getattr(settings, "MEDIACRAWLER_MAX_ITEMS_PER_PLATFORM", 80)),
        )
        self._last_comment_sidecar_diag: Dict[str, Any] = {
            "fetched_at": "",
            "hit_count": 0,
            "failures": [],
            "enabled": False,
        }
        self._init_crawlers(
            weibo_cookies,
            twitter_bearer_token,
            xhs_cookies,
            douyin_cookies,
            zhihu_cookies,
            bilibili_cookies,
            kuaishou_cookies,
            douban_cookies,
            reddit_client_id,
            reddit_client_secret,
            github_token,
            stackoverflow_api_key,
            openalex_email,
        )
        self._bootstrap_platform_domains()
        self._bootstrap_rss_sources_domains()
        self._bootstrap_search_sources_domains()

    def _default_platform_domains(self) -> Dict[str, List[str]]:
        """默认平台域名映射（用于 web fallback 与域名白名单）。"""
        return {
            "weibo": ["weibo.com", "m.weibo.cn"],
            "twitter": ["x.com", "twitter.com"],
            "xiaohongshu": ["xiaohongshu.com"],
            "zhihu": ["zhihu.com", "zhuanlan.zhihu.com"],
            "bilibili": ["bilibili.com"],
            "douyin": ["douyin.com"],
            "qq_news": ["news.qq.com"],
            "kuaishou": ["kuaishou.com"],
            "douban": ["douban.com"],
            "reddit": ["reddit.com"],
            "github": ["github.com"],
            "stackoverflow": ["stackoverflow.com", "stackexchange.com"],
            "news": ["news.cn", "xinhuanet.com", "sina.com.cn"],
            "xinhua": ["news.cn", "xinhuanet.com"],
            "reuters": ["reuters.com"],
            "ap_news": ["apnews.com"],
            "bbc": ["bbc.com", "bbci.co.uk"],
            "guardian": ["theguardian.com"],
            "caixin": ["caixin.com"],
            "the_paper": ["thepaper.cn"],
            "rss_pool": [],
            "people": ["people.com.cn"],
            "peoples_daily": ["people.com.cn"],
            "cctv": ["cctv.com", "news.cctv.com"],
            "chinanews": ["chinanews.com.cn", "chinanews.com"],
            "guancha": ["guancha.cn"],
            "samr": ["samr.gov.cn"],
            "csrc": ["csrc.gov.cn"],
            "nhc": ["nhc.gov.cn"],
            "mem": ["mem.gov.cn"],
            "mps": ["mps.gov.cn"],
            "supreme_court": ["court.gov.cn"],
            "supreme_procuratorate": ["spp.gov.cn"],
            "who": ["who.int"],
            "cdc": ["cdc.gov"],
            "thepaper": ["thepaper.cn"],
            "caixin_rsshub": ["rsshub.app"],
            "un_news": ["un.org"],
            "sec": ["sec.gov"],
            "fca_uk": ["fca.org.uk"],
            "quora": ["quora.com"],
            "gdelt": ["gdeltproject.org"],
            "common_crawl": ["commoncrawl.org", "index.commoncrawl.org"],
            "openalex": ["openalex.org", "api.openalex.org"],
        }

    def _default_platform_backup_urls(self) -> Dict[str, List[str]]:
        """
        平台备份URL清单（优先稳定免费信源）。
        用于排查 URL 失效和生成 source-health matrix。
        """
        return {
            "qq_news": [
                "https://news.google.com/rss/search?q=site:news.qq.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            ],
            "cctv": [
                "https://news.google.com/rss/search?q=site:news.cctv.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
                "https://news.google.com/rss/search?q=site:cctv.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            ],
            "bbc": [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.bbci.co.uk/news/rss.xml",
            ],
            "guardian": [
                "https://www.theguardian.com/world/rss",
                "https://www.theguardian.com/international/rss",
            ],
            "reuters": [
                "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
                "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
                "https://www.reuters.com/world/",
            ],
            "ap_news": [
                "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
                "https://feeds.apnews.com/rss/apf-topnews",
                "https://apnews.com/hub/ap-top-news",
            ],
            "xinhua": [
                "https://www.news.cn/politics/",
                "https://www.news.cn/world/",
            ],
            "news": [
                "https://www.news.cn/politics/",
                "https://www.news.cn/world/",
                "https://news.sina.com.cn/",
            ],
            "who": [
                "https://www.who.int/rss-feeds/news-english.xml",
                "https://www.who.int/news-room",
            ],
            "cdc": [
                "https://www.cdc.gov/media/rss.xml",
                "https://tools.cdc.gov/podcasts/rss.asp?c=146",
            ],
            "people": [
                "https://www.people.com.cn/rss/politics.xml",
                "https://www.people.com.cn/rss/world.xml",
            ],
            "peoples_daily": [
                "https://www.people.com.cn/rss/politics.xml",
                "https://www.people.com.cn/rss/world.xml",
            ],
            "chinanews": [
                "https://www.chinanews.com/rss/scroll-news.xml",
            ],
            "guancha": [
                "https://www.guancha.cn/rss/",
            ],
            "thepaper": [
                "https://thepaper.cn/rss/feed.xml",
            ],
            "caixin": [
                "https://rsshub.app/caixin/news",
            ],
            "un_news": [
                "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            ],
            "sec": [
                "https://www.sec.gov/news/pressreleases.rss",
            ],
            "samr": [
                "https://www.samr.gov.cn/",
                "https://www.samr.gov.cn/xw/sj/",
            ],
            "csrc": [
                "https://www.csrc.gov.cn/",
                "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
            ],
            "nhc": [
                "https://www.nhc.gov.cn/",
                "https://www.nhc.gov.cn/yjb/list.shtml",
            ],
            "mem": [
                "https://www.mem.gov.cn/",
                "https://www.mem.gov.cn/xw/",
            ],
            "mps": [
                "https://www.mps.gov.cn/",
                "https://www.mps.gov.cn/n2253534/index.html",
            ],
            "fca_uk": [
                "https://www.fca.org.uk/news",
                "https://www.fca.org.uk/markets/market-news",
            ],
        }

    def _bootstrap_platform_domains(self) -> None:
        """从 crawler 配置自动补全平台域名，避免硬编码漏项。"""
        for platform, crawler in (self.crawlers or {}).items():
            for attr in ("source_url", "rss_url", "api_base", "hot_search_url"):
                raw = getattr(crawler, attr, None)
                if not raw:
                    continue
                domain = self._extract_domain(raw)
                if domain:
                    self._append_platform_domain(platform, domain)
            if platform not in self._platform_domains:
                self._platform_domains[platform] = []

    def _bootstrap_rss_sources_domains(self) -> None:
        """把 sources.yaml 中的 RSS 入口注入 rss_pool 备份列表与域名白名单。"""
        registry = self._rss_sources_registry
        sources = self._rss_sources_snapshot or (registry.get_rss_sources() if registry else [])
        if not sources:
            return
        rss_urls: List[str] = []
        for src in sources:
            if not isinstance(src, dict):
                continue
            url = str(src.get("url") or "").strip()
            if not url:
                continue
            rss_urls.append(url)
            domain = self._extract_domain(url)
            if domain:
                self._append_platform_domain("rss_pool", domain)
        if rss_urls:
            existing = self._platform_backup_urls.setdefault("rss_pool", [])
            for url in rss_urls:
                if url not in existing:
                    existing.append(url)
            logger.info(
                f"✅ RSS pool domains injected: urls={len(rss_urls)}, domains={len(self.get_platform_domains('rss_pool'))}"
            )

    def _bootstrap_search_sources_domains(self) -> None:
        """把 search_sources.yaml 中的入口域名注入平台域名映射。"""
        registry = self._search_sources_registry
        rows = self._search_sources_snapshot or (
            registry.get_enabled_sources() if registry else []
        )
        if not rows:
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            platform = str(row.get("platform") or "").strip()
            if not platform:
                continue
            url_template = str(row.get("url_template") or row.get("url") or "").strip()
            if not url_template:
                continue
            domain = self._extract_domain(url_template)
            if domain:
                self._append_platform_domain(platform, domain)

    def get_search_sources_snapshot(self) -> List[Dict[str, Any]]:
        registry = self._search_sources_registry
        if not registry:
            self._search_sources_snapshot = []
            return []
        try:
            rows = registry.get_enabled_sources()
        except Exception as exc:
            logger.warning(f"failed to load search sources snapshot: {exc}")
            rows = []
        self._search_sources_snapshot = list(rows or [])
        return list(self._search_sources_snapshot)

    def get_search_sources_for_platform(self, platform: str) -> List[Dict[str, Any]]:
        target = str(platform or "").strip().lower()
        if not target:
            return []
        rows = self.get_search_sources_snapshot()
        return [
            row
            for row in rows
            if str(row.get("platform") or "").strip().lower() == target
        ]

    def _extract_domain(self, value: str) -> Optional[str]:
        try:
            host = (urlparse(str(value)).hostname or "").lower().strip()
            return host or None
        except Exception:
            return None

    def _append_platform_domain(self, platform: str, domain: str) -> None:
        raw = str(domain or "").strip()
        if not raw:
            return
        d = raw.lower()
        parsed = self._extract_domain(d)
        # 支持传入 URL 或域名；统一归一成 hostname，避免 "https://..." 被误当作域名导致全部 miss。
        if parsed:
            d = parsed
        elif "/" in d or ":" in d:
            try:
                parsed_guess = self._extract_domain(f"https://{d.lstrip('/')}")
            except Exception:
                parsed_guess = None
            if parsed_guess:
                d = parsed_guess
        d = d.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if not d:
            return
        rows = self._platform_domains.setdefault(platform, [])
        if d not in rows:
            rows.append(d)

    def get_platform_domains(self, platform: str) -> List[str]:
        return list(self._platform_domains.get(platform, []))

    def get_all_platform_domains(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._platform_domains.items()}

    def get_platform_primary_url(self, platform: str) -> str:
        crawler = (self.crawlers or {}).get(platform)
        if crawler:
            for attr in ("rss_url", "source_url", "api_base", "hot_search_url", "BASE_URL"):
                raw = getattr(crawler, attr, None)
                if isinstance(raw, list):
                    if raw and str(raw[0]).strip():
                        return str(raw[0]).strip()
                elif raw and str(raw).strip():
                    return str(raw).strip()
        backups = self.get_platform_backup_urls(platform)
        if backups:
            return str(backups[0]).strip()
        return ""

    def get_platform_backup_urls(self, platform: str) -> List[str]:
        return list(self._platform_backup_urls.get(platform, []))

    def get_platform_source_matrix(self) -> Dict[str, Dict[str, Any]]:
        """
        返回平台主/备URL、抓取模式、健康度、失败原因等诊断数据。
        """
        health = self.get_platform_health_snapshot()
        reasons = self.get_platform_reason_stats()
        stable_seed = set(self.get_source_profile_platforms("stable_mixed_v1"))
        account_pool = get_account_pool_manager()
        account_snapshot = account_pool.snapshot()
        matrix: Dict[str, Dict[str, Any]] = {}
        for platform in sorted(list((self.crawlers or {}).keys())):
            crawler = self.crawlers.get(platform)
            search_sources = self.get_search_sources_for_platform(platform)
            fetch_mode = "crawler"
            if crawler and hasattr(crawler, "access_method"):
                fetch_mode = str(getattr(crawler, "access_method") or "crawler")
            elif crawler and hasattr(crawler, "rss_url"):
                fetch_mode = "rss"
            elif crawler and hasattr(crawler, "search"):
                fetch_mode = "search"

            matrix[platform] = {
                "platform": platform,
                "profile_pool": "stable" if platform in stable_seed else "experimental",
                "quality_tier": self._source_tier_for_platform(platform),
                "primary_url": self.get_platform_primary_url(platform),
                "backup_urls": self.get_platform_backup_urls(platform),
                "domains": self.get_platform_domains(platform),
                "fetch_mode": fetch_mode,
                "health": health.get(platform, {}),
                "reason_stats": reasons.get(platform, {}),
                "search_sources_count": len(search_sources),
                "search_source_modes": sorted(
                    list(
                        {
                            str(row.get("discovery_mode") or "").strip().lower()
                            for row in search_sources
                            if isinstance(row, dict)
                            and str(row.get("discovery_mode") or "").strip()
                        }
                    )
                ),
                "account_pool": account_snapshot.get(platform, {}),
            }
        return matrix

    def _source_tier_for_platform(self, platform: str) -> int:
        """
        平台分层:
        - Tier 1: 官方/监管/权威公共机构域名
        - Tier 2: 主流媒体与高可信新闻域名
        - Tier 3: 社交媒体与社区平台
        """
        if str(platform or "").strip().lower() == "rss_pool":
            return 3
        domains = self.get_platform_domains(platform)
        tier1 = {
            "gov.cn",
            "samr.gov.cn",
            "csrc.gov.cn",
            "nhc.gov.cn",
            "mem.gov.cn",
            "mps.gov.cn",
            "court.gov.cn",
            "spp.gov.cn",
            "who.int",
            "cdc.gov",
            "un.org",
            "sec.gov",
            "fca.org.uk",
        }
        tier2 = {
            "news.cn",
            "xinhuanet.com",
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "bbci.co.uk",
            "theguardian.com",
            "caixin.com",
            "thepaper.cn",
        }
        for d in domains:
            host = str(d or "").lower().strip()
            if any(host == x or host.endswith(f".{x}") for x in tier1):
                return 1
        for d in domains:
            host = str(d or "").lower().strip()
            if any(host == x or host.endswith(f".{x}") for x in tier2):
                return 2
        return 3

    def get_source_profile_platforms(self, profile: str = "stable_mixed_v1") -> List[str]:
        """获取平台配置中的固定信源列表（仅返回当前可用平台）。"""
        candidates = list(self._source_profiles.get(profile, []))
        if not candidates:
            return []
        return [p for p in candidates if p in self.crawlers]

    def split_platform_pools(
        self, requested_platforms: Optional[List[str]] = None, profile: str = "stable_mixed_v1"
    ) -> Dict[str, List[str]]:
        """按 profile 把平台拆成 stable/experimental 两池。"""
        available = set(self.crawlers.keys())
        requested = (
            [p for p in (requested_platforms or []) if p in available]
            if requested_platforms
            else sorted(list(available))
        )
        stable_seed = set(self.get_source_profile_platforms(profile=profile))
        stable_pool = [p for p in requested if p in stable_seed]
        experimental_pool = [p for p in requested if p not in stable_seed]
        if not stable_pool:
            stable_pool = requested[: min(6, len(requested))]
            experimental_pool = [p for p in requested if p not in stable_pool]
        return {"stable_pool": stable_pool, "experimental_pool": experimental_pool}

    def _contains_cjk_keyword(self, keyword: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(keyword or "")))

    def _filter_platforms_by_search_registry(
        self,
        *,
        keyword: str,
        platforms: List[str],
    ) -> List[str]:
        registry = self._search_sources_registry
        if not registry:
            return list(platforms or [])
        rows = self.get_search_sources_snapshot()
        if not rows:
            return list(platforms or [])
        by_platform: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict):
                continue
            platform = str(row.get("platform") or "").strip().lower()
            if not platform:
                continue
            by_platform[platform].append(row)

        require_cn_for_zh = bool(
            getattr(settings, "SEARCH_SOURCES_REQUIRE_CN_FOR_ZH_QUERY", True)
        )
        is_zh_query = self._contains_cjk_keyword(keyword)
        selected: List[str] = []
        background: List[str] = []
        for raw in list(platforms or []):
            platform = str(raw or "").strip().lower()
            if not platform:
                continue
            source_rows = by_platform.get(platform)
            if not source_rows:
                # 未在 registry 的平台保持原行为（避免误伤已接入平台）
                selected.append(platform)
                continue
            if is_zh_query and require_cn_for_zh:
                has_zh = any(str(r.get("lang") or "").strip().lower() == "zh" for r in source_rows)
                if has_zh:
                    selected.append(platform)
                    continue
                is_background = any(
                    str(r.get("pool") or "").strip().lower() == "background"
                    for r in source_rows
                )
                if is_background:
                    background.append(platform)
                continue
            selected.append(platform)
        if background:
            logger.info(
                f"search source routing: move {len(background)} background platforms ({','.join(background[:8])})"
            )
        return selected

    def _annotate_items_with_search_source(
        self,
        *,
        platform: str,
        keyword: str,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(items, list) or not items:
            return []
        source_rows = self.get_search_sources_for_platform(platform)
        discovery_mode = "search"
        discovery_tier = "B"
        discovery_lang = "zh" if self._contains_cjk_keyword(keyword) else "en"
        discovery_pool = "evidence"
        source_id = ""
        if source_rows:
            first = source_rows[0]
            discovery_mode = str(first.get("discovery_mode") or discovery_mode).strip().lower()
            discovery_tier = str(first.get("tier") or discovery_tier).strip().upper()
            discovery_lang = str(first.get("lang") or discovery_lang).strip().lower()
            discovery_pool = str(first.get("pool") or discovery_pool).strip().lower()
            source_id = str(first.get("source_id") or "").strip()
        out: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            metadata = dict(metadata)
            metadata.setdefault("search_source_platform", str(platform))
            metadata.setdefault("search_source_mode", discovery_mode)
            metadata.setdefault("search_source_tier", discovery_tier)
            metadata.setdefault("search_source_lang", discovery_lang)
            metadata.setdefault("search_source_pool", discovery_pool)
            metadata.setdefault("search_source_id", source_id)
            metadata.setdefault("retrieval_query", str(keyword or ""))
            row["metadata"] = metadata
            out.append(row)
        return out

    def _init_crawlers(
        self,
        weibo_cookies: Optional[str],
        twitter_bearer_token: Optional[str],
        xhs_cookies: Optional[str],
        douyin_cookies: Optional[str],
        zhihu_cookies: Optional[str],
        bilibili_cookies: Optional[str],
        kuaishou_cookies: Optional[str],
        douban_cookies: Optional[str],
        reddit_client_id: Optional[str],
        reddit_client_secret: Optional[str],
        github_token: Optional[str],
        stackoverflow_api_key: Optional[str],
        openalex_email: Optional[str],
    ):
        """初始化所有爬虫实例"""

        # ==================== 原有社交媒体平台 ====================
        try:
            # WeiboCrawler 通过 settings 读取 cookie，不接收构造参数
            self.crawlers["weibo"] = WeiboCrawler()
            logger.info("✅ Weibo crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Weibo crawler init failed: {e}")

        try:
            self.crawlers["twitter"] = TwitterCrawler(bearer_token=twitter_bearer_token)
            logger.info("✅ Twitter crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Twitter crawler init failed: {e}")

        try:
            self.crawlers["xiaohongshu"] = XiaohongshuCrawler(cookies=xhs_cookies)
            logger.info("✅ Xiaohongshu crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Xiaohongshu crawler init failed: {e}")

        try:
            self.crawlers["douyin"] = DouyinCrawler(cookies=douyin_cookies)
            logger.info("✅ Douyin crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Douyin crawler init failed: {e}")

        try:
            self.crawlers["zhihu"] = ZhihuCrawler(cookies=zhihu_cookies)
            logger.info("✅ Zhihu crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Zhihu crawler init failed: {e}")

        try:
            self.crawlers["bilibili"] = BilibiliCrawler(cookies=bilibili_cookies)
            logger.info("✅ Bilibili crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Bilibili crawler init failed: {e}")

        try:
            self.crawlers["news"] = NewsAggregator()
            logger.info("✅ News aggregator initialized")
        except Exception as e:
            logger.warning(f"⚠️ News aggregator init failed: {e}")

        try:
            registry = self._rss_sources_registry
            sources = registry.get_rss_sources() if registry else []
            if sources:
                self.crawlers["rss_pool"] = RssPoolCrawler(sources=sources)
                self._rss_sources_snapshot = list(sources)
                logger.info(f"✅ RSS pool crawler initialized (sources={len(sources)})")
        except Exception as e:
            logger.warning(f"⚠️ RSS pool crawler init failed: {e}")

        try:
            self.crawlers["kuaishou"] = KuaishouCrawler(cookies=kuaishou_cookies)
            logger.info("✅ Kuaishou crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Kuaishou crawler init failed: {e}")

        try:
            self.crawlers["douban"] = DoubanCrawler(cookies=douban_cookies)
            logger.info("✅ Douban crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Douban crawler init failed: {e}")

        try:
            self.crawlers["reddit"] = RedditCrawler(
                client_id=reddit_client_id, client_secret=reddit_client_secret
            )
            logger.info("✅ Reddit crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Reddit crawler init failed: {e}")

        # ==================== 官方信源（从 OfficialSourcesManager 注入） ====================
        try:
            official_manager = OfficialSourcesManager()
            key_map = {
                "official_china_gov": "china_gov",
                "official_gov_cn": "china_gov",
                "official_samr": "samr",
                "official_csrc": "csrc",
                "official_nhc": "nhc",
                "official_mem": "mem",
                "official_mps": "mps",
                "official_supreme_court": "supreme_court",
                "official_supreme_procuratorate": "supreme_procuratorate",
                "official_xinhua": "xinhua",
                "official_people_daily": "peoples_daily",
                "official_who": "who",
                "official_cdc": "cdc",
                "official_un": "un_news",
                "official_sec": "sec",
                "official_fca": "fca_uk",
            }
            for src_key, crawler in official_manager.crawlers.items():
                mapped = key_map.get(src_key)
                if mapped:
                    self.crawlers[mapped] = crawler
            logger.info(
                "✅ Official source crawlers injected from OfficialSourcesManager"
            )
        except Exception as e:
            logger.warning(f"⚠️ Official source manager init failed: {e}")

        # ==================== 新闻媒体（从 InternationalNewsManager 注入） ====================
        try:
            news_manager = InternationalNewsManager()
            key_map = {
                "news_reuters": "reuters",
                "news_ap": "ap_news",
                "news_bbc": "bbc",
                "news_guardian": "guardian",
                "news_caixin": "caixin",
                "news_thepaper": "the_paper",
            }
            for src_key, crawler in news_manager.crawlers.items():
                mapped = key_map.get(src_key)
                if mapped:
                    self.crawlers[mapped] = crawler
            logger.info("✅ News crawlers injected from InternationalNewsManager")
        except Exception as e:
            logger.warning(f"⚠️ News manager init failed: {e}")

        # ==================== 社区论坛 ====================
        try:
            self.crawlers["github"] = GitHubEventsCrawler(access_token=github_token)
            logger.info("✅ GitHub Events crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ GitHub Events crawler init failed: {e}")

        try:
            self.crawlers["stackoverflow"] = StackOverflowCrawler(
                api_key=stackoverflow_api_key
            )
            logger.info("✅ Stack Overflow crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Stack Overflow crawler init failed: {e}")

        try:
            self.crawlers["quora"] = QuoraCrawler()
            logger.info("✅ Quora crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Quora crawler init failed: {e}")

        # ==================== 学术数据集 ====================
        try:
            self.crawlers["gdelt"] = GDELTCrawler()
            logger.info("✅ GDELT crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ GDELT crawler init failed: {e}")

        try:
            self.crawlers["common_crawl"] = CommonCrawlCrawler()
            logger.info("✅ Common Crawl crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ Common Crawl crawler init failed: {e}")

        try:
            self.crawlers["openalex"] = OpenAlexCrawler(email=openalex_email)
            logger.info("✅ OpenAlex crawler initialized")
        except Exception as e:
            logger.warning(f"⚠️ OpenAlex crawler init failed: {e}")

        logger.info(
            f"🚀 Crawler manager initialized with {len(self.crawlers)} platforms"
        )

    def get_crawler(self, platform: str):
        """获取指定平台的爬虫实例"""
        if platform not in self.crawlers:
            raise ValueError(
                f"Platform '{platform}' not supported. Available: {list(self.crawlers.keys())}"
            )
        return self.crawlers[platform]

    async def fetch_hot_topics_multi_platform(
        self, platforms: List[str] = None, limit_per_platform: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        从多个平台抓取热门话题

        Args:
            platforms: 平台列表（默认全部）
            limit_per_platform: 每个平台返回数量

        Returns:
            {platform_name: [topics]}
        """
        if platforms is None:
            platforms = list(self.crawlers.keys())

        logger.info(
            f"🔍 Fetching hot topics from {len(platforms)} platforms: {platforms}"
        )

        # 并行抓取所有平台（记录任务平台，避免索引错位）
        tasks = []
        task_platforms: List[str] = []
        for platform in platforms:
            if platform not in self.crawlers:
                continue
            crawler = self.crawlers[platform]
            task_platforms.append(platform)
            tasks.append(
                self._fetch_hot_topics_with_platform(
                    crawler, platform, limit_per_platform
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        hot_topics_by_platform = {}
        for i, platform in enumerate(task_platforms):
            if i >= len(results) or isinstance(results[i], Exception):
                logger.error(
                    f"❌ Error fetching from {platform}: "
                    f"{results[i] if i < len(results) else 'missing_result'}"
                )
                hot_topics_by_platform[platform] = []
            else:
                hot_topics_by_platform[platform] = results[i]

        total = sum(len(topics) for topics in hot_topics_by_platform.values())
        logger.info(
            f"✅ Fetched total {total} hot topics from {len(platforms)} platforms"
        )

        return hot_topics_by_platform

    async def _fetch_hot_topics_with_platform(
        self, crawler, platform: str, limit: int
    ) -> List[Dict[str, Any]]:
        """内部方法：从单个平台抓取热门话题"""
        try:
            topics = await crawler.fetch_hot_topics(limit=limit)
            logger.info(f"✅ {platform}: {len(topics)} hot topics")
            return topics
        except Exception as e:
            logger.error(f"❌ {platform} fetch failed: {e}")
            raise

    async def search_across_platforms(
        self,
        keyword: str,
        platforms: List[str] = None,
        limit_per_platform: int = 20,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
        max_concurrency: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        跨平台搜索关键词

        Args:
            keyword: 搜索关键词
            platforms: 平台列表（默认全部）
            limit_per_platform: 每个平台返回数量

        Returns:
            {platform_name: [posts]}
        """
        if platforms is None:
            platforms = list(self.crawlers.keys())
        platforms = self._filter_platforms_by_search_registry(
            keyword=keyword,
            platforms=[p for p in (platforms or []) if p in self.crawlers],
        )

        logger.info(
            f"🔍 Searching '{keyword}' across {len(platforms)} platforms: {platforms}"
        )

        task_platforms: List[str] = [p for p in platforms if p in self.crawlers]
        if not task_platforms:
            return {}

        default_concurrency = int(
            getattr(settings, "CRAWLER_SEARCH_MAX_CONCURRENCY", 8)
        )
        concurrency = max(
            1,
            min(
                len(task_platforms),
                int(max_concurrency or default_concurrency),
            ),
        )
        sem = asyncio.Semaphore(concurrency)
        results: List[Any] = [None] * len(task_platforms)

        async def _run(idx: int, platform: str) -> None:
            async with sem:
                try:
                    results[idx] = await self._search_platform(
                        platform,
                        keyword,
                        limit_per_platform,
                        mediacrawler_options=mediacrawler_options,
                    )
                except Exception as exc:
                    results[idx] = exc

        await asyncio.gather(
            *[_run(idx, platform) for idx, platform in enumerate(task_platforms)],
            return_exceptions=False,
        )

        # 整理结果
        search_results = {}
        for i, platform in enumerate(task_platforms):
            if i >= len(results) or isinstance(results[i], Exception):
                logger.error(
                    f"❌ Error searching {platform}: "
                    f"{results[i] if i < len(results) else 'missing_result'}"
                )
                search_results[platform] = []
            else:
                search_results[platform] = results[i]

        total = sum(len(posts) for posts in search_results.values())
        logger.info(
            f"✅ Found total {total} posts for '{keyword}' from {len(platforms)} platforms"
        )

        return search_results

    async def search_single_platform(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        在单个平台搜索（公开接口）

        Args:
            platform: 平台名称
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            搜索结果列表
        """
        if platform not in self.crawlers:
            raise ValueError(f"Platform '{platform}' not available")

        return await self._search_platform(
            platform,
            keyword,
            limit,
            mediacrawler_options=mediacrawler_options,
        )

    async def search_single_platform_verbose(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """在单个平台搜索并返回状态明细，便于编排层实时展示。"""
        started = time.monotonic()
        items: List[Dict[str, Any]] = []
        status = "ok"
        reason_code = "OK"
        message = ""
        sidecar_meta: Dict[str, Any] = {}
        try:
            search_row = await self._search_platform(
                platform=platform,
                keyword=keyword,
                limit=limit,
                mediacrawler_options=mediacrawler_options,
                return_diagnostics=True,
            )
            items = list((search_row or {}).get("items") or [])
            sidecar_meta = dict((search_row or {}).get("mediacrawler") or {})
            if not items:
                crawler = self.crawlers.get(platform)
                last_error_code = str(
                    getattr(crawler, "last_error_code", "") if crawler is not None else ""
                ).upper()
                if last_error_code in {
                    "PLATFORM_401",
                    "PLATFORM_402",
                    "PLATFORM_403",
                    "PLATFORM_429",
                    "CRAWLER_TIMEOUT",
                    "DNS_ERROR",
                    "MISSING_TOKEN",
                    "REQUEST_ERROR",
                }:
                    status = "error"
                    reason_code = last_error_code
                else:
                    status = "fallback"
                    reason_code = "FALLBACK_EMPTY" if self.enable_web_fallback else "EMPTY_RESULT"
                message = "no_items"

                # 对“自然语言问句”做一次轻量查询改写重试，避免平台搜索把语气词当噪声导致 0 命中。
                rewrite_retry_platforms = {
                    "weibo",
                    "zhihu",
                    "xinhua",
                    "peoples_daily",
                    "rss_pool",
                    "news",
                    "bilibili",
                    "xiaohongshu",
                    "douyin",
                    "kuaishou",
                    "douban",
                }
                if reason_code in {"FALLBACK_EMPTY", "EMPTY_RESULT"} and platform in rewrite_retry_platforms:
                    rewrite_queries = []
                    for q in self._keyword_query_variants(keyword)[1:4]:
                        qn = str(q or "").strip()
                        if not qn or qn == str(keyword or "").strip():
                            continue
                        if self._is_cjk_token(qn) and len(qn) < 3:
                            continue
                        if len(qn) < 3:
                            continue
                        rewrite_queries.append(qn)
                    for rewritten in rewrite_queries[:1]:
                        try:
                            retry_row = await self._search_platform(
                                platform=platform,
                                keyword=rewritten,
                                limit=limit,
                                mediacrawler_options=mediacrawler_options,
                                return_diagnostics=True,
                            )
                        except Exception:
                            continue
                        retry_items = list((retry_row or {}).get("items") or [])
                        if not retry_items:
                            continue
                        for item in retry_items:
                            if not isinstance(item, dict):
                                continue
                            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                            meta["query_rewritten_from"] = str(keyword or "")
                            meta["query_used"] = str(rewritten)
                            item["metadata"] = meta
                        items = retry_items
                        sidecar_meta = dict((retry_row or {}).get("mediacrawler") or sidecar_meta)
                        status = "ok"
                        reason_code = "QUERY_REWRITE_RECOVERED"
                        message = f"query_rewrite:{rewritten}"
                        break

                if items:
                    retrieval_modes = {
                        str((it.get("metadata") or {}).get("retrieval_mode", "")).lower()
                        for it in items
                        if isinstance(it, dict)
                    }
                    if "web_search_fallback" in retrieval_modes:
                        status = "fallback"
                        reason_code = "WEB_FALLBACK"
                    elif "rss_emergency_fallback" in retrieval_modes:
                        status = "fallback"
                        reason_code = "RSS_EMERGENCY_FALLBACK"
                    elif "hot_fallback" in retrieval_modes:
                        status = "fallback"
                        reason_code = "HOT_FALLBACK"
            else:
                retrieval_modes = {
                    str((it.get("metadata") or {}).get("retrieval_mode", "")).lower()
                    for it in items
                    if isinstance(it, dict)
                }
                if "web_search_fallback" in retrieval_modes:
                    status = "fallback"
                    reason_code = "WEB_FALLBACK"
                elif "rss_emergency_fallback" in retrieval_modes:
                    status = "fallback"
                    reason_code = "RSS_EMERGENCY_FALLBACK"
                elif "hot_fallback" in retrieval_modes:
                    status = "fallback"
                    reason_code = "HOT_FALLBACK"
                if (
                    sidecar_meta.get("triggered")
                    and sidecar_meta.get("mediacrawler_count", 0) > 0
                ):
                    reason_code = "MEDIACRAWLER_ENHANCED"
        except Exception as exc:
            message = str(exc)
            reason_code = self._normalize_reason_code(message)
            status = "timeout" if reason_code == "CRAWLER_TIMEOUT" else "error"
            items = []
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self._platform_reason_stats[platform][reason_code] += 1
        return {
            "platform": platform,
            "items": items,
            "status": status,
            "reason_code": reason_code,
            "message": message,
            "items_collected": len(items),
            "elapsed_ms": elapsed_ms,
            "mediacrawler": sidecar_meta,
        }

    async def search_across_platforms_verbose(
        self,
        keyword: str,
        platforms: Optional[List[str]] = None,
        limit_per_platform: int = 20,
        max_concurrency: Optional[int] = None,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """跨平台搜索并返回状态明细。"""
        if platforms is None:
            platforms = list(self.crawlers.keys())
        platforms = self._filter_platforms_by_search_registry(
            keyword=keyword,
            platforms=[p for p in (platforms or []) if p in self.crawlers],
        )

        task_platforms: List[str] = [p for p in platforms if p in self.crawlers]
        if not task_platforms:
            return {}
        default_concurrency = int(
            getattr(settings, "CRAWLER_SEARCH_MAX_CONCURRENCY", 8)
        )
        concurrency = max(
            1,
            min(
                len(task_platforms),
                int(max_concurrency or default_concurrency),
            ),
        )
        sem = asyncio.Semaphore(concurrency)
        raw: List[Any] = [None] * len(task_platforms)

        async def _run(idx: int, platform: str) -> None:
            async with sem:
                try:
                    raw[idx] = await self.search_single_platform_verbose(
                        platform=platform,
                        keyword=keyword,
                        limit=limit_per_platform,
                        mediacrawler_options=mediacrawler_options,
                    )
                except Exception as exc:
                    raw[idx] = exc

        await asyncio.gather(
            *[_run(idx, platform) for idx, platform in enumerate(task_platforms)],
            return_exceptions=False,
        )

        out: Dict[str, Dict[str, Any]] = {}
        for idx, platform in enumerate(task_platforms):
            row = raw[idx]
            if isinstance(row, Exception):
                msg = str(row)
                out[platform] = {
                    "platform": platform,
                    "items": [],
                    "status": "error",
                    "reason_code": self._normalize_reason_code(msg),
                    "message": msg,
                    "items_collected": 0,
                    "elapsed_ms": 0,
                    "mediacrawler": {},
                }
                continue
            out[platform] = row
        return out

    async def _search_platform(
        self,
        platform: str,
        keyword: str,
        limit: int,
        *,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
        return_diagnostics: bool = False,
    ) -> Any:
        """内部方法：在单个平台搜索"""
        crawler = self.crawlers[platform]
        started = time.monotonic()
        hot_limit = max(limit * self.hot_fallback_multiplier, limit)
        hot_limit = min(hot_limit, self.news_search_fetch_limit_cap)
        generic_hot_limit = max(limit * max(2, self.hot_fallback_multiplier), limit)
        generic_hot_limit = min(generic_hot_limit, self.news_search_fetch_limit_cap)
        skip_additional_fallback = False
        platform_api_error_code = ""
        sidecar_diag: Dict[str, Any] = {
            "platform": platform,
            "enabled": False,
            "active": False,
            "force_run": False,
            "triggered": False,
            "trigger_reason": "",
            "native_count": 0,
            "mediacrawler_count": 0,
            "merged_count": 0,
            "degraded": False,
            "error": "",
            "task_id": "",
            "provider": "native",
        }
        strict_search_only = bool(
            (mediacrawler_options or {}).get("strict_search_only", False)
        )
        if not strict_search_only:
            strict_search_only = bool(
                getattr(settings, "CRAWLER_DISABLE_HOT_FALLBACK_IN_SEARCH", True)
            )

        def _return(items: List[Dict[str, Any]]) -> Any:
            normalized_items = self._annotate_items_with_search_source(
                platform=platform,
                keyword=keyword,
                items=items,
            )
            if return_diagnostics:
                return {
                    "items": normalized_items,
                    "mediacrawler": sidecar_diag,
                }
            return normalized_items

        try:
            runtime_sidecar_options = self._build_mediacrawler_runtime_options(
                mediacrawler_options
            )
            sidecar_diag["enabled"] = bool(runtime_sidecar_options.get("enabled"))
            sidecar_diag["active"] = bool(runtime_sidecar_options.get("active"))
            sidecar_diag["force_run"] = bool(runtime_sidecar_options.get("force_run"))
            if not sidecar_diag["active"]:
                sidecar_diag["error"] = str(runtime_sidecar_options.get("reason") or "")

            fallback_first_enabled = platform in self._fallback_first_platforms
            if platform == "twitter" and bool(getattr(crawler, "bearer_token", None)):
                # With bearer token configured, try Twitter API first to avoid fallback-first timeout amplification.
                fallback_first_enabled = False
            if (
                platform in self._mediacrawler_supported_platforms
                and bool(runtime_sidecar_options.get("enabled"))
            ):
                # sidecar 社交平台优先走原生 + sidecar，不走 fallback-first 早退。
                fallback_first_enabled = False
            if fallback_first_enabled:
                fallback_first = await self._public_web_search_fallback(
                    platform=platform,
                    keyword=keyword,
                    limit=limit,
                    require_keyword_match=strict_search_only,
                )
                if fallback_first:
                    logger.warning(
                        f"{platform}: using fallback-first path, items={len(fallback_first)}"
                    )
                    self._record_platform_metric(
                        platform=platform,
                        success=True,
                        latency_ms=(time.monotonic() - started) * 1000.0,
                    )
                    return _return(fallback_first)

            # ==================== 社交媒体平台 ====================
            if platform == "weibo":
                results = await self._call_first_available_search(
                    crawler,
                    [
                        ("search_weibo", {"keyword": keyword, "limit": limit}),
                        ("search_content", {"keyword": keyword, "limit": limit}),
                    ],
                    platform=platform,
                )
            elif platform == "twitter":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_tweets", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
                platform_api_error_code = str(
                    getattr(crawler, "last_error_code", "") or ""
                ).upper()
                if (not results) and platform_api_error_code in {
                    "PLATFORM_401",
                    "PLATFORM_402",
                    "PLATFORM_403",
                    "PLATFORM_429",
                    "CRAWLER_TIMEOUT",
                    "DNS_ERROR",
                    "MISSING_TOKEN",
                    "REQUEST_ERROR",
                }:
                    skip_additional_fallback = True
                    logger.warning(
                        f"{platform}: API unavailable ({platform_api_error_code}), skip extra fallback fan-out"
                    )
            elif platform == "xiaohongshu":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_notes", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "douyin":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_videos", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "zhihu":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_content", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "bilibili":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_videos", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "kuaishou":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_videos", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "douban":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_groups", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "reddit":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_posts", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "news":
                results = await self._call_first_available_search(
                    crawler,
                    [("search_news", {"keyword": keyword, "limit": limit})],
                    platform=platform,
                )
            elif platform == "rss_pool":
                if hasattr(crawler, "search"):
                    results = await self._await_with_platform_timeout(
                        crawler.search(keyword=keyword, limit=limit),
                        platform=platform,
                        action="rss_pool_search",
                    )
                else:
                    all_items = await self._await_with_platform_timeout(
                        crawler.fetch_hot_topics(limit=hot_limit),
                        platform=platform,
                        action="rss_pool_hot_topics",
                    )
                    results = self._filter_items_by_keyword_with_fallback(
                        platform=platform,
                        items=all_items,
                        keyword=keyword,
                        limit=limit,
                        allow_hot_fallback=(not strict_search_only),
                    )

            # ==================== 官方信源 ====================
            # 官方信源通常通过fetch_latest获取最新公告，然后在结果中筛选关键词
            elif platform in [
                "china_gov",
                "samr",
                "csrc",
                "nhc",
                "mem",
                "mps",
                "supreme_court",
                "supreme_procuratorate",
                "xinhua",
                "peoples_daily",
                "who",
                "cdc",
                "un_news",
                "world_bank",
                "sec",
                "fca_uk",
                "eu_open_data",
            ]:
                # 官方信源优先使用其官方检索接口；无检索能力时退化为热点抓取+关键词筛选
                if hasattr(crawler, "search"):
                    try:
                        results = await self._await_with_platform_timeout(
                            crawler.search(keyword=keyword, limit=limit),
                            platform=platform,
                            action="official_search",
                        )
                    except Exception:
                        results = []
                else:
                    results = []

                if (not results) and hasattr(crawler, "fetch_hot_topics"):
                    all_items = await self._await_with_platform_timeout(
                        crawler.fetch_hot_topics(limit=hot_limit),
                        platform=platform,
                        action="official_hot_topics",
                    )
                    results = self._filter_items_by_keyword_with_fallback(
                        platform=platform,
                        items=all_items,
                        keyword=keyword,
                        limit=limit,
                        allow_hot_fallback=(not strict_search_only),
                    )

            # ==================== 新闻媒体 ====================
            elif platform in [
                "reuters",
                "ap_news",
                "bbc",
                "guardian",
                "caixin",
                "the_paper",
            ]:
                # RSS 媒体爬虫统一走 fetch_hot_topics
                all_items = await self._await_with_platform_timeout(
                    crawler.fetch_hot_topics(limit=hot_limit),
                    platform=platform,
                    action="news_hot_topics",
                )
                results = self._filter_items_by_keyword_with_fallback(
                    platform=platform,
                    items=all_items,
                    keyword=keyword,
                    limit=limit,
                    allow_hot_fallback=(not strict_search_only),
                )

            # ==================== 社区论坛 ====================
            elif platform == "github":
                # GitHub Events按类型过滤
                results = await self._call_first_available_search(
                    crawler,
                    [
                        ("fetch_events", {"event_type": keyword, "limit": limit}),
                        ("fetch_hot_topics", {"limit": limit}),
                    ],
                    platform=platform,
                )
            elif platform == "stackoverflow":
                # Stack Overflow搜索问题
                all_items = await self._call_first_available_search(
                    crawler,
                    [
                        ("search_questions", {"query": keyword, "limit": limit}),
                        ("fetch_hot_topics", {"limit": hot_limit}),
                    ],
                    platform=platform,
                )
                results = self._filter_items_by_keyword_with_fallback(
                    platform=platform,
                    items=all_items,
                    keyword=keyword,
                    limit=limit,
                    allow_hot_fallback=(not strict_search_only),
                )
            elif platform == "quora":
                # Quora (占位符)
                results = []

            # ==================== 学术数据集 ====================
            elif platform == "gdelt":
                # GDELT事件搜索
                results = await self._await_with_platform_timeout(
                    crawler.search_events(query=keyword, max_records=limit),
                    platform=platform,
                    action="gdelt_search",
                )
            elif platform == "common_crawl":
                # Common Crawl域名搜索
                results = await self._await_with_platform_timeout(
                    crawler.search_by_domain(domain=keyword, limit=limit),
                    platform=platform,
                    action="common_crawl_search",
                )
            elif platform == "openalex":
                # OpenAlex学术论文搜索
                results = await self._await_with_platform_timeout(
                    crawler.search_works(query=keyword, limit=limit),
                    platform=platform,
                    action="openalex_search",
                )

            else:
                results = []

            # 通用兜底：若搜索无命中且平台支持热点抓取，则返回热点样本（带关键词命中标记）
            if (
                (not results)
                and (not skip_additional_fallback)
                and (not strict_search_only)
                and hasattr(crawler, "fetch_hot_topics")
            ):
                try:
                    hot_items = await self._await_with_platform_timeout(
                        crawler.fetch_hot_topics(limit=generic_hot_limit),
                        platform=platform,
                        action="generic_hot_fallback",
                    )
                    hot_results = self._filter_items_by_keyword_with_fallback(
                        platform=platform,
                        items=hot_items,
                        keyword=keyword,
                        limit=limit,
                        allow_hot_fallback=(not strict_search_only),
                    )
                    if hot_results:
                        logger.warning(
                            f"{platform}: search returned empty, fallback to hot topics={len(hot_results)}"
                        )
                        results = hot_results
                except Exception as hot_err:
                    logger.warning(f"{platform}: hot fallback failed: {hot_err}")
            if (not results) and (not skip_additional_fallback):
                web_results = await self._public_web_search_fallback(
                    platform=platform,
                    keyword=keyword,
                    limit=limit,
                    require_keyword_match=strict_search_only,
                )
                if web_results:
                    logger.warning(
                        f"{platform}: empty after platform/hot fallback, use web fallback={len(web_results)}"
                    )
                    results = web_results

            # 社交平台增强：native -> sidecar 合并
            sidecar_diag["native_count"] = len(results or [])
            should_trigger, trigger_reason = self._should_trigger_mediacrawler(
                platform=platform,
                native_items=list(results or []),
                mediacrawler_options=runtime_sidecar_options,
            )
            sidecar_diag["trigger_reason"] = trigger_reason
            if should_trigger:
                sidecar_diag["triggered"] = True
                sidecar_rows = await self._collect_mediacrawler_posts(
                    platform=platform,
                    keyword=keyword,
                    timeout_sec=float(runtime_sidecar_options.get("timeout_sec") or 120.0),
                    max_items=max(
                        int(runtime_sidecar_options.get("max_items") or self._mediacrawler_max_items_per_platform),
                        int(limit),
                    ),
                )
                if sidecar_rows.get("ok"):
                    mc_items = list(sidecar_rows.get("items") or [])
                    sidecar_diag["task_id"] = str(sidecar_rows.get("task_id") or "")
                    sidecar_diag["mediacrawler_count"] = len(mc_items)
                    if mc_items:
                        results = self._merge_native_with_mediacrawler(
                            native_items=list(results or []),
                            mediacrawler_items=mc_items,
                            limit=limit,
                        )
                        sidecar_diag["merged_count"] = len(results or [])
                        sidecar_diag["provider"] = "native+mediacrawler"
                        logger.info(
                            f"{platform}: mediacrawler merged native={sidecar_diag['native_count']} + sidecar={len(mc_items)} -> {len(results or [])}"
                        )
                    else:
                        sidecar_diag["degraded"] = True
                        sidecar_diag["error"] = "MEDIACRAWLER_EMPTY"
                else:
                    sidecar_diag["degraded"] = True
                    sidecar_diag["error"] = str(
                        sidecar_rows.get("reason") or sidecar_rows.get("error") or "MEDIACRAWLER_FAILED"
                    )
                    logger.warning(
                        f"{platform}: mediacrawler degraded ({sidecar_diag['error']})"
                    )

            pre_keyword_gate_results = list(results or [])
            # 统一关键词门禁：防止某些平台分支直接返回热榜/通用流。
            if results:
                results = self._filter_items_by_keyword_with_fallback(
                    platform=platform,
                    items=list(results or []),
                    keyword=keyword,
                    limit=limit,
                    allow_hot_fallback=(not strict_search_only),
                )
                # sidecar 失败时允许软降级返回 native 兜底，避免完全空集
                if (
                    (not results)
                    and bool(sidecar_diag.get("degraded"))
                    and pre_keyword_gate_results
                ):
                    results = pre_keyword_gate_results[:limit]

            if results:
                logger.info(f"✅ {platform}: found {len(results)} posts for '{keyword}'")
                self._record_platform_metric(
                    platform=platform,
                    success=True,
                    latency_ms=(time.monotonic() - started) * 1000.0,
                )
            else:
                logger.warning(f"⚠️ {platform}: no data after all fallbacks for '{keyword}'")
                reason_hint = platform_api_error_code or "fallback empty"
                self._record_platform_metric(
                    platform=platform,
                    success=False,
                    latency_ms=(time.monotonic() - started) * 1000.0,
                    error=reason_hint,
                )
            return _return(results)
        except Exception as e:
            logger.error(f"❌ {platform} search failed: {e}")
            if platform == "twitter":
                api_reason = str(getattr(crawler, "last_error_code", "") or "").upper()
                if bool(getattr(crawler, "bearer_token", None)):
                    if api_reason in {
                        "PLATFORM_401",
                        "PLATFORM_402",
                        "PLATFORM_403",
                        "PLATFORM_429",
                        "CRAWLER_TIMEOUT",
                        "DNS_ERROR",
                        "MISSING_TOKEN",
                        "REQUEST_ERROR",
                    } or ("timed out" in str(e).lower() or "timeout" in str(e).lower()):
                        logger.warning(
                            f"{platform}: skip web fallback after api error ({api_reason or 'TIMEOUT'})"
                        )
                        self._record_platform_metric(
                            platform=platform,
                            success=False,
                            latency_ms=(time.monotonic() - started) * 1000.0,
                            error=api_reason or str(e),
                        )
                        return _return([])
            web_results = await self._public_web_search_fallback(
                platform=platform,
                keyword=keyword,
                limit=limit,
                require_keyword_match=strict_search_only,
            )
            if web_results:
                logger.warning(
                    f"{platform}: recovered by web fallback after search error, items={len(web_results)}"
                )
                self._record_platform_metric(
                    platform=platform,
                    success=True,
                    latency_ms=(time.monotonic() - started) * 1000.0,
                )
                return _return(web_results)
            logger.warning(f"{platform}: fallback empty after search error, return []")
            self._record_platform_metric(
                platform=platform,
                success=False,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error=f"fallback empty after error: {e}",
            )
            return _return([])

    async def _call_first_available_search(
        self,
        crawler: Any,
        method_specs: List[tuple[str, Dict[str, Any]]],
        platform: str = "unknown",
    ) -> List[Dict[str, Any]]:
        for method_name, kwargs in method_specs:
            fn = getattr(crawler, method_name, None)
            if not callable(fn):
                continue
            try:
                result = await self._await_with_platform_timeout(
                    fn(**kwargs),
                    platform=platform,
                    action=method_name,
                )
                return result if isinstance(result, list) else []
            except TypeError as e:
                logger.warning(f"search method {method_name} signature mismatch: {e}")
            except Exception:
                raise
        raise AttributeError(
            f"No available search method among {[name for name, _ in method_specs]}"
        )

    async def _await_with_platform_timeout(
        self,
        coro: Any,
        *,
        platform: str,
        action: str,
    ) -> Any:
        timeout_override = float(self._platform_timeout_overrides.get(platform, 0.0) or 0.0)
        timeout_sec = max(self.platform_search_timeout_seconds, timeout_override)
        timeout_sec = min(self.platform_search_timeout_max_seconds, timeout_sec)
        try:
            return await asyncio.wait_for(coro, timeout=timeout_sec)
        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"{platform}.{action} timed out after {timeout_sec:.1f}s"
            ) from e

    def _web_fallback_budget(self, platform: str) -> float:
        return max(
            3.0,
            float(
                self._web_fallback_budget_overrides.get(
                    platform, self._web_fallback_budget_sec_default
                )
            ),
        )

    async def _public_web_search_fallback(
        self,
        platform: str,
        keyword: str,
        limit: int,
        *,
        require_keyword_match: bool = False,
    ) -> List[Dict[str, Any]]:
        """公开网页检索兜底，确保无平台数据时仍有可分析样本。"""
        if not self.enable_web_fallback:
            return []
        rss_results = await self._rss_emergency_fallback(
            platform=platform,
            keyword=keyword,
            limit=limit,
            require_keyword_match=require_keyword_match,
        )
        if rss_results:
            return rss_results
        platform_key = str(platform or "").strip().lower()
        if self.enable_bocha_fallback and (
            not self._bocha_fallback_allowlist or platform_key in self._bocha_fallback_allowlist
        ):
            bocha_results = await self._bocha_web_search_fallback(
                platform=platform,
                keyword=keyword,
                limit=limit,
                require_keyword_match=require_keyword_match,
            )
            if bocha_results:
                return bocha_results
        domains = self.get_platform_domains(platform)
        if not domains:
            domains = [platform]
        query_scope = " OR ".join(f"site:{d}" for d in domains[:5])
        keyword_tokens = self._keyword_tokens(keyword)
        relaxed_keyword = " ".join(keyword_tokens[:3]) if keyword_tokens else ""
        query_variants = self._keyword_query_variants(keyword)
        queries: List[str] = []
        for query in query_variants:
            val = str(query or "").strip()
            if val and val not in queries:
                queries.append(val)
        if not queries:
            fallback_query = str(keyword or "").strip()
            if fallback_query:
                queries.append(fallback_query)
        if relaxed_keyword and all(relaxed_keyword.lower() != q.lower() for q in queries):
            queries.append(relaxed_keyword)
        max_query_variants = 2 if platform in self._fallback_first_platforms else 3
        candidate_urls: List[tuple[str, str]] = []
        for q in queries[:max_query_variants]:
            encoded = quote(f"{q} ({query_scope})")
            candidate_urls.extend(
                [
                    ("rjina_ddg_html", f"https://r.jina.ai/http://duckduckgo.com/html/?q={encoded}"),
                    ("ddg_html", f"https://duckduckgo.com/html/?q={encoded}"),
                ]
            )
        errors: List[str] = []
        threshold = float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2))
        fallback_started = time.monotonic()
        budget_sec = self._web_fallback_budget(platform)
        async with self._web_fallback_semaphore:
            for trust_env in self._httpx_trust_env_candidates():
                if (time.monotonic() - fallback_started) >= budget_sec:
                    errors.append(f"budget_exhausted:{budget_sec:.1f}s")
                    break
                try:
                    remaining = max(0.8, budget_sec - (time.monotonic() - fallback_started))
                    connect_timeout = max(
                        0.8,
                        float(
                            getattr(
                                settings,
                                "CRAWLER_WEB_FALLBACK_CONNECT_TIMEOUT_SECONDS",
                                2.0,
                            )
                        ),
                    )
                    read_timeout = max(
                        connect_timeout,
                        float(
                            getattr(
                                settings,
                                "CRAWLER_WEB_FALLBACK_READ_TIMEOUT_SECONDS",
                                max(self.web_fallback_timeout_seconds, 5.0),
                            )
                        ),
                    )
                    req_timeout = min(
                        max(read_timeout, connect_timeout),
                        remaining,
                    )
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(req_timeout, connect=min(connect_timeout, req_timeout)),
                        follow_redirects=True,
                        trust_env=trust_env,
                    ) as client:
                        async def _fetch_candidate(backend: str, url: str) -> List[Dict[str, Any]]:
                            if (time.monotonic() - fallback_started) >= budget_sec:
                                return []
                            try:
                                text = (await client.get(url)).text or ""
                                links = self._extract_links_from_search_text(text=text)
                                out: List[Dict[str, Any]] = []
                                for title, link in links:
                                    link = link.rstrip(".,;)]}>\"'")
                                    try:
                                        host = (urlparse(link).hostname or "").lower()
                                    except Exception:
                                        continue
                                    if not any(host == d or host.endswith(f".{d}") for d in domains):
                                        continue
                                    if not self._looks_like_specific_result_url(link):
                                        continue
                                    if len(out) >= limit:
                                        break
                                    kw_hit = False
                                    kw_score = 0.0
                                    matched_query = ""
                                    for query in query_variants[:5] or [keyword]:
                                        query_hit, query_score = self._keyword_hit(
                                            keyword=query,
                                            blob=f"{title}\n{link}",
                                            threshold=threshold,
                                        )
                                        if query_hit and (not kw_hit or query_score > kw_score):
                                            kw_hit = True
                                            kw_score = query_score
                                            matched_query = str(query)
                                    if require_keyword_match and keyword_tokens and (not kw_hit):
                                        continue
                                    out.append(
                                        {
                                            "id": f"{platform}_web_{len(out)+1}",
                                            "url": link,
                                            "title": (title or f"{platform} web result")[:160],
                                            "content": f"web_search_fallback hit for {platform}",
                                            "author": "web-search",
                                            "created_at": datetime.utcnow().isoformat(),
                                            "metadata": {
                                                "keyword_match": kw_hit,
                                                "keyword_match_score": round(float(kw_score), 4),
                                                "keyword_query_used": matched_query,
                                                "keyword_query_variants": list(query_variants[:5]),
                                                "retrieval_mode": "web_search_fallback",
                                                "web_search_backend": backend,
                                                "web_search_trust_env": trust_env,
                                                "likes": 0,
                                                "comments": 0,
                                                "shares": 0,
                                            },
                                            "source_platform": platform,
                                        }
                                    )
                                if out:
                                    out.sort(
                                        key=lambda x: (
                                            bool((x.get("metadata") or {}).get("keyword_match")),
                                            float((x.get("metadata") or {}).get("keyword_match_score") or 0.0),
                                        ),
                                        reverse=True,
                                    )
                                return out
                            except Exception as e:
                                errors.append(
                                    f"{backend}[trust_env={int(bool(trust_env))}]:{type(e).__name__}:{e}"
                                )
                                return []

                        rows = await asyncio.gather(
                            *[_fetch_candidate(backend, url) for backend, url in candidate_urls],
                            return_exceptions=False,
                        )
                        best: List[Dict[str, Any]] = []
                        best_score = -1.0
                        for row in rows:
                            if not row:
                                continue
                            score = (
                                sum(
                                    1
                                    for item in row
                                    if bool((item.get("metadata") or {}).get("keyword_match"))
                                )
                                * 10
                                + len(row)
                            )
                            if score > best_score:
                                best_score = float(score)
                                best = row
                        if best:
                            self._fallback_trust_env_hint = bool(trust_env)
                            return best[:limit]
                except Exception as e:
                    errors.append(
                        f"client[trust_env={int(bool(trust_env))}]:{type(e).__name__}:{e}"
                    )
        if errors:
            logger.warning(
                f"{platform}: public web fallback failed: {' | '.join(errors[:3])}"
            )
        return []

    async def _bocha_web_search_fallback(
        self,
        *,
        platform: str,
        keyword: str,
        limit: int,
        require_keyword_match: bool,
    ) -> List[Dict[str, Any]]:
        provider = BochaSearchProvider()
        if not provider.enabled:
            return []
        domains = self.get_platform_domains(platform)
        if not domains:
            return []

        query_variants = self._keyword_query_variants(keyword)
        if not query_variants:
            query_variants = [str(keyword or "").strip()]
        threshold = float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2))

        # Bocha 回退只做轻量补量，避免 429：每次少量抓取 + 查询结果缓存。
        fetch_limit = max(
            10,
            min(
                80,
                int(limit) * int(self._bocha_fallback_fetch_multiplier),
            ),
        )
        seen_urls: set[str] = set()
        out: List[Dict[str, Any]] = []
        query_rows = query_variants[: max(1, int(self._bocha_fallback_max_query_variants))]
        now_ts = time.monotonic()
        for query_row in query_rows:
            rows: List[Dict[str, Any]]
            if provider.enable_site_scoped_queries:
                domain_sig = ",".join(sorted(str(d).strip().lower() for d in domains[:6] if str(d).strip()))
                cache_key = f"{str(query_row or '').strip().lower()}|{domain_sig}|{fetch_limit}"
            else:
                cache_key = f"{str(query_row or '').strip().lower()}|{fetch_limit}"
            cache_row = self._bocha_fallback_cache.get(cache_key)
            if cache_row and (now_ts - float(cache_row[0])) <= float(self._bocha_fallback_cache_ttl_sec):
                rows = [dict(x) for x in (cache_row[1] or []) if isinstance(x, dict)]
            else:
                allowed = list(domains[:6]) if provider.enable_site_scoped_queries else None
                try:
                    rows = await provider.search_news(
                        query=query_row,
                        limit=fetch_limit,
                        allowed_domains=allowed,
                    )
                except Exception:
                    rows = []
                if len(self._bocha_fallback_cache) > 256:
                    self._bocha_fallback_cache = {}
                self._bocha_fallback_cache[cache_key] = (
                    time.monotonic(),
                    [dict(x) for x in rows if isinstance(x, dict)],
                )
            for row in rows:
                link = str(row.get("url") or "").strip()
                title = str(row.get("title") or "").strip()
                if not link or not title:
                    continue
                try:
                    host = (urlparse(link).hostname or "").lower()
                except Exception:
                    continue
                domain_matched = any(host == d or host.endswith(f".{d}") for d in domains)
                if not domain_matched:
                    platform_key = str(platform or "").strip().lower()
                    if not (
                        self._bocha_allow_cross_domain_social
                        and platform_key in self._bocha_social_platforms
                    ):
                        continue
                if not self._looks_like_specific_result_url(link):
                    continue
                normalized = self._normalized_url_for_key(link)
                if normalized and normalized in seen_urls:
                    continue
                kw_hit = False
                kw_score = 0.0
                matched_query = ""
                for qv in query_variants[:5]:
                    q_hit, q_score = self._keyword_hit(
                        keyword=qv,
                        blob=f"{title}\n{row.get('summary') or ''}\n{link}",
                        threshold=threshold,
                    )
                    if q_hit and (not kw_hit or q_score > kw_score):
                        kw_hit = True
                        kw_score = q_score
                        matched_query = str(qv)
                if require_keyword_match and not kw_hit:
                    continue
                if normalized:
                    seen_urls.add(normalized)
                out.append(
                    {
                        "id": f"{platform}_bocha_{len(out)+1}",
                        "url": link,
                        "title": title[:160],
                        "content": f"web_search_fallback hit for {platform}",
                        "author": "web-search",
                        "created_at": datetime.utcnow().isoformat(),
                        "metadata": {
                            "keyword_match": kw_hit,
                            "keyword_match_score": round(float(kw_score), 4),
                            "keyword_query_used": matched_query,
                            "keyword_query_variants": list(query_variants[:5]),
                            "retrieval_mode": "web_search_fallback",
                            "web_search_backend": "bocha_api",
                            "web_search_trust_env": True,
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                        },
                        "source_platform": platform,
                    }
                )
                if len(out) >= int(limit):
                    break
            if len(out) >= int(limit):
                break
        if out:
            out.sort(
                key=lambda x: (
                    bool((x.get("metadata") or {}).get("keyword_match")),
                    float((x.get("metadata") or {}).get("keyword_match_score") or 0.0),
                ),
                reverse=True,
            )
            logger.warning(
                f"{platform}: bocha web fallback recovered items={len(out[:limit])}"
            )
        return out[:limit]

    async def _rss_emergency_fallback(
        self,
        platform: str,
        keyword: str,
        limit: int,
        *,
        require_keyword_match: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        轻量 RSS 兜底：在平台主抓取超时/失败时，从稳定公开 RSS 快速拿到可追溯 URL。
        """
        fallback_feed_urls: Dict[str, List[str]] = {
            "qq_news": [
                "https://news.google.com/rss/search?q=site:news.qq.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            ],
            "cctv": [
                "https://news.google.com/rss/search?q=site:news.cctv.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
                "https://news.google.com/rss/search?q=site:cctv.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            ],
            "bbc": [
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "https://feeds.bbci.co.uk/news/rss.xml",
            ],
            "guardian": [
                "https://www.theguardian.com/world/rss",
                "https://www.theguardian.com/international/rss",
            ],
            "reuters": [
                "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
                "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
            ],
            "ap_news": [
                "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
                "https://feeds.apnews.com/rss/apf-topnews",
            ],
            "who": [
                "https://www.who.int/rss-feeds/news-english.xml",
                "https://www.who.int/news-room",
            ],
            "people": [
                "https://www.people.com.cn/rss/politics.xml",
                "https://www.people.com.cn/rss/world.xml",
            ],
            "chinanews": [
                "https://www.chinanews.com/rss/scroll-news.xml",
            ],
            "guancha": [
                "https://www.guancha.cn/rss/",
            ],
            "thepaper": [
                "https://thepaper.cn/rss/feed.xml",
            ],
            "caixin": [
                "https://rsshub.app/caixin/news",
            ],
            "un_news": [
                "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
            ],
            "sec": [
                "https://www.sec.gov/news/pressreleases.rss",
            ],
            "xinhua": [],
        }
        dynamic_search_feeds: List[str] = []
        kw_encoded = quote(str(keyword or "").strip())
        if kw_encoded:
            platform_query_domains: Dict[str, List[str]] = {
                "xinhua": ["news.cn", "xinhuanet.com"],
                "peoples_daily": ["people.com.cn", "paper.people.com.cn"],
                "chinanews": ["chinanews.com.cn"],
                "cctv": ["news.cctv.com", "cctv.com"],
                "china_gov": ["gov.cn"],
                "samr": ["samr.gov.cn"],
                "csrc": ["csrc.gov.cn"],
                "nhc": ["nhc.gov.cn"],
                "mem": ["mem.gov.cn"],
                "mps": ["mps.gov.cn"],
                "the_paper": ["thepaper.cn"],
                "caixin": ["caixin.com"],
                "bbc": ["bbc.com", "bbc.co.uk"],
                "guardian": ["theguardian.com"],
                "reuters": ["reuters.com"],
                "ap_news": ["apnews.com"],
            }

            def _build_domain_query_feeds(domains: List[str]) -> List[str]:
                return [
                    f"https://news.google.com/rss/search?q={kw_encoded}+site:{d}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
                    for d in (domains or [])
                ]

            if platform == "rss_pool":
                zh_priority = [
                    "news.cn",
                    "xinhuanet.com",
                    "people.com.cn",
                    "paper.people.com.cn",
                    "chinanews.com.cn",
                    "news.cctv.com",
                    "gov.cn",
                    "samr.gov.cn",
                    "csrc.gov.cn",
                    "nhc.gov.cn",
                    "mem.gov.cn",
                    "mps.gov.cn",
                    "thepaper.cn",
                    "caixin.com",
                ]
                dynamic_search_feeds.extend(_build_domain_query_feeds(zh_priority))
                # 综合中文检索，补齐域名之外的同义表达命中。
                dynamic_search_feeds.append(
                    f"https://news.google.com/rss/search?q={kw_encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
                )
            else:
                dynamic_search_feeds.extend(
                    _build_domain_query_feeds(platform_query_domains.get(platform, []))
                )
        backup_urls = list(self.get_platform_backup_urls(platform))
        if platform == "rss_pool":
            # rss_pool 备份源较多，先保留更像 RSS 的链接，避免预算被目录页/慢源耗尽。
            compact_backup: List[str] = []
            for url in backup_urls:
                lower = str(url or "").lower()
                if any(tag in lower for tag in ("/rss", "rss.", ".xml", "/feed", "news.google.com/rss/")):
                    compact_backup.append(url)
            if compact_backup:
                backup_urls = compact_backup[:16]

        # 查询场景优先 dynamic search feeds，提升关键词命中速度。
        candidates = list(
            dict.fromkeys(
                dynamic_search_feeds
                + list(fallback_feed_urls.get(platform, []))
                + backup_urls
            )
        )
        if not candidates:
            return []

        domains = self.get_platform_domains(platform)
        kw = str(keyword or "").strip()
        threshold = float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2))
        items: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        errors: List[str] = []
        fallback_started = time.monotonic()
        budget_sec = self._web_fallback_budget(platform)

        async with self._web_fallback_semaphore:
            for trust_env in self._httpx_trust_env_candidates():
                if (time.monotonic() - fallback_started) >= budget_sec:
                    errors.append(f"budget_exhausted:{budget_sec:.1f}s")
                    break
                if len(items) >= limit:
                    break
                try:
                    remaining = max(0.8, budget_sec - (time.monotonic() - fallback_started))
                    connect_timeout = max(
                        0.8,
                        float(
                            getattr(
                                settings,
                                "CRAWLER_WEB_FALLBACK_CONNECT_TIMEOUT_SECONDS",
                                2.0,
                            )
                        ),
                    )
                    read_timeout = max(
                        connect_timeout,
                        float(
                            getattr(
                                settings,
                                "CRAWLER_WEB_FALLBACK_READ_TIMEOUT_SECONDS",
                                max(self.web_fallback_timeout_seconds, 5.0),
                            )
                        ),
                    )
                    req_timeout = min(max(read_timeout, connect_timeout), remaining)
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(req_timeout, connect=min(connect_timeout, req_timeout)),
                        follow_redirects=True,
                        trust_env=trust_env,
                    ) as client:
                        for feed_url in candidates:
                            if (time.monotonic() - fallback_started) >= budget_sec:
                                break
                            if len(items) >= limit:
                                break
                            try:
                                text = (await client.get(feed_url)).text or ""
                                parsed = feedparser.parse(text)
                                entries = list(getattr(parsed, "entries", []) or [])
                                if not entries:
                                    continue
                                for entry in entries:
                                    if len(items) >= limit:
                                        break
                                    url = str(entry.get("link", "") or "").strip()
                                    title = str(entry.get("title", "") or "").strip()
                                    summary = str(entry.get("summary", "") or "").strip()
                                    src_meta = entry.get("source") if isinstance(entry.get("source"), dict) else {}
                                    source_href = str(src_meta.get("href", "") or "").strip()
                                    source_title = str(src_meta.get("title", "") or "").strip()
                                    if not url or not self._looks_like_specific_result_url(url):
                                        continue
                                    try:
                                        host = (urlparse(url).hostname or "").lower()
                                    except Exception:
                                        continue
                                    source_domain = ""
                                    if source_href:
                                        try:
                                            source_domain = (urlparse(source_href).hostname or "").lower()
                                        except Exception:
                                            source_domain = ""
                                    domain_allowed = True
                                    if domains:
                                        domain_allowed = any(
                                            host == d or host.endswith(f".{d}") for d in domains
                                        )
                                        if (not domain_allowed) and host in {"news.google.com", "news.googleusercontent.com"} and source_domain:
                                            domain_allowed = any(
                                                source_domain == d or source_domain.endswith(f".{d}")
                                                for d in domains
                                            )
                                    if not domain_allowed:
                                        continue
                                    if url in seen_urls:
                                        continue
                                    kw_hit, kw_score = self._keyword_hit(
                                        keyword=kw,
                                        blob=f"{title}\n{summary}\n{url}",
                                        threshold=threshold,
                                    )
                                    if kw and (not kw_hit):
                                        # 严格模式下，fallback 也必须命中关键词，避免热榜/通稿污染。
                                        if require_keyword_match:
                                            continue
                                        # 非严格模式下保留少量非精确命中，避免完全无数据。
                                        if len(items) >= max(2, limit // 2):
                                            continue
                                    seen_urls.add(url)
                                    items.append(
                                        {
                                            "id": f"{platform}_rss_{len(items) + 1}",
                                            "url": url,
                                            "title": (title or f"{platform} rss result")[:160],
                                            "content": summary[:1200],
                                            "author": platform,
                                            "created_at": datetime.utcnow().isoformat(),
                                            "metadata": {
                                                "keyword_match": kw_hit,
                                                "keyword_match_score": round(float(kw_score), 4),
                                                "retrieval_mode": "rss_emergency_fallback",
                                                "rss_feed_url": feed_url,
                                                "rss_trust_env": trust_env,
                                                "source_href": source_href,
                                                "source_title": source_title,
                                                "source_domain": source_domain,
                                                "likes": 0,
                                                "comments": 0,
                                                "shares": 0,
                                            },
                                            "source_platform": platform,
                                        }
                                    )
                            except Exception as e:
                                errors.append(
                                    f"{feed_url}[trust_env={int(bool(trust_env))}]:{type(e).__name__}:{e}"
                                )
                                continue
                except Exception as e:
                    errors.append(
                        f"rss_client[trust_env={int(bool(trust_env))}]:{type(e).__name__}:{e}"
                    )

        if items:
            self._fallback_trust_env_hint = bool(
                (items[0].get("metadata") or {}).get("rss_trust_env")
            )
            logger.warning(
                f"{platform}: rss emergency fallback recovered items={len(items)}"
            )
            return items[:limit]
        if errors:
            logger.warning(
                f"{platform}: rss emergency fallback failed: {' | '.join(errors[:2])}"
            )
        return []

    def _httpx_trust_env_candidates(self) -> List[bool]:
        """返回 httpx trust_env 的尝试顺序：优先当前策略，失败再尝试相反值。"""
        if bool(getattr(settings, "HTTPX_TRUST_ENV_ONLY", True)):
            return [bool(_HTTPX_TRUST_ENV)]
        has_proxy_env = any(
            bool(os.getenv(k))
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
        )
        if bool(_HTTPX_TRUST_ENV) and has_proxy_env:
            # 代理环境已配置时优先走 trust_env=True，避免在短预算内被直连超时耗尽。
            return [True, False]
        out: List[bool] = []
        preferred = (
            self._fallback_trust_env_hint
            if self._fallback_trust_env_hint is not None
            else True
        )
        for val in (
            preferred,
            not preferred,
            _HTTPX_TRUST_ENV,
            not _HTTPX_TRUST_ENV,
        ):
            if val is None:
                continue
            if val not in out:
                out.append(bool(val))
        return out

    def _extract_links_from_search_text(self, text: str) -> List[tuple[str, str]]:
        links: List[tuple[str, str]] = []
        if not text:
            return links
        # markdown links
        for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
            links.append((title, url))
        # absolute urls
        for url in re.findall(r"(https?://[^\s\])>\"']+)", text):
            links.append(("", url))
        # duckduckgo redirect links /l/?uddg=
        for path in re.findall(r'href=[\"\']((?:https?://duckduckgo\.com)?/l/\\?[^\"\']+)[\"\']', text):
            parsed = urlparse(path)
            q = parse_qs(parsed.query)
            uddg = unquote((q.get("uddg") or [""])[0] or "")
            if uddg.startswith("http://") or uddg.startswith("https://"):
                links.append(("", uddg))
        # dedupe while preserving order
        seen = set()
        out: List[tuple[str, str]] = []
        for title, url in links:
            u = str(url or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            out.append((title, u))
        return out

    def _looks_like_specific_result_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            path = (parsed.path or "").strip("/")
            query = (parsed.query or "").lower()
        except Exception:
            return False
        if not host or not path:
            return False
        if any(k in query for k in ["q=", "query=", "search=", "keyword="]):
            return False
        bad_path_tokens = {"search", "topic", "topics", "tag", "tags", "home", "index"}
        parts = [p.lower() for p in path.split("/") if p.strip()]
        if any(p in bad_path_tokens for p in parts):
            return False
        return True

    def _record_platform_metric(
        self, platform: str, success: bool, latency_ms: float, error: str = ""
    ) -> None:
        row = self._platform_metrics[platform]
        row["calls"] += 1
        row["total_latency_ms"] += max(0.0, float(latency_ms))
        if success:
            row["success"] += 1
            try:
                crawler_platform_success_total.labels(platform=platform).inc()
            except Exception:
                pass
            return
        reason = self._normalize_reason_code(error)
        self._platform_reason_stats[platform][reason] += 1
        if "timeout" in (error or "").lower():
            row["timeout"] += 1
            try:
                crawler_platform_timeout_total.labels(platform=platform).inc()
            except Exception:
                pass

    def _normalize_reason_code(self, error: str) -> str:
        low = str(error or "").lower()
        if (
            "temporary failure in name resolution" in low
            or "name or service not known" in low
            or "nodename nor servname provided" in low
            or "gaierror" in low
        ):
            return "DNS_ERROR"
        if (
            "proxy" in low
            and ("connection refused" in low or "failed to connect" in low or "cannot connect" in low)
        ) or ("127.0.0.1:7897" in low and "connect" in low):
            return "PROXY_UNREACHABLE"
        if "tls" in low and "timeout" in low:
            return "TLS_TIMEOUT"
        if "ssl handshake" in low:
            return "TLS_TIMEOUT"
        if "timed out" in low or "timeout" in low:
            return "CRAWLER_TIMEOUT"
        if "401" in low:
            return "PLATFORM_401"
        if "402" in low:
            return "PLATFORM_402"
        if "403" in low:
            return "PLATFORM_403"
        if "404" in low:
            return "PLATFORM_404"
        if "429" in low:
            return "PLATFORM_429"
        if "unreachable" in low or "connection refused" in low:
            return "UNREACHABLE"
        if "quota" in low:
            return "QUOTA_EXCEEDED"
        if "token" in low and "overflow" in low:
            return "TOKEN_OVERFLOW"
        if "fallback" in low and "empty" in low:
            return "FALLBACK_EMPTY"
        return "CRAWLER_ERROR"

    def get_platform_health_snapshot(self) -> Dict[str, Dict[str, float]]:
        """返回平台健康快照，用于编排层做动态回退决策。"""
        out: Dict[str, Dict[str, float]] = {}
        for platform, row in self._platform_metrics.items():
            calls = max(1.0, row["calls"])
            success_rate = row["success"] / calls
            timeout_rate = row["timeout"] / calls
            avg_latency_ms = row["total_latency_ms"] / calls
            # 简单健康评分：成功率优先，超时率惩罚，延迟轻惩罚
            latency_penalty = min(0.3, avg_latency_ms / 8000.0)
            health_score = max(
                0.0,
                min(1.0, success_rate * 0.75 + (1.0 - timeout_rate) * 0.25 - latency_penalty),
            )
            out[platform] = {
                "calls": round(row["calls"], 0),
                "success_rate": round(success_rate, 4),
                "timeout_rate": round(timeout_rate, 4),
                "avg_latency_ms": round(avg_latency_ms, 2),
                "health_score": round(health_score, 4),
            }
        return out

    def get_platform_reason_stats(self) -> Dict[str, Dict[str, int]]:
        return {
            platform: {reason: int(count) for reason, count in reasons.items()}
            for platform, reasons in self._platform_reason_stats.items()
        }

    def get_last_comment_sidecar_diag(self) -> Dict[str, Any]:
        diag = self._last_comment_sidecar_diag
        if not isinstance(diag, dict):
            return {"fetched_at": "", "hit_count": 0, "failures": [], "enabled": False}
        return {
            "fetched_at": str(diag.get("fetched_at") or ""),
            "hit_count": int(diag.get("hit_count") or 0),
            "enabled": bool(diag.get("enabled")),
            "failures": [row for row in list(diag.get("failures") or []) if isinstance(row, dict)],
        }

    @staticmethod
    def _is_cjk_token(token: str) -> bool:
        return bool(token) and bool(re.fullmatch(r"[\u4e00-\u9fff]+", str(token)))

    def _expand_cjk_token(self, token: str) -> List[str]:
        out: List[str] = []
        base = str(token or "").strip()
        if len(base) < 2 or not self._is_cjk_token(base):
            return out

        def _append(val: str) -> None:
            value = str(val or "").strip()
            if len(value) >= 2 and value not in out:
                out.append(value)

        _append(base)
        trimmed = re.sub(r"[了啊呀嘛吧呢吗哈]+$", "", base).strip()
        _append(trimmed)

        cjk_hints = (
            "退役",
            "复出",
            "夺冠",
            "去世",
            "辟谣",
            "回应",
            "宣布",
            "否认",
            "确认",
            "爆料",
            "传闻",
            "处罚",
        )
        for hint in cjk_hints:
            pos = base.find(hint)
            if pos > 0:
                prefix = base[:pos].strip()
                if len(prefix) >= 2:
                    _append(prefix)
                    _append(f"{prefix}{hint}")

        if len(base) >= 4:
            max_grams = 24
            used = 0
            for n in (2, 3):
                if len(base) < n:
                    continue
                for idx in range(0, len(base) - n + 1):
                    _append(base[idx : idx + n])
                    used += 1
                    if used >= max_grams:
                        break
                if used >= max_grams:
                    break
        return out

    def _keyword_tokens(self, text: str) -> List[str]:
        rows = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", str(text or "").lower())
        out: List[str] = []
        for row in rows:
            token = str(row or "").strip()
            if len(token) < 2:
                continue
            if token not in out:
                out.append(token)
            if self._is_cjk_token(token):
                for ext in self._expand_cjk_token(token):
                    if ext not in out:
                        out.append(ext)
        return out

    def _entity_tokens(self, text: str) -> List[str]:
        # 粗粒度实体片段：优先长 token（人名/机构名/地名），避免短词噪声触发。
        out: List[str] = []
        for token in self._keyword_tokens(text):
            if len(token) >= 3 or (self._is_cjk_token(token) and len(token) >= 2):
                if token not in out:
                    out.append(token)
        return out

    def _keyword_query_variants(self, keyword: str) -> List[str]:
        base = str(keyword or "").strip()
        if not base:
            return []

        variants: List[str] = [base]
        entities = self._entity_tokens(base)
        tokens = self._keyword_tokens(base)

        # 常见中文语气词裁剪，降低“整句命中失败”概率
        normalized_base = re.sub(r"[？?]+$", "", base).strip()
        trimmed = re.sub(r"[了啊呀嘛吧呢吗么]+$", "", normalized_base).strip()
        if trimmed and trimmed not in variants:
            variants.append(trimmed)

        cjk_hints = (
            "退役",
            "复出",
            "夺冠",
            "去世",
            "辟谣",
            "回应",
            "宣布",
            "否认",
            "确认",
            "爆料",
            "传闻",
            "处罚",
        )
        cjk_chunks = re.findall(r"[\u4e00-\u9fff]{3,}", base)
        for chunk in cjk_chunks[:2]:
            for hint in cjk_hints:
                pos = chunk.find(hint)
                if pos > 0:
                    prefix = chunk[:pos].strip()
                    if len(prefix) >= 2 and prefix not in variants:
                        variants.append(prefix)
                    phrase = f"{prefix}{hint}".strip()
                    if len(phrase) >= 3 and phrase not in variants:
                        variants.append(phrase)

        for row in entities[:3]:
            val = str(row).strip()
            if val and val not in variants:
                variants.append(val)
        for row in tokens[:4]:
            val = str(row).strip()
            if val and val not in variants:
                variants.append(val)

        return variants[:8]

    def _keyword_match_score(self, keyword: str, blob: str) -> float:
        kw_tokens = set(self._keyword_tokens(keyword))
        tx_tokens = set(self._keyword_tokens(blob))
        if not kw_tokens or not tx_tokens:
            return 0.0
        return float(len(kw_tokens & tx_tokens)) / float(max(1, len(kw_tokens)))

    def _keyword_hit(self, keyword: str, blob: str, threshold: float = 0.2) -> tuple[bool, float]:
        score = self._keyword_match_score(keyword=keyword, blob=blob)
        keyword_l = str(keyword or "").strip().lower()
        blob_l = str(blob or "").lower()
        exact = bool(keyword_l) and keyword_l in blob_l
        if exact:
            return True, max(score, 1.0)

        kw_entities = set(self._entity_tokens(keyword_l))
        tx_entities = set(self._entity_tokens(blob_l))
        entity_overlap = float(len(kw_entities & tx_entities)) / float(
            max(1, len(kw_entities))
        )
        entity_hit = bool(kw_entities) and entity_overlap >= 0.5
        if entity_hit:
            # entity 匹配优先于普通 token overlap，分值上做轻微提升便于排序
            return True, max(score, min(0.99, entity_overlap + 0.18))

        return (score >= float(threshold), score)

    def _build_mediacrawler_runtime_options(
        self, options: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        req = options if isinstance(options, dict) else {}
        client = get_mediacrawler_client()
        use_req = req.get("use_mediacrawler")
        req_enable = bool(use_req) if use_req is not None else True
        req_platforms = req.get("mediacrawler_platforms")
        if isinstance(req_platforms, list):
            req_platform_set = {
                str(x).strip().lower() for x in req_platforms if str(x).strip()
            }
        else:
            req_platform_set = set()
        cfg_platforms = set(client.supported_platforms or [])
        if req_platform_set:
            target_platforms = set(p for p in req_platform_set if p in cfg_platforms)
        else:
            target_platforms = set(cfg_platforms)

        timeout_req = req.get("mediacrawler_timeout_sec")
        timeout_sec = self._safe_float(
            timeout_req,
            self._safe_float(
                getattr(settings, "MEDIACRAWLER_TASK_TIMEOUT_SEC", 120),
                120.0,
            ),
        )
        timeout_sec = max(20.0, min(600.0, timeout_sec))
        force_run_req = req.get("mediacrawler_force_run")
        force_run = (
            bool(force_run_req)
            if force_run_req is not None
            else bool(getattr(settings, "MEDIACRAWLER_FORCE_RUN", True))
        )
        return {
            "enabled": bool(client.active and req_enable),
            "active": bool(client.active),
            "reason": "" if client.active else "MEDIACRAWLER_DISABLED_OR_ACK_REQUIRED",
            "platforms": target_platforms,
            "timeout_sec": timeout_sec,
            "force_run": force_run,
            "max_items": int(self._mediacrawler_max_items_per_platform),
            "trigger_empty_only": bool(
                getattr(settings, "MEDIACRAWLER_TRIGGER_EMPTY_ONLY", False)
            ),
            "trigger_all_fallback": bool(
                getattr(settings, "MEDIACRAWLER_TRIGGER_ALL_FALLBACK", True)
            ),
        }

    def _all_fallback_retrieval_modes(self, items: List[Dict[str, Any]]) -> bool:
        if not items:
            return False
        fallback_modes = {"hot_fallback", "rss_emergency_fallback", "web_search_fallback"}
        modes = []
        for row in items:
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            mode = str(meta.get("retrieval_mode") or row.get("retrieval_mode") or "").lower()
            if mode:
                modes.append(mode)
        if not modes:
            return False
        return all(mode in fallback_modes for mode in modes)

    def _keyword_match_true_count(self, items: List[Dict[str, Any]]) -> int:
        count = 0
        for row in items or []:
            if not isinstance(row, dict):
                continue
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if bool(meta.get("keyword_match") or row.get("keyword_match")):
                count += 1
        return count

    def _should_trigger_mediacrawler(
        self,
        *,
        platform: str,
        native_items: List[Dict[str, Any]],
        mediacrawler_options: Dict[str, Any],
    ) -> Tuple[bool, str]:
        if platform not in self._mediacrawler_supported_platforms:
            return False, "UNSUPPORTED_PLATFORM"
        if not bool(mediacrawler_options.get("enabled")):
            return False, str(
                mediacrawler_options.get("reason") or "MEDIACRAWLER_DISABLED_OR_ACK_REQUIRED"
            )
        target_platforms = set(mediacrawler_options.get("platforms") or set())
        if target_platforms and platform not in target_platforms:
            return False, "NOT_IN_REQUESTED_PLATFORMS"
        if bool(mediacrawler_options.get("force_run")):
            return True, "FORCE_RUN"
        if not native_items:
            return True, "NATIVE_EMPTY"
        if bool(mediacrawler_options.get("trigger_empty_only")):
            return False, "TRIGGER_EMPTY_ONLY"
        if bool(mediacrawler_options.get("trigger_all_fallback")) and self._all_fallback_retrieval_modes(native_items):
            return True, "ALL_FALLBACK_RESULTS"
        if self._keyword_match_true_count(native_items) <= 0:
            return True, "KEYWORD_MATCH_ZERO"
        return False, "NATIVE_HAS_SIGNAL"

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _pick_item_post_id(self, row: Dict[str, Any]) -> str:
        if not isinstance(row, dict):
            return ""
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        keys = [
            "post_id",
            "note_id",
            "aweme_id",
            "mblogid",
            "answer_id",
            "question_id",
            "item_id",
            "id",
        ]
        for key in keys:
            value = str(row.get(key) or meta.get(key) or "").strip()
            if value:
                return value
        return ""

    def _normalized_url_for_key(self, url: str) -> str:
        raw = str(url or "").strip()
        if not raw:
            return ""
        try:
            parsed = urlparse(raw)
            host = (parsed.hostname or "").lower()
            path = (parsed.path or "").rstrip("/")
            query = parse_qs(parsed.query or "", keep_blank_values=False)
            keep_keys = {"id", "mid", "mblogid", "note_id", "aweme_id", "item_id"}
            compact_q = "&".join(
                [
                    f"{k}={','.join(v)}"
                    for k, v in sorted(query.items())
                    if k in keep_keys and v
                ]
            )
            return f"{host}{path}?{compact_q}" if compact_q else f"{host}{path}"
        except Exception:
            return raw

    def _merge_native_with_mediacrawler(
        self,
        *,
        native_items: List[Dict[str, Any]],
        mediacrawler_items: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        url_index: Dict[str, str] = {}
        post_index: Dict[str, str] = {}

        def _priority(item: Dict[str, Any]) -> Tuple[int, int, float]:
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            provider = str(meta.get("provider") or "native").lower()
            keyword_match = bool(meta.get("keyword_match") or item.get("keyword_match"))
            score = self._safe_float(meta.get("keyword_match_score") or item.get("relevance_score"), 0.0)
            return (
                1 if keyword_match else 0,
                1 if provider == "mediacrawler" else 0,
                score,
            )

        def _dedupe_key(item: Dict[str, Any]) -> str:
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            url = self._normalized_url_for_key(
                str(item.get("url") or item.get("original_url") or meta.get("url") or "")
            )
            post_id = self._pick_item_post_id(item)
            # URL 优先。若只有一侧带 post_id，仍应把同 URL 记录合并，避免 native/sidecar 重复。
            if url:
                return f"url::{url}"
            if post_id:
                return f"post::{post_id}"
            snippet = str(item.get("content_text") or item.get("content") or item.get("title") or "")[:140]
            return f"snippet::{snippet}"

        for row in native_items + mediacrawler_items:
            if not isinstance(row, dict):
                continue
            key = _dedupe_key(row)
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            row_url = self._normalized_url_for_key(
                str(row.get("url") or row.get("original_url") or meta.get("url") or "")
            )
            row_post_id = self._pick_item_post_id(row)

            alias_key = ""
            if row_url and row_url in url_index:
                alias_key = url_index[row_url]
            if not alias_key and row_post_id and row_post_id in post_index:
                alias_key = post_index[row_post_id]
            if alias_key:
                key = alias_key

            old = merged.get(key)
            if old is None or _priority(row) > _priority(old):
                merged[key] = row
            if row_url:
                url_index[row_url] = key
            if row_post_id:
                post_index[row_post_id] = key

        ranked = sorted(
            list(merged.values()),
            key=lambda row: _priority(row),
            reverse=True,
        )
        return ranked[: max(1, int(limit))]

    async def _collect_mediacrawler_posts(
        self,
        *,
        platform: str,
        keyword: str,
        timeout_sec: float,
        max_items: int,
    ) -> Dict[str, Any]:
        client = get_mediacrawler_client()
        result = await client.collect_search_items(
            platform=platform,
            keyword=keyword,
            max_items=max_items,
            timeout_sec=timeout_sec,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "reason": str(result.get("reason") or "MEDIACRAWLER_FAILED"),
                "error": str(result.get("detail") or result.get("error") or ""),
                "task_id": str(result.get("task_id") or ""),
                "items": [],
            }
        task_id = str(result.get("task_id") or "")
        raw_items = list(result.get("items") or [])
        normalized = normalize_mediacrawler_posts(
            platform=platform,
            rows=raw_items,
            keyword=keyword,
            sidecar_task_id=task_id,
        )
        return {
            "ok": True,
            "reason": "OK",
            "task_id": task_id,
            "file_path": result.get("file_path"),
            "items": normalized,
            "raw_count": len(raw_items),
        }

    async def _collect_mediacrawler_comments(
        self,
        *,
        platform: str,
        post_id: str,
        timeout_sec: float,
        limit: int,
    ) -> Dict[str, Any]:
        client = get_mediacrawler_client()
        result = await client.collect_detail_with_comments(
            platform=platform,
            post_id=post_id,
            max_items=limit,
            timeout_sec=timeout_sec,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "reason": str(result.get("reason") or "MEDIACRAWLER_FAILED"),
                "error": str(result.get("detail") or result.get("error") or ""),
                "task_id": str(result.get("task_id") or ""),
                "items": [],
            }
        task_id = str(result.get("task_id") or "")
        raw_items = list(result.get("items") or [])
        comments = normalize_mediacrawler_comments(
            platform=platform,
            rows=raw_items,
            post_id=post_id,
            sidecar_task_id=task_id,
            limit=limit,
        )
        return {
            "ok": True,
            "reason": "OK",
            "task_id": task_id,
            "items": comments,
            "raw_count": len(raw_items),
            "file_path": result.get("file_path"),
        }

    def _filter_items_by_keyword_with_fallback(
        self,
        platform: str,
        items: List[Dict[str, Any]],
        keyword: str,
        limit: int,
        *,
        allow_hot_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        关键词优先筛选；若0命中则返回热点兜底，确保系统有可分析数据。
        """
        if not items:
            return []

        kw = (keyword or "").strip()
        if not kw:
            return items[:limit]
        query_variants = self._keyword_query_variants(kw)
        if not query_variants:
            query_variants = [kw]

        def _text_blob(item: Dict[str, Any]) -> str:
            if not isinstance(item, dict):
                return ""
            title = str(item.get("title", "") or "")
            content = str(item.get("content", "") or "")
            content_text = str(item.get("content_text", "") or "")
            text = str(item.get("text", "") or "")
            summary = str(item.get("summary", "") or "")
            snippet = str(item.get("snippet", "") or "")
            return f"{title}\n{content}\n{content_text}\n{text}\n{summary}\n{snippet}".lower()

        threshold = float(
            getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2)
        )
        scored: List[tuple[Dict[str, Any], bool, float]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            blob = _text_blob(item)
            hit = False
            score = 0.0
            matched_query = ""
            for query in query_variants:
                query_hit, query_score = self._keyword_hit(
                    keyword=query,
                    blob=blob,
                    threshold=threshold,
                )
                if query_hit and (not hit or query_score > score):
                    hit = True
                    score = query_score
                    matched_query = query
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            if matched_query:
                meta["keyword_query_used"] = matched_query
            meta["keyword_query_variants"] = query_variants[:5]
            item["metadata"] = meta
            scored.append((item, hit, score))
        scored.sort(key=lambda x: x[2], reverse=True)
        matched = [row for row in scored if row[1]]
        matched.sort(key=lambda x: x[2], reverse=True)
        if matched:
            out: List[Dict[str, Any]] = []
            for item, _hit, score in matched[:limit]:
                meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                meta["keyword_match"] = True
                meta["keyword_match_score"] = round(float(score), 4)
                if score >= 0.99:
                    meta["keyword_match_type"] = "exact"
                elif score >= max(0.38, threshold + 0.05):
                    meta["keyword_match_type"] = "entity"
                else:
                    meta["keyword_match_type"] = "token_overlap"
                item["metadata"] = meta
                out.append(item)
            return out

        platform_key = str(platform or "").strip().lower()
        if not allow_hot_fallback:
            logger.warning(
                f"{platform}: keyword '{keyword}' exact-match=0, strict_search_only enabled -> return []"
            )
            return []

        fail_closed_platforms = {
            "weibo",
            "news",
            "xinhua",
            "peoples_daily",
            "china_gov",
            "samr",
            "csrc",
            "nhc",
            "mps",
            "mem",
            "sec",
            "un_news",
            "who",
            "cdc",
            "rss_pool",
        }
        if platform_key in fail_closed_platforms:
            logger.warning(
                f"{platform}: keyword '{keyword}' exact-match=0, fail-closed platform -> return []"
            )
            return []

        # 查询扩展轮后仍无命中时返回热点兜底，同时标记来源，避免误解为“关键词精确命中”
        fallback_cap = int(
            getattr(settings, "CRAWLER_HOT_FALLBACK_MAX_ITEMS", 5)
        )
        if platform_key in self._trusted_hot_fallback_platforms:
            fallback_cap = int(
                getattr(
                    settings,
                    "CRAWLER_HOT_FALLBACK_MAX_ITEMS_TRUSTED",
                    max(10, fallback_cap),
                )
            )
        fallback_cap = max(1, fallback_cap)
        fallback_limit = min(limit, fallback_cap)
        fallback = []
        for item, _hit, score in scored[:fallback_limit]:
            if not isinstance(item, dict):
                continue
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["keyword_match"] = False
            meta["keyword_match_score"] = round(float(score), 4)
            meta["keyword_match_type"] = "fallback_no_match"
            meta["retrieval_mode"] = "hot_fallback"
            meta["low_relevance_fallback"] = True
            item["metadata"] = meta
            fallback.append(item)

        logger.warning(
            f"{platform}: keyword '{keyword}' exact-match=0, fallback to hot items={len(fallback)}"
        )
        return fallback

    async def aggregate_cross_platform_data(
        self, keyword: str, platforms: List[str] = None, limit_per_platform: int = 20
    ) -> Dict[str, Any]:
        """
        跨平台聚合数据分析

        Args:
            keyword: 搜索关键词
            platforms: 平台列表（默认全部）
            limit_per_platform: 每个平台返回数量

        Returns:
            聚合分析结果
        """
        logger.info(f"📊 Aggregating cross-platform data for '{keyword}'...")

        # 跨平台搜索
        search_results = await self.search_across_platforms(
            keyword=keyword, platforms=platforms, limit_per_platform=limit_per_platform
        )

        # 统计分析
        total_posts = 0
        total_engagement = 0
        platform_stats = {}
        all_posts = []

        for platform, posts in search_results.items():
            if not posts:
                platform_stats[platform] = {
                    "post_count": 0,
                    "total_likes": 0,
                    "total_comments": 0,
                    "total_shares": 0,
                    "avg_engagement": 0.0,
                }
                continue

            # 计算平台级统计
            likes = 0
            comments = 0
            shares = 0
            for p in posts:
                metadata = p.get("metadata") if isinstance(p, dict) else {}
                if not isinstance(metadata, dict):
                    metadata = {}
                likes += int(metadata.get("likes", 0) or 0)
                comments += int(metadata.get("comments", 0) or 0)
                shares += int(metadata.get("shares", 0) or 0)
            engagement = likes + comments + shares

            platform_stats[platform] = {
                "post_count": len(posts),
                "total_likes": likes,
                "total_comments": comments,
                "total_shares": shares,
                "avg_engagement": round(engagement / len(posts), 2),
            }

            total_posts += len(posts)
            total_engagement += engagement
            all_posts.extend(posts)

        # 检测新账户占比（水军特征）
        new_accounts = [
            p
            for p in all_posts
            if isinstance(p, dict)
            and isinstance(p.get("metadata"), dict)
            and p["metadata"].get("account_age_days") is not None
            and p["metadata"]["account_age_days"] < 30
        ]
        new_account_ratio = (
            round(len(new_accounts) / total_posts, 2) if total_posts > 0 else 0.0
        )

        # 提取高频实体（话题标签、提及）
        all_entities = []
        for post in all_posts:
            all_entities.extend(post.get("entities", []))

        entity_counts = {}
        for entity in all_entities:
            entity_counts[entity] = entity_counts.get(entity, 0) + 1

        top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        # 时间分布分析
        time_distribution = self._analyze_time_distribution(all_posts)

        # 聚合结果
        aggregated_data = {
            "keyword": keyword,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_posts": total_posts,
                "total_engagement": total_engagement,
                "avg_engagement": (
                    round(total_engagement / total_posts, 2) if total_posts > 0 else 0.0
                ),
                "platform_count": len(platform_stats),
                "new_account_ratio": new_account_ratio,
            },
            "platform_stats": platform_stats,
            "top_entities": top_entities,
            "time_distribution": time_distribution,
            "raw_posts": all_posts,  # 原始数据
        }

        logger.info(
            f"✅ Aggregated {total_posts} posts from {len(platform_stats)} platforms"
        )
        return aggregated_data

    def _analyze_time_distribution(self, posts: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        分析时间分布（检测异常发布模式）

        Args:
            posts: 帖子列表

        Returns:
            {hour: post_count}
        """
        hour_distribution = {}

        for post in posts:
            metadata = post.get("metadata") if isinstance(post, dict) else {}
            if not isinstance(metadata, dict):
                metadata = {}
            created_at = metadata.get("timestamp")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    hour = dt.hour
                    hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
                except Exception:
                    continue

        return hour_distribution

    async def fetch_user_posts_multi_platform(
        self, user_ids: Dict[str, str], limit_per_platform: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        从多个平台抓取指定用户的帖子

        Args:
            user_ids: {platform: user_id}
            limit_per_platform: 每个平台返回数量

        Returns:
            {platform_name: [posts]}
        """
        logger.info(f"🔍 Fetching user posts from {len(user_ids)} platforms...")

        tasks = []
        platforms = []

        for platform, user_id in user_ids.items():
            if platform in self.crawlers:
                crawler = self.crawlers[platform]
                tasks.append(crawler.fetch_user_posts(user_id, limit_per_platform))
                platforms.append(platform)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        user_posts = {}
        for i, platform in enumerate(platforms):
            if isinstance(results[i], Exception):
                logger.error(
                    f"❌ Error fetching user posts from {platform}: {results[i]}"
                )
                user_posts[platform] = []
            else:
                user_posts[platform] = results[i]

        total = sum(len(posts) for posts in user_posts.values())
        logger.info(
            f"✅ Fetched total {total} user posts from {len(platforms)} platforms"
        )

        return user_posts

    async def fetch_comments_multi_platform(
        self,
        post_ids: Dict[str, str],
        limit_per_platform: int = 50,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        从多个平台抓取指定帖子的评论

        Args:
            post_ids: {platform: post_id}
            limit_per_platform: 每个平台返回数量

        Returns:
            {platform_name: [comments]}
        """
        logger.info(f"🔍 Fetching comments from {len(post_ids)} platforms...")
        self._last_comment_sidecar_diag = {
            "fetched_at": datetime.utcnow().isoformat(),
            "hit_count": 0,
            "failures": [],
            "enabled": False,
        }

        tasks = []
        platforms = []

        for platform, post_id in post_ids.items():
            if platform in self.crawlers:
                crawler = self.crawlers[platform]
                tasks.append(crawler.fetch_comments(post_id, limit_per_platform))
                platforms.append(platform)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        comments_by_platform = {}
        for i, platform in enumerate(platforms):
            if isinstance(results[i], Exception):
                logger.error(
                    f"❌ Error fetching comments from {platform}: {results[i]}"
                )
                comments_by_platform[platform] = []
            else:
                comments_by_platform[platform] = results[i]

        runtime_sidecar_options = self._build_mediacrawler_runtime_options(
            mediacrawler_options
        )
        self._last_comment_sidecar_diag["enabled"] = bool(
            runtime_sidecar_options.get("enabled")
        )
        sidecar_hit_count = 0
        sidecar_failures: List[Dict[str, Any]] = []
        for platform, post_id in (post_ids or {}).items():
            if platform not in self._mediacrawler_supported_platforms:
                continue
            if platform not in comments_by_platform:
                continue
            existing = list(comments_by_platform.get(platform) or [])
            if existing:
                continue
            if not bool(runtime_sidecar_options.get("enabled")):
                sidecar_failures.append(
                    {
                        "platform": platform,
                        "post_id": str(post_id or ""),
                        "reason": str(
                            runtime_sidecar_options.get("reason")
                            or "MEDIACRAWLER_DISABLED_OR_ACK_REQUIRED"
                        ),
                    }
                )
                continue
            target_platforms = set(runtime_sidecar_options.get("platforms") or set())
            if target_platforms and platform not in target_platforms:
                continue
            sidecar = await self._collect_mediacrawler_comments(
                platform=platform,
                post_id=str(post_id or ""),
                timeout_sec=float(runtime_sidecar_options.get("timeout_sec") or 120.0),
                limit=max(10, int(limit_per_platform)),
            )
            if sidecar.get("ok"):
                rows = list(sidecar.get("items") or [])
                comments_by_platform[platform] = rows
                sidecar_hit_count += len(rows)
                logger.info(
                    f"✅ {platform}: comments recovered from mediacrawler, count={len(rows)}"
                )
            else:
                sidecar_failures.append(
                    {
                        "platform": platform,
                        "post_id": str(post_id or ""),
                        "reason": str(
                            sidecar.get("reason")
                            or sidecar.get("error")
                            or "MEDIACRAWLER_COMMENT_FAILED"
                        ),
                    }
                )
                logger.warning(
                    f"{platform}: mediacrawler comment fallback failed ({sidecar_failures[-1]['reason']})"
                )

        total = sum(len(comments) for comments in comments_by_platform.values())
        logger.info(
            f"✅ Fetched total {total} comments from {len(platforms)} platforms"
        )
        if sidecar_hit_count > 0:
            logger.info(f"ℹ️ MediaCrawler recovered comments: {sidecar_hit_count}")
        if sidecar_failures:
            logger.warning(
                f"ℹ️ MediaCrawler comment failures: {len(sidecar_failures)}"
            )
        self._last_comment_sidecar_diag = {
            "fetched_at": datetime.utcnow().isoformat(),
            "hit_count": int(sidecar_hit_count),
            "failures": [row for row in sidecar_failures if isinstance(row, dict)],
            "enabled": bool(runtime_sidecar_options.get("enabled")),
        }

        return comments_by_platform

    async def close_all(self):
        """关闭所有爬虫"""
        logger.info("🛑 Closing all crawlers...")
        for platform, crawler in self.crawlers.items():
            try:
                await crawler.close()
            except Exception as e:
                logger.error(f"❌ Error closing {platform} crawler: {e}")

        logger.info("✅ All crawlers closed")


# 单例模式管理器
_crawler_manager_instance: Optional[CrawlerManager] = None


def get_crawler_manager(
    # 社交媒体平台
    weibo_cookies: Optional[str] = None,
    twitter_bearer_token: Optional[str] = None,
    xhs_cookies: Optional[str] = None,
    douyin_cookies: Optional[str] = None,
    zhihu_cookies: Optional[str] = None,
    bilibili_cookies: Optional[str] = None,
    kuaishou_cookies: Optional[str] = None,
    douban_cookies: Optional[str] = None,
    reddit_client_id: Optional[str] = None,
    reddit_client_secret: Optional[str] = None,
    # 社区论坛
    github_token: Optional[str] = None,
    stackoverflow_api_key: Optional[str] = None,
    # 学术数据集
    openalex_email: Optional[str] = None,
) -> CrawlerManager:
    """
    获取爬虫管理器单例

    Args:
        # 社交媒体平台 (可通过MCP工具获取cookies)
        weibo_cookies: 微博Cookies
        twitter_bearer_token: Twitter Token
        xhs_cookies: 小红书Cookies
        douyin_cookies: 抖音Cookies
        zhihu_cookies: 知乎Cookies
        bilibili_cookies: B站Cookies
        kuaishou_cookies: 快手Cookies
        douban_cookies: 豆瓣Cookies
        reddit_client_id: Reddit Client ID
        reddit_client_secret: Reddit Client Secret

        # 社区论坛
        github_token: GitHub Personal Access Token
        stackoverflow_api_key: Stack Overflow API Key

        # 学术数据集
        openalex_email: OpenAlex联系邮箱

    Returns:
        爬虫管理器实例
    """
    global _crawler_manager_instance

    if _crawler_manager_instance is None:
        def _pick(*candidates: Optional[str]) -> Optional[str]:
            for value in candidates:
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
            return None

        weibo_cookies = _pick(
            weibo_cookies,
            getattr(settings, "WEIBO_COOKIES", None),
            os.getenv("WEIBO_COOKIES"),
        )
        twitter_bearer_token = _pick(
            twitter_bearer_token,
            getattr(settings, "TWITTER_BEARER_TOKEN", None),
            os.getenv("TWITTER_BEARER_TOKEN"),
        )
        xhs_cookies = _pick(
            xhs_cookies,
            getattr(settings, "XHS_COOKIES", None),
            os.getenv("XHS_COOKIES"),
        )
        douyin_cookies = _pick(
            douyin_cookies,
            getattr(settings, "DOUYIN_COOKIES", None),
            os.getenv("DOUYIN_COOKIES"),
        )
        zhihu_cookies = _pick(
            zhihu_cookies,
            getattr(settings, "ZHIHU_COOKIES", None),
            os.getenv("ZHIHU_COOKIES"),
        )
        bilibili_cookies = _pick(
            bilibili_cookies,
            getattr(settings, "BILIBILI_COOKIES", None),
            os.getenv("BILIBILI_COOKIES"),
        )
        kuaishou_cookies = _pick(
            kuaishou_cookies,
            getattr(settings, "KUAISHOU_COOKIES", None),
            os.getenv("KUAISHOU_COOKIES"),
        )
        douban_cookies = _pick(
            douban_cookies,
            getattr(settings, "DOUBAN_COOKIES", None),
            os.getenv("DOUBAN_COOKIES"),
        )
        reddit_client_id = _pick(
            reddit_client_id,
            getattr(settings, "REDDIT_CLIENT_ID", None),
            os.getenv("REDDIT_CLIENT_ID"),
        )
        reddit_client_secret = _pick(
            reddit_client_secret,
            getattr(settings, "REDDIT_CLIENT_SECRET", None),
            os.getenv("REDDIT_CLIENT_SECRET"),
        )
        github_token = _pick(
            github_token,
            getattr(settings, "GITHUB_TOKEN", None),
            os.getenv("GITHUB_TOKEN"),
        )
        stackoverflow_api_key = _pick(
            stackoverflow_api_key,
            getattr(settings, "STACKOVERFLOW_API_KEY", None),
            os.getenv("STACKOVERFLOW_API_KEY"),
        )
        openalex_email = _pick(
            openalex_email,
            getattr(settings, "OPENALEX_EMAIL", None),
            os.getenv("OPENALEX_EMAIL"),
        )

        _crawler_manager_instance = CrawlerManager(
            weibo_cookies=weibo_cookies,
            twitter_bearer_token=twitter_bearer_token,
            xhs_cookies=xhs_cookies,
            douyin_cookies=douyin_cookies,
            zhihu_cookies=zhihu_cookies,
            bilibili_cookies=bilibili_cookies,
            kuaishou_cookies=kuaishou_cookies,
            douban_cookies=douban_cookies,
            reddit_client_id=reddit_client_id,
            reddit_client_secret=reddit_client_secret,
            github_token=github_token,
            stackoverflow_api_key=stackoverflow_api_key,
            openalex_email=openalex_email,
        )

    return _crawler_manager_instance
