# -*- coding: utf-8 -*-
"""
Hot News API Collector
热搜API采集器

支持平台:
- 澎湃新闻 (thepaper)
- 微博热搜 (weibo)
- 抖音热点 (douyin)
"""

import asyncio
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

import httpx
from loguru import logger


@dataclass
class HotNewsItem:
    """热搜条目"""
    title: str
    url: str
    mobile_url: str = ""
    hot_score: int = 0
    rank: int = 0
    source: str = ""
    pic: str = ""
    publish_time: str = ""
    crawl_time: datetime = field(default_factory=datetime.now)
    article_id: str = ""

    def __post_init__(self):
        if not self.article_id:
            self.article_id = hashlib.md5(f"{self.source}_{self.title}".encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "title": self.title,
            "url": self.url,
            "mobile_url": self.mobile_url,
            "hot_score": self.hot_score,
            "rank": self.rank,
            "source": self.source,
            "pic": self.pic,
            "publish_time": self.publish_time,
            "crawl_time": self.crawl_time.isoformat(),
        }


class HotNewsCollector:
    """热搜API采集器"""

    # API端点配置
    API_ENDPOINTS = {
        "thepaper": {
            "name": "澎湃新闻",
            "url": "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar",
            "method": "GET",
            "trusted_domain": "thepaper.cn",
            "data_path": "data.hotNews",  # JSON路径
            "title_field": "name",
            "url_field": "url",
        },
        "weibo": {
            "name": "微博热搜",
            "url": "https://weibo.com/ajax/side/hotSearch",
            "method": "GET",
            "trusted_domain": "weibo.com",
            "data_path": "data.realtime",
            "title_field": "note",
            "url_field": "query",
        },
    }

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        logger.info(f"HotNewsCollector initialized with {len(self.API_ENDPOINTS)} platforms")

    async def fetch_thepaper(
        self,
        client: httpx.AsyncClient
    ) -> List[HotNewsItem]:
        """获取澎湃新闻热榜"""
        items = []
        config = self.API_ENDPOINTS["thepaper"]

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = await client.get(config["url"], headers=headers)
            data = response.json()

            # 解析数据路径
            hot_news = data.get("data", {}).get("hotNews", [])

            for i, item in enumerate(hot_news):
                title = item.get(config["title_field"], "")
                url = item.get(config["url_field"], "")

                if not title:
                    continue

                # 构建完整URL
                if url and not url.startswith("http"):
                    url = f"https://www.thepaper.cn/{url}"

                hot_item = HotNewsItem(
                    title=title,
                    url=url,
                    hot_score=int(item.get("praiseTimes", 0) or 0),
                    rank=i + 1,
                    source="thepaper",
                )
                items.append(hot_item)

            logger.info(f"[澎湃新闻] Fetched {len(items)} hot news items")

        except Exception as e:
            logger.error(f"[澎湃新闻] Error: {type(e).__name__}: {str(e)[:50]}")

        return items

    async def fetch_weibo(
        self,
        client: httpx.AsyncClient
    ) -> List[HotNewsItem]:
        """获取微博热搜"""
        items = []
        config = self.API_ENDPOINTS["weibo"]

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://weibo.com",
            }
            response = await client.get(config["url"], headers=headers)
            data = response.json()

            if data.get("ok") == 1:
                hot_list = data.get("data", {}).get("realtime", [])

                for i, item in enumerate(hot_list):
                    title = item.get("note", "") or item.get("query", "")
                    query = item.get("query", "")

                    if not title:
                        continue

                    url = f"https://s.weibo.com/weibo?q={query}" if query else ""

                    hot_item = HotNewsItem(
                        title=title,
                        url=url,
                        hot_score=int(item.get("raw_hot", 0) or 0),
                        rank=i + 1,
                        source="weibo",
                    )
                    items.append(hot_item)

                logger.info(f"[微博热搜] Fetched {len(items)} hot news items")

        except Exception as e:
            logger.error(f"[微博热搜] Error: {type(e).__name__}: {str(e)[:50]}")

        return items

    async def fetch_douyin(
        self,
        client: httpx.AsyncClient
    ) -> List[HotNewsItem]:
        """获取抖音热点"""
        items = []
        config = self.API_ENDPOINTS["douyin"]

        try:
            response = await client.post(config["url"])
            data = response.json()

            if data.get("code") == 200:
                for i, item in enumerate(data.get("data", [])):
                    hot_item = HotNewsItem(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        mobile_url=item.get("mobileUrl", ""),
                        hot_score=int(item.get("hot", 0)),
                        rank=i + 1,
                        source="douyin",
                        pic=item.get("pic", ""),
                    )
                    items.append(hot_item)

                logger.info(f"[抖音热点] Fetched {len(items)} hot news items")

        except Exception as e:
            logger.error(f"[抖音热点] Error: {type(e).__name__}: {str(e)[:50]}")

        return items

    async def fetch_platform(
        self,
        platform: str,
        client: httpx.AsyncClient
    ) -> List[HotNewsItem]:
        """获取指定平台热搜"""
        if platform == "thepaper":
            return await self.fetch_thepaper(client)
        elif platform == "weibo":
            return await self.fetch_weibo(client)
        elif platform == "douyin":
            return await self.fetch_douyin(client)
        else:
            logger.warning(f"Unknown platform: {platform}")
            return []

    async def fetch_all(
        self,
        platforms: Optional[List[str]] = None
    ) -> Dict[str, List[HotNewsItem]]:
        """获取所有平台热搜"""
        if platforms is None:
            platforms = ["thepaper", "weibo", "douyin"]

        results = {}

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True
        ) as client:
            for platform in platforms:
                items = await self.fetch_platform(platform, client)
                results[platform] = items

        return results

    def get_stats(self, results: Dict[str, List[HotNewsItem]]) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_items": 0,
            "by_platform": {}
        }

        for platform, items in results.items():
            count = len(items)
            stats["total_items"] += count
            stats["by_platform"][platform] = {
                "count": count,
                "top_title": items[0].title if items else None,
                "top_hot": items[0].hot_score if items else 0,
            }

        return stats


async def main():
    """测试热搜采集"""
    collector = HotNewsCollector()

    print("=" * 60)
    print("热搜API采集器测试")
    print("=" * 60)

    # 测试单个平台
    print("\n[澎湃新闻] 测试...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        items = await collector.fetch_thepaper(client)
        print(f"  获取 {len(items)} 条热搜")
        for item in items[:5]:
            print(f"  {item.rank}. {item.title[:30]}... (热度: {item.hot_score})")

    # 测试所有平台
    print("\n" + "=" * 60)
    print("所有平台测试")
    print("=" * 60)

    results = await collector.fetch_all()

    for platform, items in results.items():
        print(f"\n[{platform}] {len(items)} 条热搜")
        for item in items[:3]:
            print(f"  {item.rank}. {item.title[:30]}... (热度: {item.hot_score})")

    # 统计
    stats = collector.get_stats(results)
    print(f"\n" + "=" * 60)
    print(f"总计: {stats['total_items']} 条热搜")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())