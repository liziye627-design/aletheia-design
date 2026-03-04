"""
Evidence Pipeline Crawler Integration.
证据管道与爬虫集成

This module connects the crawler output to the evidence pipeline,
enabling seamless data flow from crawlers to evidence documents.

Usage:
    from services.evidence.crawler_integration import CrawlerEvidenceBridge

    bridge = CrawlerEvidenceBridge(crawler_manager)
    evidence = await bridge.collect_and_process("查询内容")
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
import structlog

from services.evidence import (
    EvidencePipeline,
    PipelineConfig,
    PipelineResult,
    BatchPipelineResult,
    SearchHit,
    EvidenceDoc,
    DiscoveryMode,
    EvidenceScorer,
    SourceTierResolver,
    URLNormalizer,
    EvidenceDeduplicator,
)
from services.evidence.evidence_scorer import ScoringContext
from services.evidence.opensearch_client import EvidenceSearchClient, get_opensearch_client
from services.evidence.metrics import get_metrics_collector, CollectionMetrics

logger = structlog.get_logger()


@dataclass
class CrawlerIntegrationConfig:
    """Configuration for crawler integration"""
    # Platforms to crawl
    platforms: List[str] = field(default_factory=lambda: [
        "weibo", "zhihu", "bilibili", "douyin", "xiaohongshu"
    ])

    # Limits
    items_per_platform: int = 20
    max_total_items: int = 100

    # Processing options
    enable_deduplication: bool = True
    enable_scoring: bool = True
    enable_versioning: bool = True

    # Filtering
    min_content_length: int = 50
    min_evidence_score: float = 0.3

    # Storage
    index_to_opensearch: bool = True


class CrawlerEvidenceBridge:
    """
    Bridge between CrawlerManager and Evidence Pipeline.
    爬虫管理器与证据管道的桥接器

    This class:
    1. Fetches data from crawlers
    2. Processes through evidence pipeline
    3. Indexes to OpenSearch
    4. Returns structured evidence documents
    """

    def __init__(
        self,
        crawler_manager=None,
        config: Optional[CrawlerIntegrationConfig] = None,
    ):
        self.crawler_manager = crawler_manager
        self.config = config or CrawlerIntegrationConfig()
        self.pipeline = EvidencePipeline(
            config=PipelineConfig(
                enable_deduplication=self.config.enable_deduplication,
                enable_scoring=self.config.enable_scoring,
            )
        )
        self.scorer = EvidenceScorer()
        self.tier_resolver = SourceTierResolver()
        self.url_normalizer = URLNormalizer()
        self.deduplicator = EvidenceDeduplicator()
        self.metrics = get_metrics_collector()
        self._opensearch_client: Optional[EvidenceSearchClient] = None

    async def _get_opensearch_client(self) -> EvidenceSearchClient:
        """Get or create OpenSearch client"""
        if self._opensearch_client is None:
            self._opensearch_client = await get_opensearch_client()
        return self._opensearch_client

    async def collect_and_process(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        discovery_mode: DiscoveryMode = DiscoveryMode.SEARCH,
    ) -> "CollectionResult":
        """
        Collect data from crawlers and process through evidence pipeline.
        从爬虫收集数据并通过证据管道处理

        Args:
            query: Search query or claim
            platforms: Platforms to search (default: config.platforms)
            discovery_mode: How the evidence was discovered

        Returns:
            CollectionResult with processed evidence documents
        """
        start_time = datetime.utcnow()
        platforms = platforms or self.config.platforms

        logger.info(
            "collecting_evidence",
            query=query[:50],
            platforms=platforms,
        )

        # Results container
        all_items = []
        all_evidence: List[EvidenceDoc] = []
        errors = []

        # Collect from each platform
        for platform in platforms:
            try:
                items, error = await self._collect_from_platform(platform, query)
                if error:
                    errors.append({"platform": platform, "error": error})
                    continue

                all_items.extend(items)

                # Process items through pipeline
                for item in items:
                    try:
                        evidence = await self._process_item(item, query, discovery_mode)
                        if evidence:
                            all_evidence.append(evidence)
                    except Exception as e:
                        logger.warning(
                            "process_item_failed",
                            platform=platform,
                            item_id=item.get("id"),
                            error=str(e),
                        )

            except Exception as e:
                logger.error(
                    "platform_collection_failed",
                    platform=platform,
                    error=str(e),
                )
                errors.append({"platform": platform, "error": str(e)})

        # Filter by score
        filtered_evidence = [
            doc for doc in all_evidence
            if doc.evidence_score >= self.config.min_evidence_score
        ]

        # Sort by score
        filtered_evidence.sort(key=lambda x: x.evidence_score, reverse=True)

        # Limit results
        filtered_evidence = filtered_evidence[:self.config.max_total_items]

        # Index to OpenSearch
        if self.config.index_to_opensearch and filtered_evidence:
            await self._index_evidence(filtered_evidence)

        # Record metrics
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        self._record_metrics(
            query=query,
            platforms=platforms,
            total_items=len(all_items),
            evidence_count=len(filtered_evidence),
            errors=errors,
            duration_ms=duration_ms,
        )

        logger.info(
            "collection_complete",
            query=query[:50],
            total_items=len(all_items),
            evidence_count=len(filtered_evidence),
            duration_ms=duration_ms,
        )

        return CollectionResult(
            query=query,
            platforms=platforms,
            total_items=len(all_items),
            evidence_docs=filtered_evidence,
            errors=errors,
            duration_ms=duration_ms,
        )

    async def _collect_from_platform(
        self,
        platform: str,
        query: str,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Collect items from a single platform

        Returns:
            Tuple of (items, error_message)
        """
        if not self.crawler_manager:
            logger.warning("no_crawler_manager", platform=platform)
            return [], "No crawler manager configured"

        try:
            items = await self.crawler_manager.search_single_platform(
                platform=platform,
                keyword=query,
                limit=self.config.items_per_platform,
            )
            return items or [], None
        except Exception as e:
            logger.error(
                "crawl_failed",
                platform=platform,
                error=str(e),
            )
            return [], str(e)

    async def _process_item(
        self,
        item: Dict[str, Any],
        query: str,
        discovery_mode: DiscoveryMode,
    ) -> Optional[EvidenceDoc]:
        """Process a single crawler item to EvidenceDoc"""

        # Extract fields
        original_url = item.get("original_url", "")
        content_text = item.get("content_text", "")
        platform = item.get("source_platform", "unknown")

        # Skip short content
        if len(content_text) < self.config.min_content_length:
            return None

        # Normalize URL
        url_result = self.url_normalizer.normalize(original_url)

        # Check for duplicates
        content_hash = ""
        if self.config.enable_deduplication:
            try:
                content_hash = self.deduplicator.content_deduper.compute_content_hash(content_text)
                dedup_result = await self.deduplicator.check_duplicate(
                    url=original_url,
                    content=content_text,
                )
                if dedup_result.is_duplicate:
                    logger.debug("duplicate_skipped", url=original_url)
                    return None
            except Exception as e:
                logger.warning("dedup_check_failed", error=str(e))

        # Determine source tier
        source_domain = url_result.domain or ""
        source_tier = self.tier_resolver.resolve(source_domain)

        # Create EvidenceDoc
        doc = EvidenceDoc(
            doc_id=item.get("id", ""),
            original_url=original_url,
            canonical_url=url_result.normalized_url,
            title=item.get("title", content_text[:100]),
            content_text=content_text,
            platform=platform,
            source_org=source_domain,  # Use source_org for domain
            source_tier=source_tier,
            url_hash=url_result.url_hash,
            content_hash=content_hash,
            publish_time=self._parse_time(item.get("created_at")),
            crawl_time=datetime.utcnow(),
        )

        # Score evidence
        if self.config.enable_scoring:
            # Create scoring context from the document
            scoring_context = ScoringContext(
                source_tier=doc.source_tier,
                source_domain=source_domain,
                platform=platform,
                publish_time=doc.publish_time,
                crawl_time=doc.crawl_time,
                extraction_confidence=doc.extraction_confidence,
            )
            score_result = self.scorer.score(scoring_context)
            doc.evidence_score = score_result.evidence_score
            doc.evidence_score_components = score_result.to_dict()

        return doc

    def _parse_time(self, time_value: Any) -> Optional[datetime]:
        """Parse time value from various formats"""
        if not time_value:
            return None

        if isinstance(time_value, datetime):
            return time_value

        if isinstance(time_value, str):
            try:
                # ISO format
                return datetime.fromisoformat(time_value.replace("Z", "+00:00"))
            except ValueError:
                pass

        return None

    async def _index_evidence(self, evidence_docs: List[EvidenceDoc]) -> None:
        """Index evidence documents to OpenSearch"""
        try:
            client = await self._get_opensearch_client()
            docs = [doc.to_dict() for doc in evidence_docs]
            success, errors = await client.bulk_index_evidence(docs)
            logger.info(
                "index_complete",
                success=success,
                errors=len(errors) if errors else 0,
            )
        except Exception as e:
            logger.error("index_failed", error=str(e))

    def _record_metrics(
        self,
        query: str,
        platforms: List[str],
        total_items: int,
        evidence_count: int,
        errors: List[Dict],
        duration_ms: int,
    ) -> None:
        """Record collection metrics"""
        metrics = CollectionMetrics(
            platform=",".join(platforms),
            query=query,
            total_items=total_items,
            successful=evidence_count,
            failed=len(errors),
            duplicates=0,  # TODO: track duplicates
            duration_ms=duration_ms,
        )
        self.metrics.record_collection(metrics)


