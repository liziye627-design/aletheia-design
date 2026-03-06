# -*- coding: utf-8 -*-
"""
Inverse Index Builder
倒排索引构建器

参考: lzjqsdd/NewsSpider

核心功能:
- TF-IDF计算
- 倒排索引构建
- 全文检索
"""

import json
import pickle
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

import jieba
import numpy as np
from loguru import logger


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: int
    score: float
    title: str = ""
    content: str = ""
    url: str = ""
    snippet: str = ""
    highlight: str = ""


@dataclass
class IndexStats:
    """索引统计"""
    total_docs: int = 0
    total_terms: int = 0
    avg_doc_length: float = 0.0
    index_size_mb: float = 0.0


class InverseIndexBuilder:
    """
    倒排索引构建器

    基于TF-IDF算法构建倒排索引
    """

    def __init__(
        self,
        index_dir: str = "data/index",
        snippet_length: int = 200
    ):
        """
        初始化构建器

        Args:
            index_dir: 索引存储目录
            snippet_length: 摘要长度
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.snippet_length = snippet_length

        # 索引数据结构
        self.inverted_index: Dict[str, Dict[int, float]] = defaultdict(dict)  # term -> {doc_id: weight}
        self.document_lengths: Dict[int, int] = {}  # doc_id -> doc_length
        self.term_doc_freq: Dict[str, int] = defaultdict(int)  # term -> doc_freq
        self.total_docs: int = 0

        # 文档存储
        self.documents: Dict[int, Dict[str, Any]] = {}  # doc_id -> document

        # 词项ID映射
        self.term_to_id: Dict[str, int] = {}
        self.id_to_term: Dict[int, str] = {}
        self._term_counter = 0

        logger.info(f"InverseIndexBuilder initialized with index_dir={index_dir}")

    def _get_term_id(self, term: str) -> int:
        """获取词项ID"""
        if term not in self.term_to_id:
            self.term_to_id[term] = self._term_counter
            self.id_to_term[self._term_counter] = term
            self._term_counter += 1
        return self.term_to_id[term]

    def _tokenize(self, text: str) -> List[str]:
        """
        分词

        Args:
            text: 文本

        Returns:
            词项列表
        """
        if not text:
            return []
        return list(jieba.cut(text, cut_all=False))

    def _compute_tf(self, term_freq: int, doc_length: int) -> float:
        """
        计算TF值

        使用对数归一化: 1 + log(tf)
        """
        if term_freq == 0:
            return 0.0
        return 1 + math.log(term_freq)

    def _compute_idf(self, doc_freq: int) -> float:
        """
        计算IDF值

        使用平滑IDF: log(N / (1 + df)) + 1
        """
        return math.log(self.total_docs / (1 + doc_freq)) + 1

    def add_document(
        self,
        doc_id: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        添加文档到索引

        Args:
            doc_id: 文档ID
            content: 文档内容
            metadata: 元数据（title, url等）
        """
        # 分词
        terms = self._tokenize(content)
        if not terms:
            return

        # 存储文档
        self.documents[doc_id] = {
            "content": content,
            "terms": terms,
            "metadata": metadata or {},
        }

        # 计算词频
        term_freq = defaultdict(int)
        for term in terms:
            term_freq[term] += 1

        # 更新索引
        doc_length = len(terms)
        self.document_lengths[doc_id] = doc_length
        self.total_docs += 1

        for term, freq in term_freq.items():
            # TF值
            tf = self._compute_tf(freq, doc_length)
            self.inverted_index[term][doc_id] = tf
            # 文档频率
            self.term_doc_freq[term] += 1

    def build_index(self, documents: List[Dict[str, Any]]):
        """
        批量构建索引

        Args:
            documents: 文档列表，每个文档包含 doc_id, content, metadata
        """
        logger.info(f"Building index for {len(documents)} documents...")

        for doc in documents:
            doc_id = doc.get("doc_id") or doc.get("id")
            content = doc.get("content", "")
            metadata = {
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "publish_time": doc.get("publish_time") or doc.get("time", 0),
                "source": doc.get("source", ""),
            }
            self.add_document(doc_id, content, metadata)

        # 计算最终TF-IDF权重
        self._compute_tfidf()

        logger.info(f"Index built: {self.total_docs} docs, {len(self.inverted_index)} terms")

    def _compute_tfidf(self):
        """计算TF-IDF权重"""
        for term, doc_weights in self.inverted_index.items():
            doc_freq = self.term_doc_freq[term]
            idf = self._compute_idf(doc_freq)

            for doc_id in doc_weights:
                tf = doc_weights[doc_id]
                doc_weights[doc_id] = tf * idf

    def save_index(self, prefix: str = "index"):
        """
        保存索引到文件

        Args:
            prefix: 文件名前缀
        """
        # 保存倒排索引
        index_path = self.index_dir / f"{prefix}_inverted.pkl"
        with open(index_path, "wb") as f:
            pickle.dump(dict(self.inverted_index), f)

        # 保存文档
        docs_path = self.index_dir / f"{prefix}_docs.pkl"
        with open(docs_path, "wb") as f:
            pickle.dump(self.documents, f)

        # 保存词项映射
        term_map_path = self.index_dir / f"{prefix}_terms.json"
        with open(term_map_path, "w", encoding="utf-8") as f:
            json.dump({
                "term_to_id": self.term_to_id,
                "id_to_term": {str(k): v for k, v in self.id_to_term.items()},
            }, f, ensure_ascii=False)

        # 保存统计信息
        stats_path = self.index_dir / f"{prefix}_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_docs": self.total_docs,
                "total_terms": len(self.inverted_index),
                "avg_doc_length": np.mean(list(self.document_lengths.values())) if self.document_lengths else 0,
            }, f)

        logger.info(f"Index saved to {self.index_dir}")

    def load_index(self, prefix: str = "index"):
        """
        加载索引

        Args:
            prefix: 文件名前缀
        """
        # 加载倒排索引
        index_path = self.index_dir / f"{prefix}_inverted.pkl"
        if index_path.exists():
            with open(index_path, "rb") as f:
                self.inverted_index = defaultdict(dict, pickle.load(f))

        # 加载文档
        docs_path = self.index_dir / f"{prefix}_docs.pkl"
        if docs_path.exists():
            with open(docs_path, "rb") as f:
                self.documents = pickle.load(f)

        # 加载词项映射
        term_map_path = self.index_dir / f"{prefix}_terms.json"
        if term_map_path.exists():
            with open(term_map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.term_to_id = data.get("term_to_id", {})
                self.id_to_term = {int(k): v for k, v in data.get("id_to_term", {}).items()}

        # 更新统计
        self.total_docs = len(self.documents)

        logger.info(f"Index loaded: {self.total_docs} docs, {len(self.inverted_index)} terms")

    def get_stats(self) -> IndexStats:
        """获取索引统计"""
        # glob返回完整路径，直接使用即可
        total_size = 0.0
        if self.index_dir.exists():
            for f in self.index_dir.glob("index_*.pkl"):
                total_size += f.stat().st_size

        return IndexStats(
            total_docs=self.total_docs,
            total_terms=len(self.inverted_index),
            avg_doc_length=np.mean(list(self.document_lengths.values())) if self.document_lengths else 0.0,
            index_size_mb=total_size / (1024 * 1024),
        )


class NewsSearcher:
    """
    新闻搜索器

    基于倒排索引进行全文检索
    """

    def __init__(
        self,
        index_builder: Optional[InverseIndexBuilder] = None,
        index_dir: str = "data/index"
    ):
        """
        初始化搜索器

        Args:
            index_builder: 索引构建器实例
            index_dir: 索引目录
        """
        if index_builder:
            self.builder = index_builder
        else:
            self.builder = InverseIndexBuilder(index_dir=index_dir)
            self.builder.load_index()

        logger.info("NewsSearcher initialized")

    def _tokenize(self, query: str) -> List[str]:
        """分词查询"""
        return list(jieba.cut(query, cut_all=False))

    def _get_snippet(
        self,
        content: str,
        query_terms: List[str],
        length: int = 200
    ) -> str:
        """
        生成摘要

        Args:
            content: 文档内容
            query_terms: 查询词项
            length: 摘要长度

        Returns:
            摘要文本
        """
        if len(content) <= length:
            return content

        # 查找第一个查询词的位置
        for term in query_terms:
            pos = content.find(term)
            if pos != -1:
                start = max(0, pos - length // 3)
                end = min(len(content), start + length)
                return "..." + content[start:end] + "..."

        return content[:length] + "..."

    def _highlight(
        self,
        content: str,
        query_terms: List[str]
    ) -> str:
        """
        高亮查询词

        Args:
            content: 文档内容
            query_terms: 查询词项

        Returns:
            高亮后的内容
        """
        highlighted = content
        for term in query_terms:
            highlighted = highlighted.replace(term, f"**{term}**")
        return highlighted

    def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        sort_by_time: bool = False
    ) -> List[SearchResult]:
        """
        搜索

        Args:
            query: 查询文本
            limit: 返回数量
            offset: 偏移量
            sort_by_time: 是否按时间排序

        Returns:
            搜索结果列表
        """
        # 分词
        query_terms = self._tokenize(query)

        if not query_terms:
            return []

        # 查询倒排索引
        doc_scores: Dict[int, float] = defaultdict(float)

        for term in query_terms:
            if term in self.builder.inverted_index:
                for doc_id, weight in self.builder.inverted_index[term].items():
                    doc_scores[doc_id] += weight

        # 排序
        if sort_by_time:
            # 按时间排序
            sorted_docs = sorted(
                doc_scores.keys(),
                key=lambda x: self.builder.documents.get(x, {}).get("metadata", {}).get("publish_time", 0),
                reverse=True
            )
        else:
            # 按分数排序
            sorted_docs = sorted(
                doc_scores.keys(),
                key=lambda x: doc_scores[x],
                reverse=True
            )

        # 分页
        paginated_docs = sorted_docs[offset:offset + limit]

        # 构建结果
        results = []
        for doc_id in paginated_docs:
            doc = self.builder.documents.get(doc_id, {})
            metadata = doc.get("metadata", {})
            content = doc.get("content", "")

            result = SearchResult(
                doc_id=doc_id,
                score=doc_scores[doc_id],
                title=metadata.get("title", ""),
                content=content,
                url=metadata.get("url", ""),
                snippet=self._get_snippet(content, query_terms, self.builder.snippet_length),
                highlight=self._highlight(content[:self.builder.snippet_length], query_terms),
            )
            results.append(result)

        return results

    def search_by_phrase(self, phrase: str, limit: int = 10) -> List[SearchResult]:
        """
        短语搜索（取交集）

        Args:
            phrase: 搜索短语
            limit: 返回数量

        Returns:
            搜索结果列表
        """
        terms = self._tokenize(phrase)

        if not terms:
            return []

        # 获取每个词的文档集合
        doc_sets = []
        for term in terms:
            if term in self.builder.inverted_index:
                doc_sets.append(set(self.builder.inverted_index[term].keys()))

        if not doc_sets:
            return []

        # 取交集
        common_docs = set.intersection(*doc_sets) if doc_sets else set()

        # 计算分数并排序
        doc_scores = {}
        for doc_id in common_docs:
            score = sum(
                self.builder.inverted_index[term].get(doc_id, 0)
                for term in terms
            )
            doc_scores[doc_id] = score

        sorted_docs = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)[:limit]

        # 构建结果
        results = []
        for doc_id in sorted_docs:
            doc = self.builder.documents.get(doc_id, {})
            metadata = doc.get("metadata", {})
            content = doc.get("content", "")

            result = SearchResult(
                doc_id=doc_id,
                score=doc_scores[doc_id],
                title=metadata.get("title", ""),
                content=content,
                url=metadata.get("url", ""),
                snippet=self._get_snippet(content, terms, self.builder.snippet_length),
            )
            results.append(result)

        return results

    def count(self, query: str) -> int:
        """
        统计匹配文档数

        Args:
            query: 查询文本

        Returns:
            匹配文档数
        """
        terms = self._tokenize(query)

        if not terms:
            return 0

        doc_set = set()
        for term in terms:
            if term in self.builder.inverted_index:
                doc_set.update(self.builder.inverted_index[term].keys())

        return len(doc_set)

    def get_similar_documents(self, doc_id: int, limit: int = 5) -> List[SearchResult]:
        """
        获取相似文档

        Args:
            doc_id: 文档ID
            limit: 返回数量

        Returns:
            相似文档列表
        """
        if doc_id not in self.builder.documents:
            return []

        # 获取文档的词项
        doc_terms = self.builder.documents[doc_id].get("terms", [])

        # 基于词项查找相似文档
        doc_scores: Dict[int, float] = defaultdict(float)

        for term in doc_terms:
            if term in self.builder.inverted_index:
                for other_id, weight in self.builder.inverted_index[term].items():
                    if other_id != doc_id:
                        doc_scores[other_id] += weight

        # 排序并返回
        sorted_docs = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)[:limit]

        results = []
        for other_id in sorted_docs:
            doc = self.builder.documents.get(other_id, {})
            metadata = doc.get("metadata", {})

            result = SearchResult(
                doc_id=other_id,
                score=doc_scores[other_id],
                title=metadata.get("title", ""),
                content=doc.get("content", ""),
                url=metadata.get("url", ""),
            )
            results.append(result)

        return results


# 便捷函数
def build_news_index(
    documents: List[Dict[str, Any]],
    index_dir: str = "data/index"
) -> InverseIndexBuilder:
    """
    构建新闻索引

    Args:
        documents: 文档列表
        index_dir: 索引目录

    Returns:
        索引构建器
    """
    builder = InverseIndexBuilder(index_dir=index_dir)
    builder.build_index(documents)
    builder.save_index()
    return builder


def search_news(
    query: str,
    index_dir: str = "data/index",
    limit: int = 10
) -> List[SearchResult]:
    """
    搜索新闻

    Args:
        query: 查询文本
        index_dir: 索引目录
        limit: 返回数量

    Returns:
        搜索结果列表
    """
    searcher = NewsSearcher(index_dir=index_dir)
    return searcher.search(query, limit=limit)