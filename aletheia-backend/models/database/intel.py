"""
情报信息数据模型
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    JSON,
    DateTime,
    Text,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Date,
    BigInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
import enum
from core.database import Base


class CredibilityLevel(str, enum.Enum):
    """可信度等级"""

    VERY_HIGH = "VERY_HIGH"  # 90-100%
    HIGH = "HIGH"  # 70-89%
    MEDIUM = "MEDIUM"  # 40-69%
    LOW = "LOW"  # 20-39%
    VERY_LOW = "VERY_LOW"  # 0-19%


class RiskFlag(str, enum.Enum):
    """风险标签"""

    DEEPFAKE = "DEEPFAKE"  # 深度伪造
    WATER_ARMY = "WATER_ARMY"  # 水军操纵
    LOGIC_FALLACY = "LOGIC_FALLACY"  # 逻辑谬误
    PHYSICS_VIOLATION = "PHYSICS_VIOLATION"  # 物理违背
    LOW_ENTROPY = "LOW_ENTROPY"  # 低熵值(人工放大)
    METADATA_MISMATCH = "METADATA_MISMATCH"  # 元数据不匹配


class ContentType(str, enum.Enum):
    """内容类型"""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    MIXED = "MIXED"


class Intel(Base):
    """情报信息主表"""

    __tablename__ = "intels"

    # 主键
    id = Column(String, primary_key=True, index=True)

    # 基础信息
    source_platform = Column(String(50), nullable=False, index=True)
    original_url = Column(Text, nullable=False)
    content_text = Column(Text, nullable=False)
    content_type = Column(SQLEnum(ContentType), nullable=False)

    # 多模态数据
    ocr_text = Column(Text, nullable=True)
    asr_text = Column(Text, nullable=True)
    image_urls = Column(JSON, nullable=True)  # List[str]
    video_url = Column(String, nullable=True)
    audio_url = Column(String, nullable=True)

    # 元数据
    meta = Column("metadata", JSON, nullable=False)
    # {
    #   "timestamp": "2026-02-01T12:34:56Z",
    #   "author_id": "user_123",
    #   "author_follower_count": 50000,
    #   "engagement_rate": 0.08,
    #   "account_age_days": 1200,
    #   "ip_location": "Beijing",
    #   "device": "iPhone12"
    # }

    # NER实体识别
    entities = Column(JSON, nullable=True)  # List[str]

    # 图片感知哈希
    image_perceptual_hash = Column(String, nullable=True, index=True)

    # 分析结果
    credibility_score = Column(Float, nullable=True)  # 0.0-1.0
    credibility_level = Column(SQLEnum(CredibilityLevel), nullable=True)
    confidence = Column(String(20), nullable=True)  # HIGH/MEDIUM/LOW

    # 风险标签
    risk_flags = Column(JSON, nullable=True)  # List[RiskFlag]

    # 推理链
    reasoning_chain = Column(JSON, nullable=True)
    # {
    #   "observations": ["observation1", "observation2"],
    #   "hypotheses": ["hypothesis1"],
    #   "evidence": {...},
    #   "conclusion": "..."
    # }

    # 关联Intel ID(用于相似内容聚类)
    related_intel_ids = Column(JSON, nullable=True)  # List[str]

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 状态
    is_archived = Column(Integer, default=0, nullable=False)

    # 关系
    # tasks = relationship("Task", back_populates="intel")

    __table_args__ = (
        Index("idx_platform_time", "source_platform", "created_at"),
        Index("idx_credibility", "credibility_score", "credibility_level"),
    )


class Baseline(Base):
    """基准线数据"""

    __tablename__ = "baselines"

    id = Column(String, primary_key=True)
    entity_id = Column(String, nullable=False, index=True)
    entity_name = Column(String, nullable=False)
    entity_type = Column(String(50), nullable=False)

    # 统计数据
    daily_mention_avg = Column(Float, nullable=False)
    daily_mention_std = Column(Float, nullable=False)

    sentiment_distribution = Column(JSON, nullable=False)
    # {"positive": 0.5, "neutral": 0.3, "negative": 0.2}

    account_type_distribution = Column(JSON, nullable=False)
    # {"verified_media": 0.2, "influencers": 0.3, "ordinary_users": 0.5}

    geographic_distribution = Column(JSON, nullable=True)
    # {"Beijing": 0.3, "Shanghai": 0.2, ...}

    time_window_days = Column(Integer, default=30, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (Index("idx_entity_id", "entity_id"),)


class WaterArmySignal(Base):
    """水军检测信号"""

    __tablename__ = "water_army_signals"

    id = Column(String, primary_key=True)
    platform = Column(String(50), nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    account_name = Column(String, nullable=True)

    # 风险评分
    risk_score = Column(Float, nullable=False)  # 0.0-1.0

    # 水军特征指标
    indicators = Column(JSON, nullable=False)
    # {
    #   "batch_creation": true,
    #   "repeated_content": 0.92,
    #   "posting_pattern_score": 0.88,
    #   "zero_follower_engagement": true,
    #   "bot_like_behavior": true
    # }

    # 关联账号
    related_accounts = Column(JSON, nullable=True)  # List[str]

    # 标记时间
    flagged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, nullable=True)

    # 状态
    is_active = Column(Integer, default=1, nullable=False)

    __table_args__ = (Index("idx_platform_risk", "platform", "risk_score"),)


class DailyStatistics(Base):
    """每日统计数据 - 用于基准线建立和趋势分析"""

    __tablename__ = "daily_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 关键词和平台
    keyword = Column(String(255), nullable=False, index=True, comment="关键词/实体名称")
    platform = Column(String(50), nullable=False, index=True, comment="平台名称")
    date = Column(Date, nullable=False, index=True, comment="统计日期")

    # 统计指标
    post_count = Column(Integer, default=0, comment="帖子数量")
    total_likes = Column(BigInteger, default=0, comment="总点赞数")
    total_comments = Column(BigInteger, default=0, comment="总评论数")
    total_shares = Column(BigInteger, default=0, comment="总分享数")
    avg_engagement = Column(Float, default=0.0, comment="平均互动率")

    # 账号类型分布
    verified_account_count = Column(Integer, default=0, comment="认证账号数")
    influencer_count = Column(Integer, default=0, comment="KOL账号数")
    ordinary_account_count = Column(Integer, default=0, comment="普通账号数")
    new_account_ratio = Column(Float, default=0.0, comment="新账号占比")

    # 情感分析
    positive_count = Column(Integer, default=0, comment="正面情感数")
    neutral_count = Column(Integer, default=0, comment="中性情感数")
    negative_count = Column(Integer, default=0, comment="负面情感数")

    # 时间戳
    created_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    updated_at = Column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "keyword", "platform", "date", name="uq_keyword_platform_date"
        ),
        Index("idx_keyword_platform_date", "keyword", "platform", "date"),
        Index("idx_date_desc", "date"),
    )
