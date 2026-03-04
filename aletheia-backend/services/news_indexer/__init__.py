# -*- coding: utf-8 -*-
"""
News Indexer Module
新闻索引模块 - 基于前人项目经验实现

功能:
1. 中文分词处理
2. TF-IDF倒排索引构建
3. 全文检索
"""

from .inverse_index import InverseIndexBuilder, NewsSearcher
from .text_processor import TextProcessor

__all__ = [
    "InverseIndexBuilder",
    "NewsSearcher",
    "TextProcessor",
]