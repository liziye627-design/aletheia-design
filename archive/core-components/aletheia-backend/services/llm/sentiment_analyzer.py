#!/usr/bin/env python3
"""
情感分析器 - 对采集数据进行情感分析

功能:
1. 单条文本情感分析
2. 批量文本情感分析
3. 情感趋势分析
4. 情感分布统计

使用方法:
    from services.llm.sentiment_analyzer import SentimentAnalyzer

    analyzer = SentimentAnalyzer()

    # 单条分析
    result = await analyzer.analyze("这个产品真的很棒!")

    # 批量分析
    results = await analyzer.analyze_batch(texts)

    # 情感统计
    stats = analyzer.get_sentiment_stats(results)
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import Counter

from .llm_provider import LLMClient


@dataclass
class SentimentResult:
    """情感分析结果"""

    text: str
    sentiment: str  # very_positive/positive/neutral/negative/very_negative
    score: float  # 0-1
    confidence: float  # 0-1
    reasoning: str
    timestamp: datetime
    source: Optional[str] = None  # 数据来源


class SentimentAnalyzer:
    """情感分析器"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.logger = logging.getLogger(__name__)
        self.llm_client = llm_client or LLMClient()

        # 情感映射
        self.sentiment_mapping = {
            "very_positive": 5,
            "positive": 4,
            "neutral": 3,
            "negative": 2,
            "very_negative": 1,
        }

        self.sentiment_cn = {
            "very_positive": "非常正面",
            "positive": "正面",
            "neutral": "中性",
            "negative": "负面",
            "very_negative": "非常负面",
        }

    async def analyze(
        self, text: str, source: Optional[str] = None, granularity: int = 5
    ) -> SentimentResult:
        """
        分析单条文本情感

        Args:
            text: 待分析文本
            source: 数据来源
            granularity: 细粒度 (3或5)

        Returns:
            SentimentResult
        """
        try:
            result = await self.llm_client.analyze_sentiment(text, granularity)

            return SentimentResult(
                text=text,
                sentiment=result["sentiment"],
                score=float(result["score"]),
                confidence=float(result["confidence"]),
                reasoning=result["reasoning"],
                timestamp=datetime.now(),
                source=source,
            )

        except Exception as e:
            self.logger.error(f"情感分析失败: {e}")
            # 返回默认值
            return SentimentResult(
                text=text,
                sentiment="neutral",
                score=0.5,
                confidence=0.5,
                reasoning="分析失败",
                timestamp=datetime.now(),
                source=source,
            )

    async def analyze_batch(
        self,
        texts: List[str],
        sources: Optional[List[str]] = None,
        batch_size: int = 10,
    ) -> List[SentimentResult]:
        """
        批量分析文本情感

        Args:
            texts: 文本列表
            sources: 来源列表
            batch_size: 批次大小

        Returns:
            情感分析结果列表
        """
        self.logger.info(f"批量情感分析: {len(texts)} 条文本")

        if sources is None:
            sources = [None] * len(texts)

        results = []

        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_sources = sources[i : i + batch_size]

            # 并发分析
            tasks = [
                self.analyze(text, source)
                for text, source in zip(batch_texts, batch_sources)
            ]

            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

            self.logger.info(f"已完成 {len(results)}/{len(texts)}")

        return results

    def get_sentiment_stats(self, results: List[SentimentResult]) -> Dict[str, Any]:
        """
        获取情感统计信息

        Args:
            results: 情感分析结果列表

        Returns:
            统计信息
        """
        if not results:
            return {
                "total": 0,
                "distribution": {},
                "average_score": 0,
                "average_confidence": 0,
            }

        # 情感分布
        sentiments = [r.sentiment for r in results]
        distribution = dict(Counter(sentiments))

        # 计算百分比
        distribution_pct = {
            s: count / len(results) * 100 for s, count in distribution.items()
        }

        # 平均分数
        average_score = sum(r.score for r in results) / len(results)
        average_confidence = sum(r.confidence for r in results) / len(results)

        # 按来源统计
        source_stats = {}
        for result in results:
            if result.source:
                if result.source not in source_stats:
                    source_stats[result.source] = []
                source_stats[result.source].append(result.sentiment)

        source_distribution = {
            source: dict(Counter(sentiments))
            for source, sentiments in source_stats.items()
        }

        return {
            "total": len(results),
            "distribution": distribution,
            "distribution_pct": distribution_pct,
            "average_score": average_score,
            "average_confidence": average_confidence,
            "dominant_sentiment": max(distribution, key=distribution.get),
            "source_distribution": source_distribution,
        }

    def get_sentiment_trend(
        self, results: List[SentimentResult], time_window: str = "hour"
    ) -> List[Dict[str, Any]]:
        """
        获取情感趋势

        Args:
            results: 情感分析结果列表
            time_window: 时间窗口 (hour/day/week)

        Returns:
            趋势数据
        """
        # 按时间分组
        from collections import defaultdict

        trends = defaultdict(list)

        for result in results:
            if time_window == "hour":
                key = result.timestamp.strftime("%Y-%m-%d %H:00")
            elif time_window == "day":
                key = result.timestamp.strftime("%Y-%m-%d")
            else:  # week
                key = result.timestamp.strftime("%Y-W%W")

            trends[key].append(result)

        # 计算每个时间窗口的统计
        trend_data = []
        for time_key, window_results in sorted(trends.items()):
            stats = self.get_sentiment_stats(window_results)
            trend_data.append({"time": time_key, "stats": stats})

        return trend_data

    def generate_sentiment_report(self, results: List[SentimentResult]) -> str:
        """
        生成情感分析报告

        Args:
            results: 情感分析结果列表

        Returns:
            报告文本
        """
        stats = self.get_sentiment_stats(results)

        report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          情感分析报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 总体统计
  • 分析样本: {stats["total"]} 条
  • 平均情感分数: {stats["average_score"]:.2f} (0-1)
  • 平均置信度: {stats["average_confidence"]:.2%}
  • 主导情感: {self.sentiment_cn.get(stats["dominant_sentiment"], stats["dominant_sentiment"])}

