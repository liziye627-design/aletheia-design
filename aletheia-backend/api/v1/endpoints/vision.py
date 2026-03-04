"""
视觉分析API端点 - 图像相似度检测和视觉内容分析
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from services.image_similarity import get_image_similarity_service
from services.vision_analysis import get_vision_service
from utils.logging import logger


router = APIRouter(tags=["vision"])


# ============= Request/Response Models =============


class ImageAnalysisRequest(BaseModel):
    """图像分析请求"""

    image_url: str = Field(..., description="图像URL")
    analysis_type: str = Field(
        default="comprehensive",
        description="分析类型: comprehensive(综合分析), fake_detection(伪造检测), ocr(文字提取)",
    )


class ImageAnalysisResponse(BaseModel):
    """图像分析响应"""

    image_url: str
    analysis_type: str
    result: Dict[str, Any]
    confidence: float
    processing_time_ms: int


class ImageComparisonRequest(BaseModel):
    """图像对比请求"""

    image_url_1: str = Field(..., description="第一张图像URL")
    image_url_2: str = Field(..., description="第二张图像URL")
    threshold: float = Field(
        default=10.0, ge=0, le=64, description="相似度阈值(Hamming距离)"
    )


class ImageComparisonResponse(BaseModel):
    """图像对比响应"""

    image_url_1: str
    image_url_2: str
    is_similar: bool
    hamming_distance: int
    similarity_percentage: float
    phash_1: str
    phash_2: str


class BatchImageAnalysisRequest(BaseModel):
    """批量图像分析请求"""

    image_urls: List[str] = Field(
        ..., max_items=20, description="图像URL列表（最多20张）"
    )
    analysis_type: str = Field(default="comprehensive", description="分析类型")


class FakeImageDetectionRequest(BaseModel):
    """伪造图像检测请求"""

    image_url: str = Field(..., description="待检测图像URL")
    context: str = Field(default="", description="上下文信息（可选）")


class FakeImageDetectionResponse(BaseModel):
    """伪造图像检测响应"""

    image_url: str
    is_fake: bool
    confidence: float
    indicators: List[Dict[str, Any]]
    explanation: str


# ============= API Endpoints =============


@router.post("/analyze-image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    """
    分析单张图像

    - **image_url**: 图像URL
    - **analysis_type**: 分析类型（comprehensive/fake_detection/ocr）

    返回图像的详细分析结果
    """
    import time

    start_time = time.time()

    logger.info(
        f"🖼️ Analyzing image: {request.image_url} (type: {request.analysis_type})"
    )

    try:
        vision_service = get_vision_service()

        if request.analysis_type == "comprehensive":
            result = await vision_service.analyze_image(request.image_url)
        elif request.analysis_type == "fake_detection":
            result = await vision_service.detect_fake_image(request.image_url)
        elif request.analysis_type == "ocr":
            result = await vision_service.extract_text_from_image(request.image_url)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid analysis_type: {request.analysis_type}. Must be: comprehensive, fake_detection, or ocr",
            )

        processing_time = int((time.time() - start_time) * 1000)

        return ImageAnalysisResponse(
            image_url=request.image_url,
            analysis_type=request.analysis_type,
            result=result,
            confidence=result.get("confidence", 0.8),
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"❌ Image analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")


@router.post("/compare-images", response_model=ImageComparisonResponse)
async def compare_images(request: ImageComparisonRequest):
    """
    对比两张图像的相似度

    - **image_url_1**: 第一张图像URL
    - **image_url_2**: 第二张图像URL
    - **threshold**: 相似度阈值（Hamming距离，默认10）

    使用感知哈希(pHash)算法计算图像相似度
    """
    logger.info(f"🔍 Comparing images: {request.image_url_1} vs {request.image_url_2}")

    try:
        similarity_service = get_image_similarity_service()

        # 计算感知哈希
        phash_1 = await similarity_service.calculate_phash(request.image_url_1)
        phash_2 = await similarity_service.calculate_phash(request.image_url_2)

        # 计算Hamming距离
        hamming_distance = similarity_service.hamming_distance(phash_1, phash_2)

        # 判断是否相似
        is_similar = hamming_distance <= request.threshold

        # 计算相似度百分比（64位哈希）
        similarity_percentage = (64 - hamming_distance) / 64 * 100

        logger.info(
            f"✅ Comparison result: hamming_distance={hamming_distance}, "
            f"similarity={similarity_percentage:.1f}%, similar={is_similar}"
        )

        return ImageComparisonResponse(
            image_url_1=request.image_url_1,
            image_url_2=request.image_url_2,
            is_similar=is_similar,
            hamming_distance=hamming_distance,
            similarity_percentage=round(similarity_percentage, 2),
            phash_1=phash_1,
            phash_2=phash_2,
        )

    except Exception as e:
        logger.error(f"❌ Image comparison failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Image comparison failed: {str(e)}"
        )


@router.post("/detect-fake-image", response_model=FakeImageDetectionResponse)
async def detect_fake_image(request: FakeImageDetectionRequest):
    """
    检测图像是否为伪造（PS、AI生成等）

    - **image_url**: 待检测图像URL
    - **context**: 上下文信息（可选，帮助提高检测准确度）

    使用SiliconFlow Qwen2-VL-72B模型进行深度分析
    """
    logger.info(f"🔍 Detecting fake image: {request.image_url}")

    try:
        vision_service = get_vision_service()

        # 调用伪造检测
        result = await vision_service.detect_fake_image(
            image_url=request.image_url, context=request.context
        )

        # 解析结果
        is_fake = result.get("is_fake", False)
        confidence = result.get("confidence", 0.0)
        indicators = result.get("indicators", [])
        explanation = result.get("explanation", "")

        logger.info(
            f"✅ Fake detection: is_fake={is_fake}, confidence={confidence:.2f}"
        )

        return FakeImageDetectionResponse(
            image_url=request.image_url,
            is_fake=is_fake,
            confidence=confidence,
            indicators=indicators,
            explanation=explanation,
        )

    except Exception as e:
        logger.error(f"❌ Fake image detection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Fake detection failed: {str(e)}")


@router.post("/batch-analyze", response_model=List[ImageAnalysisResponse])
async def batch_analyze_images(request: BatchImageAnalysisRequest):
    """
    批量分析多张图像（最多20张）

    - **image_urls**: 图像URL列表
    - **analysis_type**: 分析类型

    并发处理多张图像以提高效率
    """
    if len(request.image_urls) > 20:
        raise HTTPException(
            status_code=400, detail="Maximum 20 images per batch request"
        )

    logger.info(f"📦 Batch analyzing {len(request.image_urls)} images")

    try:
        vision_service = get_vision_service()

        # 批量处理
        results = await vision_service.batch_analyze(
            image_urls=request.image_urls,
            max_workers=5,  # 限制并发数
        )

        # 构建响应
        responses = []
        for idx, (image_url, result) in enumerate(zip(request.image_urls, results)):
            if result.get("error"):
                # 处理失败的图像
                logger.warning(f"⚠️ Image {idx + 1} failed: {result['error']}")
                continue

            responses.append(
                ImageAnalysisResponse(
                    image_url=image_url,
                    analysis_type=request.analysis_type,
                    result=result,
                    confidence=result.get("confidence", 0.8),
                    processing_time_ms=result.get("processing_time_ms", 0),
                )
            )

        logger.info(
            f"✅ Batch analysis completed: {len(responses)}/{len(request.image_urls)} successful"
        )

        return responses

    except Exception as e:
        logger.error(f"❌ Batch analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")


@router.post("/find-duplicates")
async def find_duplicate_images(
    image_urls: List[str] = Form(..., description="图像URL列表"),
    threshold: float = Form(default=10.0, ge=0, le=64, description="相似度阈值"),
):
    """
    在图像列表中查找重复或相似图像

    - **image_urls**: 图像URL列表
    - **threshold**: 相似度阈值（Hamming距离）

    返回所有相似图像对及其相似度信息
    """
    if len(image_urls) > 50:
        raise HTTPException(
            status_code=400, detail="Maximum 50 images for duplicate detection"
        )

    logger.info(
        f"🔍 Finding duplicates in {len(image_urls)} images (threshold={threshold})"
    )

    try:
        similarity_service = get_image_similarity_service()

        # 查找重复
        duplicates = await similarity_service.find_duplicates(
            image_urls=image_urls, threshold=threshold
        )

        logger.info(f"✅ Found {len(duplicates)} duplicate groups")

        return {
            "total_images": len(image_urls),
            "threshold": threshold,
            "duplicate_groups": duplicates,
            "duplicate_count": len(duplicates),
        }

    except Exception as e:
        logger.error(f"❌ Duplicate detection failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Duplicate detection failed: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    健康检查端点

    检查视觉分析服务是否正常运行
    """
    try:
        vision_service = get_vision_service()
        similarity_service = get_image_similarity_service()

        # 简单的健康检查（可以添加更多检查）
        status = {
            "status": "healthy",
            "vision_service": "available",
            "similarity_service": "available",
            "model": vision_service.model_name,
        }

        return status

    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
