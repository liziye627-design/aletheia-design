"""
Evidence models for the Search Evidence Library.
证据库核心数据模型：两段式采集模型

This module implements the two-phase collection model:
- SearchHit: Discovery records from search/hot/topic feeds
- EvidenceDoc: Full evidence documents with content and metadata
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class MediaType(str, Enum):
    """Content media types"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MIX = "mix"


class SourceTier(str, Enum):
    """Source credibility tiers"""
    S = "S"  # 权威媒体/官方机构
    A = "A"  # 主流门户/商业媒体
    B = "B"  # 大型内容平台
    C = "C"  # 高噪声社媒


class ExtractionMethod(str, Enum):
    """Content extraction methods"""
    TEMPLATE_RULES = "template_rules"  # 站点模板规则
    JSONLD = "jsonld"  # JSON-LD 结构化数据
    OPENGRAPH = "opengraph"  # Open Graph 协议
    TRAFILATURA = "trafilatura"  # Trafilatura 通用抽取
    READABILITY = "readability"  # Readability 通用抽取
    FALLBACK = "fallback"  # 兜底方案


class DiscoveryMode(str, Enum):
    """Discovery entry types"""
    SEARCH = "search"  # 站内搜索
    HOT = "hot"  # 热榜/热搜
    TOPIC = "topic"  # 话题流
    FEED = "feed"  # RSS/订阅源
    API = "api"  # 官方API


@dataclass
class SearchHit:
    """
    Search Hit - Discovery record from search results/hot lists/topic feeds.
    搜索结果命中记录 - 来自发现层的原始数据

    This represents the "context at discovery time" - what was seen when
    the evidence was first discovered through search/hot lists/topics.
    """
    # Core identification
    hit_id: str  # Unique hit identifier
    query: str  # Search query or discovery keyword
    entry_url: str  # Discovery entry URL (search page URL)
    hit_url: str  # Target detail page URL

    # Position and ranking
    rank: int  # Position in search results (1-based)
    page_no: int  # Page number in paginated results

    # Content preview
    hit_title: str  # Title shown in search results
    hit_snippet: Optional[str] = None  # Snippet/summary in search results
    hit_time_hint: Optional[str] = None  # Time hint from search results
    hit_source_hint: Optional[str] = None  # Source hint from search results

    # Discovery metadata
    platform: str = ""  # Platform identifier (weibo, zhihu, etc.)
    source_domain: str = ""  # Source domain
    discovery_mode: DiscoveryMode = DiscoveryMode.SEARCH
    captured_at: datetime = field(default_factory=datetime.utcnow)

    # Engagement metrics (if available)
    extra: Dict[str, Any] = field(default_factory=dict)
    # Example: {"hot_rank": 5, "view_count": 10000, "comment_count": 500}

    # Link to full document (filled after detail fetch)
    doc_id: Optional[str] = None
    fetch_status: str = "pending"  # pending, fetching, success, failed, skipped

    def __post_init__(self):
        """Validate search hit data"""
        if self.rank < 1:
            raise ValueError("rank must be >= 1")
        if self.page_no < 1:
            raise ValueError("page_no must be >= 1")

    @property
    def is_fetched(self) -> bool:
        """Check if detail page has been fetched"""
        return self.fetch_status == "success" and self.doc_id is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
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
            "discovery_mode": self.discovery_mode.value,
            "captured_at": self.captured_at.isoformat(),
            "extra": self.extra,
            "doc_id": self.doc_id,
            "fetch_status": self.fetch_status,
        }


