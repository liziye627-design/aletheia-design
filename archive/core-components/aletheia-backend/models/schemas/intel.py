"""
Pydantic数据模式 - 情报分析
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


# ======================
# 请求模型
# ======================


class IntelAnalyzeRequest(BaseModel):
    """分析请求"""

    content: str = Field(..., min_length=1, max_length=10000, description="待分析内容")
    source_platform: Optional[str] = Field(None, description="来源平台")
    original_url: Optional[HttpUrl] = Field(None, description="原始URL")
    image_urls: Optional[List[HttpUrl]] = Field(None, description="图片URL列表")
    video_url: Optional[HttpUrl] = Field(None, description="视频URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "某CEO卷款跑路,受害者已报警",
                "source_platform": "weibo",
                "original_url": "https://weibo.com/xxxxx",
                "image_urls": ["https://example.com/screenshot.jpg"],
                "metadata": {
                    "author_id": "user_123",
                    "timestamp": "2026-02-01T12:34:56Z",
                },
            }
        }


class IntelBatchAnalyzeRequest(BaseModel):
    """批量分析请求"""

    items: List[IntelAnalyzeRequest] = Field(..., min_length=1, max_length=100)


class IntelSearchRequest(BaseModel):
    """搜索请求"""

    keyword: Optional[str] = Field(None, description="关键词")
    platform: Optional[str] = Field(None, description="平台筛选")
    credibility_min: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="最低可信度"
    )
    credibility_max: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="最高可信度"
    )
    date_from: Optional[datetime] = Field(None, description="开始日期")
    date_to: Optional[datetime] = Field(None, description="结束日期")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


# ======================
# 响应模型
# ======================


class PhysicsVerificationResult(BaseModel):
    """物理验证结果"""

    shadow_angle_match: Optional[float] = Field(None, description="阴影角度匹配度")
    metadata_consistent: Optional[bool] = Field(None, description="元数据一致性")
    deepfake_probability: Optional[float] = Field(None, description="深伪概率")
    inconsistencies: List[str] = Field(default_factory=list, description="不一致项")


class LogicVerificationResult(BaseModel):
    """逻辑验证结果"""

    causal_chain_complete: bool = Field(..., description="因果链是否完整")
    contradictions: List[str] = Field(default_factory=list, description="矛盾点")
    fallacies: List[str] = Field(default_factory=list, description="逻辑谬误")


class EntropyAnalysisResult(BaseModel):
    """熵值分析结果"""

    source_entropy: float = Field(..., description="信息源熵值")
    water_army_ratio: float = Field(..., description="水军账号占比")
    account_clustering: Optional[Dict[str, Any]] = Field(None, description="账号聚类")


class IntelResponse(BaseModel):
    """情报响应"""

    id: str
    source_platform: str
    original_url: str
    content_text: str
    content_type: str

    # 分析结果
    credibility_score: Optional[float] = None
    credibility_level: Optional[str] = None
    confidence: Optional[str] = None
    risk_flags: Optional[List[str]] = None
    reasoning_chain: Optional[List[str]] = None

    # 验证结果
    physics_verification: Optional[PhysicsVerificationResult] = None
    logic_verification: Optional[LogicVerificationResult] = None
    entropy_analysis: Optional[EntropyAnalysisResult] = None

    # 时间
    created_at: datetime
    analyzed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IntelAnalyzeResponse(BaseModel):
    """分析响应"""

    intel: IntelResponse
    processing_time_ms: int = Field(..., description="处理时间(毫秒)")

    class Config:
        json_schema_extra = {
            "example": {
                "intel": {
                    "id": "intel_xxx",
                    "credibility_score": 0.05,
                    "credibility_level": "VERY_LOW",
                    "confidence": "VERY_HIGH",
                    "risk_flags": ["DEEPFAKE", "WATER_ARMY", "LOGIC_FALLACY"],
                    "reasoning_chain": [
                        "物理层: 图片阴影角度与声称时间不符",
                        "逻辑层: 因果链缺失,未提供报警证据",
                        "动力学层: 信息源熵值0.12,95%为新账号",
                    ],
                },
                "processing_time_ms": 4523,
            }
        }


class IntelListResponse(BaseModel):
    """情报列表响应"""

    items: List[IntelResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class TrendingTopic(BaseModel):
    """热点话题"""

    keyword: str
    mention_count: int
    platforms: List[str]
    avg_credibility: float
    trending_score: float

    class Config:
        json_schema_extra = {
            "example": {
                "keyword": "AI",
                "mention_count": 12500,
                "platforms": ["weibo", "twitter", "zhihu"],
                "avg_credibility": 0.72,
                "trending_score": 0.89,
            }
        }


class TrendingTopicsResponse(BaseModel):
    """热点话题列表"""

    topics: List[TrendingTopic]
    updated_at: datetime
