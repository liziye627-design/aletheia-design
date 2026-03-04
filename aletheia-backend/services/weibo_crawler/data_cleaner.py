# -*- coding: utf-8 -*-
"""
Weibo Data Cleaner
微博数据清洗模块

参考: stay-leave/weibo-public-opinion-analysis

核心功能:
- 去除URL链接
- 去除话题标签
- 去除@提及
- 去除表情符号
- 过滤短文本
- 中文分词
"""

import re
import jieba
import jieba.posseg as pseg
from typing import List, Set, Optional
from pathlib import Path
from loguru import logger


class WeiboDataCleaner:
    """
    微博数据清洗器

    用于清洗微博评论文本，提取有价值的内容
    """

    # 默认停用词
    DEFAULT_STOPWORDS = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "个",
        "啊", "吧", "呢", "吗", "哦", "哈", "嗯", "呀", "嘛", "罢",
        "可以", "这个", "那个", "什么", "怎么", "为什么", "哪", "哪里",
    }

    def __init__(
        self,
        stopwords_path: Optional[str] = None,
        user_dict_path: Optional[str] = None
    ):
        """
        初始化清洗器

        Args:
            stopwords_path: 停用词文件路径
            user_dict_path: 自定义词典路径
        """
        # 加载停用词
        self.stopwords = self.DEFAULT_STOPWORDS.copy()
        if stopwords_path and Path(stopwords_path).exists():
            self._load_stopwords(stopwords_path)

        # 加载自定义词典
        if user_dict_path and Path(user_dict_path).exists():
            jieba.load_userdict(user_dict_path)

        logger.info(f"WeiboDataCleaner initialized with {len(self.stopwords)} stopwords")

    def _load_stopwords(self, path: str):
        """加载停用词文件"""
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    self.stopwords.add(word)

    def remove_urls(self, text: str) -> str:
        """
        去除URL链接

        Args:
            text: 原始文本

        Returns:
            去除URL后的文本
        """
        # 匹配HTTP/HTTPS URL
        text = re.sub(r'https?://\S+', '', text)
        # 匹配www开头URL
        text = re.sub(r'www\.\S+', '', text)
        return text.strip()

    def remove_hashtags(self, text: str) -> str:
        """
        去除话题标签

        Args:
            text: 原始文本

        Returns:
            去除话题后的文本
        """
        # 匹配 #话题# 格式
        text = re.sub(r'#[^#]+#', '', text)
        # 匹配超话格式
        text = re.sub(r'#[^#]+\([^)]+\)#', '', text)
        return text.strip()

    def remove_mentions(self, text: str) -> str:
        """
        去除@提及

        Args:
            text: 原始文本

        Returns:
            去除提及后的文本
        """
        # 匹配 @用户名 格式
        text = re.sub(r'@[\w\u4e00-\u9fff]+', '', text)
        # 匹配回复格式
        text = re.sub(r'回复@[^:：]+[:：]?', '', text)
        return text.strip()

    def remove_emoji(self, text: str) -> str:
        """
        去除表情符号

        Args:
            text: 原始文本

        Returns:
            去除表情后的文本
        """
        # 匹配微博表情 [表情名] 格式
        text = re.sub(r'\[[\w\u4e00-\u9fff]+\]', '', text)
        # 匹配Unicode表情 - 修正范围，不包含中文字符
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U000024FF"  # 修正：只到U+24FF
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "]+",
            flags=re.UNICODE
        )
        text = emoji_pattern.sub('', text)
        return text.strip()

    def remove_kaomoji(self, text: str) -> str:
        """
        去除颜文字

        Args:
            text: 原始文本

        Returns:
            去除颜文字后的文本
        """
        # 常见颜文字模式
        kaomoji_patterns = [
            r'\(?[┌┐└┘│─╭╮╯╰╱╲╳]+\)?',  # 盒子风格
            r'[≧≦＞＜＝≡∧∨∩∪∈∋⊆⊇⊂⊃]',  # 数学符号
            r'[\(\[]?[\^\-\~\=\*oO•°]+[\)\]]?',  # 简单表情
            r'[_ㄏㄒㅜㅠㅇㅅㅂ]+',  # 韩文字符表情
        ]
        for pattern in kaomoji_patterns:
            text = re.sub(pattern, '', text)
        return text.strip()

    def remove_special_chars(self, text: str) -> str:
        """
        去除特殊字符

        Args:
            text: 原始文本

        Returns:
            去除特殊字符后的文本
        """
        # 保留中文、英文、数字、基本标点（更宽松）
        # 不移除感叹号、问号等常见标点
        text = re.sub(r'[^\u4e00-\u9fff\w\s，。！？、；：""''（）.!?,;:\-\(\)]', '', text)
        return text.strip()

    def remove_reposts(self, text: str) -> str:
        """
        去除转发标记

        Args:
            text: 原始文本

        Returns:
            去除转发标记后的文本
        """
        # 匹配 //用户名: 或 //@用户名: 格式
        text = re.sub(r'//[@\w\u4e00-\u9fff]+[:：]?', '', text)
        return text.strip()

    def normalize_whitespace(self, text: str) -> str:
        """
        规范化空白字符

        Args:
            text: 原始文本

        Returns:
            规范化后的文本
        """
        # 多个空格替换为单个
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def is_valid_text(self, text: str, min_length: int = 5) -> bool:
        """
        检查文本是否有效

        Args:
            text: 文本
            min_length: 最小长度

        Returns:
            是否有效
        """
        if not text or len(text.strip()) < min_length:
            return False
        # 检查是否全是标点或空白
        if not re.search(r'[\u4e00-\u9fff\w]', text):
            return False
        return True

    def clean_text(
        self,
        text: str,
        remove_url: bool = True,
        remove_hashtag: bool = True,
        remove_mention: bool = True,
        remove_emoji_flag: bool = True,
        remove_kaomoji_flag: bool = True,
        remove_special: bool = True,
        min_length: int = 5
    ) -> str:
        """
        清洗文本

        Args:
            text: 原始文本
            remove_url: 是否去除URL
            remove_hashtag: 是否去除话题
            remove_mention: 是否去除提及
            remove_emoji_flag: 是否去除表情
            remove_kaomoji_flag: 是否去除颜文字
            remove_special: 是否去除特殊字符
            min_length: 最小有效长度

        Returns:
            清洗后的文本
        """
        if not text:
            return ""

        # 按顺序执行清洗步骤
        if remove_url:
            text = self.remove_urls(text)
        if remove_hashtag:
            text = self.remove_hashtags(text)
        if remove_mention:
            text = self.remove_mentions(text)
        if remove_emoji_flag:
            text = self.remove_emoji(text)
        if remove_kaomoji_flag:
            text = self.remove_kaomoji(text)
        if remove_special:
            text = self.remove_special_chars(text)

        text = self.remove_reposts(text)
        text = self.normalize_whitespace(text)

        # 检查有效性
        if not self.is_valid_text(text, min_length):
            return ""

        return text

    def segment(
        self,
        text: str,
        remove_stopwords: bool = True,
        use_pos_filter: bool = False
    ) -> List[str]:
        """
        中文分词

        Args:
            text: 文本
            remove_stopwords: 是否去除停用词
            use_pos_filter: 是否使用词性过滤

        Returns:
            分词结果列表
        """
        if not text:
            return []

        if use_pos_filter:
            # 词性过滤：保留名词、动词、形容词
            allowed_pos = {'n', 'v', 'a', 'vn', 'an', 'nz', 'nr', 'ns'}
            words = []
            for word, pos in pseg.cut(text):
                if pos in allowed_pos and (not remove_stopwords or word not in self.stopwords):
                    words.append(word)
            return words
        else:
            # 普通分词
            words = list(jieba.cut(text))
            if remove_stopwords:
                words = [w for w in words if w not in self.stopwords and len(w.strip()) > 0]
            return words

    def clean_and_segment(
        self,
        text: str,
        **kwargs
    ) -> List[str]:
        """
        清洗并分词

        Args:
            text: 原始文本
            **kwargs: 清洗参数

        Returns:
            分词结果列表
        """
        cleaned = self.clean_text(text, **kwargs)
        return self.segment(cleaned)

    def batch_clean(
        self,
        texts: List[str],
        **kwargs
    ) -> List[str]:
        """
        批量清洗

        Args:
            texts: 文本列表
            **kwargs: 清洗参数

        Returns:
            清洗后的文本列表
        """
        return [self.clean_text(t, **kwargs) for t in texts]

    def batch_segment(
        self,
        texts: List[str],
        **kwargs
    ) -> List[List[str]]:
        """
        批量分词

        Args:
            texts: 文本列表
            **kwargs: 分词参数

        Returns:
            分词结果列表
        """
        return [self.segment(t, **kwargs) for t in texts]


# 便捷函数
def clean_weibo_text(text: str, min_length: int = 5) -> str:
    """
    清洗微博文本

    Args:
        text: 原始文本
        min_length: 最小有效长度

    Returns:
        清洗后的文本
    """
    cleaner = WeiboDataCleaner()
    return cleaner.clean_text(text, min_length=min_length)


def segment_chinese_text(text: str, remove_stopwords: bool = True) -> List[str]:
    """
    中文分词

    Args:
        text: 文本
        remove_stopwords: 是否去除停用词

    Returns:
        分词结果
    """
    cleaner = WeiboDataCleaner()
    return cleaner.segment(text, remove_stopwords=remove_stopwords)