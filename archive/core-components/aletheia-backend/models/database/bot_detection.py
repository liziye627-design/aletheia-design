"""
Bot detection and CIB cluster database models.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    JSON,
    DateTime,
    Boolean,
    Index,
    text,
)
from core.database import Base


class AccountModel(Base):
    """
    Account database model with partitioning by platform.
    Stores social media account information.
    """
    __tablename__ = "accounts"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Account identification
    account_id = Column(String, nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    username = Column(String(255), nullable=False)
    
    # Account metadata
    created_at = Column(DateTime, nullable=False)
    follower_count = Column(Integer, default=0, nullable=False)
    following_count = Column(Integer, default=0, nullable=False)
    post_count = Column(Integer, default=0, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    
    # Optional fields
    bio = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    location = Column(String(255), nullable=True)
    
    # Extensible metadata (using 'meta' to avoid SQLAlchemy reserved name)
    meta = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    first_seen = Column(DateTime, server_default=text("NOW()"), nullable=False)
    last_updated = Column(
        DateTime,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
        nullable=False
    )
    
    __table_args__ = (
        Index("idx_account_platform_id", "platform", "account_id"),
        Index("idx_account_username", "username"),
        Index("idx_account_created", "created_at"),
        # Partition by platform for better query performance
        # Note: Actual partitioning is done via SQL in migration scripts
    )


class PostModel(Base):
    """
    Post database model with partitioning by date range.
    Stores social media posts/tweets/status updates.
    """
    __tablename__ = "posts"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Post identification
    post_id = Column(String, nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    author_id = Column(String, nullable=False, index=True)
    
    # Content
    content = Column(String, nullable=False)
    content_type = Column(String(50), nullable=False)
    
    # Engagement metrics
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    
    # Structured data
    hashtags = Column(JSON, nullable=True)  # List[str]
    mentions = Column(JSON, nullable=True)  # List[str]
    urls = Column(JSON, nullable=True)  # List[str]
    media_urls = Column(JSON, nullable=True)  # List[str]
    
    # Relationships
    parent_post_id = Column(String, nullable=True, index=True)
    
    # Extensible metadata (using 'meta' to avoid SQLAlchemy reserved name)
    meta = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, index=True)
    collected_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    
    __table_args__ = (
        Index("idx_post_platform_created", "platform", "created_at"),
        Index("idx_post_author", "author_id", "created_at"),
        Index("idx_post_parent", "parent_post_id"),
        # Partition by date range for better query performance
        # Note: Actual partitioning is done via SQL in migration scripts
    )


class BotScoreModel(Base):
    """
    Bot detection score database model.
    Stores bot probability scores and features for accounts.
    """
    __tablename__ = "bot_scores"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Account reference
    account_id = Column(String, nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    
    # Bot detection result
    bot_probability = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False)  # HIGH, MEDIUM, LOW
    
    # Features (stored as JSON for flexibility)
    features = Column(JSON, nullable=False)
    # {
    #   "account_age_days": 365.5,
    #   "posting_frequency": 12.3,
    #   "interaction_ratio": 0.45,
    #   "content_similarity": 0.78,
    #   "profile_completeness": 0.9,
    #   "temporal_entropy": 2.3,
    #   "follower_following_ratio": 0.5,
    #   "verified_status": false
    # }
    
    # Model metadata
    model_version = Column(String(50), default="1.0", nullable=False)
    
    # Extensible metadata (using 'meta' to avoid SQLAlchemy reserved name)
    meta = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    detected_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    
    __table_args__ = (
        Index("idx_bot_score_account", "account_id", "detected_at"),
        Index("idx_bot_score_probability", "bot_probability"),
        Index("idx_bot_score_platform", "platform", "bot_probability"),
    )


class CIBClusterModel(Base):
    """
    Coordinated Inauthentic Behavior cluster database model.
    Stores detected CIB clusters and their characteristics.
    """
    __tablename__ = "cib_clusters"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Cluster identification
    cluster_id = Column(String, nullable=False, unique=True, index=True)
    platform = Column(String(50), nullable=False, index=True)
    
    # Cluster data
    account_ids = Column(JSON, nullable=False)  # List[str]
    cluster_score = Column(Float, nullable=False)
    
    # Behavior patterns (stored as JSON for flexibility)
    behavior_patterns = Column(JSON, nullable=False)
    # {
    #   "content_similarity": 0.95,
    #   "temporal_correlation": 0.88,
    #   "interaction_overlap": 0.76,
    #   "posting_pattern": "synchronized",
    #   "common_hashtags": ["#tag1", "#tag2"]
    # }
    
    # Extensible metadata (using 'meta' to avoid SQLAlchemy reserved name)
    meta = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    detected_at = Column(DateTime, nullable=False, index=True)
    last_updated = Column(
        DateTime,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
        nullable=False
    )
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    __table_args__ = (
        Index("idx_cib_platform_score", "platform", "cluster_score"),
        Index("idx_cib_detected", "detected_at"),
    )


class FakeNewsPredictionModel(Base):
    """
    Fake news model prediction database model.
    Stores predictions from ML-based fake news detection.
    """
    __tablename__ = "fake_news_predictions"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Content identification
    text_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # Model predictions (0-1 scores)
    logistic_regression_score = Column(Float, nullable=False)
    decision_tree_score = Column(Float, nullable=False)
    gradient_boost_score = Column(Float, nullable=False)
    random_forest_score = Column(Float, nullable=False)
    ensemble_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    
    # Model metadata
    model_version = Column(String(50), default="1.0", nullable=False)
    
    # Timestamps
    predicted_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    
    # Cache TTL (for cache invalidation)
    expires_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_prediction_hash", "text_hash"),
        Index("idx_prediction_ensemble", "ensemble_score"),
        Index("idx_prediction_expires", "expires_at"),
    )


class VerificationResultModel(Base):
    """
    Verification result database model.
    Stores final credibility assessments combining multiple analysis methods.
    """
    __tablename__ = "verification_results"
    
    # Primary key
    id = Column(String, primary_key=True, index=True)
    
    # Content identification
    content_id = Column(String, nullable=False, unique=True, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    content_text = Column(String, nullable=False)
    
    # Verification result
    credibility_score = Column(Float, nullable=False)
    credibility_level = Column(String(20), nullable=False)
    confidence = Column(String(20), nullable=False)
    
    # Risk flags and reasoning
    risk_flags = Column(JSON, nullable=True)  # List[str]
    reasoning_chain = Column(JSON, nullable=True)  # List[str]
    
    # Analysis components (stored as JSON)
    fake_news_prediction = Column(JSON, nullable=True)
    bot_scores = Column(JSON, nullable=True)  # List[BotScore]
    physics_verification = Column(JSON, nullable=True)
    logic_verification = Column(JSON, nullable=True)
    entropy_analysis = Column(JSON, nullable=True)
    
    # Performance metrics
    processing_time_ms = Column(Integer, default=0, nullable=False)
    
    # Extensible metadata (using 'meta' to avoid SQLAlchemy reserved name)
    meta = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    verified_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, server_default=text("NOW()"), nullable=False)
    
    # Cache TTL
    expires_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("idx_verification_content", "content_id"),
        Index("idx_verification_hash", "content_hash"),
        Index("idx_verification_score", "credibility_score"),
        Index("idx_verification_level", "credibility_level"),
        Index("idx_verification_verified", "verified_at"),
    )
