"""
增强版情报分析 API 端点 - 支持多步推理可视化
"""

import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse

# 开发模式：使用轻量级引擎，不依赖数据库
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from core.database import get_db
    from core.cache import get_cache, RedisCache

    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    AsyncSession = None
    RedisCache = None

from models.schemas.intel import (
    IntelAnalyzeRequest,
    IntelAnalyzeResponse,
    IntelBatchAnalyzeRequest,
    IntelSearchRequest,
    IntelListResponse,
    TrendingTopicsResponse,
)
from pydantic import BaseModel, Field

# 使用轻量级引擎（开发模式，无需数据库）
from services.layer3_reasoning.simple_cot_engine import (
    analyze_intel_enhanced,
    ReasoningChain,
    ReasoningStep,
)
from utils.logging import logger

router = APIRouter()


# =====================
# 新增：推理链响应模型
# =====================
class ReasoningStepResponse(BaseModel):
    """推理步骤响应"""

    stage: str
    timestamp: str
    reasoning: str
    conclusion: str
    confidence: float
    evidence: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    score_impact: float


class ReasoningChainResponse(BaseModel):
    """推理链响应"""

    steps: List[ReasoningStepResponse]
    final_score: float
    final_level: str
    risk_flags: List[str]
    total_confidence: float
    processing_time_ms: int


class EnhancedIntelAnalyzeResponse(BaseModel):
    """增强版分析响应"""

    intel: dict  # Intel 对象
    reasoning_chain: ReasoningChainResponse  # 推理链
    processing_time_ms: int


# =====================
# 增强版分析端点
# =====================
@router.post(
    "/analyze/enhanced",
    response_model=EnhancedIntelAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="增强版真相验证",
    description="使用多步 CoT 推理进行深度分析，返回完整推理链条",
)
async def analyze_information_enhanced(
    request: IntelAnalyzeRequest,
):
    """
    增强版信息真实性分析 - 多步推理

    **核心优势**:
    - 8 阶段推理：预处理 → 物理层 → 逻辑层 → 信源层 → 交叉验证 → 异常检测 → 证据综合 → 自我反思
    - 完整推理链：每个阶段的推理过程、证据、疑点全部可视化
    - 自我修正：AI 自我质疑，避免偏见
    - DeepSeek-V3.2/Qwen2.5-72B 驱动

    **输入**:
    - content: 待分析文本
    - source_platform: 来源平台
    - image_urls: 图片 URL（可选）
    - metadata: 元数据（账号信息、时间等）

    **输出**:
    - reasoning_chain: 完整推理链（8个阶段）
    - final_score: 可信度评分 (0.0-1.0)
    - risk_flags: 风险标签

    **示例**:
    ```python
    {
      "content": "某地发生重大事件...",
      "source_platform": "weibo",
      "metadata": {
        "author_follower_count": 1000,
        "account_age_days": 10
      }
    }
    ```
    """

    start_time = time.time()

    logger.info(
        f"📝 Enhanced analyzing intel from {request.source_platform or 'unknown'}"
    )

    try:
        # 调用轻量级推理引擎（开发模式，无需数据库）
        intel_result, reasoning_chain = await analyze_intel_enhanced(
            content=request.content,
            source_platform=request.source_platform,
            original_url=(str(request.original_url) if request.original_url else None),
            image_urls=(
                [str(url) for url in request.image_urls] if request.image_urls else None
            ),
            metadata=request.metadata,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"✅ Enhanced analysis completed - Score: {intel_result.get('credibility_score', 0):.2%} "
            f"in {processing_time_ms}ms"
        )

        # 构建响应
        reasoning_chain_response = ReasoningChainResponse(
            steps=[
                ReasoningStepResponse(
                    stage=step.stage,
                    timestamp=step.timestamp
                    if isinstance(step.timestamp, str)
                    else step.timestamp.isoformat(),
                    reasoning=step.reasoning,
                    conclusion=step.conclusion,
                    confidence=step.confidence,
                    evidence=step.evidence,
                    concerns=step.concerns,
                    score_impact=step.score_impact,
                )
                for step in reasoning_chain.steps
            ],
            final_score=reasoning_chain.final_score,
            final_level=reasoning_chain.final_level,
            risk_flags=reasoning_chain.risk_flags,
            total_confidence=reasoning_chain.total_confidence,
            processing_time_ms=reasoning_chain.processing_time_ms,
        )

        return EnhancedIntelAnalyzeResponse(
            intel=intel_result,
            reasoning_chain=reasoning_chain_response,
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ Enhanced analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enhanced analysis failed: {str(e)}",
        )