@dataclass
class EvidenceDoc:
    """
    Evidence Document - Full evidence with content and metadata.
    证据文档 - 包含完整正文和元数据的证据

    This represents the actual content extracted from detail pages,
    suitable for fact-checking and evidence analysis.
    """
    # Primary identifiers
    doc_id: str  # Stable document ID (hash of canonical_url or platform_doc_id)
    original_url: str  # Original URL as discovered

    # Content (required fields first)
    title: str  # Document title

    # Optional URL
    canonical_url: Optional[str] = None  # Canonical URL from rel=canonical

    # Content (optional)
    content_text: Optional[str] = None
    content_html: Optional[str] = None
    media_type: MediaType = MediaType.TEXT

    # Media assets
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    audio: List[str] = field(default_factory=list)

    # Metadata
    publish_time: Optional[datetime] = None
    author: Optional[str] = None
    source_org: Optional[str] = None  # Publishing organization
    language: str = "zh"
    tags: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)

    # Platform info
    platform: str = ""  # Platform identifier
    platform_doc_id: Optional[str] = None  # Platform's document ID

    # Extraction info
    extraction_method: ExtractionMethod = ExtractionMethod.FALLBACK
    extraction_confidence: float = 0.0  # 0.0-1.0

    # Crawl info
    crawl_time: datetime = field(default_factory=datetime.utcnow)
    raw_snapshot_uri: Optional[str] = None  # URI to raw HTML/JSON snapshot
    http_status: int = 200
    fetch_latency_ms: int = 0

    # Credibility scoring
    source_tier: SourceTier = SourceTier.C
    evidence_score: float = 0.0  # Calculated credibility score
    evidence_score_components: Dict[str, float] = field(default_factory=dict)

    # Version management
    version_id: str = ""  # Current version ID
    prev_version_id: Optional[str] = None  # Previous version ID
    version_count: int = 1
    is_latest: bool = True

    # Content hashes for deduplication
    url_hash: str = ""  # Hash of normalized URL
    content_hash: str = ""  # Hash of normalized content
    simhash: Optional[str] = None  # SimHash for near-duplicate detection

    # Flags
    is_deleted: bool = False  # Original was deleted
    is_updated: bool = False  # Content was updated
    has_correction: bool = False  # Contains correction/retraction notice

    # Link to discovery
    hit_ids: List[str] = field(default_factory=list)  # Related SearchHit IDs

    def __post_init__(self):
        """Validate and compute derived fields"""
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be between 0 and 1")
        if not 0.0 <= self.evidence_score <= 1.0:
            raise ValueError("evidence_score must be between 0 and 1")

    @property
    def primary_url(self) -> str:
        """Get the primary URL (canonical or original)"""
        return self.canonical_url or self.original_url

    @property
    def has_content(self) -> bool:
        """Check if document has meaningful content"""
        return bool(self.content_text and len(self.content_text.strip()) > 20)

    @property
    def word_count(self) -> int:
        """Get word count of content"""
        if not self.content_text:
            return 0
        # Simple word count for Chinese text
        return len(self.content_text.replace(" ", ""))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "doc_id": self.doc_id,
            "original_url": self.original_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "content_text": self.content_text,
            "content_html": self.content_html,
            "media_type": self.media_type.value,
            "images": self.images,
            "videos": self.videos,
            "audio": self.audio,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "source_org": self.source_org,
            "language": self.language,
            "tags": self.tags,
            "topics": self.topics,
            "platform": self.platform,
            "platform_doc_id": self.platform_doc_id,
            "extraction_method": self.extraction_method.value,
            "extraction_confidence": self.extraction_confidence,
            "crawl_time": self.crawl_time.isoformat(),
            "raw_snapshot_uri": self.raw_snapshot_uri,
            "http_status": self.http_status,
            "fetch_latency_ms": self.fetch_latency_ms,
            "source_tier": self.source_tier.value,
            "evidence_score": self.evidence_score,
            "evidence_score_components": self.evidence_score_components,
            "version_id": self.version_id,
            "prev_version_id": self.prev_version_id,
            "version_count": self.version_count,
            "is_latest": self.is_latest,
            "url_hash": self.url_hash,
            "content_hash": self.content_hash,
            "simhash": self.simhash,
            "is_deleted": self.is_deleted,
            "is_updated": self.is_updated,
            "has_correction": self.has_correction,
            "hit_ids": self.hit_ids,
        }


@dataclass
class EvidenceVersion:
    """
    Version record for evidence document history.
    证据版本记录 - 用于追踪内容变更
    """
    version_id: str
    doc_id: str
    captured_at: datetime

    # Changes from previous version
    prev_version_id: Optional[str] = None
    title_changed: bool = False
    content_diff_ratio: float = 0.0  # 0.0-1.0 similarity ratio
    diff_summary: str = ""

    # Snapshot reference
    snapshot_uri: Optional[str] = None
    content_hash: str = ""

    # Detection results
    detected_updates: List[str] = field(default_factory=list)
    # Examples: "title_changed", "content_added", "content_removed",
    #           "correction_notice", "retraction_notice", "deleted"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "doc_id": self.doc_id,
            "captured_at": self.captured_at.isoformat(),
            "prev_version_id": self.prev_version_id,
            "title_changed": self.title_changed,
            "content_diff_ratio": self.content_diff_ratio,
            "diff_summary": self.diff_summary,
            "snapshot_uri": self.snapshot_uri,
            "content_hash": self.content_hash,
            "detected_updates": self.detected_updates,
        }


@dataclass
class DiscoveryEntry:
    """
    Discovery Entry configuration - defines how to discover new evidence.
    发现入口配置 - 定义如何发现新证据
    """
    source_id: str  # Unique source identifier
    name: str  # Human-readable name
    platform: str  # Platform identifier
    domain: str  # Primary domain

    # Entry configuration
    discovery_mode: DiscoveryMode
    url_template: str  # URL template with {{keyword}} placeholder

    # Crawl parameters
    tier: SourceTier = SourceTier.C
    priority: int = 5  # 1=highest, 10=lowest
    frequency_seconds: int = 900  # Default crawl frequency
    enabled: bool = True

    # Type-specific configuration
    is_static: bool = True  # True for static HTML, False for JS-rendered
    requires_playwright: bool = False
    api_endpoint: Optional[str] = None  # For API-based discovery

    # Rate limiting
    min_delay_ms: int = 1200
    max_concurrency: int = 1
    jitter_ms: int = 800

    # Retry configuration
    max_retries: int = 3
    retry_on_status: List[int] = field(default_factory=lambda: [408, 429, 500, 502, 503, 504])

    # Parser configuration
    parser_id: Optional[str] = None  # Reference to site template

    def get_url_for_keyword(self, keyword: str, page: int = 1) -> str:
        """Generate URL for a specific keyword and page"""
        url = self.url_template.replace("{{keyword}}", keyword)
        url = url.replace("{{page}}", str(page))
        return url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "platform": self.platform,
            "domain": self.domain,
            "discovery_mode": self.discovery_mode.value,
            "url_template": self.url_template,
            "tier": self.tier.value,
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
            "retry_on_status": self.retry_on_status,
            "parser_id": self.parser_id,
        }