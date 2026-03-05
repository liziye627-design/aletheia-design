"""
Request/Response schemas for Fake News Detection API
"""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Request model for fake news prediction"""

    text: str = Field(..., min_length=20, description="待检测新闻正文")


class PredictResponse(BaseModel):
    """Response model for fake news prediction"""

    label: str = Field(..., description="预测标签")
    prediction: int = Field(..., description="预测值 (0=Fake, 1=Real)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    model_name: str = Field(..., description="模型名称")


class HealthResponse(BaseModel):
    """Response model for health check"""

    status: str = Field(..., description="服务状态")
    model: str = Field(..., description="模型名称")
    loaded: bool = Field(..., description="模型是否已加载")