# =====================
# 标准分析端点（保持向后兼容）
# =====================
@router.post(
    "/analyze",
    response_model=IntelAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="标准真相验证",
    description="标准分析模式（快速，无详细推理链）",
)
async def analyze_information(
    request: IntelAnalyzeRequest,
):
    """
    标准信息真实性分析

    使用简化推理，返回基础结果（无详细推理链）
    适用于需要快速响应的场景
    """

    start_time = time.time()

    logger.info(
        f"📝 Standard analyzing intel from {request.source_platform or 'unknown'}"
    )

    try:
        # 使用轻量级引擎（开发模式，无需数据库）
        intel_result, _ = await analyze_intel_enhanced(
            content=request.content,
            source_platform=request.source_platform,
            original_url=(str(request.original_url) if request.original_url else None),
            image_urls=(
                [str(url) for url in request.image_urls] if request.image_urls else None
            ),
            metadata=request.metadata,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"✅ Standard analysis completed - Credibility: {intel_result.get('credibility_score', 0):.2%} "
            f"in {processing_time_ms}ms"
        )

        return IntelAnalyzeResponse(
            intel=intel_result, processing_time_ms=processing_time_ms
        )

    except Exception as e:
        logger.error(f"❌ Standard analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


# =====================
# 推理链可视化端点
# =====================
@router.get(
    "/{intel_id}/reasoning-chain",
    response_model=ReasoningChainResponse,
    summary="获取推理链详情",
    description="获取已分析情报的完整推理链",
)
async def get_reasoning_chain(
    intel_id: str,
):
    """
    获取推理链详情

    返回指定情报的完整推理过程，包括：
    - 8 个推理阶段
    - 每个阶段的推理、证据、疑点
    - 分数变化轨迹

    用于：
    - 审计 AI 决策
    - 理解分析逻辑
    - 训练优化
    """

    logger.info(f"🔎 Getting reasoning chain for {intel_id}")

    # TODO: 从数据库查询
    # intel = await db.get(Intel, intel_id)
    # if not intel:
    #     raise HTTPException(status_code=404, detail="Intel not found")
    #
    # reasoning_chain_data = intel.reasoning_chain
    # return ReasoningChainResponse(**reasoning_chain_data)

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet"
    )


