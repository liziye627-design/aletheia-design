"""
Investigation Engine Evidence Adapter.
调查引擎证据适配器

This module provides an adapter to integrate the Evidence Library
with the existing InvestigationOrchestrator.

Usage:
    from services.evidence.investigation_adapter import EvidenceAdapter

    adapter = EvidenceAdapter(crawler_manager=crawler_manager)
    evidence_cards = await adapter.collect_evidence_cards(claim="...")
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from urllib.parse import urlparse
import structlog

from services.evidence.integration import (
    EvidenceCollectionOrchestrator,
    EvidenceCollectionConfig,
    EvidenceCollectionResult,
)
from services.evidence import (
    EvidenceDoc,
    SourceTier,
    EvidenceScorer,
    SourceTierResolver,
)

logger = structlog.get_logger()


@dataclass
class EvidenceCard:
    """
    Evidence card format compatible with InvestigationEngine.
    与 InvestigationEngine 兼容的证据卡片格式
    """
    id: str
    claim_ref: str
    source_tier: int  # 1=official, 2=mainstream, 3=social
    source_name: str
    source_platform: str
    evidence_origin: str
    url: str
    snippet: str
    stance: str = "unknown"
    confidence: float = 0.5
    collected_at: str = ""
    published_at: Optional[str] = None
    retrieval_query: str = ""
    validation_status: str = "provisional"
    keyword_match: bool = False
    relevance_score: float = 0.0
    retrieval_mode: str = "live"

    # Extended fields from Evidence Library
    evidence_score: float = 0.0
    extraction_method: str = "fallback"
    extraction_confidence: float = 0.0
    doc_id: Optional[str] = None
    version_id: Optional[str] = None
    has_corrections: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "claim_ref": self.claim_ref,
            "source_tier": self.source_tier,
            "source_name": self.source_name,
            "source_platform": self.source_platform,
            "evidence_origin": self.evidence_origin,
            "url": self.url,
            "snippet": self.snippet,
            "stance": self.stance,
            "confidence": self.confidence,
            "collected_at": self.collected_at,
            "published_at": self.published_at,
            "retrieval_query": self.retrieval_query,
            "validation_status": self.validation_status,
            "keyword_match": self.keyword_match,
            "relevance_score": self.relevance_score,
            "retrieval_mode": self.retrieval_mode,
            "evidence_score": self.evidence_score,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "doc_id": self.doc_id,
            "version_id": self.version_id,
            "has_corrections": self.has_corrections,
        }


class EvidenceAdapter:
    """
    Adapter to integrate Evidence Library with InvestigationEngine.
    证据库与调查引擎的集成适配器

    This adapter:
    1. Uses EvidenceCollectionOrchestrator to collect evidence
    2. Converts EvidenceDoc to EvidenceCard format
    3. Maintains compatibility with existing InvestigationEngine interfaces
    """

    # Tier mapping: Evidence Library tier -> InvestigationEngine tier
    TIER_MAP = {
        SourceTier.S: 1,  # Official/Authoritative
        SourceTier.A: 2,  # Mainstream media
        SourceTier.B: 2,  # Mainstream media (large platforms)
        SourceTier.C: 3,  # Social media
    }

    def __init__(
        self,
        crawler_manager=None,
        config: Optional[EvidenceCollectionConfig] = None,
    ):
        self.crawler_manager = crawler_manager
        self.config = config or EvidenceCollectionConfig(
            max_total_items=300,
            # 保持适配器在离线/测试环境可用，避免详情页抓取失败导致结果全空
            fetch_detail_pages=False,
            enable_deduplication=True,
            enable_scoring=True,
        )
        self.orchestrator = EvidenceCollectionOrchestrator(
            config=self.config,
            crawler_manager=crawler_manager,
        )
        self.tier_resolver = SourceTierResolver()

    async def collect_evidence_cards(
        self,
        claim: str,
        platforms: Optional[List[str]] = None,
        max_items: int = 100,
        min_evidence_score: float = 0.3,
    ) -> List[EvidenceCard]:
        """
        Collect evidence cards for a claim.
        为声明收集证据卡片

        Args:
            claim: The claim to investigate
            platforms: Optional list of platforms to search
            max_items: Maximum number of evidence cards to return
            min_evidence_score: Minimum evidence score threshold

        Returns:
            List of EvidenceCard objects
        """
        # Collect evidence using Evidence Library
        result = await self.orchestrator.collect_evidence(
            query=claim,
            platforms=platforms,
            discovery_mode="search",
        )

        # Convert to EvidenceCards
        cards = []
        for doc in result.evidence_docs:
            if doc.evidence_score < min_evidence_score:
                continue

            card = self._doc_to_card(doc, claim)
            cards.append(card)

            if len(cards) >= max_items:
                break

        # Sort by evidence score
        cards.sort(key=lambda x: x.evidence_score, reverse=True)

        # 软降级：若严格阈值导致空集，则返回最高分候选以维持流程可用性
        if (not cards) and result.evidence_docs:
            fallback_docs = sorted(
                list(result.evidence_docs),
                key=lambda d: float(getattr(d, "evidence_score", 0.0) or 0.0),
                reverse=True,
            )[:max_items]
            cards = [self._doc_to_card(doc, claim) for doc in fallback_docs]
        # 更深一层降级：当 evidence_docs 为空时，回退为 search_hits 直出卡片
        if (not cards) and result.search_hits:
            cards = self._search_hits_to_cards(
                claim=claim,
                hits=result.search_hits,
                max_items=max_items,
            )

        logger.info(
            "evidence_cards_collected",
            claim=claim[:50],
            total=result.total_evidence,
            returned=len(cards),
        )

        return cards

    def _search_hits_to_cards(
        self,
        *,
        claim: str,
        hits: List[Any],
        max_items: int,
    ) -> List[EvidenceCard]:
        out: List[EvidenceCard] = []
        for idx, hit in enumerate(list(hits)[:max_items]):
            url = str(getattr(hit, "hit_url", "") or "")
            domain = str(getattr(hit, "source_domain", "") or urlparse(url).netloc or "")
            source_tier = self.TIER_MAP.get(self.tier_resolver.resolve(domain), 3)
            snippet = str(
                getattr(hit, "hit_snippet", "") or getattr(hit, "hit_title", "") or ""
            )[:500]
            out.append(
                EvidenceCard(
                    id=f"ev_hit_{idx}_{abs(hash(url)) % 10_000_000}",
                    claim_ref=claim,
                    source_tier=source_tier,
                    source_name=domain or str(getattr(hit, "platform", "") or "unknown"),
                    source_platform=str(getattr(hit, "platform", "") or "unknown"),
                    evidence_origin="external",
                    url=url,
                    snippet=snippet,
                    confidence=0.5,
                    collected_at=datetime.utcnow().isoformat(),
                    retrieval_query=str(getattr(hit, "query", "") or claim),
                    validation_status="provisional",
                    keyword_match=True,
                    relevance_score=0.35,
                    retrieval_mode="search_hit_fallback",
                    evidence_score=0.35,
                    extraction_method="fallback",
                    extraction_confidence=0.3,
                )
            )
        return out

    async def collect_evidence_cards_from_platform(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
    ) -> List[EvidenceCard]:
        """
        Collect evidence cards from a single platform.
        从单个平台收集证据卡片

        This method provides compatibility with CrawlerManager's
        search_single_platform interface.
        """
        result = await self.orchestrator.collect_evidence(
            query=keyword,
            platforms=[platform],
            discovery_mode="search",
        )

        cards = []
        for doc in result.evidence_docs[:limit]:
            card = self._doc_to_card(doc, keyword)
            cards.append(card)

        return cards

    def _doc_to_card(
        self,
        doc: EvidenceDoc,
        claim: str,
    ) -> EvidenceCard:
        """Convert EvidenceDoc to EvidenceCard"""
        # Determine source tier (InvestigationEngine format: 1/2/3)
        source_tier = self.TIER_MAP.get(doc.source_tier, 3)

        # Determine source name
        source_name = doc.source_org or doc.source_domain

        # Generate snippet
        snippet = ""
        if doc.content_text:
            snippet = doc.content_text[:500]
            if len(doc.content_text) > 500:
                snippet += "..."

        # Generate card ID
        card_id = f"ev_{doc.platform}_{doc.doc_id[:12]}"

        # Determine validation status
        validation_status = "provisional"
        if doc.http_status == 200 and doc.content_text:
            validation_status = "reachable"
        elif doc.is_deleted:
            validation_status = "deleted"

        return EvidenceCard(
            id=card_id,
            claim_ref=claim,
            source_tier=source_tier,
            source_name=source_name,
            source_platform=doc.platform,
            evidence_origin="external",
            url=doc.canonical_url or doc.original_url,
            snippet=snippet,
            stance="unknown",
            confidence=doc.extraction_confidence,
            collected_at=doc.crawl_time.isoformat(),
            published_at=doc.publish_time.isoformat() if doc.publish_time else None,
            retrieval_query=claim,
            validation_status=validation_status,
            keyword_match=True,  # Already filtered by query
            relevance_score=doc.evidence_score,
            retrieval_mode="live",
            evidence_score=doc.evidence_score,
            extraction_method=doc.extraction_method.value,
            extraction_confidence=doc.extraction_confidence,
            doc_id=doc.doc_id,
            version_id=doc.version_id,
            has_corrections=doc.has_correction,
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        return {
            "config": {
                "max_total_items": self.config.max_total_items,
                "fetch_detail_pages": self.config.fetch_detail_pages,
                "platforms": self.config.platforms,
            },
        }


# ============================================================
# Drop-in Replacement for CrawlerManager.search_single_platform
# ============================================================

class CrawlerManagerEvidenceWrapper:
    """
    Wrapper that provides CrawlerManager-like interface using Evidence Library.

    This can be used as a drop-in replacement in InvestigationEngine
    to use the new Evidence Library pipeline while maintaining
    backward compatibility.
    """

    def __init__(
        self,
        crawler_manager=None,
        evidence_adapter: Optional[EvidenceAdapter] = None,
    ):
        self.crawler_manager = crawler_manager
        self.evidence_adapter = evidence_adapter or EvidenceAdapter(
            crawler_manager=crawler_manager,
        )

    async def search_single_platform(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Search a single platform and return standardized items.

        This provides backward compatibility with the CrawlerManager
        interface while using the Evidence Library pipeline.
        """
        # Try original crawler manager first
        if self.crawler_manager:
            try:
                items = await self.crawler_manager.search_single_platform(
                    platform=platform,
                    keyword=keyword,
                    limit=limit,
                    **kwargs,
                )
                if items:
                    return items
            except Exception as e:
                logger.warning(
                    "crawler_manager_failed",
                    platform=platform,
                    error=str(e),
                )

        # Fallback to evidence adapter
        cards = await self.evidence_adapter.collect_evidence_cards_from_platform(
            platform=platform,
            keyword=keyword,
            limit=limit,
        )

        # Convert to crawler output format
        items = []
        for card in cards:
            item = {
                "id": card.doc_id or card.id,
                "source_platform": card.source_platform,
                "original_url": card.url,
                "content_text": card.snippet,
                "content_type": "TEXT",
                "image_urls": [],
                "video_url": None,
                "metadata": {
                    "timestamp": card.collected_at,
                    "author": "",
                    "author_follower_count": 0,
                    "engagement_rate": 0.0,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "evidence_score": card.evidence_score,
                    "extraction_method": card.extraction_method,
                },
                "entities": [],
                "created_at": card.collected_at,
            }
            items.append(item)

        return items

    async def search_across_platforms(
        self,
        keyword: str,
        platforms: Optional[List[str]] = None,
        limit_per_platform: int = 20,
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across multiple platforms.
        """
        platforms = platforms or self.evidence_adapter.config.platforms

        tasks = []
        for platform in platforms:
            task = self.search_single_platform(
                platform=platform,
                keyword=keyword,
                limit=limit_per_platform,
            )
            tasks.append((platform, task))

        results = {}
        for platform, task in tasks:
            try:
                items = await task
                results[platform] = items
            except Exception as e:
                logger.error("platform_search_failed", platform=platform, error=str(e))
                results[platform] = []

        return results


# Convenience functions for integration

async def create_evidence_adapter(
    crawler_manager=None,
    max_items: int = 200,
) -> EvidenceAdapter:
    """Factory function to create EvidenceAdapter"""
    config = EvidenceCollectionConfig(
        max_total_items=max_items,
        fetch_detail_pages=True,
        enable_deduplication=True,
        enable_scoring=True,
    )
    return EvidenceAdapter(
        crawler_manager=crawler_manager,
        config=config,
    )


async def collect_evidence_for_investigation(
    claim: str,
    crawler_manager=None,
    platforms: Optional[List[str]] = None,
    max_items: int = 100,
) -> List[EvidenceCard]:
    """
    Convenience function to collect evidence for investigation.

    This is the main entry point for InvestigationEngine to use
    the Evidence Library.

    Args:
        claim: The claim to investigate
        crawler_manager: Optional CrawlerManager instance
        platforms: Optional list of platforms to search
        max_items: Maximum number of evidence cards

    Returns:
        List of EvidenceCard objects
    """
    adapter = await create_evidence_adapter(
        crawler_manager=crawler_manager,
        max_items=max_items,
    )
    return await adapter.collect_evidence_cards(
        claim=claim,
        platforms=platforms,
        max_items=max_items,
    )
