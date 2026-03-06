"""
End-to-End Tests for Evidence Pipeline.
证据管道端到端测试

Tests the complete flow:
1. Crawler data collection
2. Evidence pipeline processing
3. OpenSearch indexing
4. Evidence retrieval

Run with: pytest tests/integration/test_evidence_e2e.py -v
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

# ============================================================
# Test Configuration
# ============================================================

TEST_CONFIG = {
    "platforms": ["weibo", "zhihu"],
    "items_per_platform": 5,
    "max_total_items": 20,
    "min_evidence_score": 0.3,
}


# ============================================================
# Mock Crawler Manager
# ============================================================

class MockCrawlerManager:
    """Mock CrawlerManager for testing"""

    async def search_single_platform(
        self,
        platform: str,
        keyword: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Generate mock search results"""
        items = []
        for i in range(min(limit, 5)):
            items.append({
                "id": f"{platform}_{keyword}_{i}",
                "source_platform": platform,
                "original_url": f"https://{platform}.com/post/{i}",
                "content_text": f"这是关于{keyword}的第{i+1}条内容。这是一段测试文本，用于验证证据管道的处理能力。内容长度需要足够长才能通过最小长度检查。",
                "content_type": "TEXT",
                "title": f"关于{keyword}的讨论",
                "image_urls": [],
                "video_url": None,
                "metadata": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "author": f"用户{i}",
                    "likes": 100 + i * 10,
                    "comments": 10 + i,
                    "shares": 5 + i,
                },
                "entities": [],
                "created_at": datetime.utcnow().isoformat(),
            })
        return items

    async def search_across_platforms(
        self,
        keyword: str,
        platforms: List[str] = None,
        limit_per_platform: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Search across multiple platforms"""
        platforms = platforms or ["weibo", "zhihu", "bilibili"]
        results = {}
        for platform in platforms:
            results[platform] = await self.search_single_platform(
                platform=platform,
                keyword=keyword,
                limit=limit_per_platform,
            )
        return results


# ============================================================
# E2E Test Class
# ============================================================

class TestEvidencePipelineE2E:
    """End-to-end tests for evidence pipeline"""

    @pytest.fixture
    def crawler_manager(self):
        """Create mock crawler manager"""
        return MockCrawlerManager()

    @pytest.fixture
    def mock_opensearch(self):
        """Mock OpenSearch client"""
        mock = AsyncMock()
        mock.bulk_index_evidence = AsyncMock(return_value=(5, []))
        mock.search_evidence = AsyncMock(return_value={
            "total": 5,
            "hits": [],
            "took_ms": 10,
        })
        mock.get_evidence = AsyncMock(return_value=None)
        return mock

    @pytest.mark.asyncio
    async def test_collect_and_process(self, crawler_manager):
        """Test full collection and processing flow"""
        from services.evidence.crawler_integration import (
            CrawlerEvidenceBridge,
            CrawlerIntegrationConfig,
        )

        config = CrawlerIntegrationConfig(
            platforms=["weibo", "zhihu"],
            items_per_platform=5,
            max_total_items=20,
            index_to_opensearch=False,  # Disable for test
        )

        bridge = CrawlerEvidenceBridge(
            crawler_manager=crawler_manager,
            config=config,
        )

        result = await bridge.collect_and_process(
            query="人工智能",
            platforms=["weibo", "zhihu"],
        )

        # Verify results
        assert result.query == "人工智能"
        assert result.total_items > 0
        assert len(result.evidence_docs) > 0
        assert result.duration_ms > 0

        # Verify evidence documents
        for doc in result.evidence_docs:
            assert doc.doc_id is not None
            assert doc.content_text is not None
            assert len(doc.content_text) >= config.min_content_length
            assert doc.evidence_score >= 0

    @pytest.mark.asyncio
    async def test_url_normalization_in_pipeline(self, crawler_manager):
        """Test URL normalization during processing"""
        from services.evidence.crawler_integration import CrawlerEvidenceBridge

        bridge = CrawlerEvidenceBridge(crawler_manager=crawler_manager)
        result = await bridge.collect_and_process(
            query="测试查询",
            platforms=["weibo"],
        )

        for doc in result.evidence_docs:
            assert doc.url_hash != ""
            assert doc.original_url is not None

    @pytest.mark.asyncio
    async def test_evidence_scoring(self, crawler_manager):
        """Test evidence scoring in pipeline"""
        from services.evidence.crawler_integration import CrawlerEvidenceBridge

        bridge = CrawlerEvidenceBridge(crawler_manager=crawler_manager)
        result = await bridge.collect_and_process(
            query="虚假信息",
            platforms=["weibo", "zhihu"],
        )

        # Check that evidence scores are computed
        for doc in result.evidence_docs:
            assert 0.0 <= doc.evidence_score <= 1.0
            assert doc.source_tier is not None

    @pytest.mark.asyncio
    async def test_content_filtering(self, crawler_manager):
        """Test content filtering by length"""
        from services.evidence.crawler_integration import (
            CrawlerEvidenceBridge,
            CrawlerIntegrationConfig,
        )

        config = CrawlerIntegrationConfig(
            min_content_length=100,  # Higher threshold
            index_to_opensearch=False,
        )

        bridge = CrawlerEvidenceBridge(
            crawler_manager=crawler_manager,
            config=config,
        )

        result = await bridge.collect_and_process(
            query="测试",
            platforms=["weibo"],
        )

        # All returned docs should meet length requirement
        for doc in result.evidence_docs:
            assert len(doc.content_text) >= 100

    @pytest.mark.asyncio
    async def test_score_filtering(self, crawler_manager):
        """Test filtering by evidence score"""
        from services.evidence.crawler_integration import (
            CrawlerEvidenceBridge,
            CrawlerIntegrationConfig,
        )

        config = CrawlerIntegrationConfig(
            min_evidence_score=0.5,
            index_to_opensearch=False,
        )

        bridge = CrawlerEvidenceBridge(
            crawler_manager=crawler_manager,
            config=config,
        )

        result = await bridge.collect_and_process(
            query="新闻",
            platforms=["weibo", "zhihu"],
        )

        # All returned docs should meet score threshold
        for doc in result.evidence_docs:
            assert doc.evidence_score >= 0.5

    @pytest.mark.asyncio
    async def test_convenience_function(self, crawler_manager):
        """Test convenience function for evidence collection"""
        from services.evidence.crawler_integration import collect_evidence

        result = await collect_evidence(
            query="测试查询",
            crawler_manager=crawler_manager,
            platforms=["weibo"],
            max_items=10,
        )

        assert result is not None
        assert result.query == "测试查询"
        assert len(result.evidence_docs) <= 10

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in collection"""
        from services.evidence.crawler_integration import CrawlerEvidenceBridge

        # Create a failing mock
        failing_mock = AsyncMock()
        failing_mock.search_single_platform = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        bridge = CrawlerEvidenceBridge(crawler_manager=failing_mock)
        result = await bridge.collect_and_process(
            query="测试",
            platforms=["weibo"],
        )

        # Should handle errors gracefully
        assert result is not None
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_metrics_recording(self, crawler_manager):
        """Test that metrics are recorded"""
        from services.evidence.crawler_integration import CrawlerEvidenceBridge

        bridge = CrawlerEvidenceBridge(crawler_manager=crawler_manager)
        result = await bridge.collect_and_process(
            query="指标测试",
            platforms=["weibo"],
        )

        # Metrics should be recorded
        metrics = bridge.metrics.get_metrics()
        assert metrics["total_items"] > 0


# ============================================================
# Integration Test with Investigation Adapter
# ============================================================

class TestInvestigationAdapterE2E:
    """End-to-end tests for investigation adapter"""

    @pytest.fixture
    def crawler_manager(self):
        return MockCrawlerManager()

    @pytest.mark.asyncio
    async def test_evidence_adapter_integration(self, crawler_manager):
        """Test EvidenceAdapter integration"""
        from services.evidence.investigation_adapter import EvidenceAdapter

        adapter = EvidenceAdapter(crawler_manager=crawler_manager)

        cards = await adapter.collect_evidence_cards(
            claim="人工智能发展现状",
            platforms=["weibo", "zhihu"],
            max_items=10,
        )

        assert len(cards) > 0
        for card in cards:
            assert card.evidence_score >= 0
            assert card.source_platform is not None
            assert card.url is not None

    @pytest.mark.asyncio
    async def test_evidence_card_format(self, crawler_manager):
        """Test EvidenceCard format compatibility"""
        from services.evidence.investigation_adapter import EvidenceAdapter

        adapter = EvidenceAdapter(crawler_manager=crawler_manager)
        cards = await adapter.collect_evidence_cards(
            claim="测试声明",
            max_items=5,
        )

        for card in cards:
            card_dict = card.to_dict()
            assert "id" in card_dict
            assert "claim_ref" in card_dict
            assert "source_tier" in card_dict
            assert "evidence_score" in card_dict
            assert "extraction_method" in card_dict


# ============================================================
# OpenSearch Integration Tests (requires running OpenSearch)
# ============================================================

class TestOpenSearchIntegration:
    """Tests requiring OpenSearch instance"""

    @pytest.fixture
    def opensearch_available(self):
        """Check if OpenSearch is available"""
        import asyncio
        try:
            import httpx
            async def check():
                async with httpx.AsyncClient() as client:
                    resp = await client.get("http://localhost:9200", timeout=5)
                    return resp.status_code == 200
            return asyncio.run(check())
        except:
            return False

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,  # Skip by default, enable when OpenSearch is running
        reason="Requires running OpenSearch instance"
    )
    async def test_index_and_search(self, opensearch_available):
        """Test indexing and searching evidence"""
        from services.evidence.opensearch_client import get_opensearch_client
        from services.evidence import SearchQuery

        if not opensearch_available:
            pytest.skip("OpenSearch not available")

        client = await get_opensearch_client()

        # Index a test document
        test_doc = {
            "doc_id": "test_001",
            "title": "测试文档",
            "content_text": "这是一个测试文档的内容",
            "platform": "test",
            "evidence_score": 0.8,
        }

        success = await client.index_evidence(test_doc)
        assert success

        # Search for it
        query = SearchQuery(
            query_text="测试",
            query_fields=["title", "content_text"],
            size=10,
            from_=0,
        )

        result = await client.search_evidence(query)
        assert result["total"] >= 0


