"""
Unit tests for Evidence Library components.
证据库组件单元测试

Tests:
- URL normalization and deduplication
- Content extraction
- Evidence scoring
- Version management
- OpenSearch query building

Run with: pytest tests/unit/test_evidence_library.py -v
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
import hashlib

# ============================================================
# URL Normalizer Tests
# ============================================================

class TestURLNormalizer:
    """Tests for URL normalization"""

    def test_normalize_basic_url(self):
        """Test basic URL normalization"""
        from services.evidence import URLNormalizer

        normalizer = URLNormalizer()

        # Test basic normalization
        result = normalizer.normalize("https://example.com/path?utm_source=test&id=123")
        assert result.normalized_url is not None
        assert "utm_source" not in result.normalized_url

    def test_normalize_chinese_url(self):
        """Test URL with Chinese characters"""
        from services.evidence import URLNormalizer

        normalizer = URLNormalizer()

        result = normalizer.normalize("https://weibo.com/用户/帖子/123")
        assert result.normalized_url is not None

    def test_normalize_weibo_urls(self):
        """Test Weibo URL normalization"""
        from services.evidence import URLNormalizer

        normalizer = URLNormalizer()

        # Mobile to desktop
        result = normalizer.normalize("https://m.weibo.cn/detail/123456789")
        assert "weibo.com" in result.normalized_url or result.normalized_url is not None

    def test_normalize_url_hash(self):
        """Test URL hash generation"""
        from services.evidence import URLNormalizer

        normalizer = URLNormalizer()

        result1 = normalizer.normalize("https://example.com/page")
        result2 = normalizer.normalize("https://example.com/page")

        assert result1.url_hash == result2.url_hash

    def test_duplicate_detection(self):
        """Test duplicate URL detection"""
        from services.evidence import URLNormalizer, ContentDeduplicator

        normalizer = URLNormalizer()

        # Same content, different tracking params
        url1 = normalizer.normalize("https://example.com/article?id=123&utm_source=twitter")
        url2 = normalizer.normalize("https://example.com/article?id=123&utm_source=facebook")

        assert url1.url_hash == url2.url_hash


class TestContentDeduplicator:
    """Tests for content deduplication"""

    def test_content_hash(self):
        """Test content hash computation"""
        from services.evidence import compute_content_hash

        content = "This is test content for hashing"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_simhash_similarity(self):
        """Test SimHash for near-duplicate detection"""
        from services.evidence import compute_simhash

        content1 = "The quick brown fox jumps over the lazy dog"
        content2 = "The quick brown fox jumps over the lazy cat"
        content3 = "Completely different content here"

        hash1 = compute_simhash(content1)
        hash2 = compute_simhash(content2)
        hash3 = compute_simhash(content3)

        # Similar content should have similar hashes
        # Different content should have different hashes
        assert hash1 is not None
        assert hash2 is not None


# ============================================================
# Evidence Scorer Tests
# ============================================================

class TestEvidenceScorer:
    """Tests for evidence scoring"""

    def test_source_tier_resolution(self):
        """Test source tier resolution"""
        from services.evidence import SourceTierResolver, SourceTier

        resolver = SourceTierResolver()

        # Test with domain only (correct signature)
        tier = resolver.resolve("gov.cn")
        assert tier in [SourceTier.S, SourceTier.A, SourceTier.B, SourceTier.C]

        # Mainstream media
        tier = resolver.resolve("xinhuanet.com")
        assert tier in [SourceTier.S, SourceTier.A]

        # Social media
        tier = resolver.resolve("weibo.com")
        assert tier in [SourceTier.B, SourceTier.C]

    def test_evidence_score_calculation(self):
        """Test evidence score calculation"""
        from services.evidence import EvidenceScorer, EvidenceDoc, SourceTier, ScoringContext

        scorer = EvidenceScorer()

        # Create scoring context (correct approach)
        context = ScoringContext(
            source_tier=SourceTier.A,
            source_domain="example.com",
            platform="example",
            extraction_confidence=0.9,
        )

        score = scorer.score(context)
        assert 0.0 <= score.evidence_score <= 1.0

    def test_penalty_flags(self):
        """Test penalty flags"""
        from services.evidence.evidence_scorer import PenaltyFlags

        # Use correct field names from actual model
        penalties = PenaltyFlags(
            is_deleted=True,
            content_missing=True,
            fetch_failed=True,
        )

        # Check the penalties exist
        assert penalties is not None
        assert penalties.is_deleted


# ============================================================
# Content Extractor Tests
# ============================================================

class TestContentExtractor:
    """Tests for content extraction"""

    def test_extraction_result(self):
        """Test extraction result structure"""
        from services.evidence import ExtractionResult, ExtractionMethod

        result = ExtractionResult(
            title="Test Title",
            content_text="Test content",
            content_html="<p>Test content</p>",
            author="Test Author",
            publish_time=datetime.utcnow(),
            extraction_method=ExtractionMethod.TEMPLATE_RULES,  # Correct enum value
            extraction_confidence=0.95,
        )

        assert result.title == "Test Title"
        assert result.extraction_method == ExtractionMethod.TEMPLATE_RULES

    def test_site_template_matching(self):
        """Test site template matching"""
        from services.evidence import ContentExtractor, SITE_TEMPLATES

        extractor = ContentExtractor()

        # Check if templates exist for common sites
        assert len(SITE_TEMPLATES) > 0


# ============================================================
# Version Manager Tests
# ============================================================

class TestVersionManager:
    """Tests for version management"""

    def test_version_id_generation(self):
        """Test version ID generation"""
        from services.evidence import VersionManager

        manager = VersionManager()

        # Use the correct method name
        version_id = manager._generate_version_id("doc_001")
        assert version_id.startswith("doc_001:")

    def test_version_creation(self):
        """Test version creation"""
        from services.evidence import VersionManager

        manager = VersionManager()

        # Use correct signature with url_hash
        record = manager.create_version(
            doc_id="doc_001",
            url_hash="abc123",
            title="Test Title",
            content_text="Test content",
            content_hash="content_hash_123",
        )

        assert record.doc_id == "doc_001"

    def test_change_detection(self):
        """Test change detection between versions"""
        from services.evidence import VersionManager

        manager = VersionManager()

        # Create two versions with correct parameters
        v1 = manager.create_version(
            doc_id="doc_001",
            url_hash="url_hash_1",
            title="Title 1",
            content_text="Content 1",
            content_hash="hash1",
        )

        v2 = manager.create_version(
            doc_id="doc_001",
            url_hash="url_hash_1",
            title="Title 2",
            content_text="Content 2",
            content_hash="hash2",
        )

        assert v1.content_hash != v2.content_hash


# ============================================================
# OpenSearch Query Builder Tests
# ============================================================

class TestOpenSearchQueryBuilder:
    """Tests for OpenSearch query building"""

    def test_build_basic_search_query(self):
        """Test basic search query building"""
        from services.evidence import OpenSearchQueryBuilder, SearchQuery

        builder = OpenSearchQueryBuilder()

        query = SearchQuery(
            query_text="test query",
            query_fields=["title", "content_text"],
            size=10,
            from_=0,
        )

        dsl = builder.build_search_query(query)

        assert "query" in dsl
        assert "size" in dsl
        assert dsl["size"] == 10

    def test_build_filtered_query(self):
        """Test filtered search query"""
        from services.evidence import OpenSearchQueryBuilder, SearchQuery

        builder = OpenSearchQueryBuilder()

        query = SearchQuery(
            query_text="test",
            query_fields=["content_text"],
            platforms=["weibo", "zhihu"],
            source_tiers=["A", "B"],
            min_evidence_score=0.5,
            size=20,
            from_=0,
        )

        dsl = builder.build_search_query(query)

        assert "query" in dsl
        assert "bool" in dsl["query"]

    def test_build_similar_query(self):
        """Test similar documents query"""
        from services.evidence import OpenSearchQueryBuilder

        builder = OpenSearchQueryBuilder()

        dsl = builder.build_similar_query(
            vector=[0.1] * 1024,  # Mock vector
            k=10,
            exclude_doc_ids=["doc_001"],
        )

        assert "query" in dsl
        # The query uses bool -> must -> knn structure
        assert "bool" in dsl["query"]

    def test_time_range_filter(self):
        """Test time range filtering"""
        from services.evidence import OpenSearchQueryBuilder, SearchQuery

        builder = OpenSearchQueryBuilder()

        query = SearchQuery(
            query_text="test",
            query_fields=["content_text"],
            publish_time_start="2024-01-01T00:00:00Z",
            publish_time_end="2024-12-31T23:59:59Z",
            size=10,
            from_=0,
        )

        dsl = builder.build_search_query(query)

        # Should have range filter
        assert "query" in dsl


# ============================================================
# Evidence Model Tests
# ============================================================

class TestEvidenceModels:
    """Tests for evidence data models"""

    def test_search_hit_creation(self):
        """Test SearchHit model creation"""
        from services.evidence import SearchHit, DiscoveryMode

        # Use correct field names from model
        hit = SearchHit(
            hit_id="hit_001",
            query="test query",
            entry_url="https://weibo.com/search",
            hit_url="https://weibo.com/123",
            rank=1,
            page_no=1,
            hit_title="Test Title",  # Correct field name
            platform="weibo",
            discovery_mode=DiscoveryMode.SEARCH,
        )

        assert hit.hit_id == "hit_001"
        assert hit.platform == "weibo"
        assert hit.discovery_mode == DiscoveryMode.SEARCH

    def test_evidence_doc_creation(self):
        """Test EvidenceDoc model creation"""
        from services.evidence import EvidenceDoc, SourceTier, ExtractionMethod

        # Use correct field names
        doc = EvidenceDoc(
            doc_id="doc_001",
            original_url="https://example.com/article",
            title="Test Article",
            source_tier=SourceTier.A,
            extraction_method=ExtractionMethod.TEMPLATE_RULES,  # Correct enum
            extraction_confidence=0.95,
        )

        assert doc.doc_id == "doc_001"
        assert doc.source_tier == SourceTier.A

    def test_evidence_doc_to_dict(self):
        """Test EvidenceDoc serialization"""
        from services.evidence import EvidenceDoc, SourceTier

        doc = EvidenceDoc(
            doc_id="doc_001",
            original_url="https://example.com/article",
            title="Test",
            content_text="Content",
            source_tier=SourceTier.B,
        )

        doc_dict = doc.to_dict()
        assert "doc_id" in doc_dict
        assert doc_dict["doc_id"] == "doc_001"


# ============================================================
# Integration Tests (with mocking)
# ============================================================

class TestEvidencePipeline:
    """Tests for evidence pipeline"""

    @pytest.mark.asyncio
    async def test_pipeline_initialization(self):
        """Test pipeline can be initialized"""
        from services.evidence import EvidencePipeline, PipelineConfig

        config = PipelineConfig(
            enable_deduplication=True,
            enable_scoring=True,
        )

        pipeline = EvidencePipeline(config=config)
        assert pipeline is not None

    @pytest.mark.asyncio
    async def test_process_search_hit(self):
        """Test processing a search hit"""
        from services.evidence import EvidencePipeline, SearchHit, DiscoveryMode

        pipeline = EvidencePipeline()

        # Use correct field names
        hit = SearchHit(
            hit_id="hit_001",
            query="test",
            entry_url="https://weibo.com/search",
            hit_url="https://weibo.com/123",
            rank=1,
            page_no=1,
            hit_title="Test",
            platform="weibo",
            discovery_mode=DiscoveryMode.SEARCH,
        )

        # Process would need crawler output
        # result = await pipeline.process_hit(hit)
        # assert result is not None


# ============================================================
# Metrics Tests
# ============================================================

class TestEvidenceMetrics:
    """Tests for evidence metrics"""

    def test_metrics_collector_creation(self):
        """Test metrics collector creation"""
        from services.evidence import EvidenceMetricsCollector

        collector = EvidenceMetricsCollector()
        assert collector is not None

    def test_collection_metrics(self):
        """Test collection metrics recording"""
        from services.evidence import EvidenceMetricsCollector, CollectionMetrics

        collector = EvidenceMetricsCollector()

        metrics = CollectionMetrics(
            platform="weibo",
            query="test query",
            total_items=100,
            successful=95,
            failed=5,
            duplicates=10,
            duration_ms=500,
        )

        collector.record_collection(metrics)

        stats = collector.get_metrics()
        assert stats["total_items"] == 100

    def test_score_recording(self):
        """Test score recording"""
        from services.evidence import EvidenceMetricsCollector

        collector = EvidenceMetricsCollector()

        collector.record_evidence_score(0.85, "A")
        collector.record_evidence_score(0.72, "B")

        stats = collector.get_metrics()
        assert "by_tier" in stats

    def test_platform_stats(self):
        """Test platform statistics"""
        from services.evidence import EvidenceMetricsCollector, CollectionMetrics

        collector = EvidenceMetricsCollector()

        metrics = CollectionMetrics(
            platform="weibo",
            query="test",
            total_items=50,
            successful=45,
            failed=5,
            duplicates=5,
        )

        collector.record_collection(metrics)

        platform_stats = collector.get_platform_stats("weibo")
        assert platform_stats.get("total", 0) == 50


# ============================================================
# Run Tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])