"""
Evidence Pipeline - Integration between crawlers and evidence library.
证据管道 - 爬虫与证据库的集成层

This module bridges the Layer1 perception crawlers with the evidence library:
1. Consumes crawler output (standardized format)
2. Converts to SearchHit (discovery layer records)
3. Fetches detail pages and extracts content
4. Creates EvidenceDoc with scoring
5. Handles deduplication and version management

Author: Aletheia Team
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import urlparse
import structlog

from models.evidence import (
    SearchHit,
    EvidenceDoc,
    DiscoveryEntry,
    MediaType,
    SourceTier,
    ExtractionMethod,
    DiscoveryMode,
)
from services.evidence.url_normalizer import (
    URLNormalizer,
    EvidenceDeduplicator,
)
from services.evidence.content_extractor import (
    ContentExtractor,
    ExtractionResult,
)
from services.evidence.evidence_scorer import (
    EvidenceScorer,
    SourceTierResolver,
    ScoringContext,
    PenaltyFlags,
)
from services.evidence.version_manager import VersionManager

logger = structlog.get_logger()


@dataclass
class PipelineConfig:
    """Pipeline configuration"""
    # Fetch settings
    fetch_detail_pages: bool = True
    max_detail_fetch_concurrency: int = 5
    detail_fetch_timeout: float = 10.0

    # Content extraction
    extraction_timeout: float = 5.0

    # Deduplication
    enable_deduplication: bool = True

    # Scoring
    enable_scoring: bool = True

    # Version management
    enable_versioning: bool = True

    # Storage
    store_raw_html: bool = True
    store_screenshots: bool = False


@dataclass
class PipelineResult:
    """Result of processing a single crawler item"""
    success: bool
    search_hit: Optional[SearchHit] = None
    evidence_doc: Optional[EvidenceDoc] = None
    error: Optional[str] = None
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    processing_time_ms: int = 0


@dataclass
class BatchPipelineResult:
    """Result of processing a batch of crawler items"""
    total_items: int
    successful: int
    failed: int
    duplicates: int
    results: List[PipelineResult] = field(default_factory=list)
    total_time_ms: int = 0


class CrawlerOutputProcessor:
    """
    Process crawler output into SearchHit records.
    将爬虫输出处理为 SearchHit 记录
    """

    def __init__(self):
        self.url_normalizer = URLNormalizer()

    def process(
        self,
        crawler_item: Dict[str, Any],
        query: str,
        discovery_mode: DiscoveryMode = DiscoveryMode.SEARCH,
        entry_url: Optional[str] = None,
    ) -> SearchHit:
        """
        Process a single crawler item into a SearchHit.

        Args:
            crawler_item: Standardized crawler output
            query: Search query or keyword
            discovery_mode: How the item was discovered
            entry_url: URL of the discovery entry page

        Returns:
            SearchHit record
        """
        # Extract fields from crawler output
        original_url = crawler_item.get("original_url", "")
        title = crawler_item.get("content_text", "")[:200]  # Use as hit_title
        snippet = crawler_item.get("metadata", {}).get("description", "")

        # Normalize URL
        url_result = self.url_normalizer.normalize(original_url)

        # Parse platform
        platform = crawler_item.get("source_platform", "unknown")
        source_domain = urlparse(original_url).netloc

        # Generate hit ID
        hit_id = self._generate_hit_id(query, original_url, platform)

        # Extract metadata
        metadata = crawler_item.get("metadata", {})
        extra = {
            "likes": metadata.get("likes", 0),
            "comments": metadata.get("comments", 0),
            "shares": metadata.get("shares", 0),
            "engagement_rate": metadata.get("engagement_rate", 0.0),
            "author_name": metadata.get("author_name", ""),
            "author_follower_count": metadata.get("author_follower_count", 0),
        }

        # Add platform-specific fields
        for key in ["hot_rank", "hot_value", "view_count", "duration", "bvid", "aweme_id"]:
            if key in metadata:
                extra[key] = metadata[key]

        # Determine rank (if available in metadata)
        rank = metadata.get("rank", 0)
        if rank == 0:
            rank = 1  # Default rank

        return SearchHit(
            hit_id=hit_id,
            query=query,
            entry_url=entry_url or "",
            hit_url=url_result.normalized_url,
            rank=rank,
            page_no=1,  # Default
            hit_title=title,
            hit_snippet=snippet or crawler_item.get("content_text", "")[:300],
            hit_time_hint=metadata.get("timestamp"),
            hit_source_hint=metadata.get("author_name"),
            platform=platform,
            source_domain=source_domain,
            discovery_mode=discovery_mode,
            captured_at=datetime.utcnow(),
            extra=extra,
            fetch_status="pending",
        )

    def _generate_hit_id(self, query: str, url: str, platform: str) -> str:
        """Generate unique hit ID"""
        unique_str = f"{platform}:{query}:{url}"
        hash_suffix = hashlib.sha256(unique_str.encode()).hexdigest()[:12]
        return f"hit_{hash_suffix}"


class DetailPageFetcher:
    """
    Fetch and extract content from detail pages.
    获取并提取详情页内容
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_concurrency: int = 5,
    ):
        self.timeout = timeout
        self.max_concurrency = max_concurrency
        self.extractor = ContentExtractor()
        self.url_normalizer = URLNormalizer()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch(
        self,
        url: str,
        session=None,
    ) -> Optional[ExtractionResult]:
        """
        Fetch and extract content from a URL.

        Args:
            url: URL to fetch
            session: Optional aiohttp session

        Returns:
            ExtractionResult or None if failed
        """
        async with self._semaphore:
            try:
                start_time = time.time()

                # Fetch HTML
                html = await self._fetch_html(url, session)
                if not html:
                    logger.warning("fetch_failed", url=url)
                    return None

                # Extract content
                result = self.extractor.extract(html, url)

                # Add timing info
                elapsed_ms = int((time.time() - start_time) * 1000)

                logger.info(
                    "detail_fetched",
                    url=url,
                    method=result.extraction_method.value,
                    confidence=result.extraction_confidence,
                    elapsed_ms=elapsed_ms,
                )

                return result

            except asyncio.TimeoutError:
                logger.warning("fetch_timeout", url=url)
                return None
            except Exception as e:
                logger.error("fetch_error", url=url, error=str(e))
                return None

    async def _fetch_html(self, url: str, session=None) -> Optional[str]:
        """Fetch HTML content from URL"""
        try:
            if session is None:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as response:
                        if response.status == 200:
                            return await response.text()
                        return None
            else:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
        except Exception as e:
            logger.debug("fetch_html_error", url=url, error=str(e))
            return None


