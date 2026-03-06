# -*- coding: utf-8 -*-
"""
Local Sentiment Analyzer
本地情感分析器

参考: CodeAsPoetry/PublicOpinion (Attention+BiGRU架构)

核心功能:
- 情感分类 (正向/负向/中性)
- 批量处理
- 特征融合
"""

import re
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from loguru import logger

from .text_preprocessor import SentimentTextProcessor
from .emoji_processor import EmojiProcessor


@dataclass
class SentimentResult:
    """情感分析结果"""
    text: str
    sentiment: str  # positive, negative, neutral
    confidence: float
    scores: Dict[str, float]  # {positive: 0.x, negative: 0.x, neutral: 0.x}
    emoji_sentiment: float = 0.0
    features: Dict[str, Any] = None


class LocalSentimentAnalyzer:
    """
    本地情感分析器

    支持多种情感分析方法:
    1. 基于词典的方法
    2. 基于规则的方法
    3. 基于ML模型的方法 (如果提供模型文件)
    """

    # 默认情感词典
    POSITIVE_WORDS = {
        "好", "棒", "赞", "喜欢", "爱", "开心", "高兴", "快乐", "幸福", "美好",
        "优秀", "精彩", "完美", "出色", "厉害", "牛", "强", "棒极了", "太好了",
        "支持", "感谢", "感动", "温暖", "温馨", "甜蜜", "满足", "满意", "放心",
        "可爱", "漂亮", "美丽", "帅气", "酷", "有爱", "暖心", "治愈", "推荐",
        "值得", "不错", "挺好的", "还可以", "期待", "加油", "必胜", "胜利",
    }

    NEGATIVE_WORDS = {
        "差", "烂", "坏", "讨厌", "恨", "难过", "伤心", "痛苦", "失望", "糟糕",
        "垃圾", "废物", "恶心", "无聊", "烦", "讨厌", "厌恶", "可恨", "可恶",
        "骗", "坑", "假", "虚伪", "无耻", "下流", "卑鄙", "恶心", "呕",
        "不行", "不好", "太差", "很差", "差劲", "垃圾", "骗子", "投诉",
        "退货", "退款", "差评", "不满", "愤怒", "气愤", "无语", "心累",
    }

    # 程度副词
    INTENSIFIERS = {
        "很": 1.5, "非常": 1.8, "特别": 1.7, "极其": 2.0, "超级": 1.9,
        "太": 1.8, "真": 1.3, "实在": 1.4, "确实": 1.3, "真的": 1.4,
        "有点": 0.7, "稍微": 0.6, "略微": 0.5, "比较": 1.2, "相当": 1.5,
        "十分": 1.6, "格外": 1.5, "尤其": 1.6, "更为": 1.4, "更加": 1.5,
    }

    # 否定词
    NEGATORS = {"不", "没", "无", "非", "别", "莫", "未", "勿", "休", "不是"}

    def __init__(
        self,
        model_path: Optional[str] = None,
        vocab_path: Optional[str] = None,
        use_emoji: bool = True
    ):
        """
        初始化分析器

        Args:
            model_path: 模型文件路径 (pickle格式)
            vocab_path: 词汇表路径
            use_emoji: 是否使用Emoji情感
        """
        self.text_processor = SentimentTextProcessor()
        self.emoji_processor = EmojiProcessor() if use_emoji else None
        self.use_emoji = use_emoji

        # 模型相关
        self.model = None
        self.vectorizer = None

        if model_path and Path(model_path).exists():
            self._load_model(model_path)

        if vocab_path and Path(vocab_path).exists():
            self._load_vocab(vocab_path)

        logger.info(f"LocalSentimentAnalyzer initialized, model_loaded={self.model is not None}")

    def _load_model(self, path: str):
        """加载模型"""
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
                self.model = data.get("model")
                self.vectorizer = data.get("vectorizer")
            logger.info(f"Model loaded from {path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")

    def _load_vocab(self, path: str):
        """加载词汇表"""
        pass  # 预留接口

    def _segment(self, text: str) -> List[str]:
        """简单分词 (基于规则)"""
        # 使用jieba如果可用
        try:
            import jieba
            return list(jieba.cut(text))
        except ImportError:
            # 简单分词
            return list(text)

    def _count_sentiment_words(
        self,
        words: List[str]
    ) -> Tuple[int, int, List[str]]:
        """
        统计情感词

        Args:
            words: 词列表

        Returns:
            (正向词数, 负向词数, 匹配的词列表)
        """
        pos_count = 0
        neg_count = 0
        matched = []

        for i, word in enumerate(words):
            if word in self.POSITIVE_WORDS:
                # 检查否定词
                has_negator = any(
                    words[j] in self.NEGATORS
                    for j in range(max(0, i - 2), i)
                )
                if has_negator:
                    neg_count += 1
                    matched.append(f"不{word}")
                else:
                    # 检查程度副词
                    for j in range(max(0, i - 1), i):
                        if words[j] in self.INTENSIFIERS:
                            pos_count += self.INTENSIFIERS[words[j]]
                            matched.append(f"{words[j]}{word}")
                            break
                    else:
                        pos_count += 1
                        matched.append(word)

            elif word in self.NEGATIVE_WORDS:
                # 检查否定词 (否定+负向=正向)
                has_negator = any(
                    words[j] in self.NEGATORS
                    for j in range(max(0, i - 2), i)
                )
                if has_negator:
                    pos_count += 1
                    matched.append(f"不{word}")
                else:
                    neg_count += 1
                    matched.append(word)

        return pos_count, neg_count, matched

    def _rule_based_analyze(self, text: str) -> Dict[str, float]:
        """
        基于规则的情感分析

        Args:
            text: 文本

        Returns:
            情感分数字典
        """
        words = self._segment(text)
        pos_count, neg_count, matched = self._count_sentiment_words(words)

        # 计算情感分数
        total = pos_count + neg_count
        if total == 0:
            return {"positive": 0.33, "negative": 0.33, "neutral": 0.34}

        pos_ratio = pos_count / (total + 1)
        neg_ratio = neg_count / (total + 1)

        # 根据比例确定情感
        if pos_count > neg_count:
            positive = 0.4 + pos_ratio * 0.5
            negative = 0.1 + neg_ratio * 0.2
            neutral = 1 - positive - negative
        elif neg_count > pos_count:
            negative = 0.4 + neg_ratio * 0.5
            positive = 0.1 + pos_ratio * 0.2
            neutral = 1 - positive - negative
        else:
            neutral = 0.5
            positive = 0.25
            negative = 0.25

        return {
            "positive": min(1.0, positive),
            "negative": min(1.0, negative),
            "neutral": min(1.0, neutral),
        }

    def _model_based_analyze(self, text: str) -> Dict[str, float]:
        """
        基于模型的情感分析

        Args:
            text: 文本

        Returns:
            情感分数字典
        """
        if self.model is None or self.vectorizer is None:
            return self._rule_based_analyze(text)

        try:
            # 向量化
            vec = self.vectorizer.transform([text])

            # 预测
            if hasattr(self.model, "predict_proba"):
                proba = self.model.predict_proba(vec)[0]
                # 假设类别顺序: negative, positive (或根据实际模型调整)
                return {
                    "negative": float(proba[0]),
                    "positive": float(proba[1]),
                    "neutral": 0.0,
                }
            else:
                pred = self.model.predict(vec)[0]
                if pred == 1:
                    return {"positive": 0.9, "negative": 0.1, "neutral": 0.0}
                else:
                    return {"positive": 0.1, "negative": 0.9, "neutral": 0.0}

        except Exception as e:
            logger.error(f"Model prediction error: {e}")
            return self._rule_based_analyze(text)

    def analyze(
        self,
        text: str,
        use_emoji: Optional[bool] = None
    ) -> SentimentResult:
        """
        分析文本情感

        Args:
            text: 输入文本
            use_emoji: 是否使用Emoji情感

        Returns:
            情感分析结果
        """
        use_emoji = use_emoji if use_emoji is not None else self.use_emoji

        # 预处理
        processed_text = self.text_processor.preprocess(text)

        # 文本情感分析
        if self.model is not None:
            scores = self._model_based_analyze(processed_text)
        else:
            scores = self._rule_based_analyze(processed_text)

        # Emoji情感分析
        emoji_sentiment = 0.0
        if use_emoji and self.emoji_processor:
            emojis = self.emoji_processor.extract_emojis(text)
            emoji_sentiment = self.emoji_processor.calculate_emoji_sentiment_score(emojis)

            # 融合Emoji情感
            if emoji_sentiment > 0.3:
                scores["positive"] = min(1.0, scores["positive"] + 0.1)
                scores["negative"] = max(0.0, scores["negative"] - 0.1)
            elif emoji_sentiment < -0.3:
                scores["negative"] = min(1.0, scores["negative"] + 0.1)
                scores["positive"] = max(0.0, scores["positive"] - 0.1)

        # 归一化
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # 确定情感类别
        sentiment = max(scores, key=scores.get)
        confidence = scores[sentiment]

        # 特征统计
        features = self.text_processor.count_features(text)

        return SentimentResult(
            text=text,
            sentiment=sentiment,
            confidence=confidence,
            scores=scores,
            emoji_sentiment=emoji_sentiment,
            features=features,
        )

    def analyze_batch(
        self,
        texts: List[str],
        use_emoji: Optional[bool] = None
    ) -> List[SentimentResult]:
        """
        批量分析

        Args:
            texts: 文本列表
            use_emoji: 是否使用Emoji情感

        Returns:
            结果列表
        """
        return [self.analyze(text, use_emoji) for text in texts]

    def get_sentiment_distribution(
        self,
        results: List[SentimentResult]
    ) -> Dict[str, float]:
        """
        获取情感分布

        Args:
            results: 分析结果列表

        Returns:
            分布字典
        """
        if not results:
            return {"positive": 0.0, "negative": 0.0, "neutral": 0.0}

        counts = {"positive": 0, "negative": 0, "neutral": 0}
        for r in results:
            counts[r.sentiment] += 1

        total = len(results)
        return {k: v / total for k, v in counts.items()}

    def get_average_confidence(
        self,
        results: List[SentimentResult]
    ) -> float:
        """
        获取平均置信度

        Args:
            results: 分析结果列表

        Returns:
            平均置信度
        """
        if not results:
            return 0.0
        return sum(r.confidence for r in results) / len(results)


# 便捷函数
def analyze_sentiment(text: str) -> SentimentResult:
    """分析文本情感"""
    analyzer = LocalSentimentAnalyzer()
    return analyzer.analyze(text)


def analyze_sentiment_batch(texts: List[str]) -> List[SentimentResult]:
    """批量分析情感"""
    analyzer = LocalSentimentAnalyzer()
    return analyzer.analyze_batch(texts)