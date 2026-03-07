# -*- coding: utf-8 -*-
"""
Multi-Source News Searcher
多源新闻搜索器

整合多个新闻搜索源：
- Tavily API
- 百度千帆 AI 搜索
- SerpAPI

实现多级去重策略，避免重复新闻
"""

import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse, unquote
from enum import Enum

import httpx
from loguru import logger


class SearchSource(Enum):
    """搜索来源枚举"""
    TAVILY = "tavily"
    BAIDU_QIANFAN = "baidu_qianfan"
    SERPAPI = "serpapi"
    GOOGLE_NEWS = "google_news"


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    url: str
    content: str = ""
    snippet: str = ""
    source: str = ""
    source_domain: str = ""
    publish_time: Optional[datetime] = None
    crawl_time: datetime = field(default_factory=datetime.now)
    
    # 来源标记
    search_source: SearchSource = SearchSource.GOOGLE_NEWS
    is_trusted: bool = False
    
    # 去重标记
    url_hash: str = ""
    title_hash: str = ""
    content_hash: str = ""
    simhash: str = ""
    
    # 合并标记
    duplicate_of: Optional[str] = None  # 重复的新闻ID
    merged_sources: List[SearchSource] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.url_hash:
            self.url_hash = self._compute_url_hash()
        if not self.title_hash:
            self.title_hash = self._compute_title_hash()
    
    def _compute_url_hash(self) -> str:
        """计算URL哈希"""
        normalized = self._normalize_url(self.url)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    
    def _compute_title_hash(self) -> str:
        """计算标题哈希"""
        normalized = self._normalize_title(self.title)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    
    def _normalize_url(self, url: str) -> str:
        """规范化URL"""
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip('/')
            
            # 移除常见跟踪参数
            tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'spm', 'from', 'share_token'}
            if parsed.query:
                params = []
                for param in parsed.query.split('&'):
                    if '=' in param:
                        key = param.split('=')[0]
                        if key not in tracking_params:
                            params.append(param)
                query = '&'.join(params) if params else ''
            else:
                query = ''
            
            return f"{parsed.scheme}://{netloc}{path}?{query}".rstrip('?')
        except Exception:
            return url
    
    def _normalize_title(self, title: str) -> str:
        """规范化标题"""
        # 移除来源后缀
        title = re.sub(r'\s*[-–—]\s*(新华社|人民网|央视网|澎湃新闻|财新网|BBC|路透社|AP News|Guardian).*$', '', title)
        # 移除多余空格
        title = re.sub(r'\s+', ' ', title).strip()
        return title
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "snippet": self.snippet,
            "source": self.source,
            "source_domain": self.source_domain,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "crawl_time": self.crawl_time.isoformat(),
            "search_source": self.search_source.value,
            "is_trusted": self.is_trusted,
            "url_hash": self.url_hash,
            "title_hash": self.title_hash,
            "content_hash": self.content_hash,
            "simhash": self.simhash,
            "duplicate_of": self.duplicate_of,
            "merged_sources": [s.value for s in self.merged_sources],
        }


class TavilySearcher:
    """Tavily API 搜索器"""
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.tavily.com/search"
    
    async def search(
        self,
        query: str,
        max_results: int = 20,
        days: int = 7
    ) -> List[NewsItem]:
        """执行搜索"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                    "include_raw_content": True,
                    "include_images": False,
                    "days": days,
                }
                
                response = await client.post(self.base_url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get("results", []):
                    news_item = NewsItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                        snippet=item.get("content", "")[:500],
                        source=item.get("source", ""),
                        source_domain=self._extract_domain(item.get("url", "")),
                        publish_time=self._parse_date(item.get("published_date")),
                        search_source=SearchSource.TAVILY,
                    )
                    results.append(news_item)
                
                logger.info(f"[Tavily] Found {len(results)} results for '{query}'")
        
        except Exception as e:
            logger.error(f"[Tavily] Search error: {type(e).__name__}: {str(e)[:50]}")
        
        return results
    
    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """解析日期"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            return None