@dataclass
class CollectionResult:
    """Result of evidence collection"""
    query: str
    platforms: List[str]
    total_items: int
    evidence_docs: List[EvidenceDoc]
    errors: List[Dict[str, Any]]
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "platforms": self.platforms,
            "total_items": self.total_items,
            "evidence_count": len(self.evidence_docs),
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "evidence_docs": [doc.to_dict() for doc in self.evidence_docs[:10]],  # First 10
        }


# ============================================================
# Convenience Functions
# ============================================================

async def collect_evidence(
    query: str,
    crawler_manager=None,
    platforms: Optional[List[str]] = None,
    max_items: int = 100,
) -> CollectionResult:
    """
    Convenience function to collect evidence.

    Args:
        query: Search query or claim
        crawler_manager: CrawlerManager instance
        platforms: Platforms to search
        max_items: Maximum items to return

    Returns:
        CollectionResult with evidence documents
    """
    config = CrawlerIntegrationConfig(
        platforms=platforms or ["weibo", "zhihu", "bilibili"],
        max_total_items=max_items,
    )

    bridge = CrawlerEvidenceBridge(
        crawler_manager=crawler_manager,
        config=config,
    )

    return await bridge.collect_and_process(query)


async def collect_evidence_for_claim(
    claim: str,
    crawler_manager=None,
) -> List[EvidenceDoc]:
    """
    Collect evidence for a claim (simplified interface).

    Args:
        claim: The claim to investigate
        crawler_manager: CrawlerManager instance

    Returns:
        List of EvidenceDoc objects
    """
    result = await collect_evidence(
        query=claim,
        crawler_manager=crawler_manager,
    )
    return result.evidence_docs