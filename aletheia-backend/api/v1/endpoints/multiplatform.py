"""
多平台数据源API端点
"""

import asyncio
from typing import List, Optional, Dict, Any, Literal
import os
import glob
from urllib.parse import urlparse
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

try:
    from services.layer1_perception.crawler_manager import get_crawler_manager

    _crawler_import_error = None
except Exception as import_error:
    get_crawler_manager = None
    _crawler_import_error = import_error

try:
    from services.layer2_memory.cross_platform_fusion import get_fusion_service

    _fusion_import_error = None
except Exception as fusion_import_error:
    get_fusion_service = None
    _fusion_import_error = fusion_import_error
from utils.logging import logger
from services.rss_hot_focus_service import get_rss_hot_focus_service
from services.layer1_perception.agents import (
    ConcurrentAgentManager,
    BilibiliAgent,
    DouyinAgent,
    XiaohongshuAgent,
    ZhihuAgent,
    BrowserAgent,
)

router = APIRouter()


DEFAULT_PLATFORMS = [
    "bbc",
    "guardian",
    "reuters",
    "ap_news",
    "xinhua",
    "news",
    "who",
    "un_news",
    "sec",
]
DEFAULT_CREDIBILITY_TIMEOUT_SEC = 15


def _platforms_or_default(platforms: Optional[List[str]]) -> List[str]:
    if platforms and len(platforms) > 0:
        return platforms
    return DEFAULT_PLATFORMS


def _require_crawler_manager():
    if get_crawler_manager is None:
        logger.error(f"❌ crawler_manager unavailable: {_crawler_import_error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crawler manager is unavailable. Please fix backend crawler dependencies.",
        )
    return get_crawler_manager()


def _require_fusion_service():
    if get_fusion_service is None:
        logger.error(f"❌ fusion_service unavailable: {_fusion_import_error}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fusion service is unavailable. Please fix backend fusion dependencies.",
        )
    return get_fusion_service()


# ===== Request/Response Models =====


class MultiPlatformHotTopicsRequest(BaseModel):
    """多平台热搜请求"""

    platforms: Optional[List[str]] = Field(
        None,
        description="平台列表 (weibo, twitter, xiaohongshu)，为空则全部",
        example=["weibo", "twitter"],
    )
    limit_per_platform: int = Field(
        20, ge=1, le=100, description="每个平台返回数量", example=20
    )


class HotFocusRequest(BaseModel):
    """今日传播重点请求"""

    refresh: bool = Field(False, description="是否强制刷新快照")


class MultiPlatformSearchRequest(BaseModel):
    """跨平台搜索请求"""

    keyword: str = Field(..., description="搜索关键词", example="某CEO卷款跑路")
    platforms: Optional[List[str]] = Field(
        None,
        description="平台列表 (weibo, twitter, xiaohongshu)，为空则全部",
        example=["weibo", "twitter"],
    )
    limit_per_platform: int = Field(
        20, ge=1, le=100, description="每个平台返回数量", example=20
    )


class CrossPlatformAggregationRequest(BaseModel):
    """跨平台数据聚合请求"""

    keyword: str = Field(..., description="搜索关键词", example="某CEO卷款跑路")
    platforms: Optional[List[str]] = Field(
        None,
        description="平台列表 (weibo, twitter, xiaohongshu)，为空则全部",
        example=["weibo", "twitter", "xiaohongshu"],
    )
    limit_per_platform: int = Field(
        50, ge=1, le=100, description="每个平台返回数量", example=50
    )
    collection_rounds: int = Field(
        3, ge=1, le=10, description="多轮采集轮数（用于减少NO_DATA）"
    )
    round_interval_sec: float = Field(
        1.0, ge=0, le=10, description="轮次之间的间隔秒数"
    )


