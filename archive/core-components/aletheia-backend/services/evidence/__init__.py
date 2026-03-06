"""
Evidence Library Module.
证据库模块

This module implements the two-phase collection model:
1. Discovery Layer: SearchHit from search/hot/topic feeds
2. Evidence Layer: EvidenceDoc with full content and metadata

Core components:
- Evidence models (SearchHit, EvidenceDoc)
- URL normalization and deduplication
- Content extraction (template → JSON-LD → OG → fallback)
- Evidence credibility scoring
- Version management
- OpenSearch indexing configuration
"""

from models.evidence import (
    # Data models
    SearchHit,
    EvidenceDoc,
    EvidenceVersion,
    DiscoveryEntry,
    # Enums
    MediaType,
    SourceTier,
    ExtractionMethod,
    DiscoveryMode,
)

from services.evidence.url_normalizer import (
    URLNormalizer,
    ContentDeduplicator,
    EvidenceDeduplicator,
    URLNormalizationResult,
    normalize_url,
    compute_content_hash,
    compute_simhash,
)

from services.evidence.content_extractor import (
    ContentExtractor,
    ExtractionResult,
    SiteTemplate,
    SITE_TEMPLATES,
    extract_content,
)

from services.evidence.evidence_scorer import (
    EvidenceScorer,
    SourceTierResolver,
    ScoringContext,
    ScoringResult,
    PenaltyFlags,
    score_evidence,
    resolve_tier,
)

from services.evidence.version_manager import (
    VersionManager,
    VersionRecord,
    VersionComparator,
    ContentDiff,
    ChangeType,
    create_version,
    detect_updates,
)

from services.evidence.opensearch_config import (
    EVIDENCE_INDEX_MAPPING,
    SEARCH_HIT_INDEX_MAPPING,
    SearchQuery,
    SearchResult,
    OpenSearchQueryBuilder,
    get_evidence_index_config,
    get_search_hit_index_config,
)

from services.evidence.evidence_pipeline import (
    EvidencePipeline,
    EvidencePipelineAdapter,
    PipelineConfig,
    PipelineResult,
    BatchPipelineResult,
    CrawlerOutputProcessor,
    DetailPageFetcher,
    process_crawler_output,
)

from services.evidence.integration import (
    EvidenceCollectionOrchestrator,
    EvidenceCollectionConfig,
    EvidenceCollectionResult,
    create_evidence_collector,
    collect_evidence_for_investigation,
)

from services.evidence.opensearch_client import (
    EvidenceSearchClient,
    OpenSearchConfig,
    get_opensearch_client,
)

from services.evidence.investigation_adapter import (
    EvidenceAdapter,
    EvidenceCard,
    CrawlerManagerEvidenceWrapper,
)

from services.evidence.metrics import (
    EvidenceMetricsCollector,
    CollectionMetrics,
    AggregateMetrics,
    get_metrics_collector,
)

from services.evidence.crawler_integration import (
    CrawlerEvidenceBridge,
    CrawlerIntegrationConfig,
    CollectionResult,
    collect_evidence,
    collect_evidence_for_claim,
)


__all__ = [
    # Models
    "SearchHit",
    "EvidenceDoc",
    "EvidenceVersion",
    "DiscoveryEntry",
    "MediaType",
    "SourceTier",
    "ExtractionMethod",
    "DiscoveryMode",

    # URL Normalization
    "URLNormalizer",
    "ContentDeduplicator",
    "EvidenceDeduplicator",
    "URLNormalizationResult",
    "normalize_url",
    "compute_content_hash",
    "compute_simhash",

    # Content Extraction
    "ContentExtractor",
    "ExtractionResult",
    "SiteTemplate",
    "SITE_TEMPLATES",
    "extract_content",

    # Evidence Scoring
    "EvidenceScorer",
    "SourceTierResolver",
    "ScoringContext",
    "ScoringResult",
    "PenaltyFlags",
    "score_evidence",
    "resolve_tier",

    # Version Management
    "VersionManager",
    "VersionRecord",
    "VersionComparator",
    "ContentDiff",
    "ChangeType",
    "create_version",
    "detect_updates",

    # OpenSearch
    "EVIDENCE_INDEX_MAPPING",
    "SEARCH_HIT_INDEX_MAPPING",
    "SearchQuery",
    "SearchResult",
    "OpenSearchQueryBuilder",
    "get_evidence_index_config",
    "get_search_hit_index_config",

    # Pipeline
    "EvidencePipeline",
    "EvidencePipelineAdapter",
    "PipelineConfig",
    "PipelineResult",
    "BatchPipelineResult",
    "CrawlerOutputProcessor",
    "DetailPageFetcher",
    "process_crawler_output",

    # Integration
    "EvidenceCollectionOrchestrator",
    "EvidenceCollectionConfig",
    "EvidenceCollectionResult",
    "create_evidence_collector",
    "collect_evidence_for_investigation",

    # OpenSearch Client
    "EvidenceSearchClient",
    "OpenSearchConfig",
    "get_opensearch_client",

    # Investigation Adapter
    "EvidenceAdapter",
    "EvidenceCard",
    "CrawlerManagerEvidenceWrapper",

    # Metrics
    "EvidenceMetricsCollector",
    "CollectionMetrics",
    "AggregateMetrics",
    "get_metrics_collector",

    # Crawler Integration
    "CrawlerEvidenceBridge",
    "CrawlerIntegrationConfig",
    "CollectionResult",
    "collect_evidence",
    "collect_evidence_for_claim",
]