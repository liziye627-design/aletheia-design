"""
Evidence Pipeline Integration with Investigation Engine.
证据管道与调查引擎的集成

This module provides the integration layer between:
- Layer 1 Perception (Crawlers)
- Evidence Library (SearchHit + EvidenceDoc)
- Investigation Engine (Orchestrator)

Author: Aletheia Team
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
import structlog

from services.evidence.evidence_pipeline import (
    EvidencePipeline,
    EvidencePipelineAdapter,
    PipelineConfig,
    PipelineResult,
    BatchPipelineResult,
)
from models.evidence import (
    SearchHit,
    EvidenceDoc,
    SourceTier,
)
from services.evidence.url_normalizer import URLNormalizer
from services.evidence.evidence_scorer import SourceTierResolver

logger = structlog.get_logger()


@dataclass
class EvidenceCollectionConfig:
    """Configuration for evidence collection"""
    # Source selection
    platforms: List[str] = field(default_factory=lambda: [
        "weibo", "zhihu", "bilibili", "douyin", "xiaohongshu",
        "xinhua", "people", "cctv", "gov",
    ])

    # Tier priority
    tier_priority: List[str] = field(default_factory=lambda: ["S", "A", "B", "C"])

    # Limits
    max_items_per_platform: int = 50
    max_total_items: int = 300

    # Quality gates
    min_evidence_score: float = 0.3
    min_extraction_confidence: float = 0.5

    # Deduplication
    enable_deduplication: bool = True

    # Detail fetching
    fetch_detail_pages: bool = True
    max_concurrent_fetches: int = 10

    # Scoring
    enable_scoring: bool = True

    # Version management
    enable_versioning: bool = True


@dataclass
class EvidenceCollectionResult:
    """Result of evidence collection"""
    query: str
    total_discovered: int  # Total SearchHit records
    total_evidence: int    # Total EvidenceDoc records
    by_platform: Dict[str, int]
    by_tier: Dict[str, int]
    duplicates_found: int
    collection_time_ms: int
    evidence_docs: List[EvidenceDoc]
    search_hits: List[SearchHit]
    errors: List[str]


class EvidenceCollectionOrchestrator:
    """
    Orchestrates evidence collection from multiple platforms.
    协调多平台证据收集

    This class bridges the Investigation Engine with the Evidence Library,
    providing a unified interface for collecting and processing evidence.
    """

    def __init__(
        self,
        config: Optional[EvidenceCollectionConfig] = None,
        crawler_manager=None,
    ):
        self.config = config or EvidenceCollectionConfig()
        self.crawler_manager = crawler_manager
        self.pipeline_adapter = EvidencePipelineAdapter(
            config=PipelineConfig(
                fetch_detail_pages=self.config.fetch_detail_pages,
                max_detail_fetch_concurrency=self.config.max_concurrent_fetches,
                enable_deduplication=self.config.enable_deduplication,
                enable_scoring=self.config.enable_scoring,
                enable_versioning=self.config.enable_versioning,
            )
        )
        self.tier_resolver = SourceTierResolver()
        self.url_normalizer = URLNormalizer()

    async def collect_evidence(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        discovery_mode: str = "search",
    ) -> EvidenceCollectionResult:
        """
        Collect evidence for a query from multiple platforms.

        Args:
            query: Search query or claim text
            platforms: Optional list of specific platforms (uses config default if None)
            discovery_mode: "search", "hot", "topic", or "feed"

        Returns:
            EvidenceCollectionResult with all collected evidence
        """
        start_time = datetime.utcnow()
        platforms = platforms or self.config.platforms

        all_evidence_docs: List[EvidenceDoc] = []
        all_search_hits: List[SearchHit] = []
        by_platform: Dict[str, int] = {}
        by_tier: Dict[str, int] = {"S": 0, "A": 0, "B": 0, "C": 0}
        total_duplicates = 0
        errors: List[str] = []

        # Collect from each platform
        for platform in platforms:
            try:
                platform_result = await self._collect_from_platform(
                    platform=platform,
                    query=query,
                    discovery_mode=discovery_mode,
                )

                # Aggregate results
                by_platform[platform] = len(platform_result.get("evidence_docs", []))
                total_duplicates += platform_result.get("duplicates", 0)

                # Convert dicts back to objects for aggregation
                for doc_dict in platform_result.get("evidence_docs", []):
                    # Create EvidenceDoc from dict
                    evidence_doc = self._dict_to_evidence_doc(doc_dict)
                    all_evidence_docs.append(evidence_doc)
                    by_tier[evidence_doc.source_tier.value] += 1

                for hit_dict in platform_result.get("search_hits", []):
                    search_hit = self._dict_to_search_hit(hit_dict)
                    all_search_hits.append(search_hit)

                # Check limits
                if len(all_evidence_docs) >= self.config.max_total_items:
                    break

            except Exception as e:
                errors.append(f"{platform}: {str(e)}")
                logger.error("platform_collection_failed", platform=platform, error=str(e))

        # Sort by evidence score
        all_evidence_docs.sort(key=lambda x: x.evidence_score, reverse=True)

        # Apply quality gate
        if self.config.min_evidence_score > 0:
            all_evidence_docs = [
                doc for doc in all_evidence_docs
                if doc.evidence_score >= self.config.min_evidence_score
            ]

        collection_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return EvidenceCollectionResult(
            query=query,
            total_discovered=len(all_search_hits),
            total_evidence=len(all_evidence_docs),
            by_platform=by_platform,
            by_tier=by_tier,
            duplicates_found=total_duplicates,
            collection_time_ms=collection_time_ms,
            evidence_docs=all_evidence_docs[:self.config.max_total_items],
            search_hits=all_search_hits,
            errors=errors,
        )

    async def _collect_from_platform(
        self,
        platform: str,
        query: str,
        discovery_mode: str,
    ) -> Dict[str, Any]:
        """Collect evidence from a single platform"""
        if not self.crawler_manager:
            # Mock result for testing
            return {
                "platform": platform,
                "query": query,
                "total_items": 0,
                "successful": 0,
                "failed": 0,
                "duplicates": 0,
                "total_time_ms": 0,
                "evidence_docs": [],
                "search_hits": [],
            }

        # Use CrawlerManager to fetch items
        try:
            crawler_result = await self.crawler_manager.search_single_platform(
                platform=platform,
                keyword=query,
                limit=self.config.max_items_per_platform,
            )
        except Exception as e:
            logger.error("crawler_failed", platform=platform, error=str(e))
            crawler_result = []

        # Process through pipeline
        return await self.pipeline_adapter.process_crawler_results(
            platform=platform,
            query=query,
            crawler_results=crawler_result if isinstance(crawler_result, list) else [],
            discovery_mode=discovery_mode,
        )

    def _dict_to_evidence_doc(self, doc_dict: Dict[str, Any]) -> EvidenceDoc:
        """Convert dictionary to EvidenceDoc object"""
        return EvidenceDoc(
            doc_id=doc_dict.get("doc_id", ""),
            original_url=doc_dict.get("original_url", ""),
            canonical_url=doc_dict.get("canonical_url"),
            title=doc_dict.get("title", ""),
            content_text=doc_dict.get("content_text"),
            content_html=doc_dict.get("content_html"),
            media_type=doc_dict.get("media_type", "text"),
            images=doc_dict.get("images", []),
            videos=doc_dict.get("videos", []),
            publish_time=doc_dict.get("publish_time"),
            author=doc_dict.get("author"),
            source_org=doc_dict.get("source_org"),
            language=doc_dict.get("language", "zh"),
            tags=doc_dict.get("tags", []),
            topics=doc_dict.get("topics", []),
            platform=doc_dict.get("platform", ""),
            platform_doc_id=doc_dict.get("platform_doc_id"),
            extraction_method=doc_dict.get("extraction_method", "fallback"),
            extraction_confidence=doc_dict.get("extraction_confidence", 0.0),
            crawl_time=doc_dict.get("crawl_time", datetime.utcnow()),
            raw_snapshot_uri=doc_dict.get("raw_snapshot_uri"),
            http_status=doc_dict.get("http_status", 200),
            fetch_latency_ms=doc_dict.get("fetch_latency_ms", 0),
            source_tier=SourceTier(doc_dict.get("source_tier", "C")),
            evidence_score=doc_dict.get("evidence_score", 0.0),
            evidence_score_components=doc_dict.get("evidence_score_components", {}),
            version_id=doc_dict.get("version_id", ""),
            prev_version_id=doc_dict.get("prev_version_id"),
            version_count=doc_dict.get("version_count", 1),
            is_latest=doc_dict.get("is_latest", True),
            url_hash=doc_dict.get("url_hash", ""),
            content_hash=doc_dict.get("content_hash", ""),
            simhash=doc_dict.get("simhash"),
            is_deleted=doc_dict.get("is_deleted", False),
            is_updated=doc_dict.get("is_updated", False),
            has_correction=doc_dict.get("has_correction", False),
            hit_ids=doc_dict.get("hit_ids", []),
        )

    def _dict_to_search_hit(self, hit_dict: Dict[str, Any]) -> SearchHit:
        """Convert dictionary to SearchHit object"""
        from models.evidence import DiscoveryMode

        return SearchHit(
            hit_id=hit_dict.get("hit_id", ""),
            query=hit_dict.get("query", ""),
            entry_url=hit_dict.get("entry_url", ""),
            hit_url=hit_dict.get("hit_url", ""),
            rank=hit_dict.get("rank", 1),
            page_no=hit_dict.get("page_no", 1),
            hit_title=hit_dict.get("hit_title", ""),
            hit_snippet=hit_dict.get("hit_snippet"),
            hit_time_hint=hit_dict.get("hit_time_hint"),
            hit_source_hint=hit_dict.get("hit_source_hint"),
            platform=hit_dict.get("platform", ""),
            source_domain=hit_dict.get("source_domain", ""),
            discovery_mode=DiscoveryMode(hit_dict.get("discovery_mode", "search")),
            captured_at=hit_dict.get("captured_at", datetime.utcnow()),
            extra=hit_dict.get("extra", {}),
            doc_id=hit_dict.get("doc_id"),
            fetch_status=hit_dict.get("fetch_status", "pending"),
        )


# ============================================================
# Integration with Investigation Orchestrator
# ============================================================

def create_evidence_collector(
    crawler_manager=None,
    config: Optional[Dict[str, Any]] = None,
) -> EvidenceCollectionOrchestrator:
    """
    Factory function to create an evidence collector.

    Args:
        crawler_manager: Optional CrawlerManager instance
        config: Optional configuration dictionary

    Returns:
        EvidenceCollectionOrchestrator instance
    """
    collection_config = EvidenceCollectionConfig()

    if config:
        if "platforms" in config:
            collection_config.platforms = config["platforms"]
        if "max_items_per_platform" in config:
            collection_config.max_items_per_platform = config["max_items_per_platform"]
        if "max_total_items" in config:
            collection_config.max_total_items = config["max_total_items"]
        if "min_evidence_score" in config:
            collection_config.min_evidence_score = config["min_evidence_score"]
        if "fetch_detail_pages" in config:
            collection_config.fetch_detail_pages = config["fetch_detail_pages"]

    return EvidenceCollectionOrchestrator(
        config=collection_config,
        crawler_manager=crawler_manager,
    )


async def collect_evidence_for_investigation(
    query: str,
    crawler_manager=None,
    platforms: Optional[List[str]] = None,
    max_items: int = 200,
) -> EvidenceCollectionResult:
    """
    Convenience function to collect evidence for an investigation.

    This is the main entry point for the Investigation Engine to use
    the Evidence Library.

    Args:
        query: Search query or claim text
        crawler_manager: CrawlerManager instance (from get_crawler_manager())
        platforms: Optional list of platforms to search
        max_items: Maximum total items to collect

    Returns:
        EvidenceCollectionResult with all collected evidence

    Example:
        from services.layer1_perception.crawler_manager import get_crawler_manager
        from services.evidence.integration import collect_evidence_for_investigation

        async def investigate(claim: str):
            manager = await get_crawler_manager()
            result = await collect_evidence_for_investigation(
                query=claim,
                crawler_manager=manager,
                max_items=100,
            )
            return result.evidence_docs
    """
    config = EvidenceCollectionConfig(
        max_total_items=max_items,
    )

    orchestrator = EvidenceCollectionOrchestrator(
        config=config,
        crawler_manager=crawler_manager,
    )

    return await orchestrator.collect_evidence(
        query=query,
        platforms=platforms,
        discovery_mode="search",
    )