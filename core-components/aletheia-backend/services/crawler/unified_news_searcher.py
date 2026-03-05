# -*- coding: utf-8 -*-
"""
Unified News Searcher
统一新闻搜索器

使用 Google News RSS 作为搜索引擎，支持：
- 关键词搜索
- 站点限定搜索
- 多来源聚合
"""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx
import xml.etree.ElementTree as ET
from loguru import logger


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    source: str = ""
    source_domain: str = ""
    publish_time: Optional[datetime] = None
    snippet: str = ""
    crawl_time: datetime = field(default_factory=datetime.now)
    article_id: str = ""

    # 来源标记
    is_trusted: bool = False
    from_google_news: bool = True

    def __post_init__(self):
        if not self.article_id:
            self.article_id = hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "source_domain": self.source_domain,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "snippet": self.snippet,
            "is_trusted": self.is_trusted,
            "from_google_news": self.from_google_news,
        }


@dataclass
class SearchConfig:
    """搜索配置"""
    trusted_domains: List[str] = field(default_factory=list)
    exclude_domains: List[str] = field(default_factory=list)
    max_results: int = 20
    time_range: str = ""  # "24h", "7d", "1m" 等


class GoogleNewsSearcher:
    """
    Google News RSS 搜索器

    使用 Google News RSS 接口进行新闻搜索
    无需API密钥，无需登录
    """

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(
        self,
        timeout: float = 30.0,
        trusted_domains: Optional[Set[str]] = None
    ):
        self.timeout = timeout
        self.trusted_domains = trusted_domains or set()

        logger.info(f"GoogleNewsSearcher initialized")

    def _build_search_url(
        self,
        query: str,
        site: Optional[str] = None,
        time_range: str = ""
    ) -> str:
        """构建搜索URL"""
        # 构建查询词
        search_query = query

        if site:
            search_query = f"{query} site:{site}"

        if time_range:
            search_query = f"{search_query} when:{time_range}"

        # URL编码
        encoded_query = quote(search_query)

        # 构建完整URL
        url = f"{self.BASE_URL}?q={encoded_query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"

        return url

    def _parse_publish_time(self, pub_date: str) -> Optional[datetime]:
        """解析发布时间"""
        if not pub_date:
            return None

        # 常见格式
        formats = [
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(pub_date.strip(), fmt)
            except ValueError:
                continue

        return None

    def _extract_domain(self, url: str) -> str:
        """从URL提取域名"""
        try:
            from urllib.parse import urlparse, parse_qs

            # Google News重定向URL
            if "news.google.com" in url:
                # 尝试从URL路径解析真实链接
                # 格式: /rss/articles/CBMi... 或 /__i/rss/rd/articles/...
                return "news.google.com"

            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""

    def _extract_source_from_title(self, title: str, source_elem: str) -> str:
        """从标题或source元素提取来源"""
        # 优先使用source元素
        if source_elem:
            # 清理source元素
            source = source_elem.strip()
            if source.startswith("http"):
                # 提取域名
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(source)
                    return parsed.netloc or source
                except:
                    pass
            return source

        # 从标题提取（格式: "标题 - 来源"）
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2:
                return parts[1].strip()

        return ""

    def _is_trusted(self, domain: str) -> bool:
        """检查是否为可信来源"""
        if not self.trusted_domains:
            return True

        domain_lower = domain.lower()
        for trusted in self.trusted_domains:
            # 支持双向部分匹配
            if trusted.lower() in domain_lower or domain_lower in trusted.lower():
                return True
        return False

    async def search(
        self,
        query: str,
        site: Optional[str] = None,
        time_range: str = "",
        max_results: int = 20,
        client: Optional[httpx.AsyncClient] = None
    ) -> List[SearchResult]:
        """
        执行搜索

        Args:
            query: 搜索关键词
            site: 限定站点
            time_range: 时间范围 (24h, 7d, 1m)
            max_results: 最大结果数
            client: HTTP客户端

        Returns:
            搜索结果列表
        """
        url = self._build_search_url(query, site, time_range)

        results = []
        own_client = client is None

        if own_client:
            client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # 解析RSS
            root = ET.fromstring(response.text)

            # 提取条目
            items = root.findall('.//item')[:max_results]

            for item in items:
                title = item.findtext('title', '')
                link = item.findtext('link', '')
                source = item.findtext('source', '')
                pub_date = item.findtext('pubDate', '')
                description = item.findtext('description', '')

                if not title or not link:
                    continue

                # 提取真实来源域名（从source元素或标题）
                real_source = self._extract_source_from_title(title, source)

                # 如果source是域名，使用它；否则从URL提取
                if real_source and "." in real_source:
                    domain = real_source
                else:
                    domain = self._extract_domain(link)
                    # 如果提取的是news.google.com，尝试从标题提取
                    if "news.google.com" in domain and " - " in title:
                        parts = title.rsplit(" - ", 1)
                        if len(parts) == 2:
                            domain = parts[1].strip()

                # 清理标题（移除 " - 来源" 后缀）
                clean_title = title.rsplit(" - ", 1)[0] if " - " in title else title

                # 创建结果
                result = SearchResult(
                    title=clean_title,
                    url=link,
                    source=real_source or source,
                    source_domain=domain,
                    publish_time=self._parse_publish_time(pub_date),
                    snippet=description,
                    is_trusted=self._is_trusted(domain),
                )
                results.append(result)

            logger.info(f"[Google News] Search '{query}' found {len(results)} results")

        except Exception as e:
            logger.error(f"[Google News] Search error: {type(e).__name__}: {str(e)[:50]}")

        finally:
            if own_client:
                await client.aclose()

        return results

    async def search_trusted_sources(
        self,
        query: str,
        trusted_sites: List[str],
        time_range: str = "",
        max_per_site: int = 5
    ) -> Dict[str, List[SearchResult]]:
        """
        搜索可信来源

        Args:
            query: 搜索关键词
            trusted_sites: 可信站点列表
            time_range: 时间范围
            max_per_site: 每站点最大结果数

        Returns:
            按站点分组的结果
        """
        results = {}

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True
        ) as client:
            for site in trusted_sites:
                site_results = await self.search(
                    query=query,
                    site=site,
                    time_range=time_range,
                    max_results=max_per_site,
                    client=client
                )
                results[site] = site_results

        return results

    async def search_all_sources(
        self,
        query: str,
        time_range: str = "",
        max_results: int = 30
    ) -> List[SearchResult]:
        """
        搜索所有来源（不限站点）
        """
        return await self.search(
            query=query,
            site=None,
            time_range=time_range,
            max_results=max_results
        )


