# -*- coding: utf-8 -*-
"""
Local Sentiment Analysis Module
本地情感分析模块 - 基于前人项目经验实现

功能:
1. 文本预处理
2. 情感分类
3. 批量处理
"""

from .analyzer import LocalSentimentAnalyzer
from .text_preprocessor import SentimentTextProcessor
from .emoji_processor import EmojiProcessor

__all__ = [
    "LocalSentimentAnalyzer",
    "SentimentTextProcessor",
    "EmojiProcessor",
]