class PlaywrightOrchestrationRequest(BaseModel):
    """Playwright Agent 编排请求"""

    keywords: List[str] = Field(
        ..., min_length=1, description="要在平台站内搜索的关键词列表"
    )
    platforms: Optional[List[str]] = Field(
        default_factory=lambda: ["bilibili", "douyin", "xiaohongshu", "zhihu"],
        description="支持平台: bilibili/douyin/xiaohongshu/zhihu",
    )
    limit_per_platform: int = Field(
        10, ge=1, le=50, description="每个平台返回数量", example=10
    )
    max_concurrent_agents: int = Field(
        2, ge=1, le=5, description="最大并发Agent数", example=2
    )
    headless: bool = Field(True, description="是否无头浏览器模式")
    storage_state_path: Optional[str] = Field(
        default=None,
        description="可选：Playwright storage_state 文件路径，用于登录态复用",
    )
    storage_state_map: Optional[Dict[str, str]] = Field(
        default=None,
        description="可选：按平台传入 storage_state 路径，如 {'xiaohongshu':'/path/xhs.json'}",
    )
    manual_takeover: bool = Field(
        default=False,
        description="遇到验证墙时是否允许人工接管后继续（仅非headless有效）",
    )
    manual_takeover_timeout_sec: int = Field(
        default=120,
        ge=10,
        le=900,
        description="人工接管等待秒数",
    )
    blocked_screenshot_dir: Optional[str] = Field(
        default=None,
        description="可选：验证墙自动截图输出目录",
    )
    search_mode: Literal["keyword_search"] = Field(
        "keyword_search",
        description="固定为关键词搜索模式：不会基于当前页面内容推断，只执行站内关键词检索",
    )


