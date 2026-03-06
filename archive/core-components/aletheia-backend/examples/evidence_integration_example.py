#!/usr/bin/env python3
"""
Evidence Library Integration Example.
证据库集成示例

This script demonstrates how to integrate the Evidence Library
with the existing CrawlerManager and InvestigationEngine.

Usage:
    python examples/evidence_integration_example.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def example_basic_pipeline():
    """Example 1: Basic pipeline usage with crawler output"""
    from services.evidence import EvidencePipeline, PipelineConfig

    print("=" * 60)
    print("Example 1: Basic Evidence Pipeline")
    print("=" * 60)

    # Simulated crawler output (standardized format)
    crawler_results = [
        {
            "id": "weibo_123",
            "source_platform": "weibo",
            "original_url": "https://weibo.com/123456",
            "content_text": "这是一条关于人工智能发展的微博内容...",
            "content_type": "TEXT",
            "image_urls": [],
            "video_url": None,
            "metadata": {
                "timestamp": "2024-01-15T10:30:00Z",
                "author_id": "user_abc",
                "author_name": "科技观察者",
                "author_follower_count": 50000,
                "likes": 1200,
                "comments": 89,
                "shares": 45,
                "engagement_rate": 0.0267,
            },
            "entities": ["人工智能", "科技"],
            "created_at": "2024-01-15T10:30:00Z",
        },
        {
            "id": "zhihu_456",
            "source_platform": "zhihu",
            "original_url": "https://zhuanlan.zhihu.com/p/789012",
            "content_text": "人工智能在2024年的发展趋势分析...",
            "content_type": "TEXT",
            "image_urls": ["https://pic.zhimg.com/1.jpg"],
            "video_url": None,
            "metadata": {
                "timestamp": "2024-01-15T09:00:00Z",
                "author_id": "expert_xyz",
                "author_name": "AI研究员",
                "author_follower_count": 120000,
                "likes": 3500,
                "comments": 156,
                "shares": 230,
                "hot_rank": 15,
            },
            "entities": ["人工智能", "机器学习", "深度学习"],
            "created_at": "2024-01-15T09:00:00Z",
        },
    ]

    # Configure pipeline (without detail fetching for this example)
    config = PipelineConfig(
        fetch_detail_pages=False,  # Skip detail fetching for demo
        enable_deduplication=True,
        enable_scoring=True,
        enable_versioning=True,
    )

    pipeline = EvidencePipeline(config=config)

    # Process crawler results
    result = await pipeline.process_batch(
        crawler_items=crawler_results,
        query="人工智能发展趋势",
    )

    print(f"\nProcessing Results:")
    print(f"  Total Items: {result.total_items}")
    print(f"  Successful: {result.successful}")
    print(f"  Duplicates: {result.duplicates}")
    print(f"  Failed: {result.failed}")
    print(f"  Total Time: {result.total_time_ms}ms")

    # Show individual results
    for i, item_result in enumerate(result.results):
        if item_result.search_hit:
            hit = item_result.search_hit
            print(f"\n  Hit {i+1}:")
            print(f"    ID: {hit.hit_id}")
            print(f"    Platform: {hit.platform}")
            print(f"    Title: {hit.hit_title[:50]}...")
            print(f"    Status: {hit.fetch_status}")


async def example_evidence_scoring():
    """Example 2: Evidence credibility scoring"""
    from services.evidence import EvidenceScorer, ScoringContext, PenaltyFlags, SourceTier

    print("\n" + "=" * 60)
    print("Example 2: Evidence Credibility Scoring")
    print("=" * 60)

    scorer = EvidenceScorer()

    # Example 1: High-credibility official source
    context1 = ScoringContext(
        source_tier=SourceTier.S,
        source_domain="news.cn",
        platform="xinhua",
        extraction_confidence=0.95,
        unique_domains_count=3,
    )
    result1 = scorer.score(context1)

    print(f"\nOfficial Source (Xinhua):")
    print(f"  Evidence Score: {result1.evidence_score:.4f}")
    print(f"  Credibility Level: {result1.credibility_level}")
    print(f"  Components: {result1.components}")

    # Example 2: Social media source with penalties
    context2 = ScoringContext(
        source_tier=SourceTier.C,
        source_domain="weibo.com",
        platform="weibo",
        extraction_confidence=0.65,
        unique_domains_count=1,
        penalties=PenaltyFlags(
            is_deleted=False,
            has_correction=False,
        ),
    )
    result2 = scorer.score(context2)

    print(f"\nSocial Media Source (Weibo):")
    print(f"  Evidence Score: {result2.evidence_score:.4f}")
    print(f"  Credibility Level: {result2.credibility_level}")
    print(f"  Components: {result2.components}")

    # Example 3: Deleted content
    context3 = ScoringContext(
        source_tier=SourceTier.B,
        source_domain="thepaper.cn",
        platform="thepaper",
        extraction_confidence=0.80,
        penalties=PenaltyFlags(
            is_deleted=True,
            has_correction=False,
        ),
    )
    result3 = scorer.score(context3)

    print(f"\nDeleted Content (The Paper):")
    print(f"  Evidence Score: {result3.evidence_score:.4f}")
    print(f"  Credibility Level: {result3.credibility_level}")
    print(f"  Penalty Flags: {result3.penalty_flags}")


async def example_url_normalization():
    """Example 3: URL normalization and deduplication"""
    from services.evidence import URLNormalizer, compute_content_hash

    print("\n" + "=" * 60)
    print("Example 3: URL Normalization and Deduplication")
    print("=" * 60)

    normalizer = URLNormalizer()

    # Test URLs with tracking parameters
    test_urls = [
        "https://weibo.com/123456?utm_source=twitter&from=singlemessage",
        "https://weibo.com/123456?spm=123&share_token=abc",
        "https://news.cn/article/2024-01-15/123456.htm?from=timeline",
        "https://NEWS.CN/article/2024-01-15/123456.htm",  # Case variation
    ]

    print("\nURL Normalization Results:")
    for url in test_urls:
        result = normalizer.normalize(url)
        print(f"\n  Original: {url}")
        print(f"  Normalized: {result.normalized_url}")
        print(f"  URL Hash: {result.url_hash[:16]}...")
        print(f"  Removed Params: {result.removed_params}")

    # Content hash example
    content1 = "这是一段测试内容，用于演示内容哈希功能。"
    content2 = "这是一段测试内容，用于演示内容哈希功能。"  # Same
    content3 = "这是一段不同的内容。"

    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    hash3 = compute_content_hash(content3)

    print(f"\nContent Hash Results:")
    print(f"  Content 1 Hash: {hash1[:16]}...")
    print(f"  Content 2 Hash: {hash2[:16]}...")
    print(f"  Content 3 Hash: {hash3[:16]}...")
    print(f"  Content 1 == Content 2: {hash1 == hash2}")
    print(f"  Content 1 == Content 3: {hash1 == hash3}")


async def example_opensearch_dsl():
    """Example 4: OpenSearch DSL query building"""
    from services.evidence import OpenSearchQueryBuilder, SearchQuery

    print("\n" + "=" * 60)
    print("Example 4: OpenSearch DSL Query Building")
    print("=" * 60)

    builder = OpenSearchQueryBuilder()

    # Build a search query
    params = SearchQuery(
        query_text="人工智能 发展趋势",
        platforms=["weibo", "zhihu"],
        source_tiers=["S", "A"],
        publish_time_start="2024-01-01",
        publish_time_end="2024-12-31",
        min_evidence_score=0.5,
        exclude_deleted=True,
        size=20,
        sort_by="evidence_score",
        sort_order="desc",
        highlight=True,
    )

    dsl = builder.build_search_query(params)

    print("\nGenerated OpenSearch DSL:")
    import json
    print(json.dumps(dsl, indent=2, ensure_ascii=False))


async def example_version_management():
    """Example 5: Evidence version management"""
    from services.evidence import VersionManager, detect_updates

    print("\n" + "=" * 60)
    print("Example 5: Version Management")
    print("=" * 60)

    manager = VersionManager()

    # Create initial version
    v1 = manager.create_version(
        doc_id="doc_example_001",
        title="人工智能发展趋势报告",
        content_text="这是一篇关于人工智能发展趋势的分析文章...",
        url_hash="abc123",
        content_hash="def456",
    )

    print(f"\nVersion 1 Created:")
    print(f"  Version ID: {v1.version_id}")
    print(f"  Change Type: {v1.change_type.value}")

    # Create updated version
    v2 = manager.create_version(
        doc_id="doc_example_001",
        title="人工智能发展趋势报告（更新版）",
        content_text="这是一篇关于人工智能发展趋势的分析文章...（已更新）",
        url_hash="abc123",
        content_hash="ghi789",
    )

    print(f"\nVersion 2 Created:")
    print(f"  Version ID: {v2.version_id}")
    print(f"  Change Type: {v2.change_type.value}")
    if v2.diff:
        print(f"  Title Changed: {v2.diff.title_changed}")
        print(f"  Content Similarity: {v2.diff.content_similarity:.2%}")
        print(f"  Detected Changes: {v2.diff.detected_changes}")

    # Get version chain
    chain = manager.get_version_chain("doc_example_001")
    print(f"\nVersion Chain:")
    for v in chain:
        print(f"  {v['version_id']}: {v['change_type']}")

    # Detect update signals
    correction_text = "更正声明：此前报道有误，现更正如下..."
    signals = detect_updates(correction_text)
    print(f"\nCorrection Signal Detection:")
    print(f"  Has Correction Notice: {signals['has_correction_notice']}")
    print(f"  Has Retraction Notice: {signals['has_retraction_notice']}")


async def example_integration():
    """Example 6: Full integration with crawler manager"""
    from services.evidence import (
        EvidenceCollectionOrchestrator,
        EvidenceCollectionConfig,
    )

    print("\n" + "=" * 60)
    print("Example 6: Full Integration (Mock)")
    print("=" * 60)

    # Configure collection
    config = EvidenceCollectionConfig(
        platforms=["weibo", "zhihu"],
        max_items_per_platform=10,
        max_total_items=50,
        min_evidence_score=0.3,
        fetch_detail_pages=False,  # Skip for demo
    )

    # Create orchestrator (without crawler_manager for demo)
    orchestrator = EvidenceCollectionOrchestrator(
        config=config,
        crawler_manager=None,  # Would use get_crawler_manager() in production
    )

    # Collect evidence (mock since no crawler_manager)
    result = await orchestrator.collect_evidence(
        query="人工智能发展趋势",
        discovery_mode="search",
    )

    print(f"\nCollection Results:")
    print(f"  Query: {result.query}")
    print(f"  Total Discovered: {result.total_discovered}")
    print(f"  Total Evidence: {result.total_evidence}")
    print(f"  Duplicates Found: {result.duplicates_found}")
    print(f"  Collection Time: {result.collection_time_ms}ms")
    print(f"  By Platform: {result.by_platform}")
    print(f"  By Tier: {result.by_tier}")

    if result.errors:
        print(f"\n  Errors: {result.errors}")


async def main():
    """Run all examples"""
    print("\n" + "#" * 60)
    print("# Evidence Library Integration Examples")
    print("#" * 60)

    await example_basic_pipeline()
    await example_evidence_scoring()
    await example_url_normalization()
    await example_opensearch_dsl()
    await example_version_management()
    await example_integration()

    print("\n" + "#" * 60)
    print("# All examples completed!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(main())