class BaiduQianfanSearcher:
    """百度千帆 AI 搜索器 - 使用 AI Search Web Search API"""
    
    def __init__(self, access_key: str, timeout: float = 30.0):
        self.access_key = access_key
        self.timeout = timeout
        # 百度千帆 AI Search Web Search API 端点
        self.base_url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    
    async def search(
        self,
        query: str,
        max_results: int = 20,
        days: int = 7
    ) -> List[NewsItem]:
        """执行搜索"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 百度千帆 AI Search Web Search API 请求参数
                payload = {
                    "messages": [
                        {
                            "content": query,
                            "role": "user"
                        }
                    ],
                    "search_source": "baidu_search_v2",
                    "resource_type_filter": [{"type": "web", "top_k": max_results}],
                    "search_recency_filter": "year"
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.access_key}"
                }
                
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # 解析百度千帆返回的搜索结果
                # 根据响应结构解析结果 - 使用 references 字段
                if "references" in data:
                    for item in data["references"]:
                        news_item = NewsItem(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            content=item.get("content", ""),
                            snippet=item.get("content", "")[:200] + "..." if item.get("content") else "",
                            source=item.get("source", "百度"),
                            source_domain=self._extract_domain(item.get("url", "")),
                            publish_time=self._parse_date(item.get("date")),
                            search_source=SearchSource.BAIDU_QIANFAN,
                        )
                        results.append(news_item)
                
                logger.info(f"[Baidu Qianfan] Found {len(results)} results for '{query}'")
        
        except Exception as e:
            logger.error(f"[Baidu Qianfan] Search error: {type(e).__name__}: {str(e)}")
        
        return results
    
    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """解析日期"""
        if not date_str:
            return None
        try:
            # 尝试多种日期格式
            formats = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None


class SerpAPISearcher:
    """SerpAPI 搜索器"""
    
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://serpapi.com/search"
    
    async def search(
        self,
        query: str,
        max_results: int = 20,
        days: int = 7,
        engine: str = "google_news"
    ) -> List[NewsItem]:
        """执行搜索"""
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "api_key": self.api_key,
                    "q": query,
                    "engine": engine,
                    "num": max_results,
                }
                
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                # 解析 SerpAPI 返回的新闻结果
                if "news_results" in data:
                    for item in data["news_results"]:
                        news_item = NewsItem(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            content=item.get("snippet", ""),
                            snippet=item.get("snippet", ""),
                            source=item.get("source", ""),
                            source_domain=self._extract_domain(item.get("link", "")),
                            publish_time=self._parse_date(item.get("date")),
                            search_source=SearchSource.SERPAPI,
                        )
                        results.append(news_item)
                
                logger.info(f"[SerpAPI] Found {len(results)} results for '{query}'")
        
        except Exception as e:
            logger.error(f"[SerpAPI] Search error: {type(e).__name__}: {str(e)[:50]}")
        
        return results
    
    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """解析日期"""
        if not date_str:
            return None
        try:
            # SerpAPI 返回相对时间，如 "2 hours ago"
            if "ago" in date_str.lower():
                return None
            return datetime.fromisoformat(date_str)
        except Exception:
            return None


class MultiSourceDeduplicator:
    """多源去重器"""
    
    def __init__(
        self,
        url_exact_match: bool = True,
        title_similarity_threshold: float = 0.85,
        content_similarity_threshold: float = 0.80,
        simhash_threshold: int = 3,
    ):
        self.url_exact_match = url_exact_match
        self.title_similarity_threshold = title_similarity_threshold
        self.content_similarity_threshold = content_similarity_threshold
        self.simhash_threshold = simhash_threshold
        
        # 索引
        self._url_index: Dict[str, NewsItem] = {}
        self._title_index: Dict[str, NewsItem] = {}
        self._simhash_index: List[Tuple[str, NewsItem]] = []
    
    def compute_simhash(self, content: str) -> str:
        """计算 SimHash"""
        # 规范化内容
        content = re.sub(r'\s+', ' ', content).strip().lower()
        
        # 简单的字符级 n-gram
        tokens = []
        for i in range(len(content) - 1):
            tokens.append(content[i:i+2])
        
        # 计算 hash
        v = [0] * 64
        for token in tokens:
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
            for i in range(64):
                bit = (token_hash >> i) & 1
                v[i] += 1 if bit else -1
        
        # 生成最终 hash
        fingerprint = 0
        for i in range(64):
            if v[i] >= 0:
                fingerprint |= (1 << i)
        
        return format(fingerprint, '016x')
    
    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """计算汉明距离"""
        try:
            h1 = int(hash1, 16)
            h2 = int(hash2, 16)
            return bin(h1 ^ h2).count('1')
        except Exception:
            return 64
    
    def compute_title_similarity(self, title1: str, title2: str) -> float:
        """计算标题相似度（简单的 Jaccard 相似度）"""
        # 分词
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        # Jaccard 相似度
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def check_duplicate(
        self,
        item: NewsItem
    ) -> Tuple[bool, Optional[NewsItem], str]:
        """
        检查是否重复
        
        Returns:
            (is_duplicate, existing_item, duplicate_type)
        """
        # 1. URL 精确匹配
        if item.url_hash in self._url_index:
            return True, self._url_index[item.url_hash], "url_exact"
        
        # 2. 标题相似度
        for title_hash, existing_item in self._title_index.items():
            similarity = self.compute_title_similarity(item.title, existing_item.title)
            if similarity >= self.title_similarity_threshold:
                return True, existing_item, "title_similar"
        
        # 3. 内容 SimHash
        if item.content:
            item.simhash = self.compute_simhash(item.content)
            for simhash, existing_item in self._simhash_index:
                distance = self.hamming_distance(item.simhash, simhash)
                if distance <= self.simhash_threshold:
                    return True, existing_item, "content_similar"
        
        return False, None, "none"
    
    def add_item(self, item: NewsItem):
        """添加项目到索引"""
        self._url_index[item.url_hash] = item
        self._title_index[item.title_hash] = item
        
        if item.content and not item.simhash:
            item.simhash = self.compute_simhash(item.content)
            self._simhash_index.append((item.simhash, item))
    
    def deduplicate(
        self,
        items: List[NewsItem],
        merge_strategy: str = "keep_best"
    ) -> List[NewsItem]:
        """
        去重
        
        Args:
            items: 新闻列表
            merge_strategy: 合并策略
                - "keep_best": 保留最好的（优先级：可信来源 > 内容完整 > 发布时间早）
                - "merge_all": 合并所有来源信息
                - "keep_first": 保留第一个
        
        Returns:
            去重后的新闻列表
        """
        unique_items = []
        duplicate_groups = []
        
        for item in items:
            is_duplicate, existing_item, dup_type = self.check_duplicate(item)
            
            if is_duplicate and existing_item:
                # 记录重复
                duplicate_groups.append({
                    "original": existing_item,
                    "duplicate": item,
                    "type": dup_type,
                })
                
                # 根据策略处理
                if merge_strategy == "keep_best":
                    # 保留更好的
                    if self._is_better(item, existing_item):
                        # 替换
                        self._replace_item(existing_item, item)
                elif merge_strategy == "merge_all":
                    # 合并来源信息
                    existing_item.merged_sources.append(item.search_source)
                    if not existing_item.content and item.content:
                        existing_item.content = item.content
            else:
                # 添加到索引
                self.add_item(item)
                unique_items.append(item)
        
        logger.info(f"Deduplication: {len(items)} -> {len(unique_items)} items")
        logger.info(f"Duplicate groups: {len(duplicate_groups)}")
        
        return unique_items
    
    def _is_better(self, item1: NewsItem, item2: NewsItem) -> bool:
        """判断 item1 是否比 item2 更好"""
        # 优先级：可信来源 > 内容完整 > 发布时间早
        if item1.is_trusted and not item2.is_trusted:
            return True
        if not item1.is_trusted and item2.is_trusted:
            return False
        
        # 内容长度
        if len(item1.content) > len(item2.content) * 1.5:
            return True
        if len(item2.content) > len(item1.content) * 1.5:
            return False
        
        # 发布时间
        if item1.publish_time and item2.publish_time:
            return item1.publish_time < item2.publish_time
        
        return False
    
    def _replace_item(self, old_item: NewsItem, new_item: NewsItem):
        """替换项目"""
        # 更新索引
        del self._url_index[old_item.url_hash]
        del self._title_index[old_item.title_hash]
        
        # 保留合并的来源信息
        new_item.merged_sources = old_item.merged_sources + [old_item.search_source]
        new_item.merged_sources = list(set(new_item.merged_sources))
        
        # 添加新项目
        self.add_item(new_item)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "url_index_size": len(self._url_index),
            "title_index_size": len(self._title_index),
            "simhash_index_size": len(self._simhash_index),
        }


class MultiSourceNewsSearcher:
    """多源新闻搜索器"""
    
    # 可信域名列表
    TRUSTED_DOMAINS = {
        "xinhuanet.com", "news.cn", "people.com.cn", "cctv.com",
        "gov.cn", "thepaper.cn", "caixin.com", "jiemian.com",
        "reuters.com", "bbc.com", "apnews.com", "theguardian.com",
    }
    
    # 来源优先级（数字越小优先级越高）
    SOURCE_PRIORITY = {
        SearchSource.TAVILY: 1,
        SearchSource.BAIDU_QIANFAN: 2,
        SearchSource.SERPAPI: 3,
        SearchSource.GOOGLE_NEWS: 4,
    }
    
    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        baidu_qianfan_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.timeout = timeout
        
        # 初始化搜索器
        self.searchers = {}
        
        if tavily_api_key:
            self.searchers[SearchSource.TAVILY] = TavilySearcher(tavily_api_key, timeout)
        
        if baidu_qianfan_key:
            self.searchers[SearchSource.BAIDU_QIANFAN] = BaiduQianfanSearcher(baidu_qianfan_key, timeout)
        
        if serpapi_key:
            self.searchers[SearchSource.SERPAPI] = SerpAPISearcher(serpapi_key, timeout)
        
        # 去重器
        self.deduplicator = MultiSourceDeduplicator()
        
        logger.info(f"MultiSourceNewsSearcher initialized with {len(self.searchers)} searchers")
    
    async def search_all(
        self,
        query: str,
        max_results_per_source: int = 20,
        days: int = 7,
        merge_strategy: str = "keep_best",
    ) -> Dict[str, Any]:
        """
        从所有源搜索
        
        Args:
            query: 搜索查询
            max_results_per_source: 每个源的最大结果数
            days: 搜索天数
            merge_strategy: 合并策略
        
        Returns:
            搜索结果字典
        """
        all_items = []
        source_stats = {}
        
        # 并行搜索所有源
        tasks = []
        for source, searcher in self.searchers.items():
            task = searcher.search(query, max_results_per_source, days)
            tasks.append((source, task))
        
        # 等待所有搜索完成
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        # 收集结果
        for (source, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(f"[{source.value}] Search failed: {result}")
                source_stats[source.value] = {"count": 0, "error": str(result)}
                continue
            
            # 标记可信来源
            for item in result:
                item.is_trusted = item.source_domain in self.TRUSTED_DOMAINS
            
            all_items.extend(result)
            source_stats[source.value] = {"count": len(result)}
        
        # 去重
        unique_items = self.deduplicator.deduplicate(all_items, merge_strategy)
        
        # 按优先级排序
        unique_items.sort(key=lambda x: (
            not x.is_trusted,
            self.SOURCE_PRIORITY.get(x.search_source, 99),
            -len(x.content),
        ))
        
        # 统计
        stats = {
            "query": query,
            "total_raw_results": len(all_items),
            "unique_results": len(unique_items),
            "deduplication_rate": 1.0 - (len(unique_items) / len(all_items)) if all_items else 0.0,
            "source_stats": source_stats,
            "trusted_count": sum(1 for x in unique_items if x.is_trusted),
            "sources": list(set(str(x.source) for x in unique_items)),
            "domains": list(set(x.source_domain for x in unique_items)),
        }
        
        return {
            "stats": stats,
            "results": unique_items,
        }
    
    async def search_specific(
        self,
        query: str,
        sources: List[SearchSource],
        max_results_per_source: int = 20,
        days: int = 7,
    ) -> List[NewsItem]:
        """
        从指定源搜索
        
        Args:
            query: 搜索查询
            sources: 搜索源列表
            max_results_per_source: 每个源的最大结果数
            days: 搜索天数
        
        Returns:
            新闻列表
        """
        all_items = []
        
        for source in sources:
            if source not in self.searchers:
                logger.warning(f"Source {source.value} not available")
                continue
            
            searcher = self.searchers[source]
            results = await searcher.search(query, max_results_per_source, days)
            
            for item in results:
                item.is_trusted = item.source_domain in self.TRUSTED_DOMAINS
            
            all_items.extend(results)
        
        return all_items


async def main():
    """测试多源搜索"""
    import os
    
    # 从环境变量读取 API Keys
    tavily_key = os.getenv("TAVILY_API_KEY")
    baidu_key = os.getenv("BAIDU_QIANFAN_ACCESS_KEY")
    serpapi_key = os.getenv("SERPAPI_KEY")
    
    searcher = MultiSourceNewsSearcher(
        tavily_api_key=tavily_key,
        baidu_qianfan_key=baidu_key,
        serpapi_key=serpapi_key,
    )
    
    print("=" * 60)
    print("Multi-Source News Searcher Test")
    print("=" * 60)
    
    # 测试搜索
    query = "两会"
    print(f"\n[Query] {query}")
    
    result = await searcher.search_all(
        query=query,
        max_results_per_source=10,
        days=7,
        merge_strategy="keep_best",
    )
    
    stats = result["stats"]
    print(f"\nStatistics:")
    print(f"  Raw results: {stats['total_raw_results']}")
    print(f"  Unique results: {stats['unique_results']}")
    print(f"  Deduplication rate: {stats['deduplication_rate']:.2%}")
    print(f"  Trusted count: {stats['trusted_count']}")
    print(f"  Sources: {stats['source_stats']}")
    
    print(f"\nTop 10 results:")
    for i, item in enumerate(result["results"][:10]):
        trusted = "✓" if item.is_trusted else "✗"
        sources = ", ".join([s.value for s in item.merged_sources] + [item.search_source.value])
        print(f"  {i+1}. [{trusted}] [{item.search_source.value}] {item.title[:50]}...")
        print(f"     URL: {item.url[:60]}...")
        print(f"     Sources: {sources}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
