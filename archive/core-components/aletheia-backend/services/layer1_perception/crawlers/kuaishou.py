"""
快手爬虫 - 短视频平台数据采集
"""

import os
import re
import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from .base import BaseCrawler
from utils.logging import logger


class KuaishouCrawler(BaseCrawler):
    """快手爬虫（使用非官方API）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 5,  # 保守速率: 5 req/s
    ):
        """
        初始化快手爬虫

        Args:
            cookies: 快手登录Cookies（可选）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="kuaishou", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("KUAISHOU_COOKIES", "")
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.kuaishou.com/",
                "Origin": "https://www.kuaishou.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Content-Type": "application/json",
            }

            if self.cookies:
                headers["Cookie"] = self.cookies

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Kuaishou crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Kuaishou session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    def _generate_did(self) -> str:
        """
        生成设备ID（快手反爬机制）

        Returns:
            设备ID字符串
        """
        # 简化版本（生产环境需使用真实算法）
        timestamp = str(int(datetime.now().timestamp() * 1000))
        did_str = f"kuaishou_{timestamp}"
        return hashlib.md5(did_str.encode()).hexdigest()[:32]

    async def _make_request(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        发起API请求

        Args:
            url: 请求URL
            method: 请求方法 (GET/POST)
            params: 查询参数
            data: POST数据

        Returns:
            API响应JSON
        """
        await self.rate_limit_wait()

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        try:
            # 添加通用参数
            if params is None:
                params = {}

            # 快手需要did参数
            if "did" not in params:
                params["did"] = self._generate_did()

            if method == "POST":
                async with self.session.post(
                    url, params=params, json=data, timeout=10
                ) as response:
                    return await self._handle_response(response)
            else:
                async with self.session.get(url, params=params, timeout=10) as response:
                    return await self._handle_response(response)

        except asyncio.TimeoutError:
            logger.error("❌ Request timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    async def _handle_response(self, response) -> Optional[Dict]:
        """
        处理API响应

        Args:
            response: aiohttp响应对象

        Returns:
            解析后的JSON数据
        """
        if response.status == 200:
            data = await response.json()
            # 快手API通常返回 {"result": 1, "data": {...}}
            if data.get("result") == 1:
                return data
            else:
                logger.warning(
                    f"⚠️ Kuaishou API returned error: {data.get('error_msg', 'Unknown')}"
                )
                return None
        elif response.status == 429:
            logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
            await asyncio.sleep(60)
            return None
        else:
            logger.error(
                f"❌ Kuaishou API error: {response.status} - {await response.text()}"
            )
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取快手热榜

        Args:
            limit: 返回数量限制

        Returns:
            热搜列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Kuaishou...")

        # 快手热榜API
        url = "https://www.kuaishou.com/graphql"

        # GraphQL查询（快手使用GraphQL）
        query = """
        query {
            visionHotRank(pcursor: "") {
                result
                pcursor
                feeds {
                    id
                    photo {
                        id
                        caption
                        coverUrl
                        playUrl
                        likeCount
                        viewCount
                        commentCount
                        shareCount
                        timestamp
                        userName
                        userEid
                    }
                    hotValue
                    tag
                }
            }
        }
        """

        data = {"operationName": "visionHotRank", "query": query, "variables": {}}

        response = await self._make_request(url, method="POST", data=data)
        if not response or "data" not in response:
            logger.warning("⚠️ No hot topics found")
            return []

        hot_rank = response.get("data", {}).get("visionHotRank", {})
        feeds = hot_rank.get("feeds", [])

        results = []
        for feed in feeds[:limit]:
            photo = feed.get("photo", {})
            hot_value = feed.get("hotValue", 0)
            tag = feed.get("tag", "")

            # 提取话题标签
            entities = []
            caption = photo.get("caption", "")
            hashtags = re.findall(r"#(\w+)", caption)
            entities.extend([f"#{tag}" for tag in hashtags])
            if tag:
                entities.append(f"#{tag}")

            raw_data = {
                "url": f"https://www.kuaishou.com/short-video/{photo.get('id', '')}",
                "text": caption,
                "images": [photo.get("coverUrl", "")],
                "video": photo.get("playUrl"),
                "created_at": datetime.fromtimestamp(
                    photo.get("timestamp", 0) / 1000
                ).isoformat()
                if photo.get("timestamp")
                else datetime.utcnow().isoformat(),
                "author_id": photo.get("userEid"),
                "author_name": photo.get("userName"),
                "followers": 0,  # 热榜接口不返回粉丝数
                "account_age_days": None,
                "likes": photo.get("likeCount", 0),
                "comments": photo.get("commentCount", 0),
                "shares": photo.get("shareCount", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["photo_id"] = photo.get("id")
            standardized["metadata"]["view_count"] = photo.get("viewCount", 0)
            standardized["metadata"]["hot_value"] = hot_value
            standardized["metadata"]["hot_tag"] = tag
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot topics from Kuaishou")
        return results[:limit]

    async def search_videos(
        self, keyword: str, limit: int = 50, sort_type: int = 0
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的视频

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            sort_type: 排序方式 (0=综合, 1=最新, 2=最热)

        Returns:
            视频列表
        """
        logger.info(
            f"🔍 Searching videos with keyword: {keyword} (sort: {sort_type})..."
        )

        url = "https://www.kuaishou.com/graphql"
        all_videos = []
        pcursor = ""

        while len(all_videos) < limit:
            # GraphQL搜索查询
            query = """
            query visionSearchPhoto($keyword: String, $pcursor: String, $page: String, $searchSessionId: String) {
                visionSearchPhoto(keyword: $keyword, pcursor: $pcursor, page: $page, searchSessionId: $searchSessionId) {
                    result
                    pcursor
                    feeds {
                        type
                        photo {
                            id
                            caption
                            coverUrl
                            photoUrl
                            likeCount
                            viewCount
                            commentCount
                            shareCount
                            timestamp
                            userName
                            userEid
                            duration
                        }
                    }
                }
            }
            """

            data = {
                "operationName": "visionSearchPhoto",
                "query": query,
                "variables": {
                    "keyword": keyword,
                    "pcursor": pcursor,
                    "page": "search",
                    "searchSessionId": "",
                },
            }

            response = await self._make_request(url, method="POST", data=data)
            if not response or "data" not in response:
                break

            search_result = response.get("data", {}).get("visionSearchPhoto", {})
            feeds = search_result.get("feeds", [])

            if not feeds:
                break

            for feed in feeds:
                photo = feed.get("photo", {})

                # 提取话题标签
                entities = []
                caption = photo.get("caption", "")
                hashtags = re.findall(r"#(\w+)", caption)
                entities.extend([f"#{tag}" for tag in hashtags])

                raw_data = {
                    "url": f"https://www.kuaishou.com/short-video/{photo.get('id', '')}",
                    "text": caption,
                    "images": [photo.get("coverUrl", "")],
                    "video": photo.get("photoUrl"),
                    "created_at": datetime.fromtimestamp(
                        photo.get("timestamp", 0) / 1000
                    ).isoformat()
                    if photo.get("timestamp")
                    else datetime.utcnow().isoformat(),
                    "author_id": photo.get("userEid"),
                    "author_name": photo.get("userName"),
                    "followers": 0,
                    "account_age_days": None,
                    "likes": photo.get("likeCount", 0),
                    "comments": photo.get("commentCount", 0),
                    "shares": photo.get("shareCount", 0),
                    "entities": entities,
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["photo_id"] = photo.get("id")
                standardized["metadata"]["view_count"] = photo.get("viewCount", 0)
                standardized["metadata"]["duration"] = (
                    photo.get("duration", 0) / 1000
                )  # 转换为秒
                standardized["metadata"]["search_keyword"] = keyword
                all_videos.append(standardized)

                if len(all_videos) >= limit:
                    break

            # 获取下一页cursor
            pcursor = search_result.get("pcursor", "")
            if not pcursor or search_result.get("result") != 1:
                break

            await asyncio.sleep(0.5)  # 避免过度请求

        logger.info(f"✅ Found {len(all_videos)} videos for keyword: {keyword}")
        return all_videos[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户发布的视频

        Args:
            user_id: 用户ID（快手号或EID）
            limit: 返回数量限制

        Returns:
            用户视频列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        url = "https://www.kuaishou.com/graphql"
        all_posts = []
        pcursor = ""

        while len(all_posts) < limit:
            query = """
            query visionProfilePhotoList($userId: String, $pcursor: String, $page: String) {
                visionProfilePhotoList(userId: $userId, pcursor: $pcursor, page: $page) {
                    result
                    pcursor
                    feeds {
                        type
                        photo {
                            id
                            caption
                            coverUrl
                            photoUrl
                            likeCount
                            viewCount
                            commentCount
                            shareCount
                            timestamp
                            duration
                        }
                    }
                    userProfile {
                        ownerCount {
                            fan
                            follow
                        }
                        profile {
                            user_name
                            user_id
                        }
                    }
                }
            }
            """

            data = {
                "operationName": "visionProfilePhotoList",
                "query": query,
                "variables": {"userId": user_id, "pcursor": pcursor, "page": "profile"},
            }

            response = await self._make_request(url, method="POST", data=data)
            if not response or "data" not in response:
                break

            profile_result = response.get("data", {}).get("visionProfilePhotoList", {})
            feeds = profile_result.get("feeds", [])
            user_profile = profile_result.get("userProfile", {})

            # 获取用户信息
            fan_count = user_profile.get("ownerCount", {}).get("fan", 0)
            user_name = user_profile.get("profile", {}).get("user_name", "")

            if not feeds:
                break

            for feed in feeds:
                photo = feed.get("photo", {})

                # 提取话题标签
                entities = []
                caption = photo.get("caption", "")
                hashtags = re.findall(r"#(\w+)", caption)
                entities.extend([f"#{tag}" for tag in hashtags])

                raw_data = {
                    "url": f"https://www.kuaishou.com/short-video/{photo.get('id', '')}",
                    "text": caption,
                    "images": [photo.get("coverUrl", "")],
                    "video": photo.get("photoUrl"),
                    "created_at": datetime.fromtimestamp(
                        photo.get("timestamp", 0) / 1000
                    ).isoformat()
                    if photo.get("timestamp")
                    else datetime.utcnow().isoformat(),
                    "author_id": user_id,
                    "author_name": user_name,
                    "followers": fan_count,
                    "account_age_days": None,
                    "likes": photo.get("likeCount", 0),
                    "comments": photo.get("commentCount", 0),
                    "shares": photo.get("shareCount", 0),
                    "entities": entities,
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["photo_id"] = photo.get("id")
                standardized["metadata"]["view_count"] = photo.get("viewCount", 0)
                standardized["metadata"]["duration"] = photo.get("duration", 0) / 1000
                all_posts.append(standardized)

                if len(all_posts) >= limit:
                    break

            # 获取下一页cursor
            pcursor = profile_result.get("pcursor", "")
            if not pcursor or profile_result.get("result") != 1:
                break

            await asyncio.sleep(0.5)

        logger.info(f"✅ Fetched {len(all_posts)} posts from user {user_id}")
        return all_posts[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取视频的评论

        Args:
            post_id: 视频ID（photo_id）
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for video {post_id}...")

        url = "https://www.kuaishou.com/graphql"
        all_comments = []
        pcursor = ""

        while len(all_comments) < limit:
            query = """
            query commentListQuery($photoId: String, $pcursor: String) {
                visionCommentList(photoId: $photoId, pcursor: $pcursor) {
                    result
                    pcursor
                    rootComments {
                        commentId
                        content
                        likeCount
                        replyCount
                        timestamp
                        user {
                            id
                            name
                            fan
                        }
                    }
                }
            }
            """

            data = {
                "operationName": "commentListQuery",
                "query": query,
                "variables": {"photoId": post_id, "pcursor": pcursor},
            }

            response = await self._make_request(url, method="POST", data=data)
            if not response or "data" not in response:
                break

            comment_result = response.get("data", {}).get("visionCommentList", {})
            comments = comment_result.get("rootComments", [])

            if not comments:
                break

            for comment in comments:
                user = comment.get("user", {})

                raw_data = {
                    "url": f"https://www.kuaishou.com/short-video/{post_id}?comment_id={comment.get('commentId', '')}",
                    "text": comment.get("content", ""),
                    "images": [],
                    "video": None,
                    "created_at": datetime.fromtimestamp(
                        comment.get("timestamp", 0) / 1000
                    ).isoformat()
                    if comment.get("timestamp")
                    else datetime.utcnow().isoformat(),
                    "author_id": user.get("id"),
                    "author_name": user.get("name"),
                    "followers": user.get("fan", 0),
                    "account_age_days": None,
                    "likes": comment.get("likeCount", 0),
                    "comments": comment.get("replyCount", 0),
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["comment_id"] = comment.get("commentId")
                standardized["metadata"]["photo_id"] = post_id
                all_comments.append(standardized)

                if len(all_comments) >= limit:
                    break

            # 获取下一页cursor
            pcursor = comment_result.get("pcursor", "")
            if not pcursor or comment_result.get("result") != 1:
                break

            await asyncio.sleep(0.5)

        logger.info(f"✅ Fetched {len(all_comments)} comments for video {post_id}")
        return all_comments[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
