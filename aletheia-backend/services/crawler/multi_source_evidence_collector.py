# -*- coding: utf-8 -*-
"""
Multi-Source Evidence Collector
多源证据收集器

集成多源新闻搜索器到证据收集流程中
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from services.crawler.multi_source_news_searcher import (
    MultiSourceNewsSearcher,
    NewsItem,
    SearchSource,
)
from services.crawler.evidence_pool_manager import (
    EvidencePoolManager,
    EvidenceResult,
    NewsArticle,
)
from services.evidence.evidence_pipeline import EvidencePipeline
from models.evidence import SearchHit, EvidenceDoc


@dataclass
class MultiSourceEvidenceConfig:
    """多源证据收集配置"""
    # 搜索配置
    max_results_per_source: int = 20
    search_days: int = 7
    merge_strategy: str = "keep_best"  # keep_best, merge_all, keep_first
    
    # 质量阈值
    min_evidence_count: int = 3
    min_keyword_hit_rate: float = 0.7
    min_trusted_hit_rate: float = 0.6
    
    # 启用的搜索源
    enabled_sources: List[str] = field(default_factory=lambda: [
        "tavily",
        "baidu_qianfan",
        "serpapi",
    ])


class MultiSourceEvidenceCollector:
    """
    多源证据收集器
    
    整合多源搜索和证据收集流程
    """
    
    def __init__(
        self,
        multi_source_searcher: MultiSourceNewsSearcher,
        evidence_pool_manager: Optional[EvidencePoolManager] = None,
        evidence_pipeline: Optional[EvidencePipeline] = None,
        config: Optional[MultiSourceEvidenceConfig] = None,
    ):
        self.searcher = multi_source_searcher
        self.evidence_pool = evidence_pool_manager or EvidencePoolManager()
        self.pipeline = evidence_pipeline
        self.config = config or MultiSourceEvidenceConfig()
        
        logger.info("MultiSourceEvidenceCollector initialized")
    
    async def collect_evidence(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        收集证据
        
        Args:
            query: 查询文本
            platforms: 指定平台列表（可选）
        
        Returns:
            包含证据和统计信息的字典
        """
        logger.info(f"Starting multi-source evidence collection for query: {query}")
        
        # 步骤1: 多源搜索
        search_result = await self._search_all_sources(query)
        
        # 步骤2: 转换为 NewsArticle 格式
        articles = self._convert_to_articles(search_result["results"])
        
        # 步骤3: 使用 EvidencePoolManager 分析
        evidence_result = await self._analyze_with_evidence_pool(
            query,
            articles,
            platforms,
        )
        
        # 步骤4: 如果有 pipeline，创建证据文档
        evidence_docs = []
        if self.pipeline:
            evidence_docs = await self._create_evidence_docs(
                search_result["results"],
                query,
            )
        
        # 汇总结果
        result = {
            "query": query,
            "search_stats": search_result["stats"],
            "evidence_result": evidence_result.to_dict(),
            "evidence_docs": [doc.to_dict() for doc in evidence_docs[:10]],
            "timestamp": datetime.now().isoformat(),
        }
        
        logger.info(
            f"Evidence collection completed: "
            f"{len(search_result['results'])} raw -> "
            f"{len(articles)} articles -> "
            f"{len(evidence_result.evidence_pool)} evidence items"
        )
        
        return result
    
    async def _search_all_sources(self, query: str) -> Dict[str, Any]:
        """从所有源搜索"""
        return await self.searcher.search_all(
            query=query,
            max_results_per_source=self.config.max_results_per_source,
            days=self.config.search_days,
            merge_strategy=self.config.merge_strategy,
        )
    
    def _convert_to_articles(self, news_items: List[NewsItem]) -> List[NewsArticle]:
        """将 NewsItem 转换为 NewsArticle"""
        articles = []
        
        for item in news_items:
            article = NewsArticle(
                title=item.title,
                url=item.url,
                content=item.content,
                source=item.source or item.source_domain,
                publish_time=item.publish_time,
                is_trusted=item.is_trusted,
            )
            
            # 添加来源标记
            article.search_source = item.search_source.value
            article.merged_sources = [s.value for s in item.merged_sources]
            
            articles.append(article)
        
        return articles
    
    async def _analyze_with_evidence_pool(
        self,
        query: str,
        articles: List[NewsArticle],
        platforms: Optional[List[str]],
    ) -> EvidenceResult:
        """使用 EvidencePoolManager 分析"""
        # 提取关键词和实体
        keywords = self.evidence_pool.extract_keywords(query)
        entities = self.evidence_pool.extract_entities(query)
        
        # 分析每篇文章
        evidence_pool = []
        context_pool = []
        
        for article in articles:
            # 检查命中
            keyword_hit, keyword_hits = self.evidence_pool.check_keyword_hit(article, keywords)
            entity_hit, entity_hits = self.evidence_pool.check_entity_hit(article, entities)
            
            article.keyword_hits = keyword_hits
            article.entity_hits = entity_hits
            
            # 判断进入哪个池
            if article.is_trusted and (keyword_hit or entity_hit):
                evidence_pool.append(article)
            elif keyword_hit or entity_hit:
                context_pool.append(article)
        
        # 计算质量指标
        metrics = self.evidence_pool._calculate_metrics(evidence_pool, keywords, entities)
        
        result = EvidenceResult(
            query=query,
            evidence_pool=evidence_pool,
            context_pool=context_pool,
            quality_metrics=metrics,
        )
        
        return result
    
    async def _create_evidence_docs(
        self,
        news_items: List[NewsItem],
        query: str,
    ) -> List[EvidenceDoc]:
        """创建证据文档"""
        if not self.pipeline:
            return []
        
        # 转换为 SearchHit 格式
        search_hits = []
        for item in news_items:
            hit = SearchHit(
                url=item.url,
                title=item.title,
                snippet=item.snippet or item.content[:500],
                source=item.source or item.source_domain,
                source_domain=item.source_domain,
                publish_time=item.publish_time,
                discovery_mode="multi_source_search",
                query=query,
            )
            search_hits.append(hit)
        
        # 使用 pipeline 处理
        try:
            pipeline_result = await self.pipeline.process_batch(
                crawler_items=[hit.to_dict() for hit in search_hits],
                query=query,
            )
            
            return pipeline_result.evidence_docs
        except Exception as e:
            logger.error(f"Failed to create evidence docs: {e}")
            return []
    
    async def batch_collect(
        self,
        queries: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """批量收集证据"""
        results = {}
        
        for query in queries:
            try:
                result = await self.collect_evidence(query)
                results[query] = result
            except Exception as e:
                logger.error(f"Failed to collect evidence for '{query}': {e}")
                results[query] = {"error": str(e)}
        
        return results
    
    def generate_report(
        self,
        results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成报告"""
        total_queries = len(results)
        queries_with_evidence = 0
        total_raw_results = 0
        total_unique_results = 0
        total_evidence_items = 0
        
        source_stats = {}
        domain_stats = {}
        
        for query, result in results.items():
            if "error" in result:
                continue
            
            queries_with_evidence += 1
            
            search_stats = result.get("search_stats", {})
            evidence_result = result.get("evidence_result", {})
            
            total_raw_results += search_stats.get("total_raw_results", 0)
            total_unique_results += search_stats.get("unique_results", 0)
            total_evidence_items += evidence_result.get("evidence_count", 0)
            
            # 统计来源
            for source, stats in search_stats.get("source_stats", {}).items():
                if source not in source_stats:
                    source_stats[source] = {"count": 0, "errors": 0}
                source_stats[source]["count"] += stats.get("count", 0)
                if "error" in stats:
                    source_stats[source]["errors"] += 1
            
            # 统计域名
            for domain in search_stats.get("domains", []):
                domain_stats[domain] = domain_stats.get(domain, 0) + 1
        
        # 计算平均质量指标
        avg_keyword_hit_rate = 0.0
        avg_trusted_hit_rate = 0.0
        
        quality_results = [
            r.get("evidence_result", {}).get("quality_metrics", {})
            for r in results.values()
            if "error" not in r
        ]
        
        if quality_results:
            avg_keyword_hit_rate = sum(
                q.get("keyword_hit_rate", 0) for q in quality_results
            ) / len(quality_results)
            avg_trusted_hit_rate = sum(
                q.get("trusted_hit_rate", 0) for q in quality_results
            ) / len(quality_results)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_queries": total_queries,
                "queries_with_evidence": queries_with_evidence,
                "evidence_rate": queries_with_evidence / total_queries if total_queries > 0 else 0,
            },
            "search_stats": {
                "total_raw_results": total_raw_results,
                "total_unique_results": total_unique_results,
                "deduplication_rate": 1.0 - (total_unique_results / total_raw_results) if total_raw_results > 0 else 0,
            },
            "evidence_stats": {
                "total_evidence_items": total_evidence_items,
                "avg_evidence_per_query": total_evidence_items / queries_with_evidence if queries_with_evidence > 0 else 0,
            },
            "quality_stats": {
                "avg_keyword_hit_rate": round(avg_keyword_hit_rate, 4),
                "avg_trusted_hit_rate": round(avg_trusted_hit_rate, 4),
            },
            "source_stats": source_stats,
            "top_domains": sorted(
                domain_stats.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20],
        }


async def main():
    """测试多源证据收集"""
    import os
    
    # 从环境变量读取 API Keys
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    # 初始化多源搜索器
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    # 初始化多源证据收集器
    collector = MultiSourceEvidenceCollector(
        multi_source_searcher=searcher,
        config=MultiSourceEvidenceConfig(
            max_results_per_source=15,
            search_days=7,
            merge_strategy="keep_best",
        ),
    )
    
    print("=" * 60)
    print("Multi-Source Evidence Collector Test")
    print("=" * 60)
    
    # 测试查询
    test_queries = [
        "两会",
        "中国维和部队",
        "日本福岛核事故",
    ]
    
    results = await collector.batch_collect(test_queries)
    
    # 显示结果
    for query, result in results.items():
        if "error" in result:
            print(f"\n[Query] {query}")
            print(f"  Error: {result['error']}")
            continue
        
        print(f"\n[Query] {query}")
        
        search_stats = result["search_stats"]
        print(f"  Search: {search_stats['total_raw_results']} -> {search_stats['unique_results']} "
              f"({search_stats['deduplication_rate']:.2%} dedup)")
        print(f"  Sources: {search_stats['source_stats']}")
        
        evidence_result = result["evidence_result"]
        print(f"  Evidence: {evidence_result['evidence_count']} items")
        print(f"  Context: {evidence_result['context_count']} items")
        print(f"  Quality: {evidence_result['quality_metrics']}")
    
    # 生成报告
    report = collector.generate_report(results)
    print(f"\n" + "=" * 60)
    print("Summary Report")
    print("=" * 60)
    print(f"Queries: {report['summary']['total_queries']}")
    print(f"With Evidence: {report['summary']['queries_with_evidence']}")
    print(f"Evidence Rate: {report['summary']['evidence_rate']:.2%}")
    print(f"Total Raw Results: {report['search_stats']['total_raw_results']}")
    print(f"Total Unique Results: {report['search_stats']['total_unique_results']}")
    print(f"Deduplication Rate: {report['search_stats']['deduplication_rate']:.2%}")
    print(f"Total Evidence Items: {report['evidence_stats']['total_evidence_items']}")
    print(f"Avg Keyword Hit Rate: {report['quality_stats']['avg_keyword_hit_rate']:.2%}")
    print(f"Avg Trusted Hit Rate: {report['quality_stats']['avg_trusted_hit_rate']:.2%}")
    print(f"\nTop Sources:")
    for source, stats in report['source_stats'].items():
        print(f"  {source}: {stats['count']} results")
    print(f"\nTop Domains:")
    for domain, count in report['top_domains'][:10]:
        print(f"  {domain}: {count} occurrences")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
