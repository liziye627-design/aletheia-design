# -*- coding: utf-8 -*-
"""
Evidence Pool Manager
证据池管理器

实现 Two-Pool Strategy:
- Evidence Pool: 高可信+高相关证据
- Context Pool: 背景信息，不参与结论
"""

import asyncio
import jieba
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from loguru import logger

from services.crawler.platform_rss_collector import (
    PlatformRSSCollector,
    NewsArticle
)


@dataclass
class QualityMetrics:
    """质量指标"""
    total_items: int = 0
    keyword_hit_items: int = 0
    entity_hit_items: int = 0
    trusted_hits: int = 0

    @property
    def keyword_hit_rate(self) -> float:
        return self.keyword_hit_items / self.total_items if self.total_items > 0 else 0.0

    @property
    def entity_hit_rate(self) -> float:
        return self.entity_hit_items / self.total_items if self.total_items > 0 else 0.0

    @property
    def trusted_hit_rate(self) -> float:
        return self.trusted_hits / self.total_items if self.total_items > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_items": self.total_items,
            "keyword_hit_items": self.keyword_hit_items,
            "entity_hit_items": self.entity_hit_items,
            "trusted_hits": self.trusted_hits,
            "keyword_hit_rate": round(self.keyword_hit_rate, 4),
            "entity_hit_rate": round(self.entity_hit_rate, 4),
            "trusted_hit_rate": round(self.trusted_hit_rate, 4),
        }


@dataclass
class EvidenceResult:
    """证据结果"""
    query: str
    evidence_pool: List[NewsArticle] = field(default_factory=list)
    context_pool: List[NewsArticle] = field(default_factory=list)
    quality_metrics: QualityMetrics = field(default_factory=QualityMetrics)
    collection_time: datetime = field(default_factory=datetime.now)

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence_pool) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "has_evidence": self.has_evidence,
            "evidence_count": len(self.evidence_pool),
            "context_count": len(self.context_pool),
            "quality_metrics": self.quality_metrics.to_dict(),
            "evidence_pool": [a.to_dict() for a in self.evidence_pool[:10]],
            "context_pool": [a.to_dict() for a in self.context_pool[:5]],
        }