# ============================================================
# Performance Tests
# ============================================================

class TestPerformance:
    """Performance benchmarks"""

    @pytest.fixture
    def crawler_manager(self):
        return MockCrawlerManager()

    @pytest.mark.asyncio
    async def test_batch_processing_speed(self, crawler_manager):
        """Test batch processing speed"""
        import time

        from services.evidence.crawler_integration import CrawlerEvidenceBridge

        bridge = CrawlerEvidenceBridge(crawler_manager=crawler_manager)

        start = time.time()
        result = await bridge.collect_and_process(
            query="性能测试",
            platforms=["weibo", "zhihu", "bilibili"],
        )
        elapsed = time.time() - start

        # Should complete in reasonable time
        assert elapsed < 30  # 30 seconds max
        print(f"\nProcessed {result.total_items} items in {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_concurrent_platform_collection(self, crawler_manager):
        """Test concurrent platform collection"""
        from services.evidence.crawler_integration import collect_evidence

        import time
        start = time.time()

        # Collect from multiple platforms
        result = await collect_evidence(
            query="并发测试",
            crawler_manager=crawler_manager,
            platforms=["weibo", "zhihu", "bilibili", "douyin", "xiaohongshu"],
            max_items=50,
        )

        elapsed = time.time() - start

        assert result.total_items > 0
        print(f"\nCollected from {len(result.platforms)} platforms in {elapsed:.2f}s")


# ============================================================
# Run Tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])