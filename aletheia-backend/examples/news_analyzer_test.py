# -*- coding: utf-8 -*-
"""
News Analyzer Test
新闻分析器测试
"""

import os
import sys
from dotenv import load_dotenv
from typing import List

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from services.crawler.multi_source_news_searcher import MultiSourceNewsSearcher
from services.analyzer.news_analyzer import NewsAnalyzer


def load_api_keys() -> dict:
    """加载API密钥"""
    # 加载.env文件
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ 从 {env_path} 加载环境变量")
    else:
        print(f"❌ 未找到 .env 文件: {env_path}")
    
    # 获取API密钥
    api_keys = {
        'tavily': os.getenv('TAVILY_API_KEY'),
        'baidu_qianfan': os.getenv('BAIDU_QIANFAN_ACCESS_KEY'),
        'serpapi': os.getenv('SERPAPI_KEY'),
        'silicon_flow': os.getenv('SILICONFLOW_API_KEY')
    }
    
    return api_keys


def check_api_keys(api_keys: dict) -> bool:
    """检查API密钥"""
    print("\n📋 检查 API Keys:")
    all_configured = True
    
    for key, value in api_keys.items():
        if value:
            print(f"  {key}: ✅ 已配置")
        else:
            print(f"  {key}: ❌ 未配置")
            all_configured = False
    
    return all_configured


async def main():
    """主函数"""
    print("=" * 80)
    print("新闻分析器 - 测试")
    print("=" * 80)
    
    # 加载API密钥
    api_keys = load_api_keys()
    
    # 检查API密钥
    if not check_api_keys(api_keys):
        print("\n❌ 错误: 请在 .env 文件中配置所有必要的 API Key")
        return
    
    # 初始化多源搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=api_keys['tavily'],
        baidu_qianfan_key=api_keys['baidu_qianfan'],
        serpapi_key=api_keys['serpapi']
    )
    
    # 初始化新闻分析器
    analyzer = NewsAnalyzer(
        silicon_flow_api_key=api_keys['silicon_flow']
    )
    
    # 搜索新闻
    query = "两会"
    print(f"\n🔍 搜索查询: {query}")
    print("-" * 80)
    
    # 执行搜索
    search_result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7
    )
    news_items = search_result['results']
    
    print(f"\n📊 原始搜索结果: {len(news_items)} 条")
    
    # 分析新闻
    print("\n🔬 开始分析新闻...")
    print("-" * 80)
    
    analyses = await analyzer.analyze_news(
        news_items=news_items,
        user_opinion="两会是中国重要的政治事件",
        top_n=5,  # 为了测试速度，只分析前5条
        relevance_threshold=0.3  # 相关度阈值
    )
    
    # 保存到JSON文件
    output_file = analyzer.save_to_json(analyses)
    print(f"\n💾 分析结果已保存到: {output_file}")
    
    # 输出分析结果
    print("\n📝 分析结果:")
    print("=" * 80)
    
    for i, analysis in enumerate(analyses, 1):
        print(f"\n\n📰 第 {i} 条新闻:")
        print(f"标题: {analysis.news_item.title}")
        print(f"URL: {analysis.news_item.url}")
        print(f"来源: {analysis.news_item.source}")
        print(f"发布时间: {analysis.news_item.publish_time}")
        print(f"相关度: {analysis.relevance_score:.2f}")
        print(f"可信度: {analysis.credibility_score:.2f}")
        print(f"\n分析结果:")
        print("-" * 80)
        print(analysis.analysis)
        print("-" * 80)
    
    print("\n" + "=" * 80)
    print("✅ 测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
