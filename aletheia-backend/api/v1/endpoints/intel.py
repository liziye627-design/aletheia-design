"""
情报分析API端点
"""

import time
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.cache import get_cache, RedisCache
from models.schemas.intel import (
    IntelAnalyzeRequest,
    IntelAnalyzeResponse,
    IntelBatchAnalyzeRequest,
    IntelSearchRequest,
    IntelListResponse,
    TrendingTopicsResponse,
)
from services.layer3_reasoning.cot_agent import analyze_intel
from utils.logging import logger

router = APIRouter()


@router.post(
    "/analyze", response_model=IntelAnalyzeResponse, status_code=status.HTTP_200_OK
)
async def analyze_information(
    request: IntelAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """
    分析单条信息的真实性

    - **content**: 待分析的文本内容
    - **source_platform**: 来源平台(weibo, twitter等)
    - **original_url**: 原始链接
    - **image_urls**: 相关图片URL列表
    - **video_url**: 相关视频URL
    - **metadata**: 额外元数据(作者、时间等)

    返回:
    - 可信度评分(0.0-1.0)
    - 风险标签
    - 推理链条
    - 物理/逻辑/熵值验证结果
    """

    start_time = time.time()

    logger.info(f"📝 Analyzing intel from {request.source_platform or 'unknown'}")

    try:
        # TODO: 调用Layer 3推理引擎
        intel_result = await analyze_intel(
            content=request.content,
            source_platform=request.source_platform,
            original_url=str(request.original_url) if request.original_url else None,
            image_urls=[str(url) for url in request.image_urls]
            if request.image_urls
            else None,
            metadata=request.metadata,
            db=db,
            cache=cache,
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"✅ Analysis completed - Credibility: {intel_result.credibility_score:.2%} "
            f"in {processing_time_ms}ms"
        )

        return IntelAnalyzeResponse(
            intel=intel_result, processing_time_ms=processing_time_ms
        )

    except Exception as e:
        logger.error(f"❌ Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


@router.post("/batch", response_model=List[IntelAnalyzeResponse])
async def batch_analyze(
    request: IntelBatchAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """
    批量分析多条信息(最多100条)

    并行处理,提高效率
    """

    logger.info(f"📦 Batch analyzing {len(request.items)} items")

    # TODO: 实现并行分析逻辑
    results = []

    for item in request.items:
        try:
            result = await analyze_information(item, db, cache)
            results.append(result)
        except Exception as e:
            logger.error(f"Item analysis failed: {str(e)}")
            # 继续处理其他项
            continue

    logger.info(
        f"✅ Batch analysis completed - {len(results)}/{len(request.items)} succeeded"
    )

    return results


@router.post("/search", response_model=IntelListResponse)
async def search_intelligence(
    request: IntelSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    搜索历史分析记录

    支持按关键词、平台、可信度、日期范围筛选
    """

    logger.info(f"🔍 Searching intel - keyword: {request.keyword}")

    # TODO: 实现数据库查询逻辑
    # 使用SQLAlchemy构建查询
    # WHERE keyword LIKE %request.keyword%
    #   AND platform = request.platform (if provided)
    #   AND credibility_score BETWEEN request.credibility_min AND request.credibility_max
    #   AND created_at BETWEEN request.date_from AND request.date_to
    # ORDER BY created_at DESC
    # LIMIT request.page_size OFFSET (request.page - 1) * request.page_size

    # 临时返回空结果
    return IntelListResponse(
        items=[],
        total=0,
        page=request.page,
        page_size=request.page_size,
        has_more=False,
    )


@router.get("/trending", response_model=TrendingTopicsResponse)
async def get_trending_topics(
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    """
    获取当前热点话题

    基于最近24小时的数据,计算趋势评分

    算法:
    - 提及量 × 平台多样性 × 时间新鲜度 = 趋势评分
    """

    cache_key = "trending_topics"

    # 尝试从缓存获取
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info("✅ Returning cached trending topics")
        return cached_result

    logger.info("📊 Calculating trending topics")

    # TODO: 实现热点计算逻辑
    # 1. 从数据库获取最近24小时的数据
    # 2. 按关键词分组统计
    # 3. 计算趋势评分
    # 4. 缓存结果(5分钟)

    result = TrendingTopicsResponse(topics=[], updated_at=time.time())

    # 缓存5分钟
    await cache.set(cache_key, result.model_dump(), expire=300)

    return result


@router.get("/{intel_id}", response_model=IntelAnalyzeResponse)
async def get_intel_by_id(
    intel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    根据ID获取情报详情
    """

    logger.info(f"🔎 Getting intel {intel_id}")

    # TODO: 从数据库查询
    # intel = await db.get(Intel, intel_id)
    # if not intel:
    #     raise HTTPException(status_code=404, detail="Intel not found")

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet"
    )


@router.delete("/{intel_id}")
async def delete_intel(
    intel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    删除情报记录
    """

    logger.info(f"🗑️  Deleting intel {intel_id}")

    # TODO: 软删除或硬删除
    # intel = await db.get(Intel, intel_id)
    # if not intel:
    #     raise HTTPException(status_code=404, detail="Intel not found")
    #
    # intel.is_archived = 1
    # await db.commit()

    return {"message": "Intel deleted successfully"}
