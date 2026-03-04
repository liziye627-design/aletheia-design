"""
Aletheia Agent Tools - Sentiment Analyzer
==========================================

借鉴 BettaFish 的多语言情感分析工具，为 Aletheia 提供：
- 文本情感分析（正面/负面/中性）
- 批量情感分析
- 查询结果情感统计
"""

import os
import sys
import re
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from loguru import logger

# 添加父目录到路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)


@dataclass
class SentimentResult:
    """单个文本的情感分析结果"""

    text: str
    sentiment_label: str  # 非常负面, 负面, 中性, 正面, 非常正面
    confidence: float
    probability_distribution: Dict[str, float] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    analysis_performed: bool = True


@dataclass
class BatchSentimentResult:
    """批量情感分析结果"""

    results: List[SentimentResult] = field(default_factory=list)
    total_processed: int = 0
    success_count: int = 0
    failed_count: int = 0
    average_confidence: float = 0.0
    analysis_performed: bool = True


class SentimentAnalyzer:
    """
    情感分析器

    支持多语言文本的情感分析，使用规则+LLM混合策略：
    1. 简单规则匹配（快速路径）
    2. LLM API 分析（精确路径）

    情感等级：
    - 非常负面 (0)
    - 负面 (1)
    - 中性 (2)
    - 正面 (3)
    - 非常正面 (4)
    """

    def __init__(self, use_llm: bool = False, llm_client: Any = None):
        """
        初始化情感分析器

        Args:
            use_llm: 是否使用 LLM 进行情感分析
            llm_client: LLM 客户端实例（如果使用 LLM）
        """
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.is_initialized = True

        # 情感标签映射
        self.sentiment_map = {
            0: "非常负面",
            1: "负面",
            2: "中性",
            3: "正面",
            4: "非常正面",
        }

        # 简单规则 - 正面词汇
        self.positive_words = {
            "好",
            "棒",
            "赞",
            "优秀",
            "完美",
            "喜欢",
            "爱",
            "支持",
            "赞同",
            "满意",
            "开心",
            "快乐",
            "幸福",
            "成功",
            "胜利",
            "好消息",
            "不错",
            "挺好的",
            "厉害了",
            "牛",
            "强",
            "给力",
            "精彩",
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "love",
            "like",
            "best",
            "perfect",
            "awesome",
            "fantastic",
            "happy",
            "glad",
        }

        # 简单规则 - 负面词汇
        self.negative_words = {
            "差",
            "坏",
            "糟",
            "烂",
            "讨厌",
            "恨",
            "反对",
            "批评",
            "谴责",
            "失望",
            "愤怒",
            "悲伤",
            "痛苦",
            "失败",
            "糟糕",
            "坏消息",
            "不行",
            "不好",
            "垃圾",
            "恶心",
            "气愤",
            "郁闷",
            "可惜",
            "bad",
            "terrible",
            "awful",
            "hate",
            "worst",
            "disappointed",
            "angry",
            "sad",
            "poor",
            "disgusting",
            "fail",
            "wrong",
        }

        logger.info("SentimentAnalyzer 已初始化")
        logger.info("情感等级: 非常负面、负面、中性、正面、非常正面")

    def analyze(self, text: str) -> SentimentResult:
        """
        分析单个文本的情感

        Args:
            text: 待分析的文本

        Returns:
            情感分析结果
        """
        if not text or not text.strip():
            return SentimentResult(
                text=text,
                sentiment_label="输入错误",
                confidence=0.0,
                success=False,
                error_message="输入文本为空",
                analysis_performed=False,
            )

        try:
            # 预处理
            processed_text = self._preprocess(text)

            # 如果使用 LLM
            if self.use_llm and self.llm_client:
                return self._analyze_with_llm(processed_text)

            # 使用规则分析
            return self._analyze_with_rules(processed_text)

        except Exception as e:
            logger.error(f"情感分析失败: {str(e)}")
            return SentimentResult(
                text=text,
                sentiment_label="分析失败",
                confidence=0.0,
                success=False,
                error_message=str(e),
                analysis_performed=False,
            )

    def analyze_batch(
        self, texts: List[str], show_progress: bool = True
    ) -> BatchSentimentResult:
        """
        批量情感分析

        Args:
            texts: 文本列表
            show_progress: 是否显示进度

        Returns:
            批量分析结果
        """
        if not texts:
            return BatchSentimentResult(
                total_processed=0,
                success_count=0,
                failed_count=0,
                average_confidence=0.0,
            )

        results = []
        success_count = 0
        total_confidence = 0.0

        for i, text in enumerate(texts):
            if show_progress and len(texts) > 10 and i % 10 == 0:
                logger.info(f"情感分析进度: {i}/{len(texts)}")

            result = self.analyze(text)
            results.append(result)

            if result.success:
                success_count += 1
                total_confidence += result.confidence

        avg_confidence = total_confidence / success_count if success_count > 0 else 0.0

        return BatchSentimentResult(
            results=results,
            total_processed=len(texts),
            success_count=success_count,
            failed_count=len(texts) - success_count,
            average_confidence=avg_confidence,
        )

    def analyze_query_results(
        self,
        query_results: List[Dict[str, Any]],
        text_field: str = "content",
        min_confidence: float = 0.5,
    ) -> Dict[str, Any]:
        """
        对查询结果进行情感分析

        Args:
            query_results: 查询结果列表
            text_field: 文本字段名
            min_confidence: 最小置信度阈值

        Returns:
            包含情感分析结果的字典
        """
        if not query_results:
            return {
                "sentiment_analysis": {
                    "total_analyzed": 0,
                    "sentiment_distribution": {},
                    "high_confidence_results": [],
                    "summary": "没有内容需要分析",
                }
            }

        # 提取文本内容
        texts_to_analyze = []
        original_data = []

        for item in query_results:
            text_content = ""
            # 尝试多个可能的文本字段
            for field in [text_field, "title_or_content", "content", "title", "text"]:
                if field in item and item[field]:
                    text_content = str(item[field])
                    break

            if text_content.strip():
                texts_to_analyze.append(text_content)
                original_data.append(item)

        if not texts_to_analyze:
            return {
                "sentiment_analysis": {
                    "total_analyzed": 0,
                    "sentiment_distribution": {},
                    "high_confidence_results": [],
                    "summary": "查询结果中没有找到可分析的文本内容",
                }
            }

        # 执行批量分析
        logger.info(f"正在对 {len(texts_to_analyze)} 条内容进行情感分析...")
        batch_result = self.analyze_batch(
            texts_to_analyze, show_progress=len(texts_to_analyze) > 20
        )

        # 统计情感分布
        sentiment_distribution = {}
        high_confidence_results = []

        for result, original_item in zip(batch_result.results, original_data):
            if result.success:
                sentiment = result.sentiment_label
                sentiment_distribution[sentiment] = (
                    sentiment_distribution.get(sentiment, 0) + 1
                )

                if result.confidence >= min_confidence:
                    high_confidence_results.append(
                        {
                            "original_data": original_item,
                            "sentiment": result.sentiment_label,
                            "confidence": result.confidence,
                            "text_preview": result.text[:100] + "..."
                            if len(result.text) > 100
                            else result.text,
                        }
                    )

        # 生成摘要
        total_analyzed = batch_result.success_count
        if total_analyzed > 0:
            dominant = max(sentiment_distribution.items(), key=lambda x: x[1])
            sentiment_summary = (
                f"共分析 {total_analyzed} 条内容，"
                f"主要情感倾向为'{dominant[0]}'"
                f"({dominant[1]}条，占{dominant[1] / total_analyzed * 100:.1f}%)"
            )
        else:
            sentiment_summary = "情感分析失败"

        return {
            "sentiment_analysis": {
                "total_analyzed": total_analyzed,
                "success_rate": f"{batch_result.success_count}/{batch_result.total_processed}",
                "average_confidence": round(batch_result.average_confidence, 4),
                "sentiment_distribution": sentiment_distribution,
                "high_confidence_results": high_confidence_results,
                "summary": sentiment_summary,
            }
        }

    def _preprocess(self, text: str) -> str:
        """文本预处理"""
        # 去除多余空格
        text = re.sub(r"\s+", " ", text.strip())
        # 转换为小写（用于英文匹配）
        return text

    def _analyze_with_rules(self, text: str) -> SentimentResult:
        """使用规则进行情感分析"""
        text_lower = text.lower()

        # 计算正面和负面词出现次数
        pos_count = sum(1 for word in self.positive_words if word in text_lower)
        neg_count = sum(1 for word in self.negative_words if word in text_lower)

        # 确定情感倾向
        if pos_count > neg_count:
            if pos_count - neg_count >= 2:
                sentiment = "非常正面"
                score = 4
                confidence = min(0.5 + (pos_count - neg_count) * 0.1, 0.9)
            else:
                sentiment = "正面"
                score = 3
                confidence = min(0.5 + pos_count * 0.1, 0.8)
        elif neg_count > pos_count:
            if neg_count - pos_count >= 2:
                sentiment = "非常负面"
                score = 0
                confidence = min(0.5 + (neg_count - pos_count) * 0.1, 0.9)
            else:
                sentiment = "负面"
                score = 1
                confidence = min(0.5 + neg_count * 0.1, 0.8)
        else:
            sentiment = "中性"
            score = 2
            confidence = 0.6 if pos_count == 0 else 0.5

        # 构建概率分布
        prob_dist = {label: 0.1 for label in self.sentiment_map.values()}
        prob_dist[sentiment] = confidence

        # 归一化
        total = sum(prob_dist.values())
        prob_dist = {k: round(v / total, 4) for k, v in prob_dist.items()}

        return SentimentResult(
            text=text,
            sentiment_label=sentiment,
            confidence=round(confidence, 4),
            probability_distribution=prob_dist,
            success=True,
        )

    def _analyze_with_llm(self, text: str) -> SentimentResult:
        """使用 LLM 进行情感分析"""
        # 这里可以实现 LLM 调用
        # 目前回退到规则分析
        logger.debug("LLM 分析未实现，使用规则分析")
        return self._analyze_with_rules(text)


# 全局实例
_sentiment_analyzer = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """获取全局情感分析器实例"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer


def analyze_sentiment(text: str) -> SentimentResult:
    """
    便捷函数：分析单个文本情感

    Args:
        text: 待分析文本

    Returns:
        情感分析结果
    """
    analyzer = get_sentiment_analyzer()
    return analyzer.analyze(text)


def analyze_sentiment_batch(texts: List[str]) -> BatchSentimentResult:
    """
    便捷函数：批量分析文本情感

    Args:
        texts: 文本列表

    Returns:
        批量分析结果
    """
    analyzer = get_sentiment_analyzer()
    return analyzer.analyze_batch(texts)