class PlaywrightRenderedExtractRequest(BaseModel):
    """Playwright 渲染后抽取请求"""

    url: str = Field(..., description="目标网页URL")
    critical_selector: Optional[str] = Field(
        default=None,
        description="关键选择器（可选），用于确认页面关键区域已渲染",
    )
    extraction_schema: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        alias="schema",
        serialization_alias="schema",
        description="字段抽取规则：field -> {selector, mode, attr, many}",
    )
    api_url_keyword: str = Field(
        default="",
        description="仅保留URL包含该关键词的JSON响应",
    )
    max_api_items: int = Field(30, ge=1, le=200)
    visible_text_limit: int = Field(18000, ge=1000, le=200000)
    html_limit: int = Field(250000, ge=10000, le=2000000)
    headless: bool = Field(True, description="是否无头模式")
    storage_state_path: Optional[str] = Field(
        default=None, description="可选storage_state路径"
    )

    model_config = {"populate_by_name": True}

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http/https URL")
        return value

    @field_validator("extraction_schema")
    @classmethod
    def _validate_schema(
        cls, value: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        if not isinstance(value, dict):
            raise ValueError("schema must be an object")
        for field_name, rule in value.items():
            if not isinstance(rule, dict):
                raise ValueError(f"schema.{field_name} must be an object")
            if "selector" in rule and not isinstance(rule.get("selector"), str):
                raise ValueError(f"schema.{field_name}.selector must be string")
        return value


@router.get("/playwright/health", status_code=status.HTTP_200_OK)
async def playwright_health_check():
    """检查 Playwright 浏览器运行环境"""
    candidates = glob.glob(
        os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")
    )
    browser_path = candidates[0] if candidates else ""
    browser_installed = len(candidates) > 0 and os.path.exists(browser_path)

    deps_hint = "缺少系统依赖，请在服务器执行: sudo playwright install-deps"

    return {
        "success": True,
        "browser_installed": browser_installed,
        "browser_path": browser_path,
        "ready": browser_installed,
        "next_step": None if browser_installed else deps_hint,
    }


# ===== API Endpoints =====


@router.post("/playwright-rendered-extract", status_code=status.HTTP_200_OK)
async def playwright_rendered_extract(request: PlaywrightRenderedExtractRequest):
    """
    抓取“渲染完成后的页面信息”:
    - diagnostics
    - schema fields
    - visible_text/html
    - API JSON responses
    """
    try:
        async with BrowserAgent(
            headless=request.headless,
            storage_state_path=request.storage_state_path,
        ) as agent:
            payload = await agent.capture_rendered_page(
                url=request.url,
                critical_selector=request.critical_selector,
                schema=request.extraction_schema,
                api_url_keyword=request.api_url_keyword,
                max_api_items=request.max_api_items,
                visible_text_limit=request.visible_text_limit,
                html_limit=request.html_limit,
            )
        return payload
    except Exception as e:
        logger.error(f"❌ Playwright rendered extract failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Playwright rendered extract failed: {str(e)}",
        )


@router.post("/hot-topics", status_code=status.HTTP_200_OK)
async def get_multi_platform_hot_topics(request: MultiPlatformHotTopicsRequest):
    """
    获取多平台热搜榜

    - **platforms**: 平台列表（默认全部：weibo, twitter, xiaohongshu）
    - **limit_per_platform**: 每个平台返回数量（1-100）

    返回:
    - {platform_name: [hot_topics]}
    """
    logger.info(f"🔥 Fetching hot topics from platforms: {request.platforms or 'all'}")

    try:
        manager = _require_crawler_manager()
        hot_topics = await manager.fetch_hot_topics_multi_platform(
            platforms=_platforms_or_default(request.platforms),
            limit_per_platform=request.limit_per_platform,
        )

        total = sum(len(topics) for topics in hot_topics.values())
        logger.info(f"✅ Fetched {total} hot topics from {len(hot_topics)} platforms")

        return {
            "success": True,
            "data": hot_topics,
            "total_topics": total,
            "platform_count": len(hot_topics),
        }

    except Exception as e:
        logger.error(f"❌ Failed to fetch hot topics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch hot topics: {str(e)}",
        )


@router.post("/hot-focus", status_code=status.HTTP_200_OK)
async def get_hot_focus_snapshot(request: HotFocusRequest):
    """
    获取处理后的今日传播重点快照

    流程:
    - 聚合 RSS 多源候选
    - 标准化与去重
    - 按类别和新鲜度排序
    - 返回首页摘要与详情页列表
    """
    try:
        service = await get_rss_hot_focus_service()
        payload = await service.build_snapshot(refresh=bool(request.refresh))
        return {"success": True, **payload}
    except Exception as e:
        logger.error(f"❌ Failed to build hot focus snapshot: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build hot focus snapshot: {str(e)}",
        )


@router.post("/search", status_code=status.HTTP_200_OK)
async def search_across_platforms(request: MultiPlatformSearchRequest):
    """
    跨平台搜索关键词

    - **keyword**: 搜索关键词
    - **platforms**: 平台列表（默认全部）
    - **limit_per_platform**: 每个平台返回数量（1-100）

    返回:
    - {platform_name: [posts]}
    """
    logger.info(
        f"🔍 Searching '{request.keyword}' across platforms: {request.platforms or 'all'}"
    )

    try:
        manager = _require_crawler_manager()
        search_results = await manager.search_across_platforms(
            keyword=request.keyword,
            platforms=_platforms_or_default(request.platforms),
            limit_per_platform=request.limit_per_platform,
        )

        total = sum(len(posts) for posts in search_results.values())
        logger.info(
            f"✅ Found {total} posts for '{request.keyword}' from {len(search_results)} platforms"
        )

        return {
            "success": True,
            "keyword": request.keyword,
            "data": search_results,
            "total_posts": total,
            "platform_count": len(search_results),
        }

    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.post("/aggregate", status_code=status.HTTP_200_OK)
async def aggregate_cross_platform_data(request: CrossPlatformAggregationRequest):
    """
    跨平台数据聚合分析（核心功能）

    - **keyword**: 搜索关键词
    - **platforms**: 平台列表（默认全部）
    - **limit_per_platform**: 每个平台返回数量（1-100）

    返回:
    - 聚合统计数据（总发帖量、互动量、新账户占比等）
    - 各平台独立统计
    - 高频实体（话题标签）
    - 时间分布（检测异常发布模式）
    - 原始数据

    **用于Layer 2基线建立和异常检测**
    """
    logger.info(
        f"📊 Aggregating data for '{request.keyword}' across platforms: {request.platforms or 'all'}"
    )

    try:
        manager = _require_crawler_manager()
        aggregated_data = await manager.aggregate_cross_platform_data(
            keyword=request.keyword,
            platforms=_platforms_or_default(request.platforms),
            limit_per_platform=request.limit_per_platform,
        )

        logger.info(
            f"✅ Aggregated {aggregated_data['summary']['total_posts']} posts "
            f"from {aggregated_data['summary']['platform_count']} platforms"
        )

        return {"success": True, "data": aggregated_data}

    except Exception as e:
        logger.error(f"❌ Aggregation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Aggregation failed: {str(e)}",
        )


@router.get("/platforms", status_code=status.HTTP_200_OK)
async def get_available_platforms():
    """
    获取可用的平台列表及其状态

    返回:
    - 平台名称
    - 是否可用
    - 配置状态
    """
    logger.info("📋 Fetching available platforms")

    try:
        manager = _require_crawler_manager()

        display_names = {
            "weibo": "微博",
            "twitter": "Twitter/X",
            "xiaohongshu": "小红书",
            "douyin": "抖音",
            "zhihu": "知乎",
            "bilibili": "哔哩哔哩",
            "xinhua": "新华网",
            "peoples_daily": "人民网",
            "china_gov": "国务院官网",
            "reuters": "Reuters",
            "ap_news": "AP News",
            "bbc": "BBC",
            "guardian": "The Guardian",
            "caixin": "财新",
            "the_paper": "澎湃新闻",
        }

        platforms_info = []
        for platform_name in sorted(manager.crawlers.keys()):
            crawler = manager.crawlers.get(platform_name)
            config_status = "✅ Configured" if crawler else "❌ Not configured"
            platforms_info.append(
                {
                    "name": platform_name,
                    "display_name": display_names.get(platform_name, platform_name),
                    "available": crawler is not None,
                    "config_status": config_status,
                }
            )

        available_count = sum(1 for p in platforms_info if p["available"])

        return {
            "success": True,
            "platforms": platforms_info,
            "total_platforms": len(platforms_info),
            "available_platforms": available_count,
        }

    except Exception as e:
        logger.error(f"❌ Failed to fetch platforms: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch platforms: {str(e)}",
        )


@router.get("/platform/{platform_name}/status", status_code=status.HTTP_200_OK)
async def get_platform_status(platform_name: str):
    """
    获取单个平台的详细状态

    - **platform_name**: 平台名称 (weibo, twitter, xiaohongshu)

    返回:
    - 是否可用
    - 请求计数
    - 配置信息
    """
    logger.info(f"🔍 Checking status for platform: {platform_name}")

    try:
        manager = _require_crawler_manager()

        is_available = platform_name in manager.crawlers

        if not is_available:
            return {
                "success": False,
                "platform": platform_name,
                "available": False,
                "message": f"Platform '{platform_name}' is not configured",
            }

        crawler = manager.crawlers[platform_name]

        return {
            "success": True,
            "platform": platform_name,
            "available": True,
            "request_count": crawler._request_count,
            "rate_limit": crawler.rate_limit,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get platform status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get platform status: {str(e)}",
        )


@router.post("/analyze-credibility", status_code=status.HTTP_200_OK)
async def analyze_cross_platform_credibility(request: CrossPlatformAggregationRequest):
    """
    跨平台可信度综合分析（核心功能 - 整合Layer 1+2）

    - **keyword**: 待验证信息关键词
    - **platforms**: 平台列表（默认全部）
    - **limit_per_platform**: 每个平台返回数量（1-100）

    返回:
    - 综合可信度评分 (0.0-1.0)
    - 可信度等级 (VERY_LOW/LOW/MEDIUM/HIGH/VERY_HIGH)
    - 风险标签 (异常模式识别)
    - 各平台统计数据
    - 基线对比分析
    - 异常检测结果
    - 证据链

    **这是Aletheia系统的核心功能之一，结合多源数据采集和统计分析**
    """
    logger.info(f"🎯 Cross-platform credibility analysis for '{request.keyword}'")

    try:
        fusion_service = _require_fusion_service()
        result = await asyncio.wait_for(
            fusion_service.analyze_cross_platform_credibility(
                keyword=request.keyword,
                platforms=_platforms_or_default(request.platforms),
                limit_per_platform=request.limit_per_platform,
            ),
            timeout=DEFAULT_CREDIBILITY_TIMEOUT_SEC,
        )

        logger.info(
            f"✅ Credibility analysis completed - Score: {result['credibility_score']:.2%} "
            f"({result['credibility_level']})"
        )

        return {"success": True, "data": result}

    except asyncio.TimeoutError:
        logger.warning("⚠️ Credibility analysis timeout, fallback to degradable response")
        return {
            "success": False,
            "data": {
                "keyword": request.keyword,
                "timestamp": datetime.utcnow().isoformat(),
                "credibility_score": 0.45,
                "credibility_level": "UNCERTAIN",
                "risk_flags": ["INSUFFICIENT_EVIDENCE", "TIME_BUDGET_EXCEEDED"],
                "summary": {
                    "total_posts": 0,
                    "total_engagement": 0,
                    "avg_engagement": 0.0,
                    "platform_count": len(_platforms_or_default(request.platforms)),
                    "new_account_ratio": 0.0,
                },
                "platform_stats": {},
                "baseline": {},
                "anomalies": [
                    {
                        "type": "TIME_BUDGET_EXCEEDED",
                        "platform": "all",
                        "severity": "MEDIUM",
                        "description": "Cross-platform credibility timed out and returned fallback.",
                        "confidence": 0.9,
                    }
                ],
                "evidence": [],
            },
            "message": "Credibility analysis timed out, returned fallback result",
        }

    except Exception as e:
        logger.error(f"❌ Credibility analysis failed: {e}")
        # 降级返回，避免前端双工链路整体失败
        return {
            "success": False,
            "data": {
                "keyword": request.keyword,
                "timestamp": datetime.utcnow().isoformat(),
                "credibility_score": 0.45,
                "credibility_level": "UNCERTAIN",
                "risk_flags": ["INSUFFICIENT_EVIDENCE", "ANALYSIS_ERROR"],
                "summary": {
                    "total_posts": 0,
                    "total_engagement": 0,
                    "avg_engagement": 0.0,
                    "platform_count": len(_platforms_or_default(request.platforms)),
                    "new_account_ratio": 0.0,
                },
                "platform_stats": {},
                "baseline": {},
                "anomalies": [
                    {
                        "type": "ANALYSIS_ERROR",
                        "platform": "all",
                        "severity": "HIGH",
                        "description": str(e),
                    }
                ],
                "evidence_chain": [
                    {
                        "step": "degraded_analysis",
                        "description": f"分析失败，返回可解释降级结果: {e}",
                    }
                ],
                "top_entities": [],
                "time_distribution": {},
            },
            "error": str(e),
        }


# =====================
# 多Agent + SiliconFlow 智能分析
# =====================
@router.post("/multi-agent-analyze", status_code=status.HTTP_200_OK)
async def multi_agent_siliconflow_analyze(request: CrossPlatformAggregationRequest):
    """
    多Agent + SiliconFlow 智能分析

    **工作流程:**
    1. 各平台 Agent 并行爬取数据
    2. SiliconFlow 小模型分析每个平台数据
    3. SiliconFlow 大模型合成最终结果

    **优势:**
    - 小模型成本低，每个平台独立分析
    - 大模型做最终综合判断
    - 支持多平台交叉验证

    - **keyword**: 搜索/分析关键词
    - **platforms**: 平台列表（默认: weibo, twitter, xiaohongshu, zhihu, bilibili）
    - **limit_per_platform**: 每个平台获取数量（默认10）

    返回:
    - overall_credibility: 整体可信度 (0.0-1.0)
    - credibility_level: 可信度等级
    - platform_results: 各平台详细分析结果
    - synthesis: 大模型综合分析
    - consensus_points: 共识点
    - conflicts: 矛盾点
    - risk_flags: 风险标签
    """
    from services.multi_agent_siliconflow import get_multi_agent_processor

    logger.info(f"🤖 Multi-Agent + SiliconFlow analysis for '{request.keyword}'")

    try:
        processor = get_multi_agent_processor()

        result = await processor.search_and_analyze(
            keyword=request.keyword,
            platforms=_platforms_or_default(request.platforms),
            limit_per_platform=request.limit_per_platform,
            collection_rounds=request.collection_rounds,
            round_interval_sec=request.round_interval_sec,
        )

        logger.info(
            f"✅ Multi-agent analysis completed - Score: {result['overall_credibility']:.2%} "
            f"in {result['processing_time_ms']}ms"
        )

        return {
            "success": True,
            "data": result,
        }

    except Exception as e:
        logger.error(f"❌ Multi-agent analysis failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multi-agent analysis failed: {str(e)}",
        )


@router.post("/playwright-orchestrate", status_code=status.HTTP_200_OK)
async def playwright_agent_orchestrate(request: PlaywrightOrchestrationRequest):
    """
    Playwright Agent 编排搜索（严格关键词模式）

    说明：
    - 走浏览器自动化Agent，而非API爬虫
    - 只做“站内关键词搜索”，不会读取当前页面做自由推断
    """
    supported = {
        "bilibili": BilibiliAgent,
        "douyin": DouyinAgent,
        "xiaohongshu": XiaohongshuAgent,
        "zhihu": ZhihuAgent,
    }

    selected = [p for p in (request.platforms or []) if p in supported]
    if not selected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No supported platforms selected. Use bilibili/douyin/xiaohongshu/zhihu.",
        )

    manager = ConcurrentAgentManager(
        max_concurrent_agents=request.max_concurrent_agents,
        enable_retry=True,
        max_retries=1,
    )

    def resolve_storage_state(platform: str) -> Optional[str]:
        # 1) 请求体按平台显式指定
        if request.storage_state_map and request.storage_state_map.get(platform):
            return request.storage_state_map.get(platform)

        # 2) 通用传参
        if request.storage_state_path:
            return request.storage_state_path

        # 3) 环境变量按平台优先
        env_key = f"PLAYWRIGHT_STORAGE_STATE_{platform.upper()}"
        if os.getenv(env_key):
            return os.getenv(env_key)

        # 4) 环境变量通用兜底
        return os.getenv("PLAYWRIGHT_STORAGE_STATE")

    used_storage_states: Dict[str, str] = {}

    try:
        for platform in selected:
            storage_state_path = resolve_storage_state(platform)
            if storage_state_path:
                used_storage_states[platform] = storage_state_path
            await manager.register_platform(
                platform,
                supported[platform],
                pool_size=request.max_concurrent_agents,
                headless=request.headless,
                storage_state_path=storage_state_path,
                manual_takeover=request.manual_takeover,
                manual_takeover_timeout_sec=request.manual_takeover_timeout_sec,
                blocked_screenshot_dir=request.blocked_screenshot_dir,
            )

        all_results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        total = 0
        cleaned_keywords = [kw.strip() for kw in request.keywords if kw and kw.strip()]
        if not cleaned_keywords:
            raise HTTPException(status_code=400, detail="keywords is empty")

        for kw in cleaned_keywords:
            per_kw = await manager.concurrent_search(
                platforms=selected,
                keyword=kw,
                limit_per_platform=request.limit_per_platform,
            )
            all_results[kw] = per_kw
            total += sum(len(items) for items in per_kw.values())

        diagnostics = manager.last_platform_diagnostics
        reason_stats: Dict[str, int] = {}
        blocked_platforms: List[str] = []
        selector_miss_platforms: List[str] = []
        empty_platforms: List[str] = []
        for platform, diag in (diagnostics or {}).items():
            reason_code = str((diag or {}).get("reason_code") or "UNKNOWN")
            reason_stats[reason_code] = reason_stats.get(reason_code, 0) + 1
            if reason_code == "BLOCKED":
                blocked_platforms.append(platform)
            elif reason_code == "SELECTOR_MISS":
                selector_miss_platforms.append(platform)
            elif reason_code == "EMPTY_RESULT":
                empty_platforms.append(platform)

        return {
            "success": True,
            "search_mode": "keyword_search",
            "keywords": cleaned_keywords,
            "platforms": selected,
            "total_results": total,
            "data": all_results,
            "diagnostics": diagnostics,
            "diagnostics_summary": {
                "reason_stats": reason_stats,
                "blocked_platforms": blocked_platforms,
                "selector_miss_platforms": selector_miss_platforms,
                "empty_result_platforms": empty_platforms,
            },
            "degrade_recommendations": {
                "fallback_to_stable_sources": bool(blocked_platforms or selector_miss_platforms),
                "stable_sources": ["bbc", "guardian", "reuters", "ap_news", "xinhua", "news", "who", "un_news", "sec"],
                "notes": [
                    "blocked/selector_miss 平台建议使用持久化登录态",
                    "若仍失败，按平台降级到稳定信源链路并显式标注 retrieval_mode=degraded",
                ],
            },
            "storage_states": used_storage_states,
        }
    except Exception as e:
        logger.error(f"❌ Playwright orchestration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Playwright orchestration failed: {str(e)}",
        )
    finally:
        try:
            await manager.close_all()
        except Exception:
            pass
