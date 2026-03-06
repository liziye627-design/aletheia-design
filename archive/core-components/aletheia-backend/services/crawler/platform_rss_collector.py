# -*- coding: utf-8 -*-
"""
Platform RSS Collector
平台RSS采集器

基于 platform_capability_matrix.yaml 配置采集新闻
"""

import asyncio
import hashlib
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import jieba
from loguru import logger


@dataclass
class NewsArticle:
    """新闻文章"""
    title: str
    url: str
    content: str = ""
    summary: str = ""
    source: str = ""
    source_domain: str = ""
    publish_time: Optional[datetime] = None
    crawl_time: datetime = field(default_factory=datetime.now)
    article_id: str = ""

    # 质量标记
    is_trusted: bool = False
    keyword_hits: List[str] = field(default_factory=list)
    entity_hits: List[str] = field(default_factory=list)

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
            "is_trusted": self.is_trusted,
            "keyword_hits": self.keyword_hits,
            "entity_hits": self.entity_hits,
        }


@dataclass
class PlatformConfig:
    """平台配置"""
    name: str
    tier: str
    lang: str
    discovery_mode: str
    search_mode: str
    content_mode: str
    trusted_domains: List[str]
    timeout_ms: int
    retry_policy: Dict[str, Any]
    enabled_in_evidence_pool: bool
    status: str
    rss_urls: List[str] = field(default_factory=list)
    notes: str = ""
    issues: List[str] = field(default_factory=list)


