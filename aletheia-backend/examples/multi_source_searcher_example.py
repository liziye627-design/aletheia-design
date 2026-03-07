# -*- coding: utf-8 -*-
"""
Quick Start Example for Multi-Source News Searcher
多源新闻搜索器快速启动示例
"""

import asyncio
import os
import sys
from datetime import datetime
from loguru import logger

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.crawler.multi_source_news_searcher import MultiSourceNewsSearcher
from services.crawler.multi_source_evidence_collector import (
    MultiSourceEvidenceCollector,
    MultiSourceEvidenceConfig,
)


async def quick_start_example():
    """快速启动示例"""
    
    print("=" * 80)
    print("多源新闻搜索器 - 快速启动示例")
    print("=" * 80)
    
    # 检查 API Keys
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    print("\n📋 检查 API Keys:")
    print(f"  Tavily: {'✅ 已配置' if tavily_key else '❌ 未配置'}")
    print(f"  百度千帆: {'✅ 已配置' if baidu_key else '❌ 未配置'}")
    print(f"  SerpAPI: {'✅ 已配置' if serpapi_key else '❌ 未配置'}")
    
    if not any([tavily_key, baidu_key, serpapi_key]):
        print("\n❌ 错误: 请在 .env 文件中配置至少一个 API Key")
        return
    
    # 初始化搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    # 示例 1: 简单搜索
    print("\n" + "=" * 80)
    print("示例 1: 简单搜索")
    print("=" * 80)
    
    query = "两会"
    print(f"\n🔍 搜索查询: {query}")
    print("-" * 80)
    
    result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7,
        merge_strategy="keep_best",
    )
    
    stats = result["stats"]
    print(f"\n📊 搜索统计:")
    print(f"  原始结果数: {stats['total_raw_results']}")
    print(f"  去重后结果数: {stats['unique_results']}")
    print(f"  去重率: {stats['deduplication_rate']:.2%}")
    print(f"  可信来源数: {stats['trusted_count']}")
    
    print(f"\n📰 各源统计:")
    for source, source_stat in stats["source_stats"].items():
        count = source_stat.get("count", 0)
        error = source_stat.get("error", "")
        if error:
            print(f"  {source}: ❌ {error}")
        else:
            print(f"  {source}: ✅ {count} 条")
    
    print(f"\n📝 前 5 条结果:")
    for i, item in enumerate(result["results"][:5]):
        trusted = "✅" if item.is_trusted else "❌"
        print(f"\n  {i+1}. [{trusted}] [{item.search_source.value}] {item.title[:60]}...")
        print(f"     来源: {item.source or item.source_domain}")
        print(f"     URL: {item.url[:70]}...")
        if item.publish_time:
            print(f"     发布时间: {item.publish_time.strftime('%Y-%m-%d %H:%M')}")
    
    # 示例 2: 证据收集
    print("\n\n" + "=" * 80)
    print("示例 2: 证据收集")
    print("=" * 80)
    
    config = MultiSourceEvidenceConfig(
        max_results_per_source=15,
        search_days=7,
        merge_strategy="keep_best",
    )
    
    collector = MultiSourceEvidenceCollector(
        multi_source_searcher=searcher,
        config=config,
    )
    
    query = "中国维和部队"
    print(f"\n🔍 搜索查询: {query}")
    print("-" * 80)
    
    result = await collector.collect_evidence(query)
    
    search_stats = result["search_stats"]
    print(f"\n📊 搜索统计:")
    print(f"  原始结果: {search_stats['total_raw_results']} -> {search_stats['unique_results']} "
          f"({search_stats['deduplication_rate']:.2%} 去重)")
    
    evidence_result = result["evidence_result"]
    print(f"\n📋 证据统计:")
    print(f"  证据池: {evidence_result['evidence_count']} 条")
    print(f"  上下文池: {evidence_result['context_count']} 条")
    
    quality = evidence_result["quality_metrics"]
    print(f"\n📈 质量指标:")
    print(f"  关键词命中率: {quality['keyword_hit_rate']:.2%}")
    print(f"  实体命中率: {quality['entity_hit_rate']:.2%}")
    print(f"  可信来源命中率: {quality['trusted_hit_rate']:.2%}")
    
    if evidence_result["evidence_pool"]:
        print(f"\n📝 前 3 条证据:")
        for i, evidence in enumerate(evidence_result["evidence_pool"][:3]):
            trusted = "✅" if evidence.get("is_trusted") else "❌"
            print(f"\n  {i+1}. [{trusted}] {evidence['title'][:50]}...")
            print(f"     来源: {evidence['source']}")
            print(f"     关键词命中: {', '.join(evidence.get('keyword_hits', []))}")
    
    # 示例 3: 批量搜索
    print("\n\n" + "=" * 80)
    print("示例 3: 批量搜索")
    print("=" * 80)
    
    queries = ["人工智能", "气候变化", "太空探索"]
    print(f"\n🔍 批量搜索: {', '.join(queries)}")
    print("-" * 80)
    
    results = await collector.batch_collect(queries)
    
    print(f"\n📊 批量搜索结果:")
    for query, result in results.items():
        if "error" in result:
            print(f"\n  {query}: ❌ {result['error']}")
            continue
        
        search_stats = result["search_stats"]
        evidence_count = result["evidence_result"]["evidence_count"]
        
        print(f"\n  {query}:")
        print(f"    搜索结果: {search_stats['unique_results']} 条")
        print(f"    证据数: {evidence_count} 条")
    
    # 生成汇总报告
    report = collector.generate_report(results)
    
    print(f"\n\n📋 汇总报告:")
    print("-" * 80)
    print(f"总查询数: {report['summary']['total_queries']}")
    print(f"有证据的查询: {report['summary']['queries_with_evidence']}")
    print(f"证据率: {report['summary']['evidence_rate']:.2%}")
    print(f"总原始结果: {report['search_stats']['total_raw_results']}")
    print(f"总去重后结果: {report['search_stats']['total_unique_results']}")
    print(f"平均去重率: {report['search_stats']['deduplication_rate']:.2%}")
    print(f"总证据数: {report['evidence_stats']['total_evidence_items']}")
    print(f"平均每查询证据数: {report['evidence_stats']['avg_evidence_per_query']:.1f}")
    
    print(f"\n📊 来源统计:")
    for source, stats in report["source_stats"].items():
        print(f"  {source}: {stats['count']} 条")
    
    print(f"\n🌐 热门域名 (Top 10):")
    for domain, count in report["top_domains"][:10]:
        print(f"  {domain}: {count} 次")
    
    print("\n" + "=" * 80)
    print("✅ 快速启动示例完成!")
    print("=" * 80)
    print(f"\n💡 提示:")
    print("  - 查看 docs/MULTI_SOURCE_SEARCHER_GUIDE.md 了解更多用法")
    print("  - 运行 tests/integration/test_multi_source_searcher.py 进行完整测试")
    print("  - 调整 .env 文件中的配置以优化搜索结果")
    print()


if __name__ == "__main__":
    asyncio.run(quick_start_example())