class EvidencePipeline:
    """
    Main pipeline for converting crawler output to evidence documents.
    将爬虫输出转换为证据文档的主管道

    Flow:
    1. Crawler Output → SearchHit (discovery layer)
    2. SearchHit → Detail Fetch → Extraction
    3. Extracted Content → EvidenceDoc (with scoring)
    4. EvidenceDoc → Deduplication → Storage
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
    ):
        self.config = config or PipelineConfig()
        self.hit_processor = CrawlerOutputProcessor()
        self.detail_fetcher = DetailPageFetcher(
            timeout=self.config.detail_fetch_timeout,
            max_concurrency=self.config.max_detail_fetch_concurrency,
        )
        self.deduplicator = EvidenceDeduplicator() if self.config.enable_deduplication else None
        self.scorer = EvidenceScorer() if self.config.enable_scoring else None
        self.version_manager = VersionManager() if self.config.enable_versioning else None
        self.tier_resolver = SourceTierResolver()
        self.url_normalizer = URLNormalizer()

    async def process_item(
        self,
        crawler_item: Dict[str, Any],
        query: str,
        discovery_mode: DiscoveryMode = DiscoveryMode.SEARCH,
        entry_url: Optional[str] = None,
    ) -> PipelineResult:
        """
        Process a single crawler item through the pipeline.

        Args:
            crawler_item: Standardized crawler output
            query: Search query or keyword
            discovery_mode: How the item was discovered
            entry_url: URL of the discovery entry

        Returns:
            PipelineResult with SearchHit and optionally EvidenceDoc
        """
        start_time = time.time()

        try:
            # Step 1: Create SearchHit
            search_hit = self.hit_processor.process(
                crawler_item=crawler_item,
                query=query,
                discovery_mode=discovery_mode,
                entry_url=entry_url,
            )

            # Mark as fetching
            search_hit.fetch_status = "fetching"

            # Step 2: Check for duplicates (URL level)
            if self.deduplicator and self.config.enable_deduplication:
                dup_result = await self.deduplicator.check_duplicate(
                    url=search_hit.hit_url,
                    content="",  # No content yet
                )
                if dup_result.is_duplicate:
                    search_hit.fetch_status = "skipped"
                    search_hit.doc_id = dup_result.existing_doc_id

                    return PipelineResult(
                        success=True,
                        search_hit=search_hit,
                        is_duplicate=True,
                        duplicate_of=dup_result.existing_doc_id,
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )

            # Step 3: Fetch and extract detail page
            if not self.config.fetch_detail_pages:
                search_hit.fetch_status = "pending"
                return PipelineResult(
                    success=True,
                    search_hit=search_hit,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

            extraction_result = await self.detail_fetcher.fetch(search_hit.hit_url)

            if not extraction_result or not extraction_result.content_text:
                search_hit.fetch_status = "failed"
                return PipelineResult(
                    success=False,
                    search_hit=search_hit,
                    error="Failed to extract content",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

            # Step 4: Check for content duplicates
            if self.deduplicator and self.config.enable_deduplication:
                dup_result = await self.deduplicator.check_duplicate(
                    url=search_hit.hit_url,
                    content=extraction_result.content_text,
                    canonical_hint=extraction_result.canonical_url,
                )
                if dup_result.is_duplicate:
                    search_hit.fetch_status = "skipped"
                    search_hit.doc_id = dup_result.existing_doc_id

                    return PipelineResult(
                        success=True,
                        search_hit=search_hit,
                        is_duplicate=True,
                        duplicate_of=dup_result.existing_doc_id,
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )

            # Step 5: Create EvidenceDoc
            evidence_doc = await self._create_evidence_doc(
                search_hit=search_hit,
                extraction_result=extraction_result,
                crawler_item=crawler_item,
            )

            # Step 6: Register in deduplication index
            if self.deduplicator and self.config.enable_deduplication:
                await self.deduplicator.register_evidence(
                    doc_id=evidence_doc.doc_id,
                    url=evidence_doc.original_url,
                    content=evidence_doc.content_text,
                    canonical_hint=extraction_result.canonical_url,
                )

            # Step 7: Create version record
            if self.version_manager and self.config.enable_versioning:
                version = self.version_manager.create_version(
                    doc_id=evidence_doc.doc_id,
                    title=evidence_doc.title,
                    content_text=evidence_doc.content_text,
                    url_hash=evidence_doc.url_hash,
                    content_hash=evidence_doc.content_hash,
                )
                evidence_doc.version_id = version.version_id

            # Update hit status
            search_hit.fetch_status = "success"
            search_hit.doc_id = evidence_doc.doc_id

            return PipelineResult(
                success=True,
                search_hit=search_hit,
                evidence_doc=evidence_doc,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

        except Exception as e:
            logger.error("pipeline_error", error=str(e), query=query)
            return PipelineResult(
                success=False,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def process_batch(
        self,
        crawler_items: List[Dict[str, Any]],
        query: str,
        discovery_mode: DiscoveryMode = DiscoveryMode.SEARCH,
        entry_url: Optional[str] = None,
    ) -> BatchPipelineResult:
        """
        Process a batch of crawler items.

        Args:
            crawler_items: List of standardized crawler outputs
            query: Search query or keyword
            discovery_mode: How items were discovered
            entry_url: URL of the discovery entry

        Returns:
            BatchPipelineResult with all processing results
        """
        start_time = time.time()
        results = []

        # Process items concurrently
        tasks = [
            self.process_item(
                crawler_item=item,
                query=query,
                discovery_mode=discovery_mode,
                entry_url=entry_url,
            )
            for item in crawler_items
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(PipelineResult(
                    success=False,
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        # Count statistics
        successful = sum(1 for r in processed_results if r.success and not r.is_duplicate)
        duplicates = sum(1 for r in processed_results if r.is_duplicate)
        failed = sum(1 for r in processed_results if not r.success)

        return BatchPipelineResult(
            total_items=len(crawler_items),
            successful=successful,
            failed=failed,
            duplicates=duplicates,
            results=processed_results,
            total_time_ms=int((time.time() - start_time) * 1000),
        )

    async def _create_evidence_doc(
        self,
        search_hit: SearchHit,
        extraction_result: ExtractionResult,
        crawler_item: Dict[str, Any],
    ) -> EvidenceDoc:
        """Create EvidenceDoc from extraction result"""
        # Normalize URL
        url_result = self.url_normalizer.normalize(
            search_hit.hit_url,
            extraction_result.canonical_url,
        )

        # Generate document ID
        doc_id = self._generate_doc_id(url_result.url_hash, search_hit.platform)

        # Determine media type
        media_type = MediaType.TEXT
        if extraction_result.videos:
            media_type = MediaType.VIDEO
        elif extraction_result.images:
            media_type = MediaType.IMAGE

        # Determine source tier
        source_tier = self.tier_resolver.resolve(search_hit.source_domain)

        # Calculate content hashes
        content_hash = ""
        simhash = ""
        if extraction_result.content_text:
            from services.evidence.url_normalizer import compute_content_hash, compute_simhash
            content_hash = compute_content_hash(extraction_result.content_text)
            simhash = compute_simhash(extraction_result.content_text)

        # Create initial evidence doc
        evidence_doc = EvidenceDoc(
            doc_id=doc_id,
            original_url=search_hit.hit_url,
            canonical_url=url_result.canonical_url,
            title=extraction_result.title or search_hit.hit_title,
            content_text=extraction_result.content_text,
            content_html=extraction_result.content_html,
            media_type=media_type,
            images=extraction_result.images,
            videos=extraction_result.videos,
            publish_time=extraction_result.publish_time,
            author=extraction_result.author,
            source_org=search_hit.source_domain,
            language="zh",  # Default
            tags=extraction_result.tags,
            platform=search_hit.platform,
            platform_doc_id=crawler_item.get("id"),
            extraction_method=ExtractionMethod(extraction_result.extraction_method.value),
            extraction_confidence=extraction_result.extraction_confidence,
            crawl_time=datetime.utcnow(),
            http_status=200,
            source_tier=source_tier,
            url_hash=url_result.url_hash,
            content_hash=content_hash,
            simhash=simhash,
            hit_ids=[search_hit.hit_id],
        )

        # Calculate evidence score
        if self.scorer:
            scoring_context = self._build_scoring_context(
                evidence_doc=evidence_doc,
                crawler_item=crawler_item,
            )
            scoring_result = self.scorer.score(scoring_context)
            evidence_doc.evidence_score = scoring_result.evidence_score
            evidence_doc.evidence_score_components = scoring_result.components

        return evidence_doc

    def _build_scoring_context(
        self,
        evidence_doc: EvidenceDoc,
        crawler_item: Dict[str, Any],
    ) -> ScoringContext:
        """Build scoring context from evidence doc"""
        metadata = crawler_item.get("metadata", {})

        return ScoringContext(
            source_tier=evidence_doc.source_tier,
            source_domain=evidence_doc.source_domain,
            platform=evidence_doc.platform,
            publish_time=evidence_doc.publish_time,
            crawl_time=evidence_doc.crawl_time,
            extraction_method=evidence_doc.extraction_method.value,
            extraction_confidence=evidence_doc.extraction_confidence,
            unique_domains_count=1,
            penalties=PenaltyFlags(
                is_deleted=False,
                content_missing=not evidence_doc.content_text,
            ),
        )

    def _generate_doc_id(self, url_hash: str, platform: str) -> str:
        """Generate stable document ID"""
        return f"doc_{platform}_{url_hash[:16]}"


# ============================================================
# Integration with CrawlerManager
# ============================================================

class EvidencePipelineAdapter:
    """
    Adapter to integrate EvidencePipeline with existing CrawlerManager.
    适配器 - 将 EvidencePipeline 与现有 CrawlerManager 集成

    Usage:
        adapter = EvidencePipelineAdapter()
        results = await adapter.process_crawler_results(
            platform="weibo",
            query="test",
            crawler_results=items,
        )
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
    ):
        self.pipeline = EvidencePipeline(config=config)

    async def process_crawler_results(
        self,
        platform: str,
        query: str,
        crawler_results: List[Dict[str, Any]],
        discovery_mode: str = "search",
        entry_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process crawler results and return evidence statistics.

        Args:
            platform: Platform name
            query: Search query
            crawler_results: List of items from crawler
            discovery_mode: "search", "hot", "topic", or "feed"
            entry_url: URL of the discovery entry

        Returns:
            Processing statistics and results
        """
        mode_map = {
            "search": DiscoveryMode.SEARCH,
            "hot": DiscoveryMode.HOT,
            "topic": DiscoveryMode.TOPIC,
            "feed": DiscoveryMode.FEED,
            "api": DiscoveryMode.API,
        }
        discovery_mode_enum = mode_map.get(discovery_mode, DiscoveryMode.SEARCH)

        result = await self.pipeline.process_batch(
            crawler_items=crawler_results,
            query=query,
            discovery_mode=discovery_mode_enum,
            entry_url=entry_url,
        )

        # Collect evidence docs
        evidence_docs = [
            r.evidence_doc for r in result.results
            if r.success and r.evidence_doc
        ]

        # Collect search hits
        search_hits = [
            r.search_hit for r in result.results
            if r.search_hit
        ]

        return {
            "platform": platform,
            "query": query,
            "total_items": result.total_items,
            "successful": result.successful,
            "failed": result.failed,
            "duplicates": result.duplicates,
            "total_time_ms": result.total_time_ms,
            "evidence_docs": [doc.to_dict() for doc in evidence_docs],
            "search_hits": [hit.to_dict() for hit in search_hits],
        }


# Convenience function
async def process_crawler_output(
    crawler_items: List[Dict[str, Any]],
    query: str,
    platform: str = "unknown",
    discovery_mode: str = "search",
) -> BatchPipelineResult:
    """
    Convenience function to process crawler output.

    Args:
        crawler_items: List of standardized crawler outputs
        query: Search query or keyword
        platform: Platform name
        discovery_mode: "search", "hot", "topic", or "feed"

    Returns:
        BatchPipelineResult with all processing results
    """
    pipeline = EvidencePipeline()
    mode_map = {
        "search": DiscoveryMode.SEARCH,
        "hot": DiscoveryMode.HOT,
        "topic": DiscoveryMode.TOPIC,
        "feed": DiscoveryMode.FEED,
    }
    return await pipeline.process_batch(
        crawler_items=crawler_items,
        query=query,
        discovery_mode=mode_map.get(discovery_mode, DiscoveryMode.SEARCH),
    )