class EvidencePoolManager:
    """
    证据池管理器

    实现高可信证据收集和质量检测
    """

    def __init__(
        self,
        collector: Optional[PlatformRSSCollector] = None
    ):
        self.collector = collector or PlatformRSSCollector()

        # 质量阈值 (from platform_capability_matrix.yaml)
        self.evidence_thresholds = {
            "min_items": 3,
            "min_keyword_hit_rate": 0.8,
            "min_entity_hit_rate": 0.8,
            "min_trusted_hit_rate": 0.9,
        }

        logger.info("EvidencePoolManager initialized")

    def extract_keywords(self, query: str) -> List[str]:
        """从查询中提取关键词"""
        # 分词
        terms = list(jieba.cut(query))

        # 过滤停用词
        stopwords = {'的', '是', '在', '有', '和', '了', '吗', '什么', '怎么', '为什么', '如何'}
        keywords = [t for t in terms if len(t) > 1 and t not in stopwords]

        return keywords

    def extract_entities(self, query: str) -> List[str]:
        """提取实体词（人名、地名、机构名等）"""
        # 使用jieba的词性标注
        import jieba.posseg as pseg

        words = pseg.cut(query)
        entities = []

        # 提取命名实体
        entity_flags = ['nr', 'ns', 'nt', 'nz']  # 人名、地名、机构名、其他专名
        for word, flag in words:
            if flag in entity_flags and len(word) > 1:
                entities.append(word)

        return entities

    def check_keyword_hit(
        self,
        article: NewsArticle,
        keywords: List[str]
    ) -> Tuple[bool, List[str]]:
        """检查关键词命中"""
        text = f"{article.title} {article.content}"
        hits = [kw for kw in keywords if kw in text]
        return len(hits) > 0, hits

    def check_entity_hit(
        self,
        article: NewsArticle,
        entities: List[str]
    ) -> Tuple[bool, List[str]]:
        """检查实体命中"""
        text = f"{article.title} {article.content}"
        hits = [e for e in entities if e in text]
        return len(hits) > 0, hits

    async def collect_evidence(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
        max_per_platform: int = 30
    ) -> EvidenceResult:
        """
        收集证据

        Args:
            query: 查询文本
            platforms: 指定平台列表
            max_per_platform: 每平台最大文章数

        Returns:
            EvidenceResult: 证据结果
        """
        if platforms is None:
            platforms = self.collector.get_platforms_for_evidence()

        # 提取关键词和实体
        keywords = self.extract_keywords(query)
        entities = self.extract_entities(query)

        logger.info(f"Query: {query}")
        logger.info(f"Keywords: {keywords}")
        logger.info(f"Entities: {entities}")

        # 收集文章
        articles_by_platform = await self.collector.collect_all(
            platforms=platforms,
            max_per_platform=max_per_platform
        )

        # 合并所有文章
        all_articles = []
        for platform_articles in articles_by_platform.values():
            all_articles.extend(platform_articles)

        # 分析每篇文章
        evidence_pool = []
        context_pool = []

        for article in all_articles:
            # 检查命中
            keyword_hit, keyword_hits = self.check_keyword_hit(article, keywords)
            entity_hit, entity_hits = self.check_entity_hit(article, entities)

            article.keyword_hits = keyword_hits
            article.entity_hits = entity_hits

            # 判断进入哪个池
            if article.is_trusted and (keyword_hit or entity_hit):
                evidence_pool.append(article)
            elif keyword_hit or entity_hit:
                context_pool.append(article)

        # 计算质量指标
        metrics = self._calculate_metrics(evidence_pool, keywords, entities)

        result = EvidenceResult(
            query=query,
            evidence_pool=evidence_pool,
            context_pool=context_pool,
            quality_metrics=metrics,
        )

        # 检查是否达标
        self._check_quality(result)

        return result

    def _calculate_metrics(
        self,
        articles: List[NewsArticle],
        keywords: List[str],
        entities: List[str]
    ) -> QualityMetrics:
        """计算质量指标"""
        metrics = QualityMetrics()
        metrics.total_items = len(articles)

        for article in articles:
            if article.keyword_hits:
                metrics.keyword_hit_items += 1
            if article.entity_hits:
                metrics.entity_hit_items += 1
            if article.is_trusted:
                metrics.trusted_hits += 1

        return metrics

    def _check_quality(self, result: EvidenceResult):
        """检查质量是否达标"""
        metrics = result.quality_metrics

        issues = []

        if metrics.total_items < self.evidence_thresholds["min_items"]:
            issues.append(f"items={metrics.total_items} < min_items={self.evidence_thresholds['min_items']}")

        if metrics.keyword_hit_rate < self.evidence_thresholds["min_keyword_hit_rate"]:
            issues.append(f"keyword_hit_rate={metrics.keyword_hit_rate:.2f} < threshold")

        if metrics.entity_hit_rate < self.evidence_thresholds["min_entity_hit_rate"]:
            issues.append(f"entity_hit_rate={metrics.entity_hit_rate:.2f} < threshold")

        if metrics.trusted_hit_rate < self.evidence_thresholds["min_trusted_hit_rate"]:
            issues.append(f"trusted_hit_rate={metrics.trusted_hit_rate:.2f} < threshold")

        if issues:
            logger.warning(f"Quality check issues: {issues}")
        else:
            logger.info("Quality check passed")

    async def batch_collect(
        self,
        queries: List[str],
        platforms: Optional[List[str]] = None
    ) -> Dict[str, EvidenceResult]:
        """批量收集证据"""
        results = {}

        for query in queries:
            result = await self.collect_evidence(query, platforms)
            results[query] = result

        return results

    def generate_report(
        self,
        results: Dict[str, EvidenceResult]
    ) -> Dict[str, Any]:
        """生成报告"""
        total_queries = len(results)
        queries_with_evidence = sum(1 for r in results.values() if r.has_evidence)

        # 平台统计
        platform_stats = {}
        for result in results.values():
            for article in result.evidence_pool:
                platform = article.source
                if platform not in platform_stats:
                    platform_stats[platform] = {"count": 0, "trusted": 0}
                platform_stats[platform]["count"] += 1
                if article.is_trusted:
                    platform_stats[platform]["trusted"] += 1

        # 质量统计
        avg_keyword_rate = sum(r.quality_metrics.keyword_hit_rate for r in results.values()) / total_queries if total_queries > 0 else 0
        avg_entity_rate = sum(r.quality_metrics.entity_hit_rate for r in results.values()) / total_queries if total_queries > 0 else 0
        avg_trusted_rate = sum(r.quality_metrics.trusted_hit_rate for r in results.values()) / total_queries if total_queries > 0 else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "total_queries": total_queries,
            "queries_with_evidence": queries_with_evidence,
            "evidence_rate": queries_with_evidence / total_queries if total_queries > 0 else 0,
            "platform_stats": platform_stats,
            "quality_stats": {
                "avg_keyword_hit_rate": round(avg_keyword_rate, 4),
                "avg_entity_hit_rate": round(avg_entity_rate, 4),
                "avg_trusted_hit_rate": round(avg_trusted_rate, 4),
            },
            "thresholds": self.evidence_thresholds,
        }


async def main():
    """测试证据收集"""
    manager = EvidencePoolManager()

    # 测试查询
    test_queries = [
        "两会今日看点",
        "中国维和部队",
        "日本福岛核事故",
        "巴以冲突最新进展",
    ]

    print("=" * 60)
    print("Evidence Pool Test")
    print("=" * 60)

    results = await manager.batch_collect(test_queries)

    for query, result in results.items():
        print(f"\n[Query] {query}")
        print(f"  Evidence: {len(result.evidence_pool)} items")
        print(f"  Context: {len(result.context_pool)} items")
        print(f"  Quality: {result.quality_metrics.to_dict()}")

        if result.evidence_pool:
            print(f"  Top evidence:")
            for i, article in enumerate(result.evidence_pool[:3]):
                print(f"    {i+1}. [{article.source}] {article.title[:50]}...")

    # 生成报告
    report = manager.generate_report(results)
    print(f"\n" + "=" * 60)
    print(f"Evidence Rate: {report['evidence_rate']:.2%}")
    print(f"Avg Keyword Hit Rate: {report['quality_stats']['avg_keyword_hit_rate']:.2%}")
    print(f"Avg Trusted Hit Rate: {report['quality_stats']['avg_trusted_hit_rate']:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())