# =====================
# 批量分析（并行）
# =====================
@router.post(
    "/batch",
    response_model=List[EnhancedIntelAnalyzeResponse],
    summary="批量分析",
    description="并行分析多条信息（最多 20 条）",
)
async def batch_analyze(
    request: IntelBatchAnalyzeRequest,
    use_enhanced: bool = Query(
        True, description="是否使用增强版推理（返回完整推理链）"
    ),
):
    """
    批量分析

    **参数**:
    - items: 待分析项列表（最多 20 条）
    - use_enhanced: 是否使用增强版（True: 返回推理链, False: 仅返回结果）

    **并发处理**:
    使用 asyncio.gather 并行执行，提高效率
    """

    if len(request.items) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 20 items allowed per batch",
        )

    logger.info(
        f"📦 Batch analyzing {len(request.items)} items (enhanced={use_enhanced})"
    )

    import asyncio

    # 并行执行所有分析
    tasks = [
        analyze_information_enhanced(item)
        if use_enhanced
        else analyze_information(item)
        for item in request.items
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 过滤异常
    successful_results = [r for r in results if not isinstance(r, Exception)]
    failed_count = len(results) - len(successful_results)

    if failed_count > 0:
        logger.warning(f"⚠️ {failed_count}/{len(request.items)} items failed")

    logger.info(
        f"✅ Batch analysis completed - {len(successful_results)}/{len(request.items)} succeeded"
    )

    return successful_results


# =====================
# 搜索历史分析记录
# =====================
@router.post("/search", response_model=IntelListResponse)
async def search_intelligence(
    request: IntelSearchRequest,
):
    """
    搜索历史分析记录

    **筛选条件**:
    - keyword: 关键词搜索
    - platform: 平台筛选
    - credibility_min/max: 可信度范围
    - date_from/to: 日期范围
    - risk_flags: 风险标签

    **排序**:
    - created_at DESC (最新优先)
    """
    from core.sqlite_database import get_sqlite_db

    logger.info(f"🔍 Searching intel - keyword: {request.keyword}")

    try:
        sqlite_db = get_sqlite_db()

        # 如果有关键词，按关键词搜索
        if request.keyword:
            results = sqlite_db.search_intel(
                keyword=request.keyword, limit=request.page_size
            )
        else:
            # 否则获取最近的记录
            results = sqlite_db.get_recent_intel(limit=request.page_size)

        total = len(results)
        has_more = total > request.page * request.page_size

        return IntelListResponse(
            items=results,
            total=total,
            page=request.page,
            page_size=request.page_size,
            has_more=has_more,
        )

    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


# =====================
# 热点话题
# =====================
@router.get("/trending", response_model=TrendingTopicsResponse)
async def get_trending_topics():
    """
    获取当前热点话题

    **算法**:
    - 最近 24 小时数据
    - 趋势评分 = 提及量 × 平台多样性 × 时间新鲜度 × 可信度

    **缓存**: 5 分钟
    """
    from datetime import datetime

    logger.info("📊 Calculating trending topics")

    # TODO: 实现热点计算逻辑

    result = TrendingTopicsResponse(topics=[], updated_at=datetime.utcnow())

    return result


# =====================
# 获取情报详情
# =====================
@router.get("/{intel_id}", response_model=EnhancedIntelAnalyzeResponse)
async def get_intel_by_id(
    intel_id: str,
):
    """
    根据 ID 获取情报详情
    """
    from core.sqlite_database import get_sqlite_db

    logger.info(f"🔎 Getting intel {intel_id}")

    try:
        sqlite_db = get_sqlite_db()
        # 使用 raw=True 获取原始格式（保持 reasoning_chain 为对象）
        intel_data = sqlite_db.get_intel(intel_id, raw=True)

        if not intel_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Intel not found"
            )

        # 构建响应
        reasoning_chain = intel_data.get("reasoning_chain", {})

        return EnhancedIntelAnalyzeResponse(
            intel=intel_data,
            reasoning_chain=ReasoningChainResponse(
                steps=[
                    ReasoningStepResponse(
                        stage=step.get("stage", ""),
                        timestamp=step.get("timestamp", ""),
                        reasoning=step.get("reasoning", ""),
                        conclusion=step.get("conclusion", ""),
                        confidence=step.get("confidence", 0),
                        evidence=step.get("evidence", []),
                        concerns=step.get("concerns", []),
                        score_impact=step.get("score_impact", 0),
                    )
                    for step in reasoning_chain.get("steps", [])
                ],
                final_score=reasoning_chain.get("final_score", 0),
                final_level=reasoning_chain.get("final_level", "UNCERTAIN"),
                risk_flags=reasoning_chain.get("risk_flags", []),
                total_confidence=reasoning_chain.get("total_confidence", 0),
                processing_time_ms=reasoning_chain.get("processing_time_ms", 0),
            ),
            processing_time_ms=reasoning_chain.get("processing_time_ms", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get intel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get intel: {str(e)}",
        )


# =====================
# 删除情报
# =====================
@router.delete("/{intel_id}")
async def delete_intel(
    intel_id: str,
):
    """
    删除情报记录（软删除）
    """

    logger.info(f"🗑️  Deleting intel {intel_id}")

    # TODO: 软删除实现

    return {"message": "Intel deleted successfully"}


# =====================
# 推理链可视化（HTML）
# =====================
@router.get(
    "/{intel_id}/reasoning-visualization",
    response_class=HTMLResponse,
    summary="推理链可视化",
    description="生成推理链的交互式可视化页面",
)
async def visualize_reasoning_chain(
    intel_id: str,
):
    """
    推理链可视化

    生成一个交互式 HTML 页面，展示：
    - 推理流程图
    - 各阶段评分变化
    - 证据/疑点标注
    - 时间轴
    """

    logger.info(f"🎨 Generating reasoning visualization for {intel_id}")

    # TODO: 从数据库获取数据并生成 HTML

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aletheia - 推理链可视化</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: 'Microsoft YaHei', sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }
            .stage { margin: 20px 0; padding: 20px; border-left: 4px solid #1890ff; background: #f0f9ff; }
            .score { font-size: 24px; font-weight: bold; color: #52c41a; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧠 Aletheia 推理链可视化</h1>
            <p>情报 ID: {intel_id}</p>
            <div class="stage">
                <h3>阶段 1: 预处理</h3>
                <p>推理过程...</p>
                <p class="score">置信度: 85%</p>
            </div>
            <!-- 更多阶段 -->
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content.format(intel_id=intel_id))


# 导入 HTMLResponse
from fastapi.responses import HTMLResponse
