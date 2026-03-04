"""
核心配置管理模块
"""

import os
from functools import lru_cache
from typing import Any, Dict, Optional
from pydantic import PostgresDsn, RedisDsn, Field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    # ======================
    # 应用基础配置
    # ======================
    APP_NAME: str = "Aletheia"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # ======================
    # 安全配置
    # ======================
    SECRET_KEY: str = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ======================
    # 数据库配置
    # ======================
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: Optional[PostgresDsn] = None
    SQLITE_DB_PATH: str = "./aletheia.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if isinstance(v, str):
            return v
        values: Dict[str, Any] = info.data or {}
        user = values.get("POSTGRES_USER") or ""
        password = values.get("POSTGRES_PASSWORD") or ""
        host = values.get("POSTGRES_SERVER") or "localhost"
        db = values.get("POSTGRES_DB") or ""
        return f"postgresql+asyncpg://{user}:{password}@{host}/{db}"

    # ======================
    # Redis配置
    # ======================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_ENABLED: bool = False
    REDIS_URL: Optional[RedisDsn] = None

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if isinstance(v, str):
            return v
        values: Dict[str, Any] = info.data or {}
        password = values.get("REDIS_PASSWORD")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/{values.get('REDIS_DB')}"

    # ======================
    # Kafka配置
    # ======================
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_RAW_DATA: str = "aletheia.raw.data"
    KAFKA_TOPIC_ANALYZED: str = "aletheia.analyzed"
    KAFKA_CONSUMER_GROUP: str = "aletheia-processors"

    # ======================
    # AI服务配置
    # ======================
    # 通用 LLM 配置（OpenAI 兼容接口）
    LLM_API_KEY: Optional[str] = None
    LLM_API_BASE: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    LLM_VISION_MODEL: Optional[str] = None
    LLM_SMALL_MODEL: Optional[str] = None
    LLM_LARGE_MODEL: Optional[str] = None
    LLM_RERANK_MODEL: Optional[str] = None
    LLM_TEMPERATURE: Optional[float] = None
    LLM_MAX_TOKENS: Optional[int] = None
    LLM_ALLOW_WEB_SEARCH_FALLBACK: Optional[bool] = None

    # SiliconFlow（默认 LLM 提供商配置）
    SILICONFLOW_API_KEY: str
    SILICONFLOW_MODEL: str = "Pro/MiniMaxAI/MiniMax-M2.5"
    SILICONFLOW_VISION_MODEL: str = "deepseek-ai/DeepSeek-VL2"
    SILICONFLOW_API_BASE: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_TEMPERATURE: float = 0.3
    SILICONFLOW_MAX_TOKENS: int = 4096
    SILICONFLOW_PREFERRED: bool = True
    SILICONFLOW_SMALL_MODEL: str = "deepseek-ai/DeepSeek-V3"
    SILICONFLOW_LARGE_MODEL: str = "deepseek-ai/DeepSeek-V3"
    SILICONFLOW_RERANK_MODEL: str = "Qwen/Qwen3-Reranker-8B"
    SILICONFLOW_ALLOW_WEB_SEARCH_FALLBACK: bool = True

    # ======================
    # Investigation 编排配置
    # ======================
    INVESTIGATION_ENABLE_EXTERNAL_SOURCES: bool = True
    INVESTIGATION_EXTERNAL_TIMEOUT_SEC: int = 20
    INVESTIGATION_EXTERNAL_SEARCH_ENABLED: bool = True
    INVESTIGATION_EXTERNAL_SEARCH_MODE: str = "always"  # adaptive | always | disabled
    INVESTIGATION_EXTERNAL_SEARCH_PROVIDER: str = "google_news_rss"
    INVESTIGATION_EXTERNAL_SEARCH_PROVIDER_CHAIN: str = "google_news_rss"
    INVESTIGATION_EXTERNAL_SEARCH_TRIGGER_MIN_EVIDENCE: int = 120
    INVESTIGATION_EXTERNAL_SEARCH_TRIGGER_MIN_PLATFORMS: int = 4
    INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS: int = 20
    INVESTIGATION_EXTERNAL_SEARCH_PER_PROVIDER_LIMIT: int = 20
    INVESTIGATION_EXTERNAL_SEARCH_TIMEOUT_SEC: float = 6.0
    INVESTIGATION_EXTERNAL_SEARCH_WHITELIST_ONLY: bool = True
    INVESTIGATION_EXTERNAL_SEARCH_ALLOWED_DOMAINS: str = (
        "news.cn,people.com.cn,chinanews.com.cn,cctv.com,china.com.cn,gov.cn,"
        "xinhuanet.com,thepaper.cn,caixin.com,36kr.com,jiemian.com,samr.gov.cn,"
        "csrc.gov.cn,nhc.gov.cn,mps.gov.cn,mem.gov.cn"
    )
    INVESTIGATION_EXTERNAL_SEARCH_MAX_DOMAIN_QUERIES: int = 8
    INVESTIGATION_EXTERNAL_SEARCH_CONCURRENCY: int = 4
    INVESTIGATION_EXTERNAL_SEARCH_MAX_TOTAL_RESULTS: int = 200
    INVESTIGATION_EXTERNAL_SEARCH_MIN_RELEVANCE: float = 0.15
    INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_ENTITY_HIT: bool = True
    INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_EVENT_HINT_HIT: bool = False
    INVESTIGATION_EXTERNAL_SEARCH_SEARXNG_BASE_URL: str = ""
    INVESTIGATION_EXTERNAL_SEARCH_SEARXNG_TIMEOUT_SEC: float = 6.0
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_BASE_URL: str = "https://api.bocha.cn/v1"
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_API_KEY: str = ""
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_TIMEOUT_SEC: float = 8.0
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_MAX_RESULTS: int = 50
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_SUMMARY: bool = True
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_FRESHNESS: str = "noLimit"
    INVESTIGATION_EXTERNAL_SEARCH_BOCHA_ENABLE_SITE_SCOPED_QUERIES: bool = False
    INVESTIGATION_TEMPLATE_PATH: str = "../deep-research-report.md"
    INVESTIGATION_MAX_CONCURRENT_RUNS: int = 8
    INVESTIGATION_MIN_VALID_EVIDENCE_HARD_FLOOR: int = 100
    INVESTIGATION_TARGET_VALID_EVIDENCE_MIN: int = 300
    INVESTIGATION_QUALITY_MODE: str = "strict"
    INVESTIGATION_MAX_RUNTIME_SEC: int = 180
    INVESTIGATION_MIN_PLATFORMS_WITH_DATA: int = 8
    INVESTIGATION_FREE_SOURCE_ONLY: bool = True
    INVESTIGATION_FAST_PHASE_SECONDS: int = 30
    INVESTIGATION_MAX_SEARCH_ROUNDS: int = 6
    INVESTIGATION_FALLBACK_COVERAGE_THRESHOLD: float = 0.45
    INVESTIGATION_EXPAND_TO_ALL_PLATFORMS_ON_GAP: bool = True
    INVESTIGATION_LLM_SEMANTIC_RERANK_ENABLED: bool = True
    INVESTIGATION_LLM_SEMANTIC_RERANK_MODE: str = "rerank"
    INVESTIGATION_LLM_SEMANTIC_RERANK_MAX_ITEMS: int = 60
    INVESTIGATION_LLM_SEMANTIC_RERANK_CONCURRENCY: int = 12
    INVESTIGATION_LLM_SEMANTIC_RERANK_TIMEOUT_SEC: int = 12
    INVESTIGATION_LLM_SEMANTIC_RERANK_THRESHOLD: float = 0.45
    INVESTIGATION_LLM_SEMANTIC_RERANK_FALLBACK_RELEVANCE: float = 0.6
    INVESTIGATION_LLM_RERANK_BATCH_SIZE: int = 32
    INVESTIGATION_MULTI_AGENT_TIMEOUT_SEC: int = 240
    INVESTIGATION_MULTI_AGENT_SINGLETON: bool = False
    INVESTIGATION_KEYWORD_MATCH_THRESHOLD: float = 0.2
    INVESTIGATION_RELEVANCE_THRESHOLD_STRICT: float = 0.3
    INVESTIGATION_RELEVANCE_THRESHOLD_BALANCED: float = 0.22
    INVESTIGATION_RELEVANCE_FLOOR: float = 0.22
    INVESTIGATION_EXTERNAL_EVIDENCE_MIN_RELEVANCE: float = 0.3
    INVESTIGATION_ALLOW_LOW_RELEVANCE_RESCUE: bool = False
    INVESTIGATION_EVIDENCE_ORDER_MODE: str = "relevance_desc"  # relevance_desc | interleave_platform
    INVESTIGATION_SOURCE_PROFILE_DEFAULT: str = "stable_mixed_v1"
    INVESTIGATION_STRICT_PIPELINE_DEFAULT: str = "staged_strict"
    INVESTIGATION_ENABLE_CACHED_EVIDENCE: bool = True
    INVESTIGATION_LIVE_EVIDENCE_TARGET: int = 30
    INVESTIGATION_PHASE1_TARGET_VALID_EVIDENCE: int = 50
    INVESTIGATION_PHASE1_DEADLINE_SEC: int = 90
    INVESTIGATION_MAX_CONCURRENT_PLATFORMS_FAST: int = 6
    INVESTIGATION_MAX_CONCURRENT_PLATFORMS_FILL: int = 2
    INVESTIGATION_ENHANCED_REASONING_TIMEOUT_SEC: int = 25
    INVESTIGATION_MAX_LIVE_RESCUE_ROUNDS: int = 3
    INVESTIGATION_FORCE_LIVE_BEFORE_CACHE: bool = True
    INVESTIGATION_STAGED_STRICT_CANDIDATE_TOP_N: int = 200
    INVESTIGATION_STAGED_STRICT_FINAL_TOP_M: int = 50
    INVESTIGATION_EVIDENCE_CACHE_MAX_AGE_HOURS: int = 72
    INVESTIGATION_HISTORICAL_CACHE_MIN_TOKEN_OVERLAP: float = 0.25
    INVESTIGATION_CACHED_EVIDENCE_MIN_RELEVANCE: float = 0.22
    INVESTIGATION_URL_PROBE_TIMEOUT_SEC: float = 4.0
    INVESTIGATION_URL_PROBE_CONCURRENCY: int = 16
    INVESTIGATION_EVIDENCE_CARD_MAX_PER_PLATFORM_STRICT: int = 60
    INVESTIGATION_EVIDENCE_CARD_MAX_PER_PLATFORM_BALANCED: int = 30
    INVESTIGATION_AGENT_TOPK_PER_PLATFORM: int = 12
    INVESTIGATION_AGENT_MAX_CONTENT_CHARS: int = 2400
    INVESTIGATION_NETWORK_PRECHECK_ENABLED: bool = True
    INVESTIGATION_NETWORK_PRECHECK_TIMEOUT_SEC: float = 2.5
    INVESTIGATION_NETWORK_PRECHECK_FAIL_RATIO_THRESHOLD: float = 0.7
    INVESTIGATION_NETWORK_PRECHECK_MIN_HOSTS: int = 3
    INVESTIGATION_NETWORK_PRECHECK_HOSTS: str = (
        "duckduckgo.com,feeds.bbci.co.uk,api.siliconflow.cn"
    )
    INVESTIGATION_ENABLE_CLAIM_ANALYSIS: bool = True
    INVESTIGATION_PREVIEW_DECOMPOSITION_ENABLED: bool = False
    INVESTIGATION_TIERED_SEARCH_ENABLED: bool = False
    INVESTIGATION_LOGIC_CHECK_ENABLED: bool = False
    INVESTIGATION_LOGIC_CHECK_MIN_MATCH_RATIO: float = 0.2
    INVESTIGATION_ITERATION_ENABLED: bool = False
    INVESTIGATION_ITERATION_MAX_ROUNDS: int = 2
    INVESTIGATION_ITERATION_MAX_QUERIES: int = 3
    INVESTIGATION_ITERATION_LIMIT_PER_PLATFORM: int = 20

    # ======================
    # Source Tier Config
    # ======================
    SOURCE_TIER_CONFIG_PATH: str = "config/source_tier_config.json"
    SOURCE_TIER_CONFIG_REFRESH_SEC: float = 2.0
    RSS_SOURCES_CONFIG_PATH: str = "config/sources.yaml"
    RSS_SOURCES_CONFIG_EXTRA_PATHS: str = ""
    RSS_SOURCES_CONFIG_REFRESH_SEC: float = 5.0
    RSS_SOURCES_CONFIG_ENABLED: bool = True
    SEARCH_SOURCES_CONFIG_PATH: str = "config/search_sources.yaml"
    SEARCH_SOURCES_CONFIG_EXTRA_PATHS: str = ""
    SEARCH_SOURCES_CONFIG_REFRESH_SEC: float = 5.0
    SEARCH_SOURCES_CONFIG_ENABLED: bool = True
    SEARCH_SOURCES_REQUIRE_CN_FOR_ZH_QUERY: bool = True
    RSS_POOL_MAX_SOURCES_PER_FETCH: int = 8
    RSS_POOL_MAX_SOURCES_PER_SEARCH_FETCH: int = 24
    RSS_POOL_FETCH_TIMEOUT_SECONDS: float = 8.0
    RSS_POOL_FETCH_RETRIES: int = 2
    RSS_POOL_RETRY_BACKOFF_BASE: float = 0.6
    RSS_POOL_FETCH_CONCURRENCY: int = 6
    RSS_POOL_ITEMS_PER_SOURCE: int = 12
    RSS_POOL_ENABLE_LOCAL_INDEX_SEARCH: bool = True
    RSS_POOL_SEARCH_LOCAL_FIRST: bool = True
    RSS_POOL_SEARCH_SKIP_NETWORK_IF_LOCAL_ENOUGH: bool = True
    RSS_POOL_SEARCH_LOCAL_MIN_RESULTS: int = 8
    RSS_POOL_LOCAL_INDEX_LOOKBACK_DAYS: int = 180
    RSS_POOL_LOCAL_INDEX_MAX_CANDIDATES: int = 120
    RSS_AUTOEXPAND_CONFIG_PATH: str = "config/autoexpand.yaml"
    RSS_AUTOEXPAND_OUTPUT_PATH: str = "config/sources.auto.yaml"
    RSS_AUTOEXPAND_ENABLED: bool = False
    RSS_PIPELINE_ENABLED: bool = False
    RSS_PIPELINE_INTERVAL_SECONDS: int = 600
    RSS_PIPELINE_LIMIT: int = 50
    RSS_PIPELINE_WITH_COMMENTS: bool = False
    RSS_PIPELINE_ITEM_CONCURRENCY: int = 6
    RULES_CONFIG_PATH: str = "config/rules.yaml"
    RULES_CONFIG_REFRESH_SEC: float = 5.0
    RULES_CONFIG_ENABLED: bool = True
    RULES_DEEP_FETCH_TIMEOUT_SECONDS: float = 10.0
    RULES_DEEP_SUMMARY_USE_LLM: bool = False
    RULES_DEEP_SUMMARY_MAX_LENGTH: int = 200
    COMMENTS_CONFIG_PATH: str = "config/comments.yaml"
    COMMENTS_CONFIG_REFRESH_SEC: float = 5.0
    COMMENTS_CONFIG_ENABLED: bool = True
    SPAM_RULES_CONFIG_PATH: str = "config/spam_rules.yaml"
    SPAM_RULES_CONFIG_REFRESH_SEC: float = 5.0
    SPAM_RULES_CONFIG_ENABLED: bool = True
    INVESTIGATION_PREVIEW_TTL_MINUTES: int = 30
    INVESTIGATION_PREVIEW_LLM_TIMEOUT_SEC: int = 8
    INVESTIGATION_PREVIEW_MAX_CLAIMS: int = 6
    INVESTIGATION_PREVIEW_SUMMARY_TARGET_CHARS: int = 200
    INVESTIGATION_PREVIEW_SUMMARY_MIN_CHARS: int = 160
    INVESTIGATION_PREVIEW_SUMMARY_MAX_CHARS: int = 260
    SOURCE_PLANNER_MODE: str = "precision"
    INVESTIGATION_CLAIM_MAX_CLAIMS: int = 8
    INVESTIGATION_CLAIM_LINK_MAX_PER_CLAIM: int = 24
    INVESTIGATION_CLAIM_MIN_RELEVANCE: float = 0.2
    INVESTIGATION_CLAIM_REASONING_ENABLE_LLM: bool = True
    INVESTIGATION_CLAIM_REASONING_TIMEOUT_SEC: int = 15
    INVESTIGATION_CLAIM_REASONING_MAX_CLAIMS: int = 4
    INVESTIGATION_CLAIM_REASONING_CONCURRENCY: int = 8
    INVESTIGATION_CLAIM_REASONING_REQUIRE_LLM: bool = False
    INVESTIGATION_CLAIM_REASONING_RETRIES: int = 1
    INVESTIGATION_CLAIM_REASONING_RETRY_BACKOFF_SEC: float = 1.5
    INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_ENABLED: bool = False
    INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_TIMEOUT_SEC: int = 12
    INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_CONCURRENCY: int = 8
    INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_TOPK: int = 6
    INVESTIGATION_FACTCHECK_MAX_CLAIMS: int = 3
    INVESTIGATION_ENABLE_OPINION_MONITORING: bool = True
    INVESTIGATION_OPINION_COMMENT_TARGET: int = 120
    INVESTIGATION_OPINION_COMMENT_LIMIT_PER_POST: int = 40
    INVESTIGATION_OPINION_MAX_POSTS_PER_PLATFORM: int = 2
    INVESTIGATION_OPINION_MAX_PLATFORMS: int = 6
    INVESTIGATION_OPINION_ALLOW_SYNTHETIC_COMMENTS: bool = False
    INVESTIGATION_OPINION_GAP_FORCE_REVIEW: bool = False
    INVESTIGATION_OPINION_SUSPICIOUS_RATIO_MEDIUM: float = 0.25
    INVESTIGATION_OPINION_SUSPICIOUS_RATIO_HIGH: float = 0.45
    INVESTIGATION_HARD_FAIL_ON_ZERO_EVIDENCE: bool = True
    INVESTIGATION_HARD_FAIL_NETWORK_RATIO_THRESHOLD: float = 0.7
    INVESTIGATION_STRICT_SEARCH_ONLY: bool = True
    INVESTIGATION_ENTITY_GATE_ENABLED: bool = True
    INVESTIGATION_ONLY_TRUSTED_PLATFORMS: bool = True
    INVESTIGATION_TRUSTED_PLATFORMS: str = (
        "rss_pool,weibo,zhihu,xinhua,peoples_daily,china_gov,samr,csrc,nhc"
    )
    INVESTIGATION_TRUSTED_HEALTH_REPORT_PATH: str = "docs/source-health-report-zh-core.json"
    INVESTIGATION_TRUSTED_MIN_SUCCESS_RATE: float = 0.34
    INVESTIGATION_TRUSTED_REQUIRE_ITEMS: bool = True
    INVESTIGATION_TRUSTED_MIN_PLATFORM_COUNT: int = 4
    INVESTIGATION_LANGUAGE_ROUTING_ENABLED: bool = True
    INVESTIGATION_ZH_QUERY_BACKGROUND_PLATFORMS: str = (
        "bbc,reuters,guardian,ap_news,who,un_news,sec,fca_uk,cdc"
    )
    INVESTIGATION_STRICT_MUST_HAVE_GATING: bool = False
    FACTCHECK_ENABLE: bool = True
    FACTCHECK_TIMEOUT_SEC: int = 6
    GOOGLE_FACTCHECK_API_KEY: Optional[str] = None
    GOOGLE_FACTCHECK_API_URL: str = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    MEDIACRAWLER_ENABLED: bool = False
    MEDIACRAWLER_NONCOMMERCIAL_ACK: bool = False
    MEDIACRAWLER_BASE_URL: str = "http://127.0.0.1:8080"
    MEDIACRAWLER_AUTO_START: bool = True
    MEDIACRAWLER_HOME: str = "../MediaCrawler"
    MEDIACRAWLER_START_COMMAND: str = "uv run uvicorn api.main:app --host 127.0.0.1 --port 8080"
    MEDIACRAWLER_HEADLESS: bool = False
    MEDIACRAWLER_STARTUP_TIMEOUT_SEC: int = 45
    MEDIACRAWLER_REQUEST_TIMEOUT_SEC: int = 15
    MEDIACRAWLER_TASK_TIMEOUT_SEC: int = 120
    MEDIACRAWLER_PLATFORMS: str = "xiaohongshu,douyin,weibo,zhihu"
    MEDIACRAWLER_MAX_ITEMS_PER_PLATFORM: int = 80
    MEDIACRAWLER_TRIGGER_EMPTY_ONLY: bool = False
    MEDIACRAWLER_TRIGGER_ALL_FALLBACK: bool = True

    # ======================
    # OCR/ASR配置
    # ======================
    PADDLE_OCR_USE_GPU: bool = False
    PADDLE_OCR_LANG: str = "ch"
    WHISPER_MODEL: str = "base"  # tiny, base, small, medium, large

    # ======================
    # 爬虫配置
    # ======================
    CRAWLER_TRUST_ENV: bool = True
    CRAWLER_AUTO_DISABLE_BROKEN_LOCAL_PROXY: bool = True
    CRAWLER_PROXY_PROBE_TIMEOUT_SEC: float = 0.2
    OUTBOUND_NETWORK_MODE: str = "fixed_proxy"  # fixed_proxy | direct | auto
    OUTBOUND_PROXY_URL: str = ""
    OUTBOUND_NO_PROXY: str = "127.0.0.1,localhost,::1"
    HTTPX_TRUST_ENV: bool = True
    HTTPX_TRUST_ENV_ONLY: bool = True
    HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY: bool = True
    HTTPX_PROXY_PROBE_TIMEOUT_SEC: float = 0.2
    CRAWLER_PLATFORM_SEARCH_TIMEOUT_SECONDS: float = 15.0
    CRAWLER_PLATFORM_SEARCH_TIMEOUT_MAX_SECONDS: float = 25.0
    CRAWLER_WEB_FALLBACK_TIMEOUT_SECONDS: float = 12.0
    CRAWLER_KEYWORD_MATCH_THRESHOLD: float = 0.2
    CRAWLER_DISABLE_HOT_FALLBACK_IN_SEARCH: bool = True
    CRAWLER_HOT_FALLBACK_MAX_ITEMS: int = 5
    CRAWLER_HOT_FALLBACK_MAX_ITEMS_TRUSTED: int = 20
    OFFICIAL_SOURCE_SEARCH_LOCAL_FIRST: bool = True
    OFFICIAL_SOURCE_SEARCH_LOCAL_MIN_RESULTS: int = 2
    OFFICIAL_SOURCE_SEARCH_LOCAL_LOOKBACK_DAYS: int = 180
    OFFICIAL_SOURCE_SEARCH_FETCH_MULTIPLIER: int = 8
    OFFICIAL_SOURCE_SEARCH_FETCH_MIN_LIMIT: int = 60
    OFFICIAL_SOURCE_SEARCH_INDEX_WRITE_ENABLED: bool = True
    OFFICIAL_SOURCE_SEARCH_INDEX_WRITE_MAX_ITEMS: int = 120
    WEIBO_SEARCH_ALLOW_HOT_FALLBACK: bool = False
    CRAWLER_HTTP_CONNECT_TIMEOUT_SECONDS: float = 6.0
    CRAWLER_HTTP_READ_TIMEOUT_SECONDS: float = 15.0
    CRAWLER_WEB_FALLBACK_CONNECT_TIMEOUT_SECONDS: float = 6.0
    CRAWLER_WEB_FALLBACK_READ_TIMEOUT_SECONDS: float = 12.0
    CRAWLER_ENABLE_WEB_FALLBACK: bool = True
    CRAWLER_WEB_FALLBACK_CONCURRENCY: int = 3
    CRAWLER_SEARCH_MAX_CONCURRENCY: int = 8
    CRAWLER_BOCHA_FALLBACK_ENABLED: bool = True
    CRAWLER_BOCHA_FALLBACK_PLATFORM_ALLOWLIST: str = (
        "rss_pool,news,weibo,zhihu,xinhua,peoples_daily"
    )
    CRAWLER_BOCHA_FALLBACK_MAX_QUERY_VARIANTS: int = 1
    CRAWLER_BOCHA_FALLBACK_FETCH_MULTIPLIER: int = 2
    CRAWLER_BOCHA_FALLBACK_CACHE_TTL_SEC: int = 120
    CRAWLER_BOCHA_FALLBACK_ALLOW_CROSS_DOMAIN_FOR_SOCIAL: bool = True
    CRAWLER_BOCHA_FALLBACK_SOCIAL_PLATFORMS: str = (
        "weibo,zhihu,xiaohongshu,douyin,bilibili,kuaishou,douban"
    )

    # 微博
    WEIBO_COOKIES: Optional[str] = None
    WEIBO_COOKIES_POOL: str = ""
    WEIBO_RATE_LIMIT: int = 10  # 每秒请求数
    WEIBO_ENABLE_PUBLIC_SEARCH: bool = True

    # Twitter/X
    TWITTER_BEARER_TOKEN: Optional[str] = None
    TWITTER_API_KEY: Optional[str] = None
    TWITTER_API_SECRET: Optional[str] = None

    # 小红书
    XHS_COOKIES: Optional[str] = None

    # 抖音
    DOUYIN_COOKIES: Optional[str] = None

    # 知乎 / B站 / 快手 / 豆瓣
    ZHIHU_COOKIES: Optional[str] = None
    ZHIHU_COOKIES_POOL: str = ""
    BILIBILI_COOKIES: Optional[str] = None
    KUAISHOU_COOKIES: Optional[str] = None
    DOUBAN_COOKIES: Optional[str] = None
    ACCOUNT_POOL_ENABLED: bool = True
    ACCOUNT_POOL_MAX_FAILURES: int = 3
    ACCOUNT_POOL_COOLDOWN_SEC: int = 300

    # Reddit
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USER_AGENT: Optional[str] = None

    # GitHub / Stack Overflow
    GITHUB_TOKEN: Optional[str] = None
    STACKOVERFLOW_API_KEY: Optional[str] = None

    # OpenAlex
    OPENALEX_EMAIL: Optional[str] = None

    # ======================
    # MCP服务器配置
    # ======================
    MCP_SERVER_HOST: str = "0.0.0.0"
    MCP_SERVER_PORT: int = 3000
    MCP_SERVER_NAME: str = "aletheia-reasoning-engine"

    # ======================
    # 物理验证配置
    # ======================
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    DEEPFAKE_DETECTION_THRESHOLD: float = 0.7

    # ======================
    # 熵值计算配置
    # ======================
    ENTROPY_LOW_THRESHOLD: float = 0.3  # 低于此值标记为人工放大
    ENTROPY_HIGH_THRESHOLD: float = 0.7  # 高于此值认为自然传播

    # ======================
    # CORS配置
    # ======================
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]
    BACKEND_CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # ======================
    # 日志配置
    # ======================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text

    # ======================
    # 监控配置
    # ======================
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True

    # ======================
    # 缓存配置
    # ======================
    CACHE_DEFAULT_TIMEOUT: int = 300  # 5分钟
    CACHE_ANALYSIS_RESULT_TIMEOUT: int = 3600  # 1小时
    CACHE_BASELINE_TIMEOUT: int = 86400  # 24小时

    # ======================
    # 速率限制
    # ======================
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # ======================
    # 超时配置 (Timeout Configuration)
    # ======================

    # Database timeouts
    DB_CONNECT_TIMEOUT: int = 10  # Connection timeout in seconds
    DB_QUERY_TIMEOUT: int = 60    # Query timeout in seconds
    DB_POOL_TIMEOUT: int = 30     # Pool wait timeout in seconds
    DB_POOL_RECYCLE: int = 1800   # Recycle connections after N seconds

    # SQLite timeouts
    SQLITE_BUSY_TIMEOUT: int = 30000  # Busy timeout in milliseconds
    SQLITE_CONNECT_TIMEOUT: int = 30  # Connection timeout in seconds

    # Redis timeouts
    REDIS_CONNECT_TIMEOUT: int = 2    # Connection timeout in seconds
    REDIS_SOCKET_TIMEOUT: int = 5     # Socket operation timeout
    REDIS_POOL_SIZE: int = 20         # Connection pool size
    REDIS_RECONNECT_BACKOFF_MAX: int = 60  # Max backoff for reconnection

    # LLM timeouts
    LLM_CONNECT_TIMEOUT: int = 10     # Connection timeout
    LLM_READ_TIMEOUT: int = 30        # Read/response timeout
    LLM_MAX_RETRIES: int = 3          # Max retry attempts
    LLM_RETRY_BACKOFF_BASE: float = 1.0  # Base for exponential backoff

    # HTTP timeouts (for crawlers and external APIs)
    HTTP_DEFAULT_TIMEOUT: int = 30    # Default HTTP timeout
    HTTP_CONNECT_TIMEOUT: int = 6     # HTTP connection timeout
    HTTP_READ_TIMEOUT: int = 15       # HTTP read timeout

    # Circuit breaker defaults
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 60
    CIRCUIT_BREAKER_HALF_OPEN_REQUESTS: int = 3

    # Health check intervals
    HEALTH_CHECK_INTERVAL: int = 30   # Seconds between health checks
    HEALTH_CHECK_TIMEOUT: int = 10    # Timeout for health check operations

    # ======================
    # 告警配置 (Alerting Configuration)
    # ======================
    ALERT_ENABLED: bool = True

    # ======================
    # Fake News Detection 配置
    # ======================
    FAKE_NEWS_MODEL_PATH: str = "models/fake_news_model.joblib"
    FAKE_NEWS_MIN_TEXT_LENGTH: int = 20

    # DingTalk
    ALERT_DINGTALK_WEBHOOK: Optional[str] = None
    ALERT_DINGTALK_SECRET: Optional[str] = None

    # WeChat Work
    ALERT_WECHAT_WEBHOOK: Optional[str] = None

    # Slack
    ALERT_SLACK_WEBHOOK: Optional[str] = None

    # Email
    ALERT_SMTP_HOST: Optional[str] = None
    ALERT_SMTP_PORT: int = 587
    ALERT_SMTP_USER: str = ""
    ALERT_SMTP_PASSWORD: str = ""
    ALERT_SMTP_FROM: str = "alerts@aletheia.local"
    ALERT_SMTP_TO: str = ""  # Comma-separated list
    ALERT_SMTP_USE_TLS: bool = True

    # Generic Webhook
    ALERT_WEBHOOK_URL: Optional[str] = None
    ALERT_WEBHOOK_HEADERS: Dict[str, str] = {}

    @property
    def DATABASE_CONNECT_ARGS(self) -> dict:
        """Get database connection arguments"""
        return {
            "connect_timeout": self.DB_CONNECT_TIMEOUT,
            "command_timeout": self.DB_QUERY_TIMEOUT,
        }

    @property
    def REDIS_POOL_KWARGS(self) -> dict:
        """Get Redis pool arguments"""
        return {
            "max_connections": self.REDIS_POOL_SIZE,
            "socket_connect_timeout": self.REDIS_CONNECT_TIMEOUT,
            "socket_timeout": self.REDIS_SOCKET_TIMEOUT,
            "socket_keepalive": True,
            "retry_on_timeout": True,
        }

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


def _apply_outbound_network_env(cfg: Settings) -> None:
    """
    将 .env 中的网络模式应用到当前进程环境，确保所有 httpx/aiohttp 客户端行为一致。
    """
    mode = str(getattr(cfg, "OUTBOUND_NETWORK_MODE", "auto") or "auto").strip().lower()
    proxy = str(getattr(cfg, "OUTBOUND_PROXY_URL", "") or "").strip()
    required_no_proxy = str(
        getattr(cfg, "OUTBOUND_NO_PROXY", "127.0.0.1,localhost,::1")
        or "127.0.0.1,localhost,::1"
    ).strip()

    if required_no_proxy:
        os.environ["NO_PROXY"] = required_no_proxy
        os.environ["no_proxy"] = required_no_proxy

    if mode == "direct":
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)
        return

    if mode == "fixed_proxy" and proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy


# 导出配置实例
settings = get_settings()
_apply_outbound_network_env(settings)
