# -*- coding: utf-8 -*-
"""
Official Site Crawler
官方站点爬虫

用于政府官方站点的新闻列表采集
支持增量抓取和本地索引
"""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger


@dataclass
class OfficialArticle:
    """官方文章"""
    title: str
    url: str
    content: str = ""
    summary: str = ""
    source: str = ""
    source_domain: str = ""
    publish_time: Optional[datetime] = None
    crawl_time: datetime = field(default_factory=datetime.now)
    article_id: str = ""
    category: str = ""

    def __post_init__(self):
        if not self.article_id:
            self.article_id = hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "summary": self.summary,
            "source": self.source,
            "source_domain": self.source_domain,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "crawl_time": self.crawl_time.isoformat(),
            "category": self.category,
        }


@dataclass
class SiteConfig:
    """站点配置"""
    name: str
    base_url: str
    list_pages: List[str]
    article_patterns: List[str] = field(default_factory=lambda: ['.htm', '.html', '.shtml'])
    exclude_patterns: List[str] = field(default_factory=lambda: ['javascript:', 'mailto:', '#'])
    encoding: str = "utf-8"
    timeout: float = 30.0
    trust_domain: bool = True


class OfficialSiteCrawler:
    """官方站点爬虫"""

    # 预定义站点配置
    SITE_CONFIGS = {
        "csrc": SiteConfig(
            name="证监会",
            base_url="https://www.csrc.gov.cn",
            list_pages=[
                "/csrc_new/",
                "/csrc_new/flk/",
            ],
            article_patterns=['.htm', '.html', '.shtml', '/content'],
        ),
        "mem": SiteConfig(
            name="应急管理部",
            base_url="https://www.mem.gov.cn",
            list_pages=[
                "/xw/",
            ],
            article_patterns=['.htm', '.html', '.shtml', '/content'],
        ),
    }

    def __init__(
        self,
        site_id: Optional[str] = None,
        config: Optional[SiteConfig] = None,
        timeout: float = 30.0
    ):
        if config:
            self.config = config
        elif site_id and site_id in self.SITE_CONFIGS:
            self.config = self.SITE_CONFIGS[site_id]
        else:
            raise ValueError(f"Unknown site_id: {site_id}")

        self.timeout = timeout
        self.base_url = self.config.base_url
        self.seen_urls: Set[str] = set()

        logger.info(f"OfficialSiteCrawler initialized for {self.config.name}")

    def _is_article_url(self, url: str) -> bool:
        """判断是否为文章URL"""
        url_lower = url.lower()

        # 排除模式
        for pattern in self.config.exclude_patterns:
            if pattern in url_lower:
                return False

        # 文章模式
        for pattern in self.config.article_patterns:
            if pattern in url_lower:
                return True

        return False

    def _extract_publish_time(self, text: str) -> Optional[datetime]:
        """从文本中提取发布时间"""
        # 常见日期格式
        patterns = [
            (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),
            (r'(\d{4})/(\d{2})/(\d{2})', '%Y/%m/%d'),
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', None),  # 中文格式
        ]

        for pattern, fmt in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    if fmt:
                        return datetime.strptime(match.group(0), fmt)
                    else:
                        # 中文格式
                        year, month, day = match.groups()
                        return datetime(int(year), int(month), int(day))
                except ValueError:
                    continue

        return None

    async def fetch_list_page(
        self,
        list_path: str,
        client: httpx.AsyncClient
    ) -> List[OfficialArticle]:
        """获取列表页文章"""
        articles = []
        list_url = urljoin(self.base_url, list_path)

        try:
            response = await client.get(list_url)
            response.raise_for_status()

            # 处理编码
            content = response.text
            soup = BeautifulSoup(content, 'html.parser')

            # 查找所有文章链接
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True)

                # 检查是否为文章URL
                if not self._is_article_url(href):
                    continue

                # 检查标题有效性
                if len(title) < 5:
                    continue

                # 构建完整URL
                full_url = urljoin(list_url, href)

                # 去重
                if full_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_url)

                # 提取发布时间（从父元素）
                parent_text = ''
                parent = a.find_parent(['li', 'div', 'tr'])
                if parent:
                    parent_text = parent.get_text()

                publish_time = self._extract_publish_time(parent_text)

                article = OfficialArticle(
                    title=title,
                    url=full_url,
                    source=self.config.name,
                    source_domain=urlparse(self.base_url).netloc,
                    publish_time=publish_time,
                    category=list_path.strip('/'),
                )
                articles.append(article)

            logger.info(f"[{self.config.name}] Found {len(articles)} articles from {list_path}")

        except httpx.HTTPStatusError as e:
            logger.warning(f"[{self.config.name}] HTTP {e.response.status_code} from {list_path}")
        except Exception as e:
            logger.error(f"[{self.config.name}] Error fetching {list_path}: {type(e).__name__}")

        return articles

    async def fetch_article_content(
        self,
        article: OfficialArticle,
        client: httpx.AsyncClient
    ) -> OfficialArticle:
        """获取文章正文"""
        try:
            response = await client.get(article.url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 移除脚本和样式
            for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
                tag.decompose()

            # 查找正文区域
            content_selectors = [
                {'name': 'div', 'class_': re.compile(r'content|article|text|TRS', re.I)},
                {'name': 'div', 'id': re.compile(r'content|article|text', re.I)},
                {'name': 'article'},
            ]

            content_text = ""
            for selector in content_selectors:
                content_div = soup.find(**selector)
                if content_div:
                    # 提取段落
                    paragraphs = content_div.find_all('p')
                    if paragraphs:
                        content_text = '\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    else:
                        content_text = content_div.get_text(strip=True)
                    break

            if not content_text:
                # 使用body内容
                body = soup.find('body')
                if body:
                    content_text = body.get_text(strip=True)[:5000]

            article.content = content_text
            article.summary = content_text[:300] if content_text else ""

            # 提取发布时间
            if not article.publish_time:
                time_selectors = [
                    {'name': 'span', 'class_': re.compile(r'date|time', re.I)},
                    {'name': 'div', 'class_': re.compile(r'date|time|info', re.I)},
                ]
                for selector in time_selectors:
                    time_elem = soup.find(**selector)
                    if time_elem:
                        article.publish_time = self._extract_publish_time(time_elem.get_text())
                        if article.publish_time:
                            break

        except Exception as e:
            logger.warning(f"[{self.config.name}] Error fetching article {article.url}: {type(e).__name__}")

        return article

    async def crawl(
        self,
        max_articles: int = 50,
        fetch_content: bool = True
    ) -> List[OfficialArticle]:
        """
        执行爬取

        Args:
            max_articles: 最大文章数
            fetch_content: 是否获取正文

        Returns:
            文章列表
        """
        all_articles = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            verify=False
        ) as client:
            # 获取所有列表页
            for list_page in self.config.list_pages:
                articles = await self.fetch_list_page(list_page, client)
                all_articles.extend(articles)

                if len(all_articles) >= max_articles:
                    break

            # 限制数量
            all_articles = all_articles[:max_articles]

            # 获取正文
            if fetch_content and all_articles:
                logger.info(f"[{self.config.name}] Fetching content for {len(all_articles)} articles...")

                for article in all_articles:
                    await self.fetch_article_content(article, client)

        logger.info(f"[{self.config.name}] Crawled {len(all_articles)} articles")
        return all_articles


