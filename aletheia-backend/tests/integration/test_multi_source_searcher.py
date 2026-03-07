# -*- coding: utf-8 -*-
"""
Test Multi-Source News Searcher
测试多源新闻搜索器

验证多源搜索和去重功能
"""

import asyncio
import os
import sys
from datetime import datetime
from loguru import logger

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from services.crawler.multi_source_news_searcher import (
    MultiSourceNewsSearcher,
    SearchSource,
)
from services.crawler.multi_source_evidence_collector import (
    MultiSourceEvidenceCollector,
    MultiSourceEvidenceConfig,
)


async def test_multi_source_search():
    """测试多源搜索"""
    print("=" * 70)
    print("测试 1: 多源新闻搜索")
    print("=" * 70)
    
    # 从环境变量读取 API Keys
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    print(f"\n可用的搜索源:")
    print(f"  Tavily: {'✓' if tavily_key else '✗'}")
    print(f"  百度千帆: {'✓' if baidu_key else '✗'}")
    print(f"  SerpAPI: {'✓' if serpapi_key else '✗'}")
    
    # 初始化搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    # 测试搜索
    query = "两会"
    print(f"\n搜索查询: {query}")
    print("-" * 70)
    
    result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7,
        merge_strategy="keep_best",
    )
    
    stats = result["stats"]
    print(f"\n搜索统计:")
    print(f"  原始结果数: {stats['total_raw_results']}")
    print(f"  去重后结果数: {stats['unique_results']}")
    print(f"  去重率: {stats['deduplication_rate']:.2%}")
    print(f"  可信来源数: {stats['trusted_count']}")
    
    print(f"\n各源统计:")
    for source, source_stat in stats["source_stats"].items():
        print(f"  {source}: {source_stat['count']} 条")
        if "error" in source_stat:
            print(f"    错误: {source_stat['error']}")
    
    print(f"\n前 10 条结果:")
    for i, item in enumerate(result["results"][:10]):
        trusted = "✓" if item.is_trusted else "✗"
        sources = ", ".join([s.value for s in item.merged_sources] + [item.search_source.value])
        print(f"\n  {i+1}. [{trusted}] [{item.search_source.value}] {item.title[:60]}...")
        print(f"     来源: {item.source or item.source_domain}")
        print(f"     URL: {item.url[:70]}...")
        print(f"     搜索源: {sources}")
        if item.publish_time:
            print(f"     发布时间: {item.publish_time.strftime('%Y-%m-%d %H:%M')}")
        if item.content:
            print(f"     内容长度: {len(item.content)} 字符")


async def test_deduplication():
    """测试去重功能"""
    print("\n\n" + "=" * 70)
    print("测试 2: 去重功能")
    print("=" * 70)
    
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    if not tavily_key:
        print("\n跳过去重测试（需要 TAVILY_API_KEY）")
        return
    
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
    )
    
    # 测试不同合并策略
    query = "人工智能"
    strategies = ["keep_best", "merge_all", "keep_first"]
    
    for strategy in strategies:
        print(f"\n合并策略: {strategy}")
        print("-" * 70)
        
        result = await searcher.search_all(
            query=query,
            max_results_per_source=20,
            days=7,
            merge_strategy=strategy,
        )
        
        stats = result["stats"]
        print(f"  原始结果: {stats['total_raw_results']}")
        print(f"  去重后: {stats['unique_results']}")
        print(f"  去重率: {stats['deduplication_rate']:.2%}")
        
        # 统计合并的来源
        merged_count = sum(1 for item in result["results"] if item.merged_sources)
        print(f"  合并了多个来源的新闻: {merged_count} 条")
        
        # 显示一个合并的例子
        for item in result["results"]:
            if item.merged_sources:
                print(f"\n  合并示例:")
                print(f"    标题: {item.title[:50]}...")
                print(f"    主要来源: {item.search_source.value}")
                print(f"    合并的来源: {', '.join([s.value for s in item.merged_sources])}")
                break


