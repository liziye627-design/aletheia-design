# -*- coding: utf-8 -*-
"""
Simple Test for Multi-Source News Searcher
多源新闻搜索器简单测试

直接测试多源搜索器功能，不启动服务器
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load .env file from project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ 从 {env_path} 加载环境变量")
else:
    print(f"❌ 未找到 .env 文件: {env_path}")


# Import only what we need
from services.crawler.multi_source_news_searcher import MultiSourceNewsSearcher


async def simple_test():
    """简单测试"""
    
    print("=" * 80)
    print("多源新闻搜索器 - 简单测试")
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
    
    # 执行搜索
    query = "两会"
    print(f"\n🔍 搜索查询: {query}")
    print("-" * 80)
    
    result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7,
        merge_strategy="keep_best",
    )
    
    # 显示结果
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
    
    print("\n" + "=" * 80)
    print("✅ 测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(simple_test())
