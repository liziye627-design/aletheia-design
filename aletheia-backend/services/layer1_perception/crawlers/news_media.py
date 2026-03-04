"""
国际新闻媒体RSS爬虫
支持: Reuters, AP News, BBC, Guardian, 财新, 澎湃
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from .enhanced_base import EnhancedBaseCrawler
import feedparser
from utils.logging import logger


class NewsMediaCrawler(EnhancedBaseCrawler):
    """新闻媒体RSS爬虫基类"""

    def __init__(
        self,
        source_name: str,
        rss_url: str,
        backup_rss_urls: Optional[List[str]] = None,
        rate_limit: int = 10,
    ):
        """
        初始化新闻媒体爬虫

        Args:
            source_name: 媒体名称
            rss_url: RSS Feed URL
            rate_limit: 速率限制
        """
        super().__init__(
            platform_name=f"news_{source_name}",
            rate_limit=rate_limit,
            max_retries=3,
        )
        self.source_name = source_name
        self.rss_url = rss_url
        self.backup_rss_urls = [
            str(url).strip()
            for url in ([rss_url] + list(backup_rss_urls or []))
            if str(url).strip()
        ]

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取新闻RSS

        Args:
            limit: 返回数量限制

        Returns:
            标准化新闻列表
        """
        try:
            results = []
            fetch_errors = []
            for feed_url in self.backup_rss_urls:
                try:
                    response = await self._make_request(
                        url=feed_url,
                        use_random_ua=True,
                    )
                    feed_content = response.get("text", "")
                    feed = feedparser.parse(feed_content)
                    if not getattr(feed, "entries", None):
                        continue
                    for entry in feed.entries[:limit]:
                        raw_data = {
                            "url": entry.get("link", ""),
                            "text": f"{entry.get('title', '')}\n{entry.get('summary', '')}",
                            "created_at": self._parse_date(entry.get("published", "")),
                            "author_name": self.source_name,
                            "author_id": self.source_name,
                            "followers": 0,
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                            "entities": self._extract_tags(entry),
                        }

                        standardized = self.standardize_item(raw_data)
                        standardized["metadata"]["source_type"] = "news_media"
                        standardized["metadata"]["source_agency"] = self.source_name
                        standardized["metadata"]["rss_url"] = feed_url
                        results.append(standardized)
                    if results:
                        break
                except Exception as feed_err:
                    fetch_errors.append(f"{feed_url}:{type(feed_err).__name__}")

            if results:
                logger.info(f"✅ {self.source_name}: fetched {len(results)} news items")
                return results
            if fetch_errors:
                logger.warning(
                    f"⚠️ {self.source_name}: all feed urls failed: {' | '.join(fetch_errors[:3])}"
                )
            return []

        except Exception as e:
            logger.error(f"❌ {self.source_name} RSS fetch error: {e}")
            return []

    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串"""
        try:
            from dateutil import parser

            dt = parser.parse(date_str)
            return dt.isoformat()
        except:
            return datetime.utcnow().isoformat()

    def _extract_tags(self, entry) -> List[str]:
        """提取标签"""
        tags = []
        if hasattr(entry, "tags"):
            tags = [tag.term for tag in entry.tags if hasattr(tag, "term")]
        return tags

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """新闻媒体不支持用户维度"""
        logger.warning(f"{self.source_name} does not support user posts")
        return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """新闻媒体不支持评论"""
        logger.warning(f"{self.source_name} does not support comments")
        return []


# 国际新闻媒体配置
INTERNATIONAL_NEWS_SOURCES = {
    "reuters": {
        "name": "Reuters",
        "rss_url": "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
        "backup_rss_urls": [
            "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=site:reuters.com+technology&hl=en-US&gl=US&ceid=US:en",
            "https://www.reuters.com/world/",
        ],
    },
    "ap": {
        "name": "AP News",
        "rss_url": "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "backup_rss_urls": [
            "https://feeds.apnews.com/rss/apf-topnews",
            "https://apnews.com/hub/ap-top-news",
        ],
    },
    "bbc": {
        "name": "BBC News",
        "rss_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "backup_rss_urls": [
            "https://feeds.bbci.co.uk/news/rss.xml",
        ],
    },
    "guardian": {
        "name": "The Guardian",
        "rss_url": "https://www.theguardian.com/world/rss",
        "backup_rss_urls": [
            "https://www.theguardian.com/international/rss",
        ],
    },
}

# 中国新闻媒体配置
CHINA_NEWS_SOURCES = {
    "caixin": {
        "name": "财新网",
        "rss_url": "https://news.google.com/rss/search?q=site:caixin.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "backup_rss_urls": [
            "https://www.caixin.com/rss/index.xml",
            "https://www.caixin.com/",
        ],
    },
    "thepaper": {
        "name": "澎湃新闻",
        "rss_url": "https://news.google.com/rss/search?q=site:thepaper.cn&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "backup_rss_urls": [
            "https://rsshub.app/thepaper/featured",
            "https://www.thepaper.cn/",
        ],
    },
}


class InternationalNewsManager:
    """国际新闻媒体管理器"""

    def __init__(self):
        self.crawlers = {}
        self._init_crawlers()

    def _init_crawlers(self):
        """初始化所有新闻媒体爬虫"""
        # 国际新闻
        for key, config in INTERNATIONAL_NEWS_SOURCES.items():
            try:
                self.crawlers[f"news_{key}"] = NewsMediaCrawler(
                    source_name=config["name"],
                    rss_url=config["rss_url"],
                    backup_rss_urls=config.get("backup_rss_urls"),
                )
                logger.info(f"✅ News source initialized: {config['name']}")
            except Exception as e:
                logger.warning(f"⚠️ {config['name']} init failed: {e}")

        # 中国新闻
        for key, config in CHINA_NEWS_SOURCES.items():
            try:
                self.crawlers[f"news_{key}"] = NewsMediaCrawler(
                    source_name=config["name"],
                    rss_url=config["rss_url"],
                    backup_rss_urls=config.get("backup_rss_urls"),
                )
                logger.info(f"✅ News source initialized: {config['name']}")
            except Exception as e:
                logger.warning(f"⚠️ {config['name']} init failed: {e}")

    async def fetch_all_news(
        self, limit_per_source: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """并行抓取所有新闻源"""
        tasks = {}
        for source_name, crawler in self.crawlers.items():
            tasks[source_name] = crawler.fetch_hot_topics(limit=limit_per_source)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        output = {}
        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"❌ {source_name} failed: {result}")
                output[source_name] = []
            else:
                output[source_name] = result

        return output

    def get_available_sources(self) -> List[str]:
        """获取可用的新闻源列表"""
        return list(self.crawlers.keys())
