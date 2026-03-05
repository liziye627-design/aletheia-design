"""
Twitter/X 爬虫 - 使用Twitter API v2
"""

import os
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
from urllib.parse import unquote
from .base import BaseCrawler
from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env


_AIOHTTP_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "CRAWLER_TRUST_ENV", True)),
    auto_disable_local_proxy=bool(
        getattr(settings, "CRAWLER_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "CRAWLER_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ Twitter crawler disable trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


class TwitterCrawler(BaseCrawler):
    """Twitter/X 爬虫（使用官方API v2）"""

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        rate_limit: int = 15,  # Twitter API: 15 req/15min
    ):
        """
        初始化Twitter爬虫

        Args:
            bearer_token: Twitter API Bearer Token
            rate_limit: 速率限制(每分钟请求数)
        """
        super().__init__(platform_name="twitter", rate_limit=rate_limit)
        raw_token = (
            bearer_token
            or getattr(settings, "TWITTER_BEARER_TOKEN", None)
            or os.getenv("TWITTER_BEARER_TOKEN")
            or ""
        ).strip()
        if raw_token:
            # Some dashboards provide URL-encoded token fragments (e.g. `%3D`).
            self.bearer_token = unquote(raw_token.strip("\"'"))
        else:
            self.bearer_token = None
        self.last_error_code = "OK"
        self.last_error_detail = ""
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        if not self.bearer_token:
            logger.warning("⚠️ Twitter bearer token missing, Twitter crawler disabled")
            return
        try:
            import aiohttp
            from core.config import settings as app_settings

            req_timeout = float(
                getattr(app_settings, "CRAWLER_PLATFORM_SEARCH_TIMEOUT_SECONDS", 10.0)
            )
            connect_timeout = min(4.0, max(1.0, req_timeout / 2.0))
            read_timeout = min(8.0, max(2.0, req_timeout))

            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=read_timeout,
                    connect=connect_timeout,
                    sock_read=read_timeout,
                ),
                trust_env=_AIOHTTP_TRUST_ENV,
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "User-Agent": "Aletheia-Truth-Engine/1.0",
                }
            )
            logger.info("✅ Twitter crawler session initialized")
        except RuntimeError as e:
            # 允许在无事件循环的构造阶段延迟初始化，会在首次请求时再创建会话
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Twitter session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    async def _make_request(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        发起API请求

        Args:
            endpoint: API端点路径
            params: 查询参数

        Returns:
            API响应JSON
        """
        await self.rate_limit_wait()
        self.last_error_code = "OK"
        self.last_error_detail = ""

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            self.last_error_code = "MISSING_TOKEN"
            self.last_error_detail = "twitter_bearer_token_missing"
            return None

        url = f"https://api.twitter.com/2/{endpoint}"

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    # 速率限制
                    logger.warning("⚠️ Twitter API rate limit hit")
                    self.last_error_code = "PLATFORM_429"
                    self.last_error_detail = "rate_limit"
                    return None
                else:
                    body_text = await response.text()
                    if response.status == 401:
                        self.last_error_code = "PLATFORM_401"
                    elif response.status == 402:
                        self.last_error_code = "PLATFORM_402"
                    elif response.status == 403:
                        self.last_error_code = "PLATFORM_403"
                    else:
                        self.last_error_code = f"HTTP_{response.status}"
                    self.last_error_detail = body_text[:500]
                    logger.error(
                        f"❌ Twitter API error: {response.status} - {body_text}"
                    )
                    return None
        except Exception as e:
            err_text = str(e)
            low = err_text.lower()
            if isinstance(e, asyncio.TimeoutError) or "timeout" in low:
                self.last_error_code = "CRAWLER_TIMEOUT"
            elif (
                "name or service not known" in low
                or "temporary failure in name resolution" in low
                or "nodename nor servname provided" in low
            ):
                self.last_error_code = "DNS_ERROR"
            else:
                self.last_error_code = "REQUEST_ERROR"
            self.last_error_detail = err_text[:500]
            logger.error(f"❌ Request failed: {e}")
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取Twitter热门话题（Trending Topics）

        Args:
            limit: 返回数量限制

        Returns:
            热门话题列表
        """
        logger.info(f"🔍 Fetching {limit} trending topics from Twitter...")

        # Twitter API v2: GET /2/trends/place (需要Enterprise账户)
        # 这里使用搜索API作为替代方案：搜索高互动的推文

        endpoint = "tweets/search/recent"
        params = {
            "query": "-is:retweet lang:zh",  # 非转推,中文推文
            "max_results": min(limit, 100),  # API限制100
            "tweet.fields": "created_at,public_metrics,author_id,entities,referenced_tweets",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "created_at,public_metrics,verified",
            "media.fields": "url,preview_image_url",
            "sort_order": "relevancy",  # 按相关性排序（类似热度）
        }

        data = await self._make_request(endpoint, params)
        if not data or "data" not in data:
            logger.warning("⚠️ No trending topics found")
            return []

        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {user["id"]: user for user in includes.get("users", [])}
        media_items = {media["media_key"]: media for media in includes.get("media", [])}

        results = []
        for tweet in tweets:
            author = users.get(tweet["author_id"], {})
            metrics = tweet.get("public_metrics", {})

            # 提取媒体
            media_keys = (
                tweet.get("attachments", {}).get("media_keys", [])
                if "attachments" in tweet
                else []
            )
            images = []
            video = None
            for key in media_keys:
                media = media_items.get(key)
                if media:
                    if media.get("type") == "photo":
                        images.append(media.get("url"))
                    elif media.get("type") == "video":
                        video = media.get("preview_image_url")  # 视频预览图

            # 提取实体（hashtags, mentions, URLs）
            entities = []
            raw_entities = tweet.get("entities", {})
            if "hashtags" in raw_entities:
                entities.extend([f"#{tag['tag']}" for tag in raw_entities["hashtags"]])
            if "mentions" in raw_entities:
                entities.extend(
                    [f"@{mention['username']}" for mention in raw_entities["mentions"]]
                )

            # 计算账户年龄
            account_created = author.get("created_at")
            account_age_days = None
            if account_created:
                created_dt = datetime.fromisoformat(
                    account_created.replace("Z", "+00:00")
                )
                account_age_days = (datetime.now(created_dt.tzinfo) - created_dt).days

            raw_data = {
                "url": f"https://twitter.com/i/web/status/{tweet['id']}",
                "text": tweet.get("text", ""),
                "images": images,
                "video": video,
                "created_at": tweet.get("created_at"),
                "author_id": tweet.get("author_id"),
                "author_name": author.get("username"),
                "followers": author.get("public_metrics", {}).get("followers_count", 0),
                "account_age_days": account_age_days,
                "verified": author.get("verified", False),
                "likes": metrics.get("like_count", 0),
                "comments": metrics.get("reply_count", 0),
                "shares": metrics.get("retweet_count", 0)
                + metrics.get("quote_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            # 添加Twitter特有字段
            standardized["metadata"]["verified"] = raw_data["verified"]
            standardized["metadata"]["tweet_id"] = tweet["id"]
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} trending tweets from Twitter")
        return results[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户的推文

        Args:
            user_id: 用户ID（数字ID或用户名）
            limit: 返回数量限制

        Returns:
            用户推文列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        # 如果是用户名,先获取用户ID
        if not user_id.isdigit():
            user_data = await self._make_request(f"users/by/username/{user_id}")
            if not user_data or "data" not in user_data:
                logger.error(f"❌ User {user_id} not found")
                return []
            user_id = user_data["data"]["id"]

        endpoint = f"users/{user_id}/tweets"
        params = {
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,entities,referenced_tweets",
            "expansions": "attachments.media_keys",
            "media.fields": "url,preview_image_url,type",
        }

        data = await self._make_request(endpoint, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No posts found for user {user_id}")
            return []

        tweets = data.get("data", [])
        includes = data.get("includes", {})
        media_items = {media["media_key"]: media for media in includes.get("media", [])}

        # 获取用户信息
        user_info_data = await self._make_request(
            f"users/{user_id}",
            params={"user.fields": "created_at,public_metrics,verified"},
        )
        user_info = user_info_data.get("data", {}) if user_info_data else {}

        results = []
        for tweet in tweets:
            metrics = tweet.get("public_metrics", {})

            # 提取媒体
            media_keys = (
                tweet.get("attachments", {}).get("media_keys", [])
                if "attachments" in tweet
                else []
            )
            images = []
            video = None
            for key in media_keys:
                media = media_items.get(key)
                if media:
                    if media.get("type") == "photo":
                        images.append(media.get("url"))
                    elif media.get("type") == "video":
                        video = media.get("preview_image_url")

            # 提取实体
            entities = []
            raw_entities = tweet.get("entities", {})
            if "hashtags" in raw_entities:
                entities.extend([f"#{tag['tag']}" for tag in raw_entities["hashtags"]])
            if "mentions" in raw_entities:
                entities.extend(
                    [f"@{mention['username']}" for mention in raw_entities["mentions"]]
                )

            # 计算账户年龄
            account_created = user_info.get("created_at")
            account_age_days = None
            if account_created:
                created_dt = datetime.fromisoformat(
                    account_created.replace("Z", "+00:00")
                )
                account_age_days = (datetime.now(created_dt.tzinfo) - created_dt).days

            raw_data = {
                "url": f"https://twitter.com/i/web/status/{tweet['id']}",
                "text": tweet.get("text", ""),
                "images": images,
                "video": video,
                "created_at": tweet.get("created_at"),
                "author_id": user_id,
                "author_name": user_info.get("username"),
                "followers": user_info.get("public_metrics", {}).get(
                    "followers_count", 0
                ),
                "account_age_days": account_age_days,
                "verified": user_info.get("verified", False),
                "likes": metrics.get("like_count", 0),
                "comments": metrics.get("reply_count", 0),
                "shares": metrics.get("retweet_count", 0)
                + metrics.get("quote_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["verified"] = raw_data["verified"]
            standardized["metadata"]["tweet_id"] = tweet["id"]
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} posts from user {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取推文的回复（评论）

        Args:
            post_id: 推文ID
            limit: 返回数量限制

        Returns:
            回复列表
        """
        logger.info(f"🔍 Fetching {limit} replies for tweet {post_id}...")

        # Twitter API v2: 搜索包含该推文链接的回复
        endpoint = "tweets/search/recent"
        params = {
            "query": f"conversation_id:{post_id}",
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,author_id,referenced_tweets",
            "expansions": "author_id",
            "user.fields": "created_at,public_metrics,verified",
        }

        data = await self._make_request(endpoint, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No replies found for tweet {post_id}")
            return []

        replies = data.get("data", [])
        includes = data.get("includes", {})
        users = {user["id"]: user for user in includes.get("users", [])}

        results = []
        for reply in replies:
            author = users.get(reply["author_id"], {})
            metrics = reply.get("public_metrics", {})

            # 计算账户年龄
            account_created = author.get("created_at")
            account_age_days = None
            if account_created:
                created_dt = datetime.fromisoformat(
                    account_created.replace("Z", "+00:00")
                )
                account_age_days = (datetime.now(created_dt.tzinfo) - created_dt).days

            raw_data = {
                "url": f"https://twitter.com/i/web/status/{reply['id']}",
                "text": reply.get("text", ""),
                "images": [],
                "video": None,
                "created_at": reply.get("created_at"),
                "author_id": reply.get("author_id"),
                "author_name": author.get("username"),
                "followers": author.get("public_metrics", {}).get("followers_count", 0),
                "account_age_days": account_age_days,
                "verified": author.get("verified", False),
                "likes": metrics.get("like_count", 0),
                "comments": metrics.get("reply_count", 0),
                "shares": metrics.get("retweet_count", 0),
                "entities": [],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["verified"] = raw_data["verified"]
            standardized["metadata"]["tweet_id"] = reply["id"]
            standardized["metadata"]["in_reply_to"] = post_id
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} replies for tweet {post_id}")
        return results[:limit]

    async def search_tweets(
        self, keyword: str, limit: int = 50, time_window_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的推文（用于特定信息验证）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            time_window_hours: 时间窗口（小时）

        Returns:
            推文列表
        """
        logger.info(
            f"🔍 Searching tweets with keyword: {keyword} (last {time_window_hours}h)..."
        )

        # 构建时间范围
        start_time = (datetime.utcnow() - timedelta(hours=time_window_hours)).isoformat(
            "T"
        ) + "Z"

        endpoint = "tweets/search/recent"
        params = {
            "query": f"{keyword} -is:retweet lang:zh",
            "max_results": min(limit, 100),
            "start_time": start_time,
            "tweet.fields": "created_at,public_metrics,author_id,entities",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "created_at,public_metrics,verified",
            "media.fields": "url,type",
        }

        data = await self._make_request(endpoint, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No tweets found for keyword: {keyword}")
            return []

        tweets = data.get("data", [])
        includes = data.get("includes", {})
        users = {user["id"]: user for user in includes.get("users", [])}
        media_items = {media["media_key"]: media for media in includes.get("media", [])}

        results = []
        for tweet in tweets:
            author = users.get(tweet["author_id"], {})
            metrics = tweet.get("public_metrics", {})

            # 提取媒体
            media_keys = (
                tweet.get("attachments", {}).get("media_keys", [])
                if "attachments" in tweet
                else []
            )
            images = []
            video = None
            for key in media_keys:
                media = media_items.get(key)
                if media:
                    if media.get("type") == "photo":
                        images.append(media.get("url"))
                    elif media.get("type") == "video":
                        video = media.get("url")

            # 提取实体
            entities = []
            raw_entities = tweet.get("entities", {})
            if "hashtags" in raw_entities:
                entities.extend([f"#{tag['tag']}" for tag in raw_entities["hashtags"]])
            if "mentions" in raw_entities:
                entities.extend(
                    [f"@{mention['username']}" for mention in raw_entities["mentions"]]
                )

            # 计算账户年龄
            account_created = author.get("created_at")
            account_age_days = None
            if account_created:
                created_dt = datetime.fromisoformat(
                    account_created.replace("Z", "+00:00")
                )
                account_age_days = (datetime.now(created_dt.tzinfo) - created_dt).days

            raw_data = {
                "url": f"https://twitter.com/i/web/status/{tweet['id']}",
                "text": tweet.get("text", ""),
                "images": images,
                "video": video,
                "created_at": tweet.get("created_at"),
                "author_id": tweet.get("author_id"),
                "author_name": author.get("username"),
                "followers": author.get("public_metrics", {}).get("followers_count", 0),
                "account_age_days": account_age_days,
                "verified": author.get("verified", False),
                "likes": metrics.get("like_count", 0),
                "comments": metrics.get("reply_count", 0),
                "shares": metrics.get("retweet_count", 0)
                + metrics.get("quote_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["verified"] = raw_data["verified"]
            standardized["metadata"]["tweet_id"] = tweet["id"]
            results.append(standardized)

        logger.info(f"✅ Found {len(results)} tweets for keyword: {keyword}")
        return results[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
