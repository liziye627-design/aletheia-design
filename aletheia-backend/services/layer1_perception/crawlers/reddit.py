"""
Reddit爬虫 - 国际论坛平台数据采集
"""

import os
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from .base import BaseCrawler
from utils.logging import logger


class RedditCrawler(BaseCrawler):
    """Reddit爬虫（使用官方API）"""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        rate_limit: int = 10,  # Reddit较宽松: 10 req/s
    ):
        """
        初始化Reddit爬虫

        Args:
            client_id: Reddit API Client ID
            client_secret: Reddit API Client Secret
            user_agent: User Agent字符串
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="reddit", rate_limit=rate_limit)

        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET", "")
        self.user_agent = user_agent or os.getenv(
            "REDDIT_USER_AGENT", "Aletheia/1.0 (by /u/aletheia_bot)"
        )

        self.session = None
        self.access_token = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": self.user_agent,
            }

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Reddit crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Reddit session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    async def _get_access_token(self) -> bool:
        """
        获取OAuth2访问令牌

        Returns:
            是否成功获取令牌
        """
        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return False

        if not self.client_id or not self.client_secret:
            logger.error("❌ Reddit API credentials not provided")
            return False

        try:
            import aiohttp

            auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
            data = {
                "grant_type": "client_credentials",
            }

            async with self.session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth,
                data=data,
                timeout=10,
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get("access_token")
                    logger.info("✅ Reddit OAuth token obtained")
                    return True
                else:
                    logger.error(f"❌ Failed to get Reddit token: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"❌ Token request failed: {e}")
            return False

    async def _make_request(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        发起Reddit API请求

        Args:
            endpoint: API端点（如 /r/all/hot）
            params: 查询参数

        Returns:
            API响应JSON
        """
        await self.rate_limit_wait()

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        # 确保有访问令牌
        if not self.access_token:
            success = await self._get_access_token()
            if not success:
                return None

        try:
            url = f"https://oauth.reddit.com{endpoint}.json"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            async with self.session.get(
                url, headers=headers, params=params, timeout=10
            ) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    # Token过期，重新获取
                    logger.warning("⚠️ Token expired, refreshing...")
                    self.access_token = None
                    return await self._make_request(endpoint, params)
                elif response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    return await self._make_request(endpoint, params)
                else:
                    logger.error(f"❌ Reddit API error: {response.status}")
                    return None

        except asyncio.TimeoutError:
            logger.error("❌ Request timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    def _parse_post(self, post_data: Dict) -> Dict[str, Any]:
        """
        解析Reddit帖子数据

        Args:
            post_data: 原始帖子数据

        Returns:
            标准化帖子数据
        """
        data = post_data.get("data", {})

        # 提取标题和内容
        title = data.get("title", "")
        selftext = data.get("selftext", "")
        text = f"{title}\n{selftext}" if selftext else title

        # 提取媒体
        images = []
        video = None

        # 图片帖子
        if data.get("post_hint") == "image":
            url_img = data.get("url", "")
            if url_img:
                images.append(url_img)

        # 画廊帖子
        gallery_data = data.get("gallery_data", {})
        if gallery_data:
            items = gallery_data.get("items", [])
            for item in items:
                media_id = item.get("media_id")
                if media_id:
                    media_metadata = data.get("media_metadata", {})
                    media_info = media_metadata.get(media_id, {})
                    img_url = media_info.get("s", {}).get("u", "")
                    if img_url:
                        # Reddit URL需要解码HTML实体
                        img_url = img_url.replace("&amp;", "&")
                        images.append(img_url)

        # 视频帖子
        if data.get("is_video"):
            video_data = data.get("media", {})
            if video_data:
                reddit_video = video_data.get("reddit_video", {})
                video = reddit_video.get("fallback_url")

        # 外部链接
        url_link = f"https://www.reddit.com{data.get('permalink', '')}"

        # 提取flair作为实体
        entities = []
        link_flair = data.get("link_flair_text")
        if link_flair:
            entities.append(f"#{link_flair}")

        # 提取subreddit
        subreddit = data.get("subreddit_name_prefixed", "")
        if subreddit:
            entities.append(subreddit)

        # 账户年龄
        created_utc = data.get("created_utc", 0)
        account_age_days = None
        if created_utc > 0:
            account_age_days = int((datetime.now().timestamp() - created_utc) / 86400)

        raw_data = {
            "url": url_link,
            "text": text,
            "images": images,
            "video": video,
            "created_at": datetime.fromtimestamp(created_utc).isoformat()
            if created_utc > 0
            else datetime.utcnow().isoformat(),
            "author_id": data.get("author_fullname", ""),
            "author_name": data.get("author", ""),
            "followers": 0,  # Reddit API不返回粉丝数
            "account_age_days": account_age_days,
            "likes": data.get("ups", 0),  # upvotes
            "comments": data.get("num_comments", 0),
            "shares": 0,  # Reddit不直接提供分享数
            "entities": entities,
        }

        standardized = self.standardize_item(raw_data)
        standardized["metadata"]["post_id"] = data.get("id")
        standardized["metadata"]["subreddit"] = data.get("subreddit")
        standardized["metadata"]["upvote_ratio"] = data.get("upvote_ratio", 0)
        standardized["metadata"]["score"] = data.get("score", 0)
        standardized["metadata"]["is_video"] = data.get("is_video", False)
        standardized["metadata"]["link_flair"] = link_flair

        return standardized

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取Reddit热门帖子（r/all）

        Args:
            limit: 返回数量限制

        Returns:
            热门帖子列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Reddit...")

        endpoint = "/r/all/hot"
        params = {
            "limit": min(limit, 100),
        }

        data = await self._make_request(endpoint, params)
        if not data:
            logger.warning("⚠️ No hot topics found")
            return []

        children = data.get("data", {}).get("children", [])
        results = []

        for child in children:
            if child.get("kind") == "t3":  # t3 = link/post
                post = self._parse_post(child)
                results.append(post)

        logger.info(f"✅ Fetched {len(results)} hot topics from Reddit")
        return results[:limit]

    async def search_posts(
        self,
        keyword: str,
        subreddit: Optional[str] = None,
        limit: int = 50,
        sort: str = "relevance",
    ) -> List[Dict[str, Any]]:
        """
        搜索Reddit帖子

        Args:
            keyword: 搜索关键词
            subreddit: 限定subreddit（可选）
            limit: 返回数量限制
            sort: 排序方式 (relevance, hot, top, new, comments)

        Returns:
            搜索结果列表
        """
        logger.info(
            f"🔍 Searching Reddit for: {keyword} (subreddit: {subreddit or 'all'})..."
        )

        if subreddit:
            endpoint = f"/r/{subreddit}/search"
            params = {
                "q": keyword,
                "restrict_sr": "on",  # 限定在该subreddit
                "sort": sort,
                "limit": min(limit, 100),
            }
        else:
            endpoint = "/search"
            params = {
                "q": keyword,
                "sort": sort,
                "limit": min(limit, 100),
            }

        data = await self._make_request(endpoint, params)
        if not data:
            logger.warning(f"⚠️ No search results found for: {keyword}")
            return []

        children = data.get("data", {}).get("children", [])
        results = []

        for child in children:
            if child.get("kind") == "t3":
                post = self._parse_post(child)
                post["metadata"]["search_keyword"] = keyword
                results.append(post)

        logger.info(f"✅ Found {len(results)} posts for keyword: {keyword}")
        return results[:limit]

    async def fetch_subreddit_posts(
        self, subreddit: str, listing: str = "hot", limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        抓取特定subreddit的帖子

        Args:
            subreddit: Subreddit名称（如 "worldnews"）
            listing: 列表类型 (hot, new, top, rising)
            limit: 返回数量限制

        Returns:
            帖子列表
        """
        logger.info(f"🔍 Fetching {limit} {listing} posts from r/{subreddit}...")

        endpoint = f"/r/{subreddit}/{listing}"
        params = {
            "limit": min(limit, 100),
        }

        data = await self._make_request(endpoint, params)
        if not data:
            logger.warning(f"⚠️ No posts found for r/{subreddit}")
            return []

        children = data.get("data", {}).get("children", [])
        results = []

        for child in children:
            if child.get("kind") == "t3":
                post = self._parse_post(child)
                results.append(post)

        logger.info(f"✅ Fetched {len(results)} posts from r/{subreddit}")
        return results[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户发布的帖子

        Args:
            user_id: Reddit用户名（不含u/前缀）
            limit: 返回数量限制

        Returns:
            用户帖子列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user u/{user_id}...")

        endpoint = f"/user/{user_id}/submitted"
        params = {
            "limit": min(limit, 100),
        }

        data = await self._make_request(endpoint, params)
        if not data:
            logger.warning(f"⚠️ No posts found for user u/{user_id}")
            return []

        children = data.get("data", {}).get("children", [])
        results = []

        for child in children:
            if child.get("kind") == "t3":
                post = self._parse_post(child)
                results.append(post)

        logger.info(f"✅ Fetched {len(results)} posts from user u/{user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取帖子的评论

        Args:
            post_id: 帖子ID（不含t3_前缀）
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for post {post_id}...")

        # 需要先获取帖子信息来构建正确的URL
        # Reddit评论API需要subreddit和post_id
        # 简化处理：使用r/all
        endpoint = f"/comments/{post_id}"
        params = {
            "limit": min(limit, 500),
            "depth": 1,  # 只获取顶级评论
        }

        data = await self._make_request(endpoint, params)
        if not data or len(data) < 2:
            logger.warning(f"⚠️ No comments found for post {post_id}")
            return []

        # Reddit返回数组：[post_data, comments_data]
        comments_listing = data[1]
        children = comments_listing.get("data", {}).get("children", [])

        results = []

        for child in children:
            if child.get("kind") == "t1":  # t1 = comment
                comment_data = child.get("data", {})

                # 跳过"more comments"类型
                if comment_data.get("body") in ["[deleted]", "[removed]"]:
                    continue

                created_utc = comment_data.get("created_utc", 0)

                raw_data = {
                    "url": f"https://www.reddit.com{comment_data.get('permalink', '')}",
                    "text": comment_data.get("body", ""),
                    "images": [],
                    "video": None,
                    "created_at": datetime.fromtimestamp(created_utc).isoformat()
                    if created_utc > 0
                    else datetime.utcnow().isoformat(),
                    "author_id": comment_data.get("author_fullname", ""),
                    "author_name": comment_data.get("author", ""),
                    "followers": 0,
                    "account_age_days": None,
                    "likes": comment_data.get("ups", 0),
                    "comments": 0,  # 子评论数暂不处理
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["comment_id"] = comment_data.get("id")
                standardized["metadata"]["post_id"] = post_id
                standardized["metadata"]["score"] = comment_data.get("score", 0)
                results.append(standardized)

                if len(results) >= limit:
                    break

        logger.info(f"✅ Fetched {len(results)} comments for post {post_id}")
        return results[:limit]

    async def fetch_trending_subreddits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        抓取热门subreddit列表

        Args:
            limit: 返回数量限制

        Returns:
            Subreddit信息列表
        """
        logger.info(f"🔍 Fetching {limit} trending subreddits...")

        endpoint = "/subreddits/popular"
        params = {
            "limit": min(limit, 100),
        }

        data = await self._make_request(endpoint, params)
        if not data:
            logger.warning("⚠️ No trending subreddits found")
            return []

        children = data.get("data", {}).get("children", [])
        results = []

        for child in children:
            if child.get("kind") == "t5":  # t5 = subreddit
                sub_data = child.get("data", {})

                display_name = sub_data.get("display_name", "")
                title = sub_data.get("title", "")
                description = sub_data.get("public_description", "")

                text = f"r/{display_name} - {title}\n{description}"

                raw_data = {
                    "url": f"https://www.reddit.com/r/{display_name}",
                    "text": text,
                    "images": [sub_data.get("icon_img", "")],
                    "video": None,
                    "created_at": datetime.fromtimestamp(
                        sub_data.get("created_utc", 0)
                    ).isoformat()
                    if sub_data.get("created_utc")
                    else datetime.utcnow().isoformat(),
                    "author_id": "reddit_official",
                    "author_name": "Reddit",
                    "followers": sub_data.get("subscribers", 0),
                    "account_age_days": None,
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "entities": [f"r/{display_name}"],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["subreddit_id"] = sub_data.get("id")
                standardized["metadata"]["subscribers"] = sub_data.get("subscribers", 0)
                standardized["metadata"]["active_users"] = sub_data.get(
                    "active_user_count", 0
                )
                results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} trending subreddits")
        return results[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