class PlatformRSSCollector:
    """平台RSS采集器"""

    def __init__(
        self,
        config_path: str = "config/platform_capability_matrix.yaml",
        timeout: float = 20.0
    ):
        self.config_path = Path(config_path)
        self.timeout = timeout
        self.platforms: Dict[str, PlatformConfig] = {}
        self.trusted_domains: Set[str] = set()

        self._load_config()
        logger.info(f"PlatformRSSCollector initialized with {len(self.platforms)} platforms")

    def _load_config(self):
        """加载配置"""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        platforms = config.get("platforms", {})
        for name, pconfig in platforms.items():
            self.platforms[name] = PlatformConfig(
                name=name,
                tier=pconfig.get("tier", "background"),
                lang=pconfig.get("lang", "zh"),
                discovery_mode=pconfig.get("discovery_mode", "rss"),
                search_mode=pconfig.get("search_mode", "none"),
                content_mode=pconfig.get("content_mode", "direct_article"),
                trusted_domains=pconfig.get("trusted_domains", []),
                timeout_ms=pconfig.get("timeout_ms", 10000),
                retry_policy=pconfig.get("retry_policy", {"max_retries": 2}),
                enabled_in_evidence_pool=pconfig.get("enabled_in_evidence_pool", False),
                status=pconfig.get("status", "observe"),
                rss_urls=pconfig.get("rss_urls", []),
                notes=pconfig.get("notes", ""),
                issues=pconfig.get("issues", []),
            )

            # 收集可信域名
            for domain in pconfig.get("trusted_domains", []):
                self.trusted_domains.add(domain.lower())

    def get_stable_platforms(self) -> List[str]:
        """获取稳定平台列表"""
        return [
            name for name, config in self.platforms.items()
            if config.status == "stable" and config.enabled_in_evidence_pool
        ]

    def get_platforms_for_evidence(self) -> List[str]:
        """获取可用于证据池的平台"""
        return [
            name for name, config in self.platforms.items()
            if config.enabled_in_evidence_pool and config.status in ("stable", "observe")
        ]

    async def fetch_rss(
        self,
        url: str,
        platform: str,
        client: httpx.AsyncClient
    ) -> List[NewsArticle]:
        """获取单个RSS源"""
        articles = []

        try:
            response = await client.get(url, timeout=self.timeout)
            response.raise_for_status()

            # 解析XML
            content = response.text
            if not ('<rss' in content.lower() or '<?xml' in content.lower()):
                logger.warning(f"[{platform}] Not a valid RSS feed: {url}")
                return articles

            root = ET.fromstring(content)

            # 获取平台配置
            platform_config = self.platforms.get(platform)
            trusted_domains = platform_config.trusted_domains if platform_config else []

            # 解析文章
            for item in root.findall('.//item'):
                title = item.findtext('title', '').strip()
                link = item.findtext('link', '').strip()
                description = item.findtext('description', '').strip()
                pub_date = item.findtext('pubDate', '').strip()

                if not title or not link:
                    continue

                # 解析发布时间
                publish_time = None
                if pub_date:
                    try:
                        # 尝试多种日期格式
                        for fmt in [
                            "%a, %d %b %Y %H:%M:%S %z",
                            "%a, %d %b %Y %H:%M:%S GMT",
                            "%Y-%m-%d",
                            "%Y-%m-%d %H:%M:%S",
                        ]:
                            try:
                                publish_time = datetime.strptime(pub_date, fmt)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass

                # 提取域名
                source_domain = self._extract_domain(link)

                # 检查是否可信
                is_trusted = any(
                    domain in source_domain.lower()
                    for domain in trusted_domains
                ) if trusted_domains else False

                article = NewsArticle(
                    title=title,
                    url=link,
                    content=description,
                    summary=description[:300] if description else "",
                    source=platform,
                    source_domain=source_domain,
                    publish_time=publish_time,
                    is_trusted=is_trusted,
                )
                articles.append(article)

            logger.info(f"[{platform}] Fetched {len(articles)} articles from {url}")

        except httpx.TimeoutException:
            logger.warning(f"[{platform}] Timeout fetching {url}")
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{platform}] HTTP error {e.response.status_code} from {url}")
        except ET.ParseError as e:
            logger.warning(f"[{platform}] XML parse error from {url}: {e}")
        except Exception as e:
            logger.error(f"[{platform}] Error fetching {url}: {type(e).__name__}: {e}")

        return articles

    def _extract_domain(self, url: str) -> str:
        """从URL提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""

    async def collect_from_platform(
        self,
        platform: str,
        client: Optional[httpx.AsyncClient] = None,
        max_articles: int = 100
    ) -> List[NewsArticle]:
        """从单个平台采集"""
        config = self.platforms.get(platform)
        if not config:
            logger.warning(f"Unknown platform: {platform}")
            return []

        if not config.rss_urls:
            logger.warning(f"[{platform}] No RSS URLs configured")
            return []

        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(
                follow_redirects=True,
                verify=False,
                timeout=self.timeout
            )

        try:
            articles = []
            for url in config.rss_urls:
                feed_articles = await self.fetch_rss(url, platform, client)
                articles.extend(feed_articles)

                if len(articles) >= max_articles:
                    break

            # 去重
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    unique_articles.append(article)

            return unique_articles[:max_articles]

        finally:
            if own_client:
                await client.aclose()

    async def collect_all(
        self,
        platforms: Optional[List[str]] = None,
        max_per_platform: int = 50
    ) -> Dict[str, List[NewsArticle]]:
        """从多个平台采集"""
        if platforms is None:
            platforms = self.get_stable_platforms()

        results = {}

        async with httpx.AsyncClient(
            follow_redirects=True,
            verify=False,
            timeout=self.timeout
        ) as client:
            tasks = {
                platform: self.collect_from_platform(
                    platform, client, max_per_platform
                )
                for platform in platforms
            }

            for platform, task in tasks.items():
                articles = await task
                results[platform] = articles

        return results

    def search_by_keywords(
        self,
        articles: List[NewsArticle],
        keywords: List[str],
        min_hits: int = 1
    ) -> List[NewsArticle]:
        """关键词搜索"""
        results = []

        for article in articles:
            # 分词标题和内容
            text = f"{article.title} {article.content}"
            terms = set(jieba.cut(text))

            # 匹配关键词
            hits = [kw for kw in keywords if kw in terms or kw in text]

            if len(hits) >= min_hits:
                article.keyword_hits = hits
                results.append(article)

        # 按命中数排序
        results.sort(key=lambda x: len(x.keyword_hits), reverse=True)
        return results

    def filter_trusted(
        self,
        articles: List[NewsArticle]
    ) -> List[NewsArticle]:
        """过滤可信来源"""
        return [a for a in articles if a.is_trusted]

    def get_stats(self, articles: Dict[str, List[NewsArticle]]) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_articles": 0,
            "total_trusted": 0,
            "by_platform": {}
        }

        for platform, platform_articles in articles.items():
            count = len(platform_articles)
            trusted = sum(1 for a in platform_articles if a.is_trusted)

            stats["total_articles"] += count
            stats["total_trusted"] += trusted
            stats["by_platform"][platform] = {
                "count": count,
                "trusted": trusted,
                "trusted_rate": trusted / count if count > 0 else 0
            }

        return stats


async def main():
    """测试采集"""
    collector = PlatformRSSCollector()

    print("=" * 60)
    print("Platform RSS Collector Test")
    print("=" * 60)

    # 获取稳定平台
    stable = collector.get_stable_platforms()
    print(f"\nStable platforms: {stable}")

    # 采集测试
    print("\nCollecting from stable platforms...")
    results = await collector.collect_all(max_per_platform=20)

    # 显示结果
    for platform, articles in results.items():
        print(f"\n[{platform}] {len(articles)} articles")
        for i, article in enumerate(articles[:3]):
            print(f"  {i+1}. {article.title[:50]}...")
            print(f"     URL: {article.url[:60]}...")
            print(f"     Trusted: {article.is_trusted}")

    # 统计
    stats = collector.get_stats(results)
    print(f"\n" + "=" * 60)
    print(f"Total: {stats['total_articles']} articles, {stats['total_trusted']} trusted")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())