"""
Evidence Database Models.
证据数据库模型

SQLAlchemy models for EvidenceDoc and SearchHit storage.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    JSON,
    DateTime,
    Text,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class EvidenceDocDB(Base):
    """
    Evidence Document database model.
    证据文档数据库模型
    """
    __tablename__ = "evidence_docs"

    # Primary identifiers
    doc_id = Column(String(64), primary_key=True, nullable=False)
    version_id = Column(String(80), nullable=False, index=True)

    # URLs
    original_url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)

    # Content
    title = Column(String(500), nullable=False)
    content_text = Column(Text, nullable=True)
    content_html = Column(Text, nullable=True)
    media_type = Column(String(20), default="text")

    # Media assets
    images = Column(JSON, nullable=True)  # List[str]
    videos = Column(JSON, nullable=True)  # List[str]

    # Metadata
    publish_time = Column(DateTime, nullable=True, index=True)
    author = Column(String(200), nullable=True)
    source_org = Column(String(200), nullable=True)
    language = Column(String(10), default="zh")
    tags = Column(JSON, nullable=True)  # List[str]
    topics = Column(JSON, nullable=True)  # List[str]

    # Platform info
    platform = Column(String(50), nullable=False, index=True)
    source_domain = Column(String(200), nullable=False, index=True)
    platform_doc_id = Column(String(100), nullable=True)

    # Extraction info
    extraction_method = Column(String(30), nullable=False)
    extraction_confidence = Column(Float, default=0.0)

    # Crawl info
    crawl_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    raw_snapshot_uri = Column(Text, nullable=True)
    http_status = Column(Integer, default=200)
    fetch_latency_ms = Column(Integer, default=0)

    # Credibility scoring
    source_tier = Column(String(1), default="C", index=True)  # S, A, B, C
    evidence_score = Column(Float, default=0.0, index=True)
    evidence_score_components = Column(JSON, nullable=True)

    # Version management
    prev_version_id = Column(String(80), nullable=True)
    version_count = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True, index=True)

    # Content hashes
    url_hash = Column(String(64), nullable=False, index=True)
    content_hash = Column(String(64), nullable=True, index=True)
    simhash = Column(String(16), nullable=True)

    # Flags
    is_deleted = Column(Boolean, default=False, index=True)
    is_updated = Column(Boolean, default=False)
    has_correction = Column(Boolean, default=False)

    # Related discovery hits
    hit_ids = Column(JSON, nullable=True)  # List[str]

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_evidence_platform_tier", "platform", "source_tier"),
        Index("idx_evidence_score_time", "evidence_score", "publish_time"),
        Index("idx_evidence_domain_time", "source_domain", "crawl_time"),
        UniqueConstraint("doc_id", "version_id", name="uq_doc_version"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "doc_id": self.doc_id,
            "version_id": self.version_id,
            "original_url": self.original_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "content_text": self.content_text,
            "content_html": self.content_html,
            "media_type": self.media_type,
            "images": self.images or [],
            "videos": self.videos or [],
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "source_org": self.source_org,
            "language": self.language,
            "tags": self.tags or [],
            "topics": self.topics or [],
            "platform": self.platform,
            "source_domain": self.source_domain,
            "platform_doc_id": self.platform_doc_id,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "crawl_time": self.crawl_time.isoformat(),
            "raw_snapshot_uri": self.raw_snapshot_uri,
            "http_status": self.http_status,
            "fetch_latency_ms": self.fetch_latency_ms,
            "source_tier": self.source_tier,
            "evidence_score": self.evidence_score,
            "evidence_score_components": self.evidence_score_components or {},
            "prev_version_id": self.prev_version_id,
            "version_count": self.version_count,
            "is_latest": self.is_latest,
            "url_hash": self.url_hash,
            "content_hash": self.content_hash,
            "simhash": self.simhash,
            "is_deleted": self.is_deleted,
            "is_updated": self.is_updated,
            "has_correction": self.has_correction,
            "hit_ids": self.hit_ids or [],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SearchHitDB(Base):
    """
    Search Hit database model.
    搜索命中记录数据库模型
    """
    __tablename__ = "search_hits"

    # Primary identifier
    hit_id = Column(String(64), primary_key=True, nullable=False)

    # Discovery context
    query = Column(String(500), nullable=False, index=True)
    entry_url = Column(Text, nullable=False)
    hit_url = Column(Text, nullable=False, index=True)

    # Position info
    rank = Column(Integer, default=1)
    page_no = Column(Integer, default=1)

    # Content preview
    hit_title = Column(String(500), nullable=False)
    hit_snippet = Column(Text, nullable=True)
    hit_time_hint = Column(String(100), nullable=True)
    hit_source_hint = Column(String(200), nullable=True)

    # Platform info
    platform = Column(String(50), nullable=False, index=True)
    source_domain = Column(String(200), nullable=False)
    discovery_mode = Column(String(20), default="search")  # search/hot/topic/feed

    # Timestamps
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Extra metadata
    extra = Column(JSON, nullable=True)  # Dict with hot_rank, likes, etc.

    # Link to evidence doc
    doc_id = Column(String(64), nullable=True, index=True)
    fetch_status = Column(String(20), default="pending")  # pending/fetching/success/failed/skipped

    # Created/Updated
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_hit_query_platform", "query", "platform"),
        Index("idx_hit_captured_time", "captured_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "hit_id": self.hit_id,
            "query": self.query,
            "entry_url": self.entry_url,
            "hit_url": self.hit_url,
            "rank": self.rank,
            "page_no": self.page_no,
            "hit_title": self.hit_title,
            "hit_snippet": self.hit_snippet,
            "hit_time_hint": self.hit_time_hint,
            "hit_source_hint": self.hit_source_hint,
            "platform": self.platform,
            "source_domain": self.source_domain,
            "discovery_mode": self.discovery_mode,
            "captured_at": self.captured_at.isoformat(),
            "extra": self.extra or {},
            "doc_id": self.doc_id,
            "fetch_status": self.fetch_status,
            "created_at": self.created_at.isoformat(),
        }


class EvidenceVersionDB(Base):
    """
    Evidence Version database model.
    证据版本数据库模型
    """
    __tablename__ = "evidence_versions"

    version_id = Column(String(80), primary_key=True, nullable=False)
    doc_id = Column(String(64), nullable=False, index=True)

    # Chain links
    prev_version_id = Column(String(80), nullable=True)

    # Timestamps
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Content snapshot
    snapshot_uri = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)

    # Change info
    title_changed = Column(Boolean, default=False)
    content_diff_ratio = Column(Float, default=1.0)  # Similarity ratio
    diff_summary = Column(Text, nullable=True)

    # Detected changes
    detected_updates = Column(JSON, nullable=True)  # List[str]
    change_type = Column(String(20), default="created")  # created/updated/corrected/retracted/deleted

    # Created
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_version_doc_time", "doc_id", "captured_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "doc_id": self.doc_id,
            "prev_version_id": self.prev_version_id,
            "captured_at": self.captured_at.isoformat(),
            "snapshot_uri": self.snapshot_uri,
            "content_hash": self.content_hash,
            "title_changed": self.title_changed,
            "content_diff_ratio": self.content_diff_ratio,
            "diff_summary": self.diff_summary,
            "detected_updates": self.detected_updates or [],
            "change_type": self.change_type,
            "created_at": self.created_at.isoformat(),
        }


class DiscoveryEntryDB(Base):
    """
    Discovery Entry configuration database model.
    发现入口配置数据库模型
    """
    __tablename__ = "discovery_entries"

    source_id = Column(String(50), primary_key=True, nullable=False)
    name = Column(String(200), nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    domain = Column(String(200), nullable=False)

    # Entry configuration
    discovery_mode = Column(String(20), default="search")
    url_template = Column(Text, nullable=False)

    # Crawl parameters
    tier = Column(String(1), default="C")
    priority = Column(Integer, default=5)
    frequency_seconds = Column(Integer, default=900)
    enabled = Column(Boolean, default=True)

    # Type-specific configuration
    is_static = Column(Boolean, default=True)
    requires_playwright = Column(Boolean, default=False)
    api_endpoint = Column(Text, nullable=True)

    # Rate limiting
    min_delay_ms = Column(Integer, default=1200)
    max_concurrency = Column(Integer, default=1)
    jitter_ms = Column(Integer, default=800)

    # Retry configuration
    max_retries = Column(Integer, default=3)
    retry_on_status = Column(JSON, nullable=True)  # List[int]

    # Parser reference
    parser_id = Column(String(50), nullable=True)

    # Last crawl info
    last_crawl_at = Column(DateTime, nullable=True)
    last_crawl_status = Column(String(20), nullable=True)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "platform": self.platform,
            "domain": self.domain,
            "discovery_mode": self.discovery_mode,
            "url_template": self.url_template,
            "tier": self.tier,
            "priority": self.priority,
            "frequency_seconds": self.frequency_seconds,
            "enabled": self.enabled,
            "is_static": self.is_static,
            "requires_playwright": self.requires_playwright,
            "api_endpoint": self.api_endpoint,
            "min_delay_ms": self.min_delay_ms,
            "max_concurrency": self.max_concurrency,
            "jitter_ms": self.jitter_ms,
            "max_retries": self.max_retries,
            "retry_on_status": self.retry_on_status or [],
            "parser_id": self.parser_id,
            "last_crawl_at": self.last_crawl_at.isoformat() if self.last_crawl_at else None,
            "last_crawl_status": self.last_crawl_status,
            "last_error": self.last_error,
        }