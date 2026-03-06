"""
抖音/TikTok 爬虫 - 短视频平台数据采集
"""

import os
import re
import json
import hashlib
import urllib.parse
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio

import httpx
from bs4 import BeautifulSoup

from .base import BaseCrawler
from utils.logging import logger


class DouyinCrawler(BaseCrawler):
    """抖音爬虫（使用非官方API）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 5,  # 保守速率: 5 req/s
    ):
        """
        初始化抖音爬虫

        Args:
            cookies: 抖音登录Cookies（可选）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="douyin", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("DOUYIN_COOKIES", "")
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/",
                "Origin": "https://www.douyin.com",
            }

            if self.cookies:
                headers["Cookie"] = self.cookies

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Douyin crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Douyin session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    def _generate_signature(self, url: str) -> str:
        """
        生成抖音签名（反爬机制）
        注意: 这是简化版本，实际需要更复杂的算法

        Args:
            url: 请求URL

        Returns:
            签名字符串
        """
        # 简化签名（生产环境需使用真实算法或第三方库）
        timestamp = str(int(datetime.now().timestamp() * 1000))
        sign_str = f"{url}{timestamp}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()
        return signature

    async def _make_request(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        发起API请求

        Args:
            url: 请求URL
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

        try:
            # 添加签名参数
            if params is None:
                params = {}

            signature = self._generate_signature(url)
            params["_signature"] = signature

            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    # 抖音API通常返回 {"status_code": 0, "data": {...}}
                    if data.get("status_code") == 0:
                        return data
                    else:
                        logger.warning(
                            f"⚠️ Douyin API returned error: {data.get('status_msg', 'Unknown')}"
                        )
                        return None
                elif response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    return await self._make_request(url, params)
                else:
                    logger.error(
                        f"❌ Douyin API error: {response.status} - {await response.text()}"
                    )
                    return None
        except asyncio.TimeoutError:
            logger.error("❌ Request timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取抖音热搜榜

        Args:
            limit: 返回数量限制

        Returns:
            热搜列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Douyin...")

        # 抖音热搜API
        url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"

        data = await self._make_request(url)
        if not data or "data" not in data:
            logger.warning("⚠️ No hot topics found")
            return []

        hot_list = data.get("data", {}).get("word_list", [])

        results = []
        for item in hot_list[:limit]:
            hot_word = item.get("word", "")
            hot_value = item.get("hot_value", 0)  # 热度值

            # 搜索该话题下的视频
            videos = await self._search_videos(hot_word, limit=3)

            if videos:
                # 使用第一个视频作为代表
                video = videos[0]
                video["metadata"]["hot_topic"] = hot_word
                video["metadata"]["hot_value"] = hot_value
                results.append(video)
            else:
                # 如果没有视频，创建纯话题项
                raw_data = {
                    "url": f"https://www.douyin.com/search/{hot_word}",
                    "text": f"抖音热搜: {hot_word}",
                    "images": [],
                    "video": None,
                    "created_at": datetime.utcnow().isoformat(),
                    "author_id": "douyin_official",
                    "author_name": "抖音热搜",
                    "followers": 0,
                    "account_age_days": 3650,
                    "likes": hot_value,
                    "comments": 0,
                    "shares": 0,
                    "entities": [f"#{hot_word}"],
                }
                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["hot_topic"] = hot_word
                standardized["metadata"]["hot_value"] = hot_value
                results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot topics from Douyin")
        return results[:limit]

    async def _search_videos(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索视频（内部方法）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            视频列表
        """
        url = "https://www.douyin.com/aweme/v1/web/general/search/single/"
        params = {
            "keyword": keyword,
            "search_channel": "aweme_video_web",
            "search_source": "normal_search",
            "query_correct_type": "1",
            "is_filter_search": "0",
            "offset": 0,
            "count": min(limit, 20),
        }

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            return []

        aweme_list = data.get("data", [])
        results = []

        for aweme in aweme_list:
            aweme_info = aweme.get("aweme_info", {})
            author = aweme_info.get("author", {})
            statistics = aweme_info.get("statistics", {})
            video_info = aweme_info.get("video", {})

            # 提取视频封面
            cover_url = video_info.get("cover", {}).get("url_list", [None])[0]

            # 提取视频播放地址
            play_url = video_info.get("play_addr", {}).get("url_list", [None])[0]

            # 提取话题标签
            entities = []
            text_extra = aweme_info.get("text_extra", [])
            for extra in text_extra:
                if extra.get("hashtag_name"):
                    entities.append(f"#{extra['hashtag_name']}")

            # 账户年龄
            create_time = author.get("create_time", 0)
            if create_time > 0:
                account_age_days = (datetime.now().timestamp() - create_time) // 86400
            else:
                account_age_days = None

            raw_data = {
                "url": f"https://www.douyin.com/video/{aweme_info.get('aweme_id', '')}",
                "text": aweme_info.get("desc", ""),
                "images": [cover_url] if cover_url else [],
                "video": play_url,
                "created_at": datetime.fromtimestamp(
                    aweme_info.get("create_time", 0)
                ).isoformat()
                if aweme_info.get("create_time")
                else datetime.utcnow().isoformat(),
                "author_id": author.get("uid"),
                "author_name": author.get("nickname"),
                "followers": author.get("follower_count", 0),
                "account_age_days": account_age_days,
                "likes": statistics.get("digg_count", 0),
                "comments": statistics.get("comment_count", 0),
                "shares": statistics.get("share_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["aweme_id"] = aweme_info.get("aweme_id")
            standardized["metadata"]["view_count"] = statistics.get("play_count", 0)
            standardized["metadata"]["duration"] = (
                video_info.get("duration", 0) / 1000
            )  # 转换为秒
            results.append(standardized)

        return results

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户发布的视频

        Args:
            user_id: 用户ID（抖音号或UID）
            limit: 返回数量限制

        Returns:
            用户视频列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        url = "https://www.douyin.com/aweme/v1/web/aweme/post/"
        params = {
            "sec_user_id": user_id,
            "count": min(limit, 35),
            "max_cursor": 0,
        }

        data = await self._make_request(url, params)
        if not data or "aweme_list" not in data:
            logger.warning(f"⚠️ No posts found for user {user_id}")
            return []

        aweme_list = data.get("aweme_list", [])
        results = []

        for aweme in aweme_list:
            author = aweme.get("author", {})
            statistics = aweme.get("statistics", {})
            video_info = aweme.get("video", {})

            # 提取视频封面和播放地址
            cover_url = video_info.get("cover", {}).get("url_list", [None])[0]
            play_url = video_info.get("play_addr", {}).get("url_list", [None])[0]

            # 提取话题标签
            entities = []
            text_extra = aweme.get("text_extra", [])
            for extra in text_extra:
                if extra.get("hashtag_name"):
                    entities.append(f"#{extra['hashtag_name']}")

            # 账户年龄
            create_time = author.get("create_time", 0)
            account_age_days = (
                int((datetime.now().timestamp() - create_time) // 86400)
                if create_time > 0
                else None
            )

            raw_data = {
                "url": f"https://www.douyin.com/video/{aweme.get('aweme_id', '')}",
                "text": aweme.get("desc", ""),
                "images": [cover_url] if cover_url else [],
                "video": play_url,
                "created_at": datetime.fromtimestamp(
                    aweme.get("create_time", 0)
                ).isoformat()
                if aweme.get("create_time")
                else datetime.utcnow().isoformat(),
                "author_id": user_id,
                "author_name": author.get("nickname"),
                "followers": author.get("follower_count", 0),
                "account_age_days": account_age_days,
                "likes": statistics.get("digg_count", 0),
                "comments": statistics.get("comment_count", 0),
                "shares": statistics.get("share_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["aweme_id"] = aweme.get("aweme_id")
            standardized["metadata"]["view_count"] = statistics.get("play_count", 0)
            standardized["metadata"]["duration"] = video_info.get("duration", 0) / 1000
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} posts from user {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取视频的评论

        Args:
            post_id: 视频ID（aweme_id）
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for video {post_id}...")

        url = "https://www.douyin.com/aweme/v1/web/comment/list/"
        all_comments = []
        cursor = 0

        while len(all_comments) < limit:
            params = {
                "aweme_id": post_id,
                "cursor": cursor,
                "count": min(20, limit - len(all_comments)),
            }

            data = await self._make_request(url, params)
            if not data or "comments" not in data:
                break

            comments = data.get("comments", [])
            if not comments:
                break

            for comment in comments:
                user = comment.get("user", {})

                # 账户年龄
                create_time = user.get("create_time", 0)
                account_age_days = (
                    int((datetime.now().timestamp() - create_time) // 86400)
                    if create_time > 0
                    else None
                )

                raw_data = {
                    "url": f"https://www.douyin.com/video/{post_id}?comment_id={comment.get('cid', '')}",
                    "text": comment.get("text", ""),
                    "images": [],
                    "video": None,
                    "created_at": datetime.fromtimestamp(
                        comment.get("create_time", 0)
                    ).isoformat()
                    if comment.get("create_time")
                    else datetime.utcnow().isoformat(),
                    "author_id": user.get("uid"),
                    "author_name": user.get("nickname"),
                    "followers": user.get("follower_count", 0),
                    "account_age_days": account_age_days,
                    "likes": comment.get("digg_count", 0),
                    "comments": comment.get("reply_comment_total", 0),  # 回复数
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["comment_id"] = comment.get("cid")
                standardized["metadata"]["aweme_id"] = post_id
                all_comments.append(standardized)

                if len(all_comments) >= limit:
                    break

            # 获取下一页cursor
            cursor = data.get("cursor", 0)
            if not data.get("has_more", False):
                break

            await asyncio.sleep(0.5)  # 避免过度请求

        logger.info(f"✅ Fetched {len(all_comments)} comments for video {post_id}")
        return all_comments[:limit]

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

        url = "https://www.douyin.com/aweme/v1/web/general/search/single/"
        all_videos = []
        offset = 0

        while len(all_videos) < limit:
            params = {
                "keyword": keyword,
                "search_channel": "aweme_video_web",
                "sort_type": sort_type,
                "publish_time": 0,  # 0=不限, 1=一天内, 7=一周内, 182=半年内
                "offset": offset,
                "count": min(20, limit - len(all_videos)),
            }

            data = await self._make_request(url, params)
            if not data or "data" not in data:
                break

            aweme_list = data.get("data", [])
            if not aweme_list:
                break

            for aweme in aweme_list:
                aweme_info = aweme.get("aweme_info", {})
                author = aweme_info.get("author", {})
                statistics = aweme_info.get("statistics", {})
                video_info = aweme_info.get("video", {})

                # 提取视频封面和播放地址
                cover_url = video_info.get("cover", {}).get("url_list", [None])[0]
                play_url = video_info.get("play_addr", {}).get("url_list", [None])[0]

                # 提取话题标签
                entities = []
                text_extra = aweme_info.get("text_extra", [])
                for extra in text_extra:
                    if extra.get("hashtag_name"):
                        entities.append(f"#{extra['hashtag_name']}")

                # 账户年龄
                create_time = author.get("create_time", 0)
                account_age_days = (
                    int((datetime.now().timestamp() - create_time) // 86400)
                    if create_time > 0
                    else None
                )

                raw_data = {
                    "url": f"https://www.douyin.com/video/{aweme_info.get('aweme_id', '')}",
                    "text": aweme_info.get("desc", ""),
                    "images": [cover_url] if cover_url else [],
                    "video": play_url,
                    "created_at": datetime.fromtimestamp(
                        aweme_info.get("create_time", 0)
                    ).isoformat()
                    if aweme_info.get("create_time")
                    else datetime.utcnow().isoformat(),
                    "author_id": author.get("uid"),
                    "author_name": author.get("nickname"),
                    "followers": author.get("follower_count", 0),
                    "account_age_days": account_age_days,
                    "likes": statistics.get("digg_count", 0),
                    "comments": statistics.get("comment_count", 0),
                    "shares": statistics.get("share_count", 0),
                    "entities": entities,
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["aweme_id"] = aweme_info.get("aweme_id")
                standardized["metadata"]["view_count"] = statistics.get("play_count", 0)
                standardized["metadata"]["duration"] = (
                    video_info.get("duration", 0) / 1000
                )
                standardized["metadata"]["search_keyword"] = keyword
                all_videos.append(standardized)

            offset += len(aweme_list)
            await asyncio.sleep(0.5)  # 避免过度请求

            # 如果返回的结果少于请求数量，说明已经到底
            if len(aweme_list) < params["count"]:
                break

        if not all_videos:
            public_videos = await self._search_public_site_index(keyword=keyword, limit=limit)
            if public_videos:
                logger.info(
                    f"✅ Douyin public search fallback returned {len(public_videos)} videos"
                )
                return public_videos[:limit]

        logger.info(f"✅ Found {len(all_videos)} videos for keyword: {keyword}")
        return all_videos[:limit]

    async def _search_public_site_index(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """无登录态兜底：使用公开搜索索引抓取抖音链接。"""
        kw = (keyword or "").strip()
        if not kw:
            return []
        await self.rate_limit_wait()
        queries = [
            f"site:douyin.com/video {kw}",
            f"site:www.douyin.com/video {kw}",
            f"site:douyin.com {kw}",
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://duckduckgo.com/",
        }
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=15.0,
                follow_redirects=True,
            ) as client:
                for query in queries:
                    resp = await client.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                    )
                    resp.raise_for_status()
                    parsed = self._parse_public_site_results(
                        resp.text,
                        keyword=kw,
                        limit=limit,
                    )
                    if parsed:
                        return parsed
                    jina_url = (
                        "https://r.jina.ai/http://html.duckduckgo.com/html/?q="
                        + urllib.parse.quote(query)
                    )
                    jina_resp = await client.get(jina_url)
                    jina_resp.raise_for_status()
                    parsed = self._parse_public_markdown_results(
                        jina_resp.text,
                        keyword=kw,
                        limit=limit,
                    )
                    if parsed:
                        return parsed
            return []
        except Exception as e:
            logger.warning(f"⚠️ Douyin public search fallback failed: {e}")
            return []

    def _parse_public_site_results(
        self,
        html: str,
        *,
        keyword: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html or "", "html.parser")
        rows = soup.select(".result") or soup.select(".web-result")
        out: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for row in rows:
            a = row.select_one("a.result__a")
            snippet_el = row.select_one(".result__snippet")
            if a is None:
                continue
            target_url = self._decode_public_search_url(str(a.get("href") or ""))
            if not target_url:
                continue
            if not self._is_valid_public_content_url(target_url):
                continue
            normalized_url = target_url.split("#", 1)[0]
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)

            title = a.get_text(" ", strip=True)
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            text = " ".join([x for x in [title, snippet] if x]).strip()
            if not text:
                continue
            score = self._keyword_match_score(keyword, text)
            aweme_id = self._extract_aweme_id_from_url(target_url)
            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "douyin_public_search",
                "author_name": "Douyin Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["aweme_id"] = aweme_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "douyin_public_search"
            meta["provider"] = "native_public_search"
            meta["search_engine"] = "duckduckgo"
            item["metadata"] = meta
            out.append(item)
            if len(out) >= int(limit):
                break
        return out

    def _parse_public_markdown_results(
        self,
        markdown_text: str,
        *,
        keyword: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
        rows: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for title, href in pattern.findall(markdown_text or ""):
            target_url = self._decode_public_search_url(href)
            if not target_url:
                continue
            if not self._is_valid_public_content_url(target_url):
                continue
            normalized_url = target_url.split("#", 1)[0]
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            text = str(title or "").strip()
            if not text:
                continue
            score = self._keyword_match_score(keyword, text)
            aweme_id = self._extract_aweme_id_from_url(target_url)
            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "douyin_public_search",
                "author_name": "Douyin Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["aweme_id"] = aweme_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "douyin_public_search"
            meta["provider"] = "native_public_search"
            meta["search_engine"] = "duckduckgo_jina"
            item["metadata"] = meta
            rows.append(item)
            if len(rows) >= int(limit):
                break
        return rows

    def _is_valid_public_content_url(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower()
            path = (parsed.path or "").lower()
            if host in {"v.douyin.com"}:
                return True
            if host not in {"www.douyin.com", "douyin.com"}:
                return False
            return "/video/" in path or "/note/" in path
        except Exception:
            return False

    def _decode_public_search_url(self, href: str) -> str:
        href = (href or "").strip()
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or ""):
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("uddg"):
                return urllib.parse.unquote(qs["uddg"][0])
        return href

    def _extract_aweme_id_from_url(self, url: str) -> Optional[str]:
        try:
            parsed = urllib.parse.urlparse(url)
            parts = [p for p in parsed.path.split("/") if p]
            if not parts:
                return None
            if "video" in parts:
                idx = parts.index("video")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            return parts[-1]
        except Exception:
            return None

    def _keyword_match_score(self, keyword: str, text: str) -> float:
        kw = (keyword or "").strip().lower()
        content = (text or "").strip().lower()
        if not kw or not content:
            return 0.0
        kw_compact = re.sub(r"\s+", "", kw)
        content_compact = re.sub(r"\s+", "", content)
        if not kw_compact or not content_compact:
            return 0.0
        if kw_compact in content_compact:
            return 1.0

        tokens = {
            tok
            for tok in re.split(r"[\s,，。！？!?:：;；、/|]+", kw_compact)
            if tok
        }
        if re.search(r"[\u4e00-\u9fff]", kw_compact):
            for i in range(max(0, len(kw_compact) - 1)):
                gram = kw_compact[i : i + 2]
                if len(gram) == 2 and re.search(r"[\u4e00-\u9fff]", gram):
                    tokens.add(gram)
        token_hits = sum(1 for tok in tokens if tok in content_compact)
        token_ratio = token_hits / max(1, len(tokens))

        char_set = {
            ch
            for ch in kw_compact
            if re.match(r"[\u4e00-\u9fffA-Za-z0-9]", ch)
        }
        char_hits = sum(1 for ch in char_set if ch in content_compact)
        char_ratio = char_hits / max(1, len(char_set))

        score = max(token_ratio, char_ratio * 0.85)
        if char_ratio >= 0.6 and token_hits > 0:
            score = max(score, 0.55)
        return round(min(score, 1.0), 4)

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
