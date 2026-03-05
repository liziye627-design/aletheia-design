"""
Bilibili(B站) 爬虫 - 视频平台数据采集
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from .base import BaseCrawler
from utils.logging import logger


class BilibiliCrawler(BaseCrawler):
    """B站爬虫（使用官方API）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 10,  # 10 req/s
    ):
        """
        初始化B站爬虫

        Args:
            cookies: B站登录Cookies（可选）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="bilibili", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("BILIBILI_COOKIES", "")
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            }

            if self.cookies:
                headers["Cookie"] = self.cookies

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Bilibili crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Bilibili session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    async def _make_request(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """发起API请求"""
        await self.rate_limit_wait()

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        try:
            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data
                    else:
                        logger.warning(
                            f"⚠️ Bilibili API error: {data.get('message', 'Unknown')}"
                        )
                        return None
                elif response.status == 412:
                    logger.warning("⚠️ Bilibili anti-bot triggered. Need verification.")
                    return None
                else:
                    logger.error(f"❌ Bilibili API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取B站热门视频（综合热门）

        Args:
            limit: 返回数量限制

        Returns:
            热门视频列表
        """
        logger.info(f"🔍 Fetching {limit} hot videos from Bilibili...")

        # B站热门视频API
        url = "https://api.bilibili.com/x/web-interface/popular"
        params = {"ps": min(limit, 50), "pn": 1}

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            logger.warning("⚠️ No hot videos found")
            return []

        video_list = data.get("data", {}).get("list", [])
        results = []

        for video in video_list:
            owner = video.get("owner", {})
            stat = video.get("stat", {})

            # 视频封面
            cover_url = video.get("pic", "")

            # 提取标签
            entities = []
            if video.get("tname"):  # 分区名称
                entities.append(f"#{video['tname']}")

            raw_data = {
                "url": f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                "text": f"{video.get('title', '')}\n\n{video.get('desc', '')}",
                "images": [cover_url] if cover_url else [],
                "video": None,  # B站视频需要额外API获取播放地址
                "created_at": datetime.fromtimestamp(
                    video.get("pubdate", 0)
                ).isoformat()
                if video.get("pubdate")
                else datetime.utcnow().isoformat(),
                "author_id": str(owner.get("mid", "")),
                "author_name": owner.get("name", ""),
                "followers": 0,  # 需要额外API获取
                "account_age_days": None,
                "likes": stat.get("like", 0),
                "comments": stat.get("reply", 0),
                "shares": stat.get("share", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["bvid"] = video.get("bvid")
            standardized["metadata"]["aid"] = video.get("aid")
            standardized["metadata"]["view_count"] = stat.get("view", 0)
            standardized["metadata"]["coin"] = stat.get("coin", 0)  # 投币数
            standardized["metadata"]["favorite"] = stat.get("favorite", 0)  # 收藏数
            standardized["metadata"]["duration"] = video.get("duration", 0)
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot videos from Bilibili")
        return results[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取UP主发布的视频

        Args:
            user_id: UP主ID（mid）
            limit: 返回数量限制

        Returns:
            UP主视频列表
        """
        logger.info(f"🔍 Fetching {limit} videos from UP {user_id}...")

        url = "https://api.bilibili.com/x/space/wbi/arc/search"
        params = {
            "mid": user_id,
            "ps": min(limit, 30),
            "pn": 1,
            "order": "pubdate",  # 按发布时间排序
        }

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No videos found for UP {user_id}")
            return []

        video_list = data.get("data", {}).get("list", {}).get("vlist", [])
        results = []

        for video in video_list:
            # 提取标签
            entities = []
            if video.get("typeid"):
                entities.append(f"#{video.get('typeid')}")

            raw_data = {
                "url": f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                "text": f"{video.get('title', '')}\n\n{video.get('description', '')}",
                "images": [video.get("pic", "")] if video.get("pic") else [],
                "video": None,
                "created_at": datetime.fromtimestamp(
                    video.get("created", 0)
                ).isoformat()
                if video.get("created")
                else datetime.utcnow().isoformat(),
                "author_id": user_id,
                "author_name": video.get("author", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,  # 列表API不返回点赞数
                "comments": video.get("comment", 0),
                "shares": 0,
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["bvid"] = video.get("bvid")
            standardized["metadata"]["aid"] = video.get("aid")
            standardized["metadata"]["view_count"] = video.get("play", 0)
            standardized["metadata"]["duration"] = video.get("length", "")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} videos from UP {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取视频的评论

        Args:
            post_id: 视频ID（av号或bv号）
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for video {post_id}...")

        # 如果是bv号，需要转换为av号
        if post_id.startswith("BV"):
            # 这里简化处理，实际需要转换API
            logger.warning("⚠️ BV号暂不支持，请使用AV号")
            return []

        url = "https://api.bilibili.com/x/v2/reply/main"
        params = {
            "type": 1,  # 1=视频
            "oid": post_id,  # av号
            "mode": 3,  # 3=按热度, 2=按时间
            "ps": 20,
            "pn": 1,
        }

        all_comments = []
        pn = 1

        while len(all_comments) < limit:
            params["pn"] = pn
            data = await self._make_request(url, params)

            if not data or "data" not in data:
                break

            replies = data.get("data", {}).get("replies", [])
            if not replies:
                break

            for reply in replies:
                member = reply.get("member", {})

                # 创建时间
                created_at = reply.get("ctime")
                if created_at:
                    created_at = datetime.fromtimestamp(created_at).isoformat()
                else:
                    created_at = datetime.utcnow().isoformat()

                raw_data = {
                    "url": f"https://www.bilibili.com/video/av{post_id}?reply={reply.get('rpid')}",
                    "text": reply.get("content", {}).get("message", ""),
                    "images": [],
                    "video": None,
                    "created_at": created_at,
                    "author_id": str(member.get("mid", "")),
                    "author_name": member.get("uname", ""),
                    "followers": 0,
                    "account_age_days": None,
                    "likes": reply.get("like", 0),
                    "comments": reply.get("rcount", 0),  # 回复数
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["rpid"] = reply.get("rpid")
                standardized["metadata"]["aid"] = post_id
                all_comments.append(standardized)

                if len(all_comments) >= limit:
                    break

            pn += 1
            await asyncio.sleep(0.5)

        logger.info(f"✅ Fetched {len(all_comments)} comments for video {post_id}")
        return all_comments[:limit]

    async def search_videos(
        self, keyword: str, limit: int = 50, order: str = "totalrank"
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的视频

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            order: 排序方式 (totalrank=综合排序, click=播放量, pubdate=发布时间, dm=弹幕数, stow=收藏数)

        Returns:
            视频列表
        """
        logger.info(f"🔍 Searching videos with keyword: {keyword} (order: {order})...")

        url = "https://api.bilibili.com/x/web-interface/search/type"
        all_videos = []
        page = 1

        while len(all_videos) < limit:
            params = {
                "search_type": "video",
                "keyword": keyword,
                "order": order,
                "page": page,
                "page_size": min(20, limit - len(all_videos)),
            }

            data = await self._make_request(url, params)
            if not data or "data" not in data:
                break

            result_list = data.get("data", {}).get("result", [])
            if not result_list:
                break

            for video in result_list:
                # 提取作者
                author = video.get("author", "")
                mid = video.get("mid", "")

                # 提取标签
                entities = []
                if video.get("tag"):
                    entities.append(f"#{video['tag']}")

                # 发布时间
                pubdate = video.get("pubdate")
                if pubdate:
                    created_at = datetime.fromtimestamp(pubdate).isoformat()
                else:
                    created_at = datetime.utcnow().isoformat()

                raw_data = {
                    "url": f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                    "text": f"{video.get('title', '')}\n\n{video.get('description', '')}",
                    "images": [
                        f"https:{video.get('pic', '')}" if video.get("pic") else ""
                    ],
                    "video": None,
                    "created_at": created_at,
                    "author_id": str(mid),
                    "author_name": author,
                    "followers": 0,
                    "account_age_days": None,
                    "likes": video.get("like", 0),
                    "comments": video.get("review", 0),
                    "shares": 0,
                    "entities": entities,
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["bvid"] = video.get("bvid")
                standardized["metadata"]["aid"] = video.get("aid")
                standardized["metadata"]["view_count"] = video.get("play", 0)
                standardized["metadata"]["duration"] = video.get("duration", "")
                standardized["metadata"]["search_keyword"] = keyword
                all_videos.append(standardized)

            page += 1
            await asyncio.sleep(0.5)

            if len(result_list) < params["page_size"]:
                break

        logger.info(f"✅ Found {len(all_videos)} videos for keyword: {keyword}")
        return all_videos[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