class UnifiedNewsSearcher:
    """
    统一新闻搜索器

    整合多种搜索方式：
    - Google News RSS
    - 本地RSS索引
    - 官方站点爬虫
    """

    # 可信新闻源
    TRUSTED_NEWS_SITES = [
        "xinhuanet.com",
        "news.cn",
        "新华网",
        "people.com.cn",
        "chinanews.com.cn",
        "thepaper.cn",
        "澎湃新闻",
        "cctv.com",
        "央视网",
        "caixin.com",
        "财新",
        "gov.cn",
        "中国政府网",
        "bbc.com",
        "BBC",
        "reuters.com",
        "路透社",
    ]

    # 官方政府站点
    OFFICIAL_SITES = [
        "gov.cn",
        "csrc.gov.cn",
        "samr.gov.cn",
        "nhc.gov.cn",
        "mem.gov.cn",
    ]

    def __init__(
        self,
        timeout: float = 30.0
    ):
        self.timeout = timeout

        # 所有可信域名
        self.all_trusted = set(self.TRUSTED_NEWS_SITES + self.OFFICIAL_SITES)

        # Google News 搜索器
        self.google_searcher = GoogleNewsSearcher(
            timeout=timeout,
            trusted_domains=self.all_trusted
        )

        logger.info(f"UnifiedNewsSearcher initialized with {len(self.all_trusted)} trusted domains")

    async def search(
        self,
        query: str,
        sources: str = "all",  # "all", "news", "official"
        time_range: str = "",
        max_results: int = 20
    ) -> List[SearchResult]:
        """
        执行搜索

        Args:
            query: 搜索关键词
            sources: 来源类型 (all/news/official)
            time_range: 时间范围
            max_results: 最大结果数

        Returns:
            搜索结果列表
        """
        all_results = []

        # 根据来源类型选择站点
        if sources == "news":
            sites = self.TRUSTED_NEWS_SITES
        elif sources == "official":
            sites = self.OFFICIAL_SITES
        else:
            sites = None  # 搜索所有

        if sites:
            # 搜索指定站点
            site_results = await self.google_searcher.search_trusted_sources(
                query=query,
                trusted_sites=sites,
                time_range=time_range,
                max_per_site=max_results // len(sites) + 1
            )
            for site_results_list in site_results.values():
                all_results.extend(site_results_list)
        else:
            # 搜索所有来源
            all_results = await self.google_searcher.search_all_sources(
                query=query,
                time_range=time_range,
                max_results=max_results
            )

        # 去重
        seen_urls = set()
        unique_results = []
        for result in all_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        # 按可信度排序
        unique_results.sort(key=lambda x: (not x.is_trusted, x.title))

        return unique_results[:max_results]

    async def search_for_evidence(
        self,
        query: str,
        max_results: int = 30
    ) -> Dict[str, Any]:
        """
        为证据池搜索

        Args:
            query: 查询关键词
            max_results: 最大结果数

        Returns:
            包含统计信息的搜索结果
        """
        # 搜索所有可信来源
        results = await self.search(
            query=query,
            sources="all",
            time_range="7d",  # 最近7天
            max_results=max_results
        )

        # 统计
        trusted_count = sum(1 for r in results if r.is_trusted)
        sources = set(r.source_domain for r in results)

        return {
            "query": query,
            "total_results": len(results),
            "trusted_results": trusted_count,
            "unique_sources": len(sources),
            "sources": list(sources),
            "results": [r.to_dict() for r in results],
        }


async def main():
    """测试搜索功能"""
    searcher = UnifiedNewsSearcher()

    print("=" * 60)
    print("统一新闻搜索器测试")
    print("=" * 60)

    # 测试1：搜索"两会"
    print("\n[测试1] 搜索 '两会' - 新闻来源")
    results = await searcher.search(
        query="两会",
        sources="news",
        max_results=10
    )
    print(f"找到 {len(results)} 条结果")
    for r in results[:5]:
        trusted = "✓" if r.is_trusted else "✗"
        print(f"  [{trusted}] [{r.source_domain}] {r.title[:40]}...")

    # 测试2：搜索"福岛核事故"
    print("\n[测试2] 搜索 '日本福岛核事故' - 所有来源")
    evidence = await searcher.search_for_evidence(
        query="日本福岛核事故",
        max_results=15
    )
    print(f"统计: {evidence['total_results']} 条结果, {evidence['trusted_results']} 条可信")
    print(f"来源: {', '.join(evidence['sources'][:5])}")

    # 测试3：搜索特定站点
    print("\n[测试3] 搜索 '澎湃新闻两会' - 澎湃站点")
    gn = GoogleNewsSearcher()
    results = await gn.search(
        query="两会",
        site="thepaper.cn",
        max_results=5
    )
    print(f"澎湃新闻找到 {len(results)} 条")
    for r in results:
        print(f"  - {r.title[:50]}...")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())