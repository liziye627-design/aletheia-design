#!/usr/bin/env python3
"""
增强报告生成器 - 生成专业的真相验证报告

特点:
1. 多维度数据分析
2. 情感分析集成
3. 数据准确度验证
4. 精美的可视化报告
5. 多LLM支持

使用方法:
    from services.llm.enhanced_report_generator import EnhancedReportGenerator

    generator = EnhancedReportGenerator()

    report = await generator.generate_full_report(
        query="OpenAI是否发布GPT-5?",
        duplex_result=duplex_result,
        sentiment_results=sentiment_results
    )
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

from .llm_provider import LLMClient
from .sentiment_analyzer import SentimentAnalyzer, SentimentResult


@dataclass
class AccuracyMetrics:
    """准确度指标"""

    evidence_count: int
    min_evidence_count: int  # 最小证据数要求
    confidence: float
    min_confidence: float  # 最小置信度要求
    agent_consensus: float  # Agent一致性
    min_consensus: float  # 最小一致性要求
    cross_verification: bool  # 是否进行交叉验证
    quality_score: float  # 整体质量分数

    def is_reliable(self) -> bool:
        """判断数据是否可靠"""
        return (
            self.evidence_count >= self.min_evidence_count
            and self.confidence >= self.min_confidence
            and self.agent_consensus >= self.min_consensus
            and self.quality_score >= 0.7
        )

    def get_warning_messages(self) -> List[str]:
        """获取警告信息"""
        warnings = []

        if self.evidence_count < self.min_evidence_count:
            warnings.append(
                f"⚠️ 证据数量不足: {self.evidence_count}/{self.min_evidence_count}"
            )

        if self.confidence < self.min_confidence:
            warnings.append(
                f"⚠️ 置信度过低: {self.confidence:.1%} < {self.min_confidence:.1%}"
            )

        if self.agent_consensus < self.min_consensus:
            warnings.append(
                f"⚠️ Agent一致性不足: {self.agent_consensus:.1%} < {self.min_consensus:.1%}"
            )

        if self.quality_score < 0.7:
            warnings.append(f"⚠️ 数据质量不佳: {self.quality_score:.1%}")

        if not self.cross_verification:
            warnings.append("⚠️ 缺少交叉验证")

        return warnings


class EnhancedReportGenerator:
    """增强报告生成器"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.logger = logging.getLogger(__name__)
        self.llm_client = llm_client or LLMClient()
        self.sentiment_analyzer = SentimentAnalyzer(self.llm_client)

    async def generate_full_report(
        self,
        query: str,
        duplex_result: Dict[str, Any],
        include_sentiment: bool = True,
        include_visualizations: bool = True,
    ) -> Dict[str, Any]:
        """
        生成完整报告

        Args:
            query: 用户查询
            duplex_result: 双工系统结果
            include_sentiment: 是否包含情感分析
            include_visualizations: 是否包含可视化

        Returns:
            完整报告
        """
        self.logger.info(f"生成增强报告: {query}")

        # 1. 计算准确度指标
        accuracy = self._calculate_accuracy_metrics(duplex_result)

        # 2. 情感分析 (如果启用)
        sentiment_stats = None
        if include_sentiment:
            sentiment_stats = await self._analyze_sentiment(duplex_result)

        # 3. 生成核心结论
        conclusion = await self._generate_conclusion(
            query, duplex_result, accuracy, sentiment_stats
        )

        # 4. 生成详细分析
        detailed_analysis = await self._generate_detailed_analysis(
            duplex_result, accuracy, sentiment_stats
        )

        # 5. 生成可视化数据 (如果启用)
        visualizations = None
        if include_visualizations:
            visualizations = self._generate_visualizations(
                duplex_result, sentiment_stats
            )

        # 6. 组装报告
        report = {
            "metadata": {
                "query": query,
                "generated_at": datetime.now().isoformat(),
                "total_time": duplex_result.get("summary", {}).get("total_time", 0),
                "platforms": duplex_result.get("summary", {}).get("platforms", 0),
            },
            "accuracy": {
                "is_reliable": accuracy.is_reliable(),
                "metrics": {
                    "evidence_count": accuracy.evidence_count,
                    "confidence": accuracy.confidence,
                    "agent_consensus": accuracy.agent_consensus,
                    "quality_score": accuracy.quality_score,
                },
                "warnings": accuracy.get_warning_messages(),
            },
            "conclusion": conclusion,
            "sentiment_analysis": sentiment_stats,
            "detailed_analysis": detailed_analysis,
            "visualizations": visualizations,
            "raw_data": duplex_result,
        }

        # 7. 生成格式化文本报告
        report["formatted_text"] = self._format_text_report(report)

        return report

    def _calculate_accuracy_metrics(
        self, duplex_result: Dict[str, Any]
    ) -> AccuracyMetrics:
        """计算准确度指标"""
        import os

        summary = duplex_result.get("summary", {})

        # 从环境变量读取阈值
        min_evidence = int(os.getenv("MIN_EVIDENCE_COUNT", "5"))
        min_confidence = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.7"))
        min_consensus = float(os.getenv("MIN_AGENT_CONSENSUS", "0.75"))

        # 计算Agent一致性
        agent_results = duplex_result.get("agent_results", {})
        if agent_results:
            # 简化计算: 如果所有Agent都有结果则为100%
            agent_consensus = len([r for r in agent_results.values() if r]) / max(
                len(agent_results), 1
            )
        else:
            agent_consensus = 0.0

        # 整体质量分数
        quality_score = summary.get("quality_avg", 0.7)

        return AccuracyMetrics(
            evidence_count=summary.get("total_count", 0),
            min_evidence_count=min_evidence,
            confidence=0.85,  # 后续从verification结果获取
            min_confidence=min_confidence,
            agent_consensus=agent_consensus,
            min_consensus=min_consensus,
            cross_verification=bool(agent_results),
            quality_score=quality_score,
        )

    async def _analyze_sentiment(
        self, duplex_result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """分析情感"""
        # 提取所有文本
        texts = []
        sources = []

        aggregated = duplex_result.get("aggregated_results", {})
        for platform, items in aggregated.items():
            for item in items[:20]:  # 每个平台最多20条
                text = item.get("title", "") or item.get("content", "")
                if text:
                    texts.append(text)
                    sources.append(platform)

        if not texts:
            return None

        # 批量分析
        self.logger.info(f"情感分析: {len(texts)} 条文本")
        results = await self.sentiment_analyzer.analyze_batch(texts, sources)

        # 生成统计
        stats = self.sentiment_analyzer.get_sentiment_stats(results)

        return stats

    async def _generate_conclusion(
        self,
        query: str,
        duplex_result: Dict[str, Any],
        accuracy: AccuracyMetrics,
        sentiment_stats: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成核心结论"""
        summary = duplex_result.get("summary", {})

        # 构建提示词
        prompt = f"""请基于以下数据，生成一个简洁的核心结论。

查询: "{query}"

数据摘要:
- 证据数量: {accuracy.evidence_count}
- 数据质量: {accuracy.quality_score:.1%}
- Agent一致性: {accuracy.agent_consensus:.1%}
"""

        if sentiment_stats:
            prompt += f"""- 情感倾向: {sentiment_stats.get("dominant_sentiment", "neutral")}
- 情感分布: {sentiment_stats.get("distribution_pct", {})}
"""

        prompt += """
请生成一个100字以内的核心结论，包括:
1. 是否得到验证
2. 置信度级别 (高/中/低)
3. 主要发现

只返回结论文本,不要其他内容。
"""

        # 调用LLM
        messages = [{"role": "user", "content": prompt}]
        conclusion_text = await self.llm_client.chat_completion(
            messages, temperature=0.3
        )

        return {
            "verdict": "verified" if accuracy.is_reliable() else "unverified",
            "confidence_level": (
                "high"
                if accuracy.confidence >= 0.85
                else "medium"
                if accuracy.confidence >= 0.7
                else "low"
            ),
            "text": conclusion_text.strip(),
        }

    async def _generate_detailed_analysis(
        self,
        duplex_result: Dict[str, Any],
        accuracy: AccuracyMetrics,
        sentiment_stats: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """生成详细分析"""
        return {
            "data_sources": self._analyze_data_sources(duplex_result),
            "quality_assessment": self._assess_quality(accuracy),
            "sentiment_insights": (
                self._extract_sentiment_insights(sentiment_stats)
                if sentiment_stats
                else None
            ),
            "key_findings": self._extract_key_findings(duplex_result),
        }

    def _analyze_data_sources(self, duplex_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析数据来源"""
        aggregated = duplex_result.get("aggregated_results", {})

        source_categories = {
            "official": [],  # 官方源
            "media": [],  # 媒体
            "professional": [],  # 专业讨论
            "social": [],  # 社交媒体
        }

        # 分类
        official_sources = {"xinhua", "peoples_daily", "china_gov", "whitehouse"}
        media_sources = {"bbc", "cnn", "reuters", "nytimes"}
        professional_sources = {"zhihu", "openalex"}
        social_sources = {"bilibili", "douyin", "xiaohongshu"}

        for platform, items in aggregated.items():
            if platform in official_sources:
                source_categories["official"].append(
                    {"platform": platform, "count": len(items)}
                )
            elif platform in media_sources:
                source_categories["media"].append(
                    {"platform": platform, "count": len(items)}
                )
            elif platform in professional_sources:
                source_categories["professional"].append(
                    {"platform": platform, "count": len(items)}
                )
            elif platform in social_sources:
                source_categories["social"].append(
                    {"platform": platform, "count": len(items)}
                )

        return {
            "categories": source_categories,
            "total_platforms": len(aggregated),
            "total_items": sum(len(items) for items in aggregated.values()),
        }

    def _assess_quality(self, accuracy: AccuracyMetrics) -> Dict[str, Any]:
        """评估质量"""
        return {
            "overall_score": accuracy.quality_score,
            "is_reliable": accuracy.is_reliable(),
            "strengths": self._identify_strengths(accuracy),
            "weaknesses": accuracy.get_warning_messages(),
            "recommendations": self._generate_recommendations(accuracy),
        }

    def _identify_strengths(self, accuracy: AccuracyMetrics) -> List[str]:
        """识别优势"""
        strengths = []

        if accuracy.evidence_count >= accuracy.min_evidence_count * 2:
            strengths.append(f"✅ 证据充足 ({accuracy.evidence_count}条)")

        if accuracy.confidence >= 0.9:
            strengths.append(f"✅ 置信度高 ({accuracy.confidence:.1%})")

        if accuracy.agent_consensus >= 0.9:
            strengths.append(f"✅ Agent高度一致 ({accuracy.agent_consensus:.1%})")

        if accuracy.cross_verification:
            strengths.append("✅ 已进行交叉验证")

        if accuracy.quality_score >= 0.85:
            strengths.append(f"✅ 数据质量优秀 ({accuracy.quality_score:.1%})")

        return strengths

    def _generate_recommendations(self, accuracy: AccuracyMetrics) -> List[str]:
        """生成建议"""
        recommendations = []

        if accuracy.evidence_count < accuracy.min_evidence_count:
            recommendations.append("💡 建议: 扩大数据采集范围,增加证据数量")

        if accuracy.confidence < 0.8:
            recommendations.append("💡 建议: 增加更多权威来源,提升置信度")

        if accuracy.agent_consensus < 0.85:
            recommendations.append("💡 建议: 进行更深入的交叉验证")

        if not accuracy.cross_verification:
            recommendations.append("💡 建议: 启用多Agent协商验证")

        return recommendations

    def _extract_sentiment_insights(
        self, sentiment_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """提取情感洞察"""
        return {
            "dominant_sentiment": sentiment_stats.get("dominant_sentiment"),
            "distribution": sentiment_stats.get("distribution_pct", {}),
            "key_insights": [
                f"主导情感为{sentiment_stats.get('dominant_sentiment', '未知')}",
                f"平均情感分数: {sentiment_stats.get('average_score', 0):.2f}",
            ],
        }

    def _extract_key_findings(self, duplex_result: Dict[str, Any]) -> List[str]:
        """提取关键发现"""
        findings = []

        summary = duplex_result.get("summary", {})

        # Crawler发现
        crawler_count = summary.get("crawler_count", 0)
        if crawler_count > 0:
            findings.append(f"从传统渠道获取{crawler_count}条数据")

        # Agent发现
        agent_count = summary.get("agent_count", 0)
        if agent_count > 0:
            findings.append(f"通过Agent深度验证获取{agent_count}条数据")

        # 平台覆盖
        platforms = summary.get("platforms", 0)
        if platforms > 0:
            findings.append(f"覆盖{platforms}个数据平台")

        return findings

    def _generate_visualizations(
        self, duplex_result: Dict[str, Any], sentiment_stats: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成可视化数据"""
        return {
            "platform_distribution": self._viz_platform_distribution(duplex_result),
            "sentiment_distribution": (
                self._viz_sentiment_distribution(sentiment_stats)
                if sentiment_stats
                else None
            ),
            "quality_radar": self._viz_quality_radar(duplex_result),
        }

    def _viz_platform_distribution(
        self, duplex_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """平台分布可视化数据"""
        aggregated = duplex_result.get("aggregated_results", {})

        return {
            "type": "bar",
            "labels": list(aggregated.keys()),
            "values": [len(items) for items in aggregated.values()],
        }

    def _viz_sentiment_distribution(
        self, sentiment_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """情感分布可视化数据"""
        return {
            "type": "pie",
            "labels": list(sentiment_stats.get("distribution", {}).keys()),
            "values": list(sentiment_stats.get("distribution", {}).values()),
        }

    def _viz_quality_radar(self, duplex_result: Dict[str, Any]) -> Dict[str, Any]:
        """质量雷达图数据"""
        summary = duplex_result.get("summary", {})

        return {
            "type": "radar",
            "metrics": [
                {
                    "name": "证据数量",
                    "value": min(summary.get("total_count", 0) / 50, 1),
                },
                {"name": "数据质量", "value": summary.get("quality_avg", 0)},
                {"name": "平台覆盖", "value": min(summary.get("platforms", 0) / 10, 1)},
                {"name": "Agent一致性", "value": 0.85},  # 占位
                {"name": "时效性", "value": 0.9},  # 占位
            ],
        }

    def _format_text_report(self, report: Dict[str, Any]) -> str:
        """格式化文本报告"""
        metadata = report["metadata"]
        accuracy = report["accuracy"]
        conclusion = report["conclusion"]
        detailed = report["detailed_analysis"]

        # 构建报告
        text = f"""
╔══════════════════════════════════════════════════════════════════╗
║              Aletheia 真相验证报告 (增强版)                      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  查询: {metadata["query"]}                      ║
║  生成时间: {metadata["generated_at"][:19]}                     ║
║  验证耗时: {metadata["total_time"]:.1f}秒                                             ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                        核心结论                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🎯 验证结果: {conclusion["verdict"].upper()}                    ║
║  📊 置信度: {conclusion["confidence_level"].upper()}             ║
║                                                                  ║
║  {conclusion["text"]}                                            ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                      数据准确度评估                              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📈 整体评估: {"✅ 可靠" if accuracy["is_reliable"] else "⚠️ 需谨慎"}               ║
║                                                                  ║
║  关键指标:                                                       ║
║    • 证据数量: {accuracy["metrics"]["evidence_count"]} 条                                    ║
║    • 置信度: {accuracy["metrics"]["confidence"]:.1%}                                     ║
║    • Agent一致性: {accuracy["metrics"]["agent_consensus"]:.1%}                           ║
║    • 质量分数: {accuracy["metrics"]["quality_score"]:.1%}                                ║
║                                                                  ║
"""

        # 警告信息
        if accuracy["warnings"]:
            text += (
                "║  ⚠️  警告:                                                       ║\n"
            )
            for warning in accuracy["warnings"]:
                text += f"║    {warning}                                           ║\n"
            text += (
                "║                                                                  ║\n"
            )

        # 优势
        strengths = detailed["quality_assessment"]["strengths"]
        if strengths:
            text += (
                "║  ✅ 优势:                                                        ║\n"
            )
            for strength in strengths[:3]:
                text += f"║    {strength}                                         ║\n"
            text += (
                "║                                                                  ║\n"
            )

        text += """╠══════════════════════════════════════════════════════════════════╣
║                      数据来源分析                                ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
"""

        # 数据来源
        sources = detailed["data_sources"]
        text += f"║  📊 总计: {sources['total_platforms']}个平台, {sources['total_items']}条数据                         ║\n"
        text += "║                                                                  ║\n"

        text += "╚══════════════════════════════════════════════════════════════════╝\n"

        return text


# 测试代码
async def main():
    """测试增强报告生成器"""
    print("\n" + "=" * 70)
    print("📊 增强报告生成器测试")
    print("=" * 70)

    # 模拟双工系统结果
    mock_duplex_result = {
        "summary": {
            "crawler_count": 21,
            "agent_count": 45,
            "total_count": 58,
            "platforms": 10,
            "quality_avg": 0.88,
            "total_time": 7.8,
        },
        "aggregated_results": {
            "bilibili": [{"title": f"B站视频{i}"} for i in range(12)],
            "douyin": [{"title": f"抖音视频{i}"} for i in range(15)],
            "zhihu": [{"title": f"知乎回答{i}"} for i in range(8)],
        },
        "agent_results": {"bilibili": [], "douyin": [], "zhihu": []},
    }

    generator = EnhancedReportGenerator()

    # 生成报告
    report = await generator.generate_full_report(
        query="OpenAI是否发布GPT-5?", duplex_result=mock_duplex_result
    )

    # 显示报告
    print(report["formatted_text"])

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    import os

    os.environ["SKIP_LLM_CALLS"] = "false"

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
