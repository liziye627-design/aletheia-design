# -*- coding: utf-8 -*-
"""
Emoji Processor
Emoji处理器

参考: CodeAsPoetry/PublicOpinion

核心功能:
- 提取文本中的Emoji
- 分离Emoji和文本
- 构建Emoji特征向量
"""

import re
from typing import List, Dict, Tuple, Optional
from collections import Counter
from pathlib import Path
import json
from loguru import logger


class EmojiProcessor:
    """
    Emoji处理器

    处理中文社交媒体文本中的Emoji表情
    """

    # Unicode Emoji范围
    EMOJI_RANGES = [
        (0x1F600, 0x1F64F),  # Emoticons
        (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs
        (0x1F680, 0x1F6FF),  # Transport and Map
        (0x1F1E0, 0x1F1FF),  # Flags
        (0x2600, 0x26FF),    # Misc symbols
        (0x2700, 0x27BF),    # Dingbats
        (0xFE00, 0xFE0F),    # Variation Selectors
        (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
        (0x1FA00, 0x1FA6F),  # Chess Symbols
        (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
    ]

    # 表情情感映射 (正向/负向)
    EMOJI_SENTIMENT = {
        # 正向表情
        "😀": 1.0, "😃": 1.0, "😄": 1.0, "😁": 1.0, "😊": 0.8, "😇": 0.9,
        "🙂": 0.6, "🙃": 0.5, "😉": 0.7, "😌": 0.7, "😍": 1.0, "🥰": 1.0,
        "😘": 0.9, "😗": 0.7, "😙": 0.7, "😚": 0.7, "😋": 0.8, "😛": 0.7,
        "😜": 0.7, "🤪": 0.6, "😝": 0.7, "🤑": 0.5, "🤗": 0.8, "🤭": 0.6,
        "👍": 0.9, "👏": 0.9, "💪": 0.8, "🎉": 1.0, "🎊": 1.0, "💖": 1.0,
        "💗": 1.0, "💕": 0.9, "💞": 0.9, "💓": 0.9, "💝": 0.9, "❤️": 1.0,
        "🧡": 0.9, "💛": 0.8, "💚": 0.8, "💙": 0.8, "💜": 0.9, "🖤": 0.5,

        # 负向表情
        "😒": -0.7, "😓": -0.6, "😔": -0.7, "😕": -0.5, "😖": -0.7, "😣": -0.7,
        "😞": -0.8, "😟": -0.7, "😤": -0.8, "😠": -0.9, "😡": -1.0, "🤬": -1.0,
        "😢": -0.8, "😭": -0.9, "😩": -0.8, "😫": -0.8, "🥺": -0.6, "😦": -0.6,
        "😧": -0.7, "😨": -0.8, "😰": -0.8, "😱": -0.9, "🤯": -0.7, "💔": -1.0,
        "👎": -0.9, "👊": -0.6, "✊": -0.5, "🤬": -1.0,
    }

    def __init__(self, emoji_vocab_path: Optional[str] = None):
        """
        初始化处理器

        Args:
            emoji_vocab_path: Emoji词汇表路径
        """
        self.emoji_vocab: Dict[str, int] = {}
        self.reverse_vocab: Dict[int, str] = {}

        if emoji_vocab_path and Path(emoji_vocab_path).exists():
            self._load_vocab(emoji_vocab_path)

        logger.info(f"EmojiProcessor initialized with {len(self.EMOJI_SENTIMENT)} sentiment emojis")

    def _load_vocab(self, path: str):
        """加载Emoji词汇表"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.emoji_vocab = data.get("emoji_to_id", {})
            self.reverse_vocab = {int(k): v for k, v in data.get("id_to_emoji", {}).items()}

    def is_emoji(self, char: str) -> bool:
        """
        判断字符是否为Emoji

        Args:
            char: 单个字符

        Returns:
            是否为Emoji
        """
        code = ord(char)
        for start, end in self.EMOJI_RANGES:
            if start <= code <= end:
                return True
        return False

    def extract_emojis(self, text: str) -> List[str]:
        """
        提取文本中的Emoji

        Args:
            text: 输入文本

        Returns:
            Emoji列表
        """
        emojis = []
        for char in text:
            if self.is_emoji(char):
                emojis.append(char)
        return emojis

    def remove_emojis(self, text: str) -> str:
        """
        移除文本中的Emoji

        Args:
            text: 输入文本

        Returns:
            移除Emoji后的文本
        """
        result = []
        for char in text:
            if not self.is_emoji(char):
                result.append(char)
        return "".join(result)

    def separate_text_emoji(self, text: str) -> Tuple[str, List[str]]:
        """
        分离文本和Emoji

        Args:
            text: 输入文本

        Returns:
            (纯文本, Emoji列表)
        """
        pure_text = []
        emojis = []

        for char in text:
            if self.is_emoji(char):
                emojis.append(char)
            else:
                pure_text.append(char)

        return "".join(pure_text), emojis

    def get_emoji_sentiment(self, emoji: str) -> float:
        """
        获取Emoji的情感值

        Args:
            emoji: Emoji字符

        Returns:
            情感值 (-1.0 到 1.0)
        """
        return self.EMOJI_SENTIMENT.get(emoji, 0.0)

    def calculate_emoji_sentiment_score(self, emojis: List[str]) -> float:
        """
        计算Emoji列表的整体情感分数

        Args:
            emojis: Emoji列表

        Returns:
            平均情感分数
        """
        if not emojis:
            return 0.0

        scores = [self.get_emoji_sentiment(e) for e in emojis]
        return sum(scores) / len(scores)

    def build_emoji_features(
        self,
        emojis: List[str],
        max_length: int = 10
    ) -> Dict[str, any]:
        """
        构建Emoji特征

        Args:
            emojis: Emoji列表
            max_length: 最大长度

        Returns:
            特征字典
        """
        if not emojis:
            return {
                "count": 0,
                "unique_count": 0,
                "sentiment_score": 0.0,
                "indices": [],
                "top_emojis": [],
            }

        # 截断
        truncated = emojis[:max_length]

        # 统计
        counter = Counter(emojis)
        top_emojis = counter.most_common(5)

        # 索引
        indices = []
        for emoji in truncated:
            if emoji in self.emoji_vocab:
                indices.append(self.emoji_vocab[emoji])
            else:
                # 动态添加新Emoji
                new_id = len(self.emoji_vocab)
                self.emoji_vocab[emoji] = new_id
                self.reverse_vocab[new_id] = emoji
                indices.append(new_id)

        # 填充
        while len(indices) < max_length:
            indices.append(0)

        return {
            "count": len(emojis),
            "unique_count": len(counter),
            "sentiment_score": self.calculate_emoji_sentiment_score(emojis),
            "indices": indices,
            "top_emojis": [e[0] for e in top_emojis],
        }

    def process_text(
        self,
        text: str,
        max_emoji_length: int = 10
    ) -> Dict[str, any]:
        """
        处理文本

        Args:
            text: 输入文本
            max_emoji_length: 最大Emoji长度

        Returns:
            处理结果
        """
        pure_text, emojis = self.separate_text_emoji(text)
        features = self.build_emoji_features(emojis, max_emoji_length)

        return {
            "pure_text": pure_text,
            "emojis": emojis,
            "features": features,
        }

    def build_vocab_from_texts(
        self,
        texts: List[str],
        output_path: Optional[str] = None
    ) -> Dict[str, int]:
        """
        从文本构建Emoji词汇表

        Args:
            texts: 文本列表
            output_path: 输出路径

        Returns:
            Emoji到ID的映射
        """
        all_emojis = []
        for text in texts:
            all_emojis.extend(self.extract_emojis(text))

        unique_emojis = sorted(set(all_emojis))
        self.emoji_vocab = {e: i + 1 for i, e in enumerate(unique_emojis)}
        self.reverse_vocab = {i: e for e, i in self.emoji_vocab.items()}

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({
                    "emoji_to_id": self.emoji_vocab,
                    "id_to_emoji": {str(k): v for k, v in self.reverse_vocab.items()},
                }, f, ensure_ascii=False, indent=2)

        logger.info(f"Built emoji vocab with {len(self.emoji_vocab)} emojis")
        return self.emoji_vocab


# 便捷函数
def extract_emojis_from_text(text: str) -> List[str]:
    """提取文本中的Emoji"""
    processor = EmojiProcessor()
    return processor.extract_emojis(text)


def remove_emojis_from_text(text: str) -> str:
    """移除文本中的Emoji"""
    processor = EmojiProcessor()
    return processor.remove_emojis(text)


def get_emoji_sentiment_score(text: str) -> float:
    """获取文本中Emoji的情感分数"""
    processor = EmojiProcessor()
    emojis = processor.extract_emojis(text)
    return processor.calculate_emoji_sentiment_score(emojis)