async def test_evidence_collection():
    """测试证据收集"""
    print("\n\n" + "=" * 70)
    print("测试 3: 多源证据收集")
    print("=" * 70)
    
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    if not any([tavily_key, baidu_key, serpapi_key]):
        print("\n跳过证据收集测试（需要至少一个 API Key）")
        return
    
    # 初始化搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    # 初始化证据收集器
    config = MultiSourceEvidenceConfig(
        max_results_per_source=15,
        search_days=7,
        merge_strategy="keep_best",
        min_evidence_count=3,
        min_keyword_hit_rate=0.7,
        min_trusted_hit_rate=0.6,
    )
    
    collector = MultiSourceEvidenceCollector(
        multi_source_searcher=searcher,
        config=config,
    )
    
    # 测试查询
    test_queries = [
        "两会",
        "中国维和部队",
    ]
    
    print(f"\n测试查询: {', '.join(test_queries)}")
    print("-" * 70)
    
    results = await collector.batch_collect(test_queries)
    
    for query, result in results.items():
        if "error" in result:
            print(f"\n查询: {query}")
            print(f"  错误: {result['error']}")
            continue
        
        print(f"\n查询: {query}")
        
        search_stats = result["search_stats"]
        print(f"  搜索结果: {search_stats['total_raw_results']} -> {search_stats['unique_results']} "
              f"({search_stats['deduplication_rate']:.2%} 去重)")
        
        evidence_result = result["evidence_result"]
        print(f"  证据池: {evidence_result['evidence_count']} 条")
        print(f"  上下文池: {evidence_result['context_count']} 条")
        
        quality = evidence_result["quality_metrics"]
        print(f"  质量指标:")
        print(f"    关键词命中率: {quality['keyword_hit_rate']:.2%}")
        print(f"    实体命中率: {quality['entity_hit_rate']:.2%}")
        print(f"    可信来源命中率: {quality['trusted_hit_rate']:.2%}")
        
        # 显示前 3 条证据
        if evidence_result["evidence_pool"]:
            print(f"\n  前 3 条证据:")
            for i, evidence in enumerate(evidence_result["evidence_pool"][:3]):
                trusted = "✓" if evidence.get("is_trusted") else "✗"
                print(f"    {i+1}. [{trusted}] {evidence['title'][:50]}...")
                print(f"       来源: {evidence['source']}")
    
    # 生成报告
    report = collector.generate_report(results)
    
    print(f"\n\n汇总报告:")
    print("-" * 70)
    print(f"总查询数: {report['summary']['total_queries']}")
    print(f"有证据的查询: {report['summary']['queries_with_evidence']}")
    print(f"证据率: {report['summary']['evidence_rate']:.2%}")
    print(f"总原始结果: {report['search_stats']['total_raw_results']}")
    print(f"总去重后结果: {report['search_stats']['total_unique_results']}")
    print(f"平均去重率: {report['search_stats']['deduplication_rate']:.2%}")
    print(f"总证据数: {report['evidence_stats']['total_evidence_items']}")
    print(f"平均每查询证据数: {report['evidence_stats']['avg_evidence_per_query']:.1f}")


async def test_source_priority():
    """测试来源优先级"""
    print("\n\n" + "=" * 70)
    print("测试 4: 来源优先级")
    print("=" * 70)
    
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    if not any([tavily_key, baidu_key, serpapi_key]):
        print("\n跳过来源优先级测试（需要至少一个 API Key）")
        return
    
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    query = "科技新闻"
    print(f"\n查询: {query}")
    print("-" * 70)
    
    result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7,
        merge_strategy="keep_best",
    )
    
    # 按来源分组统计
    source_groups = {}
    for item in result["results"]:
        source = item.search_source.value
        if source not in source_groups:
            source_groups[source] = []
        source_groups[source].append(item)
    
    print(f"\n各源结果数:")
    for source, items in source_groups.items():
        trusted_count = sum(1 for item in items if item.is_trusted)
        print(f"  {source}: {len(items)} 条 (可信: {trusted_count})")
    
    print(f"\n按优先级排序的前 10 条:")
    for i, item in enumerate(result["results"][:10]):
        trusted = "✓" if item.is_trusted else "✗"
        priority = searcher.SOURCE_PRIORITY.get(item.search_source, 99)
        print(f"  {i+1}. [{trusted}] [优先级:{priority}] [{item.search_source.value}] {item.title[:50]}...")


async def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("多源新闻搜索器测试套件")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    try:
        # 测试 1: 多源搜索
        await test_multi_source_search()
        
        # 测试 2: 去重功能
        await test_deduplication()
        
        # 测试 3: 证据收集
        await test_evidence_collection()
        
        # 测试 4: 来源优先级
        await test_source_priority()
        
        print("\n\n" + "=" * 70)
        print("所有测试完成")
        print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
