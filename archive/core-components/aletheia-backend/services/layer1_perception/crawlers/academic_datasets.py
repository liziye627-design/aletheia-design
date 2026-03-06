"""
学术数据集爬虫模块

支持的数据源:
1. GDELT Project - 全球事件、语言和基调数据库
2. Common Crawl - 大规模网页存档
3. OpenAlex - 开放学术论文和引用数据库

使用增强型基础爬虫,自动支持:
- 反爬虫(UA轮换、完整Header伪装)
- 性能优化(连接池、速率限制)
- 稳定性(指数退避重试、熔断器)
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode, quote

from .enhanced_base import EnhancedBaseCrawler
from utils.logging import logger


class GDELTCrawler(EnhancedBaseCrawler):
    """
    GDELT Project 爬虫

    数据源: The Global Database of Events, Language, and Tone
    - 监控全球广播、印刷和网络新闻
    - 每15分钟更新一次
    - 支持事件查询、主题查询、时间线分析

    API文档: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
    """

    BASE_URL = "https://api.gdeltproject.org/api/v2"

    def __init__(self):
        super().__init__(
            platform_name="gdelt",
            rate_limit=10,  # GDELT建议每秒不超过10次请求
            max_retries=3,
            enable_circuit_breaker=True,
        )
        self.logger = logger

    async def search_events(
        self,
        query: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        mode: str = "artlist",  # artlist | timeline | tonenews
        max_records: int = 250,
        source_country: Optional[str] = None,  # CN, US, GB等ISO代码
        theme: Optional[str] = None,  # TAX_FNCACT (金融活动) 等
    ) -> List[Dict[str, Any]]:
        """
        搜索GDELT事件

        Args:
            query: 搜索关键词(支持布尔运算符: AND, OR, NOT)
            start_date: 起始日期
            end_date: 结束日期
            mode: 查询模式
                - artlist: 文章列表
                - timeline: 时间线分析
                - tonenews: 基调新闻
            max_records: 最大结果数(最多250)
            source_country: 来源国家ISO代码
            theme: GDELT主题代码

        Returns:
            标准化的事件数据列表
        """
        params = {
            "query": query,
            "mode": mode,
            "maxrecords": min(max_records, 250),
            "format": "json",
        }

        # 构建时间范围
        if start_date and end_date:
            # GDELT使用YYYYMMDDHHmmss格式
            params["startdatetime"] = start_date.strftime("%Y%m%d%H%M%S")
            params["enddatetime"] = end_date.strftime("%Y%m%d%H%M%S")

        # 添加过滤器
        if source_country:
            params["sourcecountry"] = source_country
        if theme:
            params["theme"] = theme

        url = f"{self.BASE_URL}/doc/doc"

        try:
            response = await self._make_request(url, params=params)

            if mode == "artlist":
                articles = response.get("articles", [])
                return [self._standardize_article(article) for article in articles]
            elif mode == "timeline":
                timeline = response.get("timeline", [])
                return [self._standardize_timeline_point(point) for point in timeline]
            else:
                return [self.standardize_item(response)]

        except Exception as e:
            self.logger.error(f"GDELT事件搜索失败: {e}")
            return []

    async def get_trending_themes(
        self,
        timespan: str = "1d",  # 15min, 1h, 1d, 7d
        source_country: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取热门主题

        Args:
            timespan: 时间跨度 (15min/1h/1d/7d)
            source_country: 来源国家

        Returns:
            热门主题列表
        """
        # GDELT主题查询
        end_date = datetime.utcnow()

        # 根据timespan计算start_date
        timespan_map = {
            "15min": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
        }
        start_date = end_date - timespan_map.get(timespan, timedelta(days=1))

        # 使用空查询获取所有事件,通过主题聚合
        params = {
            "mode": "timelinevol",
            "startdatetime": start_date.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end_date.strftime("%Y%m%d%H%M%S"),
            "format": "json",
        }

        if source_country:
            params["sourcecountry"] = source_country

        url = f"{self.BASE_URL}/doc/doc"

        try:
            response = await self._make_request(url, params=params)
            timeline = response.get("timeline", [])

            # 按音量排序
            timeline_sorted = sorted(
                timeline, key=lambda x: x.get("Volume Intensity", 0), reverse=True
            )

            return [
                self._standardize_timeline_point(point)
                for point in timeline_sorted[:20]
            ]

        except Exception as e:
            self.logger.error(f"GDELT热门主题获取失败: {e}")
            return []

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = await self.get_trending_themes(timespan="1d")
        return items[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        # 学术/事件数据集无“用户发帖”概念，退化为关键词事件检索
        return await self.search_events(query=user_id, max_records=limit)

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        # 数据集不提供评论流
        return []

    def _standardize_article(self, article: Dict) -> Dict[str, Any]:
        """标准化GDELT文章数据"""
        return self.standardize_item(
            {
                "title": article.get("title", ""),
                "content": article.get(
                    "seendate", ""
                ),  # GDELT没有完整内容,使用发现日期
                "url": article.get("url", ""),
                "author": article.get("domain", ""),  # 使用域名作为来源
                "publish_time": article.get("seendate", ""),
                "metadata": {
                    "language": article.get("language", ""),
                    "domain": article.get("domain", ""),
                    "source_country": article.get("sourcecountry", ""),
                    "theme": article.get("theme", ""),
                    "tone": article.get("tone", 0),  # 情感基调 (-100到100)
                    "image_url": article.get("socialimage", ""),
                },
            }
        )

    def _standardize_timeline_point(self, point: Dict) -> Dict[str, Any]:
        """标准化GDELT时间线数据点"""
        return self.standardize_item(
            {
                "title": f"Volume at {point.get('date', '')}",
                "content": f"Event volume: {point.get('Volume Intensity', 0)}",
                "publish_time": point.get("date", ""),
                "metadata": {
                    "volume_intensity": point.get("Volume Intensity", 0),
                    "date": point.get("date", ""),
                },
            }
        )


class CommonCrawlCrawler(EnhancedBaseCrawler):
    """
    Common Crawl 爬虫

    数据源: 开放的网页存档库
    - 每月爬取数十亿网页
    - 提供索引API查询URL
    - 可下载原始HTML、提取的元数据

    API文档: https://commoncrawl.org/the-data/get-started/
    """

    INDEX_URL = "https://index.commoncrawl.org"
    CDX_API_URL = f"{INDEX_URL}/CC-MAIN-2024-10-index"  # 示例索引

    def __init__(self):
        super().__init__(
            platform_name="common_crawl",
            rate_limit=5,  # 建议较低速率
            max_retries=3,
            enable_circuit_breaker=True,
        )
        self.logger = logger

    async def get_available_indexes(self) -> List[str]:
        """
        获取可用的爬取索引列表

        Returns:
            索引ID列表 (例如: CC-MAIN-2024-10)
        """
        url = f"{self.INDEX_URL}/collinfo.json"

        try:
            response = await self._make_request(url)
            indexes = [item["id"] for item in response if "id" in item]
            return indexes

        except Exception as e:
            self.logger.error(f"Common Crawl索引获取失败: {e}")
            return []

    async def search_url(
        self,
        url_pattern: str,
        index_id: Optional[str] = None,
        match_type: str = "prefix",  # exact | prefix | host | domain
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        搜索URL存档记录

        Args:
            url_pattern: URL模式 (例如: "example.com/*")
            index_id: 索引ID (不指定则使用最新)
            match_type: 匹配类型
                - exact: 精确匹配
                - prefix: 前缀匹配
                - host: 主机匹配
                - domain: 域名匹配
            limit: 最大结果数

        Returns:
            URL存档记录列表
        """
        if not index_id:
            # 使用最新索引
            indexes = await self.get_available_indexes()
            if not indexes:
                return []
            index_id = indexes[0]

        params = {
            "url": url_pattern,
            "matchType": match_type,
            "output": "json",
            "limit": limit,
        }

        url = f"{self.INDEX_URL}/{index_id}-index"

        try:
            # CDX API返回NDJSON (每行一个JSON对象)
            response = await self._make_request(url, params=params)
            if isinstance(response, dict):
                response_text = str(response.get("text", ""))
            else:
                response_text = str(response or "")

            records = []
            for line in response_text.strip().split("\n"):
                if line:
                    try:
                        record = json.loads(line)
                        records.append(self._standardize_cdx_record(record))
                    except json.JSONDecodeError:
                        continue

            return records

        except Exception as e:
            self.logger.error(f"Common Crawl URL搜索失败: {e}")
            return []

    async def search_by_domain(
        self,
        domain: str,
        index_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        按域名搜索存档

        Args:
            domain: 域名 (例如: "reuters.com")
            index_id: 索引ID
            limit: 最大结果数

        Returns:
            该域名的存档URL列表
        """
        return await self.search_url(
            url_pattern=f"*.{domain}/*",
            index_id=index_id,
            match_type="domain",
            limit=limit,
        )

    def _standardize_cdx_record(self, record: Dict) -> Dict[str, Any]:
        """标准化CDX存档记录"""
        return self.standardize_item(
            {
                "title": record.get("url", ""),
                "content": f"Archived snapshot from {record.get('timestamp', '')}",
                "url": record.get("url", ""),
                "publish_time": self._parse_cdx_timestamp(record.get("timestamp", "")),
                "metadata": {
                    "mime_type": record.get("mime", ""),
                    "status_code": record.get("status", ""),
                    "digest": record.get("digest", ""),
                    "length": record.get("length", 0),
                    "offset": record.get("offset", 0),
                    "filename": record.get("filename", ""),
                    # 可用于下载原始内容: https://data.commoncrawl.org/{filename}
                },
            }
        )

    def _parse_cdx_timestamp(self, timestamp: str) -> str:
        """解析CDX时间戳 (YYYYMMDDHHmmss)"""
        try:
            if len(timestamp) == 14:
                dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                return dt.isoformat()
        except:
            pass
        return timestamp

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        # Common Crawl 不提供“热榜”，返回空并由上游执行回退
        return []

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        # 将 user_id 视为 domain 关键字进行检索
        return await self.search_by_domain(domain=user_id, limit=limit)

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return []


class OpenAlexCrawler(EnhancedBaseCrawler):
    """
    OpenAlex 爬虫

    数据源: 开放的学术图谱
    - 2.5亿+学术论文
    - 作者、机构、期刊、引用关系
    - 完全免费,无需API密钥(建议提供邮箱以获得更高速率限制)

    API文档: https://docs.openalex.org/
    """

    BASE_URL = "https://api.openalex.org"

    def __init__(self, email: Optional[str] = None):
        """
        Args:
            email: 联系邮箱(可选,但建议提供以获得更高速率限制)
        """
        super().__init__(
            platform_name="openalex",
            rate_limit=10 if not email else 100,  # 有邮箱可提升到100req/s
            max_retries=3,
            enable_circuit_breaker=True,
        )
        self.email = email
        self.logger = logger

    def _get_headers(self) -> Dict[str, str]:
        """添加邮箱到User-Agent"""
        headers = {
            "User-Agent": "Aletheia-OpenAlex-Crawler/1.0",
            "Accept": "application/json",
        }
        if self.email:
            headers["User-Agent"] += f"; mailto:{self.email}"
        return headers

    async def search_works(
        self,
        query: str,
        publication_year: Optional[int] = None,
        cited_by_count_min: Optional[int] = None,
        is_open_access: Optional[bool] = None,
        sort: str = "cited_by_count:desc",  # relevance_score:desc | publication_date:desc
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        搜索学术论文

        Args:
            query: 搜索关键词
            publication_year: 发表年份
            cited_by_count_min: 最小引用次数
            is_open_access: 是否仅开放获取
            sort: 排序方式
            limit: 最大结果数

        Returns:
            标准化的论文列表
        """
        # 构建过滤器
        filters = []
        if publication_year:
            filters.append(f"publication_year:{publication_year}")
        if cited_by_count_min:
            filters.append(f"cited_by_count:>{cited_by_count_min}")
        if is_open_access is not None:
            filters.append(f"is_oa:{str(is_open_access).lower()}")

        params = {
            "search": query,
            "sort": sort,
            "per-page": min(limit, 200),  # API最大200
        }

        if filters:
            params["filter"] = ",".join(filters)

        url = f"{self.BASE_URL}/works"

        try:
            response = await self._make_request(
                url, params=params, headers=self._get_headers()
            )

            works = response.get("results", [])
            return [self._standardize_work(work) for work in works]

        except Exception as e:
            self.logger.error(f"OpenAlex论文搜索失败: {e}")
            return []

    async def get_trending_topics(
        self,
        field: Optional[str] = None,  # computer-science, medicine等
        years_back: int = 1,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        获取热门研究主题

        Args:
            field: 研究领域
            years_back: 回溯年数
            limit: 最大结果数

        Returns:
            热门主题/论文列表
        """
        # 获取高引用论文作为热门主题指标
        current_year = datetime.now().year
        start_year = current_year - years_back

        filters = [f"publication_year:{start_year}-{current_year}"]
        if field:
            filters.append(
                f"primary_topic.domain.id:https://openalex.org/domains/{field}"
            )

        params = {
            "filter": ",".join(filters),
            "sort": "cited_by_count:desc",
            "per-page": limit,
        }

        url = f"{self.BASE_URL}/works"

        try:
            response = await self._make_request(
                url, params=params, headers=self._get_headers()
            )

            works = response.get("results", [])
            return [self._standardize_work(work) for work in works]

        except Exception as e:
            self.logger.error(f"OpenAlex热门主题获取失败: {e}")
            return []

    async def search_by_author(
        self,
        author_name: str,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        按作者搜索论文

        Args:
            author_name: 作者姓名
            limit: 最大结果数

        Returns:
            该作者的论文列表
        """
        params = {
            "filter": f"authorships.author.display_name:{author_name}",
            "sort": "cited_by_count:desc",
            "per-page": min(limit, 200),
        }

        url = f"{self.BASE_URL}/works"

        try:
            response = await self._make_request(
                url, params=params, headers=self._get_headers()
            )

            works = response.get("results", [])
            return [self._standardize_work(work) for work in works]

        except Exception as e:
            self.logger.error(f"OpenAlex作者搜索失败: {e}")
            return []

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.get_trending_topics(limit=limit)

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        return await self.search_by_author(author_name=user_id, limit=limit)

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return []

    def _standardize_work(self, work: Dict) -> Dict[str, Any]:
        """标准化OpenAlex论文数据"""
        # 提取作者列表
        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in work.get("authorships", [])
        ]

        # 提取主题
        topics = [topic.get("display_name", "") for topic in work.get("topics", [])]

        return self.standardize_item(
            {
                "title": work.get("title", ""),
                "content": work.get("abstract", "")
                or f"Topics: {', '.join(topics[:3])}",
                "url": work.get("doi", "") or work.get("id", ""),
                "author": ", ".join(authors[:3]),  # 前3位作者
                "publish_time": work.get("publication_date", ""),
                "metadata": {
                    "doi": work.get("doi", ""),
                    "publication_year": work.get("publication_year", 0),
                    "cited_by_count": work.get("cited_by_count", 0),
                    "is_open_access": work.get("open_access", {}).get("is_oa", False),
                    "oa_url": work.get("open_access", {}).get("oa_url", ""),
                    "topics": topics[:5],  # 前5个主题
                    "type": work.get("type", ""),
                    "venue": work.get("primary_location", {})
                    .get("source", {})
                    .get("display_name", ""),
                    "authors_full": authors,
                },
            }
        )


# 导出所有爬虫类
__all__ = [
    "GDELTCrawler",
    "CommonCrawlCrawler",
    "OpenAlexCrawler",
]
