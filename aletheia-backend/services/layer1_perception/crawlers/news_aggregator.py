"""
新闻源聚合器 - 整合多家主流新闻媒体
"""

import os
import re
import random
import time
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import asyncio
from .base import BaseCrawler
from utils.logging import logger


NewsSource = Literal["toutiao", "sina", "qq", "163", "all"]


class NewsAggregator(BaseCrawler):
    """新闻源聚合器 - 整合今日头条、新浪新闻、腾讯新闻等"""

    def __init__(
        self,
        rate_limit: int = 10,  # 10 req/s
    ):
        """
        初始化新闻聚合器

        Args:
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="news_aggregator", rate_limit=rate_limit)
        self.session = None
        self.timeout_total = float(os.getenv("NEWS_AGGREGATOR_TIMEOUT_TOTAL", "20"))
        self.timeout_connect = float(
            os.getenv("NEWS_AGGREGATOR_CONNECT_TIMEOUT", "5")
        )
        self.timeout_read = float(os.getenv("NEWS_AGGREGATOR_READ_TIMEOUT", "20"))
        self.max_retries = int(os.getenv("NEWS_AGGREGATOR_MAX_RETRIES", "2"))
        self.retry_base_delay = float(
            os.getenv("NEWS_AGGREGATOR_RETRY_BASE_DELAY", "0.6")
        )
        self.retry_max_delay = float(
            os.getenv("NEWS_AGGREGATOR_RETRY_MAX_DELAY", "3.0")
        )
        self.failure_threshold = int(
            os.getenv("NEWS_AGGREGATOR_FAILURE_THRESHOLD", "2")
        )
        self.cooldown_seconds = float(
            os.getenv("NEWS_AGGREGATOR_COOLDOWN_SEC", "120")
        )
        self._source_failures: Dict[str, int] = {}
        self._source_blocked_until: Dict[str, float] = {}
        self._request_timeout = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Encoding": "gzip, deflate",
            }
            self._request_timeout = aiohttp.ClientTimeout(
                total=self.timeout_total,
                connect=self.timeout_connect,
                sock_read=self.timeout_read,
            )
            self.session = aiohttp.ClientSession(
                headers=headers, timeout=self._request_timeout
            )
            logger.info("✅ News aggregator session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ News aggregator session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    def _is_source_blocked(self, source: str) -> bool:
        blocked_until = self._source_blocked_until.get(source, 0.0)
        if not blocked_until:
            return False
        return time.monotonic() < blocked_until

    def _register_failure(self, source: Optional[str], reason: str) -> None:
        if not source:
            return
        count = self._source_failures.get(source, 0) + 1
        self._source_failures[source] = count
        if count >= self.failure_threshold:
            self._source_blocked_until[source] = time.monotonic() + self.cooldown_seconds
            logger.warning(
                f"⚠️ {source} hit failure threshold={count}, cooldown {self.cooldown_seconds:.0f}s"
            )

    def _register_success(self, source: Optional[str]) -> None:
        if not source:
            return
        self._source_failures[source] = 0
        if source in self._source_blocked_until:
            self._source_blocked_until.pop(source, None)

    def _next_backoff(self, attempt: int) -> float:
        base = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt))
        jitter = random.uniform(0.7, 1.3)
        return max(0.2, base * jitter)

    async def _make_request(
        self,
        url: str,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        source: Optional[str] = None,
    ) -> Optional[Dict]:
        """发起API请求"""
        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        if source and self._is_source_blocked(source):
            logger.warning(f"⚠️ {source} in cooldown, skip request")
            return None

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error = ""

        for attempt in range(self.max_retries + 1):
            await self.rate_limit_wait()
            try:
                async with self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._request_timeout,
                ) as response:
                    if response.status == 200:
                        self._register_success(source)
                        return await response.json()
                    body = await response.text()
                    last_error = f"status={response.status}, url={url}, body={body[:200]}"
                    if response.status in retryable_statuses and attempt < self.max_retries:
                        delay = self._next_backoff(attempt)
                        logger.warning(
                            f"⚠️ News API retryable status={response.status}, retry in {delay:.2f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error(f"❌ News API error: {last_error}")
                    self._register_failure(source, last_error)
                    return None
            except Exception as e:
                last_error = f"{type(e).__name__}: {e} (url={url})"
                low = str(e).lower()
                is_timeout = isinstance(e, (asyncio.TimeoutError, TimeoutError)) or "timeout" in low
                if is_timeout and attempt < self.max_retries:
                    delay = self._next_backoff(attempt)
                    logger.warning(
                        f"⚠️ News API timeout, retry in {delay:.2f}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(f"❌ Request failed: {last_error}")
                self._register_failure(source, last_error)
                return None

        if last_error:
            self._register_failure(source, last_error)
        return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取所有新闻源的热点新闻

        Args:
            limit: 返回数量限制

        Returns:
            热点新闻列表
        """
        logger.info(f"🔍 Fetching {limit} hot news from all sources...")

        # 并行抓取所有新闻源
        tasks = [
            self._fetch_toutiao_news(limit // 4),
            self._fetch_sina_news(limit // 4),
            self._fetch_qq_news(limit // 4),
            self._fetch_163_news(limit // 4),
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果
        all_news = []
        for results in results_list:
            if isinstance(results, Exception):
                logger.error(f"❌ Error fetching news: {results}")
                continue
            all_news.extend(results)

        # 按时间排序
        all_news.sort(key=lambda x: x["metadata"]["timestamp"], reverse=True)

        logger.info(f"✅ Fetched {len(all_news)} hot news from all sources")
        return all_news[:limit]

    async def _fetch_toutiao_news(self, limit: int) -> List[Dict[str, Any]]:
        """抓取今日头条新闻"""
        logger.info(f"📰 Fetching news from Toutiao...")

        # 今日头条新闻API（简化版）
        url = "https://www.toutiao.com/api/pc/feed/"
        params = {
            "category": "news_hot",
            "max_behot_time": 0,
        }

        data = await self._make_request(url, params=params, source="toutiao")
        if not data or "data" not in data:
            return []

        news_list = data.get("data", [])
        results = []

        for news in news_list[:limit]:
            if news.get("item_type") != 0:  # 只要新闻类型
                continue

            # 提取标签
            entities = []
            if news.get("tag"):
                entities.append(f"#{news['tag']}")
            if news.get("keywords"):
                keywords = news["keywords"].split(",")
                entities.extend([f"#{k}" for k in keywords[:3]])

            raw_data = {
                "url": f"https://www.toutiao.com{news.get('source_url', '')}",
                "text": news.get("title", ""),
                "images": [news.get("image_url", "")] if news.get("image_url") else [],
                "video": None,
                "created_at": datetime.fromtimestamp(
                    news.get("behot_time", 0)
                ).isoformat()
                if news.get("behot_time")
                else datetime.utcnow().isoformat(),
                "author_id": news.get("source", ""),
                "author_name": news.get("source", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": news.get("comment_count", 0),
                "shares": 0,
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["news_source"] = "toutiao"
            standardized["metadata"]["category"] = news.get("tag", "")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} news from Toutiao")
        return results

    async def _fetch_sina_news(self, limit: int) -> List[Dict[str, Any]]:
        """抓取新浪新闻"""
        logger.info(f"📰 Fetching news from Sina...")

        # 新浪新闻API（简化版）
        url = "https://feed.mix.sina.com.cn/api/roll/get"
        params = {
            "pageid": "153",
            "lid": "2509",
            "num": limit,
            "versionNumber": "1.2.4",
        }

        data = await self._make_request(url, params=params, source="sina")
        if not data or "result" not in data:
            return []

        news_list = data.get("result", {}).get("data", [])
        results = []

        for news in news_list[:limit]:
            # 提取分类标签
            entities = []
            if news.get("channel", {}).get("title"):
                entities.append(f"#{news['channel']['title']}")

            raw_data = {
                "url": news.get("url", ""),
                "text": news.get("title", ""),
                "images": [news.get("images", [])[0] if news.get("images") else ""],
                "video": None,
                "created_at": news.get("ctime", datetime.utcnow().isoformat()),
                "author_id": news.get("media_name", ""),
                "author_name": news.get("media_name", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["news_source"] = "sina"
            standardized["metadata"]["category"] = news.get("channel", {}).get(
                "title", ""
            )
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} news from Sina")
        return results

    async def _fetch_qq_news(self, limit: int) -> List[Dict[str, Any]]:
        """抓取腾讯新闻"""
        logger.info(f"📰 Fetching news from Tencent...")

        # 腾讯新闻API（简化版）
        url = "https://pacaio.match.qq.com/irs/rcd"
        params = {
            "cid": "137",
            "token": "d0f13d594edfc180f5bf6b845456f3ea",
            "num": limit,
        }

        data = await self._make_request(url, params=params, source="qq")
        if not data or "data" not in data:
            return []

        news_list = data.get("data", [])
        results = []

        for news in news_list[:limit]:
            # 提取标签
            entities = []
            if news.get("tags"):
                entities.extend([f"#{tag['name']}" for tag in news["tags"][:3]])

            # 提取图片
            images = []
            if news.get("thumbnails"):
                images = [img["url"] for img in news["thumbnails"][:1]]

            raw_data = {
                "url": news.get("vurl", ""),
                "text": news.get("title", ""),
                "images": images,
                "video": None,
                "created_at": news.get("publish_time", datetime.utcnow().isoformat()),
                "author_id": news.get("source", ""),
                "author_name": news.get("source", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": news.get("commentNum", 0),
                "shares": 0,
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["news_source"] = "qq"
            standardized["metadata"]["category"] = news.get("category", "")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} news from Tencent")
        return results

    async def _fetch_163_news(self, limit: int) -> List[Dict[str, Any]]:
        """抓取网易新闻"""
        logger.info(f"📰 Fetching news from NetEase...")

        # 网易新闻API（简化版）
        url = "https://c.m.163.com/nc/article/list/T1467284926140/0-20.html"

        data = await self._make_request(url, source="163")
        if not data:
            return []

        # 网易API返回格式特殊，key是动态的
        news_list = []
        for key, value in data.items():
            if isinstance(value, list):
                news_list = value
                break

        results = []

        for news in news_list[:limit]:
            # 提取标签
            entities = []
            if news.get("tag"):
                entities.append(f"#{news['tag']}")

            # 提取图片
            images = []
            if news.get("imgextra"):
                images = [img["imgsrc"] for img in news["imgextra"][:1]]
            elif news.get("imgsrc"):
                images = [news["imgsrc"]]

            raw_data = {
                "url": news.get("url", ""),
                "text": news.get("title", ""),
                "images": images,
                "video": None,
                "created_at": news.get("ptime", datetime.utcnow().isoformat()),
                "author_id": news.get("source", ""),
                "author_name": news.get("source", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": news.get("replyCount", 0),
                "shares": 0,
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["news_source"] = "163"
            standardized["metadata"]["category"] = news.get("tag", "")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} news from NetEase")
        return results

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """新闻聚合器不支持此功能"""
        logger.warning("⚠️ News aggregator does not support user posts")
        return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """新闻聚合器不支持此功能"""
        logger.warning("⚠️ News aggregator does not support comments")
        return []

    async def search_news(
        self, keyword: str, limit: int = 50, source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的新闻

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            source: 新闻源（toutiao/sina/qq/163），为空则全部

        Returns:
            新闻列表
        """
        logger.info(
            f"🔍 Searching news with keyword: {keyword} (source: {source or 'all'})..."
        )

        # 这里简化实现：抓取热点新闻后做关键词/词元匹配
        fetch_cap = max(20, int(os.getenv("NEWS_AGGREGATOR_SEARCH_FETCH_CAP", "80")))
        fetch_limit = min(fetch_cap, max(limit * 3, limit))
        all_news = await self.fetch_hot_topics(limit=fetch_limit)

        kw = str(keyword or "").strip().lower()
        kw_tokens = [t for t in re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", kw) if len(t) >= 2]
        kw_token_set = set(kw_tokens)

        def _score(news: Dict[str, Any]) -> float:
            blob = "\n".join(
                [
                    str(news.get("title") or ""),
                    str(news.get("content_text") or ""),
                    str(news.get("summary") or ""),
                    str(news.get("url") or ""),
                ]
            ).lower()
            if kw and kw in blob:
                return 1.0
            if not kw_token_set:
                return 0.0
            token_hits = sum(1 for t in kw_token_set if t in blob)
            return float(token_hits) / float(max(1, len(kw_token_set)))

        scored_news: List[tuple[float, Dict[str, Any]]] = []
        for news in all_news:
            if not isinstance(news, dict):
                continue
            score = _score(news)
            if score >= 0.2:
                scored_news.append((score, news))
        scored_news.sort(key=lambda x: x[0], reverse=True)
        filtered_news = [n for _s, n in scored_news]

        # 如果指定了新闻源，进一步过滤
        if source:
            filtered_news = [
                news
                for news in filtered_news
                if news["metadata"].get("news_source") == source
            ]

        for news in filtered_news:
            if not isinstance(news, dict):
                continue
            meta = news.get("metadata") if isinstance(news.get("metadata"), dict) else {}
            meta["keyword_match"] = True
            meta["keyword_match_score"] = round(_score(news), 4)
            news["metadata"] = meta

        logger.info(f"✅ Found {len(filtered_news)} news for keyword: {keyword}")
        return filtered_news[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
