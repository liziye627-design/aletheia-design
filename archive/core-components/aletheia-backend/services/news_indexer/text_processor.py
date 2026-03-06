# -*- coding: utf-8 -*-
"""
Text Processor
文本处理模块

参考: lzjqsdd/NewsSpider

核心功能:
- 中文分词
- 文本预处理
- 文档分块存储
"""

import re
import json
import jieba
import linecache
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass
from loguru import logger


@dataclass
class NewsDocument:
    """新闻文档结构"""
    doc_id: int
    title: str
    content: str
    publish_time: int  # Unix时间戳
    url: str
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "publish_time": self.publish_time,
            "url": self.url,
            "source": self.source,
        }


class TextProcessor:
    """
    文本处理器

    处理中文新闻文本，支持分词和存储
    """

    def __init__(
        self,
        data_dir: str = "data/news",
        chunk_size: int = 100
    ):
        """
        初始化处理器

        Args:
            data_dir: 数据存储目录
            chunk_size: 每个文件的文档数
        """
        self.data_dir = Path(data_dir)
        self.chunk_size = chunk_size
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 初始化jieba分词
        jieba.initialize()
        logger.info(f"TextProcessor initialized with data_dir={data_dir}")

    def segment_text(self, text: str) -> str:
        """
        对文本进行分词

        Args:
            text: 原始文本

        Returns:
            分词后的文本（空格分隔）
        """
        if not text:
            return ""
        words = jieba.cut(text, cut_all=False)
        return " ".join(words)

    def preprocess_text(self, text: str) -> str:
        """
        文本预处理

        Args:
            text: 原始文本

        Returns:
            预处理后的文本
        """
        if not text:
            return ""

        # 去除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 去除特殊字符（保留中文、英文、数字）
        text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)

        return text.strip()

    def process_document(self, doc: Dict[str, Any]) -> NewsDocument:
        """
        处理单个文档

        Args:
            doc: 文档字典

        Returns:
            NewsDocument对象
        """
        # 预处理
        content = self.preprocess_text(doc.get("content", ""))
        title = self.preprocess_text(doc.get("title", ""))

        # 分词
        segmented_content = self.segment_text(content)

        return NewsDocument(
            doc_id=doc.get("doc_id", 0),
            title=title,
            content=segmented_content,
            publish_time=doc.get("time", 0) or doc.get("publish_time", 0),
            url=doc.get("url", ""),
            source=doc.get("source", ""),
        )

    def save_documents(
        self,
        documents: List[Dict[str, Any]],
        filename: str = "news.json"
    ) -> str:
        """
        保存文档到JSON文件

        Args:
            documents: 文档列表
            filename: 文件名

        Returns:
            文件路径
        """
        filepath = self.data_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            for doc in documents:
                processed = self.process_document(doc)
                f.write(json.dumps(processed.to_dict(), ensure_ascii=False) + "\n")

        logger.info(f"Saved {len(documents)} documents to {filepath}")
        return str(filepath)

    def save_documents_chunked(
        self,
        documents: List[Dict[str, Any]],
        prefix: str = "news"
    ) -> List[str]:
        """
        分块保存文档

        Args:
            documents: 文档列表
            prefix: 文件名前缀

        Returns:
            文件路径列表
        """
        filepaths = []
        chunk_index = 0

        for i in range(0, len(documents), self.chunk_size):
            chunk = documents[i:i + self.chunk_size]
            chunk_index = i // self.chunk_size + 1

            filename = f"{prefix}_{chunk_index}.json"
            filepath = self.save_documents(chunk, filename)
            filepaths.append(filepath)

        return filepaths

    def load_documents(
        self,
        filename: str = "news.json"
    ) -> Generator[NewsDocument, None, None]:
        """
        加载文档

        Args:
            filename: 文件名

        Yields:
            NewsDocument对象
        """
        filepath = self.data_dir / filename

        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    doc = json.loads(line.strip())
                    yield NewsDocument(
                        doc_id=doc.get("doc_id", line_num),
                        title=doc.get("title", ""),
                        content=doc.get("content", ""),
                        publish_time=doc.get("publish_time", 0) or doc.get("time", 0),
                        url=doc.get("url", ""),
                        source=doc.get("source", ""),
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Parse error at line {line_num}: {e}")

    def get_document_by_line(
        self,
        filename: str,
        line_number: int
    ) -> Optional[NewsDocument]:
        """
        按行号获取文档

        Args:
            filename: 文件名
            line_number: 行号（从1开始）

        Returns:
            NewsDocument对象或None
        """
        filepath = self.data_dir / filename

        if not filepath.exists():
            return None

        try:
            line = linecache.getline(str(filepath), line_number)
            if line:
                doc = json.loads(line.strip())
                return NewsDocument(
                    doc_id=doc.get("doc_id", line_number),
                    title=doc.get("title", ""),
                    content=doc.get("content", ""),
                    publish_time=doc.get("publish_time", 0) or doc.get("time", 0),
                    url=doc.get("url", ""),
                    source=doc.get("source", ""),
                )
        except Exception as e:
            logger.error(f"Get document error: {e}")

        return None

    def count_documents(self, filename: str = "news.json") -> int:
        """
        统计文档数量

        Args:
            filename: 文件名

        Returns:
            文档数量
        """
        filepath = self.data_dir / filename

        if not filepath.exists():
            return 0

        count = 0
        with open(filepath, "r", encoding="utf-8") as f:
            for _ in f:
                count += 1

        return count

    def build_corpus(
        self,
        filename: str = "news.json"
    ) -> List[str]:
        """
        构建语料库

        Args:
            filename: 文件名

        Returns:
            文档内容列表（已分词）
        """
        corpus = []

        for doc in self.load_documents(filename):
            if doc.content:
                corpus.append(doc.content)

        return corpus