class MultiSiteCrawler:
    """多站点爬虫"""

    def __init__(
        self,
        site_ids: Optional[List[str]] = None,
        timeout: float = 30.0
    ):
        if site_ids is None:
            site_ids = list(OfficialSiteCrawler.SITE_CONFIGS.keys())

        self.crawlers = {}
        for site_id in site_ids:
            if site_id in OfficialSiteCrawler.SITE_CONFIGS:
                self.crawlers[site_id] = OfficialSiteCrawler(site_id=site_id, timeout=timeout)

        logger.info(f"MultiSiteCrawler initialized for {len(self.crawlers)} sites")

    async def crawl_all(
        self,
        max_per_site: int = 20,
        fetch_content: bool = True
    ) -> Dict[str, List[OfficialArticle]]:
        """爬取所有站点"""
        results = {}

        for site_id, crawler in self.crawlers.items():
            try:
                articles = await crawler.crawl(
                    max_articles=max_per_site,
                    fetch_content=fetch_content
                )
                results[site_id] = articles
            except Exception as e:
                logger.error(f"Error crawling {site_id}: {e}")
                results[site_id] = []

        return results

    def get_stats(self, results: Dict[str, List[OfficialArticle]]) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_articles": 0,
            "by_site": {}
        }

        for site_id, articles in results.items():
            count = len(articles)
            with_content = sum(1 for a in articles if a.content)
            with_time = sum(1 for a in articles if a.publish_time)

            stats["total_articles"] += count
            stats["by_site"][site_id] = {
                "count": count,
                "with_content": with_content,
                "with_time": with_time,
            }

        return stats


async def main():
    """测试爬虫"""
    print("=" * 60)
    print("Official Site Crawler Test")
    print("=" * 60)

    # 测试单个站点
    print("\n[CSRC] 单站点测试...")
    crawler = OfficialSiteCrawler(site_id="csrc")
    articles = await crawler.crawl(max_articles=10, fetch_content=True)

    for i, article in enumerate(articles[:5]):
        print(f"\n  {i+1}. {article.title[:50]}...")
        print(f"     URL: {article.url}")
        print(f"     Time: {article.publish_time}")
        if article.content:
            print(f"     Content: {article.content[:100]}...")

    # 测试多站点
    print("\n" + "=" * 60)
    print("[MultiSite] 多站点测试...")
    print("=" * 60)

    multi = MultiSiteCrawler(site_ids=["csrc", "mem"])
    results = await multi.crawl_all(max_per_site=10, fetch_content=False)

    stats = multi.get_stats(results)
    print(f"\n总文章数: {stats['total_articles']}")
    for site_id, site_stats in stats['by_site'].items():
        print(f"  {site_id}: {site_stats['count']} articles")


if __name__ == "__main__":
    asyncio.run(main())