📈 情感分布
"""

        # 情感分布
        for sentiment, percentage in sorted(
            stats["distribution_pct"].items(),
            key=lambda x: self.sentiment_mapping.get(x[0], 0),
            reverse=True,
        ):
            count = stats["distribution"].get(sentiment, 0)
            bar = "█" * int(percentage / 5)
            report += f"  {self.sentiment_cn.get(sentiment, sentiment):8s}: {bar} {percentage:5.1f}% ({count}条)\n"

        # 按来源统计
        if stats["source_distribution"]:
            report += "\n📍 按来源统计\n"
            for source, dist in stats["source_distribution"].items():
                total = sum(dist.values())
                dominant = max(dist, key=dist.get)
                report += f"  • {source}: {total}条, 主导情感: {self.sentiment_cn.get(dominant, dominant)}\n"

        report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        return report


# 测试代码
async def main():
    """测试情感分析器"""
    print("\n" + "=" * 70)
    print("😊 情感分析器测试")
    print("=" * 70)

    analyzer = SentimentAnalyzer()

    # 测试数据
    test_data = [
        ("这个产品真的太棒了！强烈推荐！", "bilibili"),
        ("质量还可以，价格有点贵。", "xiaohongshu"),
        ("非常失望，完全是浪费钱。", "douyin"),
        ("一般般，没什么特别的。", "zhihu"),
        ("超级满意，物超所值！", "bilibili"),
        ("还行吧，凑合能用。", "xiaohongshu"),
        ("太差了，不推荐购买。", "douyin"),
        ("非常好用，会回购的。", "zhihu"),
    ]

    texts = [t[0] for t in test_data]
    sources = [t[1] for t in test_data]

    # 批量分析
    print("\n📊 批量分析中...")
    results = await analyzer.analyze_batch(texts, sources, batch_size=4)

    # 显示结果
    print("\n" + "=" * 70)
    print("分析结果:")
    print("=" * 70)

    for result in results:
        print(f"\n文本: {result.text}")
        print(f"来源: {result.source}")
        print(f"情感: {analyzer.sentiment_cn.get(result.sentiment, result.sentiment)}")
        print(f"分数: {result.score:.2f}")
        print(f"置信度: {result.confidence:.2%}")

    # 生成报告
    print("\n" + "=" * 70)
    report = analyzer.generate_sentiment_report(results)
    print(report)

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    import os

    # 测试模式
    os.environ["SKIP_LLM_CALLS"] = "false"

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
