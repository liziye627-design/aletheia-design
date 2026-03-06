# -*- coding: utf-8 -*-
"""
Sentiment Text Processor
情感分析文本预处理器

参考: CodeAsPoetry/PublicOpinion

核心功能:
- 微博评论清洗
- 转载处理
- 正则过滤
"""

import re
from typing import List, Optional, Tuple
from loguru import logger


class SentimentTextProcessor:
    """
    情感分析文本预处理器

    针对中文社交媒体文本进行清洗和预处理
    """

    # 微博转载模式
    REPOST_PATTERN = re.compile(r'//[\s]*@.*?[\:\：]{1}')

    # @提及模式
    MENTION_PATTERN = re.compile(r'@[\w\u4e00-\u9fff_-]+')

    # 话题模式
    TOPIC_PATTERN = re.compile(r'#[^#]+#')

    # URL模式
    URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')

    # HTML标签模式
    HTML_PATTERN = re.compile(r'<[^>]+>')

    # 表情符号模式 (微博格式)
    WEIBO_EMOJI_PATTERN = re.compile(r'\[[\w\u4e00-\u9fff]+\]')

    def __init__(
        self,
        remove_repost: bool = True,
        remove_mention: bool = False,
        remove_topic: bool = False,
        remove_url: bool = True,
        remove_html: bool = True,
        min_length: int = 5
    ):
        """
        初始化处理器

        Args:
            remove_repost: 是否移除转载内容
            remove_mention: 是否移除@提及
            remove_topic: 是否移除话题标签
            remove_url: 是否移除URL
            remove_html: 是否移除HTML标签
            min_length: 最小文本长度
        """
        self.remove_repost = remove_repost
        self.remove_mention = remove_mention
        self.remove_topic = remove_topic
        self.remove_url = remove_url
        self.remove_html = remove_html
        self.min_length = min_length

        logger.info("SentimentTextProcessor initialized")

    def clean_repost(self, text: str) -> List[str]:
        """
        处理微博转载

        将转载内容分割成多条评论

        Args:
            text: 原始文本

        Returns:
            评论列表
        """
        # 按转载标记分割
        parts = re.split(self.REPOST_PATTERN, text)
        # 清理并过滤空内容
        comments = [p.strip() for p in parts if p.strip()]
        return comments

    def remove_mentions(self, text: str) -> str:
        """移除@提及"""
        return re.sub(self.MENTION_PATTERN, '', text).strip()

    def remove_topics(self, text: str) -> str:
        """移除话题标签"""
        return re.sub(self.TOPIC_PATTERN, '', text).strip()

    def remove_urls(self, text: str) -> str:
        """移除URL"""
        return re.sub(self.URL_PATTERN, '', text).strip()

    def remove_html_tags(self, text: str) -> str:
        """移除HTML标签"""
        return re.sub(self.HTML_PATTERN, '', text).strip()

    def remove_weibo_emoji(self, text: str) -> str:
        """移除微博格式表情"""
        return re.sub(self.WEIBO_EMOJI_PATTERN, '', text).strip()

    def normalize_whitespace(self, text: str) -> str:
        """规范化空白字符"""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def preprocess(self, text: str) -> str:
        """
        预处理文本

        Args:
            text: 原始文本

        Returns:
            处理后的文本
        """
        if not text:
            return ""

        # 移除HTML标签
        if self.remove_html:
            text = self.remove_html_tags(text)

        # 移除URL
        if self.remove_url:
            text = self.remove_urls(text)

        # 移除转载
        if self.remove_repost:
            comments = self.clean_repost(text)
            text = comments[0] if comments else ""

        # 移除话题
        if self.remove_topic:
            text = self.remove_topics(text)

        # 移除提及
        if self.remove_mention:
            text = self.remove_mentions(text)

        # 规范化空白
        text = self.normalize_whitespace(text)

        return text

    def is_valid_text(self, text: str) -> bool:
        """
        检查文本是否有效

        Args:
            text: 文本

        Returns:
            是否有效
        """
        if not text:
            return False
        if len(text) < self.min_length:
            return False
        # 检查是否包含中文
        if not re.search(r'[\u4e00-\u9fff]', text):
            return False
        return True

    def process_batch(
        self,
        texts: List[str],
        filter_invalid: bool = True
    ) -> List[Tuple[str, bool]]:
        """
        批量处理文本

        Args:
            texts: 文本列表
            filter_invalid: 是否过滤无效文本

        Returns:
            (处理后的文本, 是否有效) 元组列表
        """
        results = []
        for text in texts:
            processed = self.preprocess(text)
            is_valid = self.is_valid_text(processed)
            results.append((processed, is_valid))

        if filter_invalid:
            return [(t, v) for t, v in results if v]
        return results

    def extract_main_comment(self, text: str) -> str:
        """
        提取主要评论内容

        对于转载的评论，只取第一部分

        Args:
            text: 原始文本

        Returns:
            主要评论内容
        """
        if self.remove_repost:
            comments = self.clean_repost(text)
            return comments[0] if comments else ""
        return text

    def count_features(self, text: str) -> dict:
        """
        统计文本特征

        Args:
            text: 文本

        Returns:
            特征统计
        """
        return {
            "length": len(text),
            "has_repost": bool(self.REPOST_PATTERN.search(text)),
            "mention_count": len(self.MENTION_PATTERN.findall(text)),
            "topic_count": len(self.TOPIC_PATTERN.findall(text)),
            "has_url": bool(self.URL_PATTERN.search(text)),
            "emoji_count": len(self.WEIBO_EMOJI_PATTERN.findall(text)),
            "chinese_char_count": len(re.findall(r'[\u4e00-\u9fff]', text)),
        }


# 便捷函数
def preprocess_sentiment_text(text: str) -> str:
    """预处理情感分析文本"""
    processor = SentimentTextProcessor()
    return processor.preprocess(text)