"""
小红书爬虫 - 使用HTTP API（非官方）
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


class XiaohongshuCrawler(BaseCrawler):
    """小红书爬虫（使用非官方API）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 5,  # 保守速率: 5 req/s
    ):
        """
        初始化小红书爬虫

        Args:
            cookies: 小红书登录Cookies（可选,有助于访问更多内容）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="xiaohongshu", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("XHS_COOKIES", "")
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.xiaohongshu.com/",
                "Origin": "https://www.xiaohongshu.com",
            }

            if self.cookies:
                headers["Cookie"] = self.cookies

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Xiaohongshu crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Xiaohongshu session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    def _sign_request(self, url: str, params: Dict) -> Dict:
        """
        为请求生成签名（小红书反爬）
        注意: 这是一个简化版本，实际签名算法更复杂

        Args:
            url: 请求URL
            params: 请求参数

        Returns:
            添加签名后的参数
        """
        # 简化签名: 在生产环境中需要使用更复杂的算法
        # 建议使用 xhs 库或逆向工程小红书的签名算法
        params_str = json.dumps(params, sort_keys=True)
        timestamp = str(int(datetime.now().timestamp() * 1000))
        sign_str = f"{url}{params_str}{timestamp}"
        signature = hashlib.md5(sign_str.encode()).hexdigest()

        params["timestamp"] = timestamp
        params["sign"] = signature
        return params

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
            # 添加签名（防爬虫）
            if params:
                params = self._sign_request(url, params)

            async with self.session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success") or data.get("code") == 0:
                        return data
                    else:
                        logger.warning(
                            f"⚠️ XHS API returned error: {data.get('msg', 'Unknown error')}"
                        )
                        return None
                elif response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    return await self._make_request(url, params)
                else:
                    body = await response.text()
                    logger.error(
                        f"❌ XHS API error: status={response.status}, url={url}, body={body[:200]}"
                    )
                    return None
        except asyncio.TimeoutError:
            logger.error(f"❌ Request timeout: GET {url}")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {type(e).__name__}: {e} (url={url})")
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取小红书热搜榜

        Args:
            limit: 返回数量限制

        Returns:
            热搜列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Xiaohongshu...")

        # 小红书热搜API（可能需要更新）
        url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/hot_list"

        data = await self._make_request(url)
        if not data or "data" not in data:
            logger.warning("⚠️ No hot topics found")
            return []

        hot_items = data.get("data", {}).get("items", [])

        results = []
        for item in hot_items[:limit]:
            hot_query = item.get("hot_query", "")
            hot_value = item.get("hot_value", 0)  # 热度值

            # 获取该话题下的热门笔记
            notes = await self._search_notes(hot_query, limit=3)

            if notes:
                # 使用第一篇笔记作为代表
                note = notes[0]
                note["metadata"]["hot_topic"] = hot_query
                note["metadata"]["hot_value"] = hot_value
                results.append(note)
            else:
                # 如果没有笔记，创建一个纯话题项
                raw_data = {
                    "url": f"https://www.xiaohongshu.com/search_result?keyword={hot_query}",
                    "text": f"热搜话题: {hot_query}",
                    "images": [],
                    "video": None,
                    "created_at": datetime.utcnow().isoformat(),
                    "author_id": "xiaohongshu_official",
                    "author_name": "小红书热搜",
                    "followers": 0,
                    "account_age_days": 3650,  # 假设10年
                    "likes": hot_value,
                    "comments": 0,
                    "shares": 0,
                    "entities": [f"#{hot_query}"],
                }
                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["hot_topic"] = hot_query
                standardized["metadata"]["hot_value"] = hot_value
                results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot topics from Xiaohongshu")
        return results[:limit]

    async def _search_notes(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索笔记（内部方法）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            笔记列表
        """
        url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
        params = {
            "keyword": keyword,
            "page": 1,
            "page_size": min(limit, 20),
            "search_id": hashlib.md5(keyword.encode()).hexdigest(),
            "sort": "general",  # general=综合, time_descending=最新, popularity_descending=最热
        }

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            return []

        items = data.get("data", {}).get("items", [])
        results = []

        for item in items:
            note_card = item.get("note_card", {})
            user = note_card.get("user", {})
            interact_info = note_card.get("interact_info", {})

            # 提取图片
            image_list = note_card.get("image_list", [])
            images = [
                img.get("url_default") for img in image_list if img.get("url_default")
            ]

            # 提取视频
            video = None
            video_info = note_card.get("video", {})
            if video_info:
                video = video_info.get("consumer", {}).get("origin_video_key")

            # 提取实体（话题标签）
            entities = []
            tag_list = note_card.get("tag_list", [])
            for tag in tag_list:
                tag_name = tag.get("name", "")
                if tag_name:
                    entities.append(f"#{tag_name}")

            # 计算账户年龄（小红书API不提供,设为None）
            account_age_days = None

            raw_data = {
                "url": f"https://www.xiaohongshu.com/explore/{note_card.get('note_id', '')}",
                "text": note_card.get("display_title", "")
                or note_card.get("title", ""),
                "images": images,
                "video": video,
                "created_at": datetime.fromtimestamp(
                    note_card.get("time", 0) / 1000
                ).isoformat()
                if note_card.get("time")
                else datetime.utcnow().isoformat(),
                "author_id": user.get("user_id"),
                "author_name": user.get("nickname"),
                "followers": 0,  # 小红书API不直接返回粉丝数
                "account_age_days": account_age_days,
                "likes": interact_info.get("liked_count", 0),
                "comments": interact_info.get("comment_count", 0),
                "shares": interact_info.get("share_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["note_id"] = note_card.get("note_id")
            standardized["metadata"]["note_type"] = note_card.get(
                "type"
            )  # normal/video
            results.append(standardized)

        return results

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户发布的笔记

        Args:
            user_id: 用户ID
            limit: 返回数量限制

        Returns:
            用户笔记列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        url = "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted"
        params = {
            "user_id": user_id,
            "cursor": "",
            "num": min(limit, 30),
            "image_scenes": "FD_PRV_WEBP,FD_WM_WEBP",
        }

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No posts found for user {user_id}")
            return []

        notes = data.get("data", {}).get("notes", [])
        results = []

        for note in notes:
            # 提取图片
            image_list = note.get("image_list", [])
            images = [
                img.get("url_default") for img in image_list if img.get("url_default")
            ]

            # 提取视频
            video = None
            video_info = note.get("video", {})
            if video_info:
                video = video_info.get("consumer", {}).get("origin_video_key")

            # 提取实体
            entities = []
            tag_list = note.get("tag_list", [])
            for tag in tag_list:
                tag_name = tag.get("name", "")
                if tag_name:
                    entities.append(f"#{tag_name}")

            interact_info = note.get("interact_info", {})

            raw_data = {
                "url": f"https://www.xiaohongshu.com/explore/{note.get('note_id', '')}",
                "text": note.get("display_title", "") or note.get("title", ""),
                "images": images,
                "video": video,
                "created_at": datetime.fromtimestamp(
                    note.get("time", 0) / 1000
                ).isoformat()
                if note.get("time")
                else datetime.utcnow().isoformat(),
                "author_id": user_id,
                "author_name": note.get("user", {}).get("nickname"),
                "followers": 0,
                "account_age_days": None,
                "likes": interact_info.get("liked_count", 0),
                "comments": interact_info.get("comment_count", 0),
                "shares": interact_info.get("share_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["note_id"] = note.get("note_id")
            standardized["metadata"]["note_type"] = note.get("type")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} posts from user {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取笔记的评论

        Args:
            post_id: 笔记ID
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for note {post_id}...")

        url = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
        params = {
            "note_id": post_id,
            "cursor": "",
            "top_comment_id": "",
            "image_scenes": "FD_PRV_WEBP,FD_WM_WEBP",
        }

        all_comments = []
        cursor = ""

        while len(all_comments) < limit:
            params["cursor"] = cursor
            data = await self._make_request(url, params)

            if not data or "data" not in data:
                break

            comments = data.get("data", {}).get("comments", [])
            if not comments:
                break

            for comment in comments:
                user = comment.get("user_info", {})

                # 提取图片（评论可能包含图片）
                images = []
                pics = comment.get("pictures", [])
                for pic in pics:
                    if pic.get("url_default"):
                        images.append(pic["url_default"])

                raw_data = {
                    "url": f"https://www.xiaohongshu.com/explore/{post_id}?comment_id={comment.get('id', '')}",
                    "text": comment.get("content", ""),
                    "images": images,
                    "video": None,
                    "created_at": datetime.fromtimestamp(
                        comment.get("create_time", 0) / 1000
                    ).isoformat()
                    if comment.get("create_time")
                    else datetime.utcnow().isoformat(),
                    "author_id": user.get("user_id"),
                    "author_name": user.get("nickname"),
                    "followers": 0,
                    "account_age_days": None,
                    "likes": comment.get("like_count", 0),
                    "comments": comment.get("sub_comment_count", 0),  # 子评论数
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["comment_id"] = comment.get("id")
                standardized["metadata"]["note_id"] = post_id
                all_comments.append(standardized)

                if len(all_comments) >= limit:
                    break

            # 获取下一页cursor
            cursor = data.get("data", {}).get("cursor", "")
            if not cursor:
                break

            # 避免过度请求
            await asyncio.sleep(0.5)

        logger.info(f"✅ Fetched {len(all_comments)} comments for note {post_id}")
        return all_comments[:limit]

    async def search_notes(
        self, keyword: str, limit: int = 50, sort_by: str = "general"
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的笔记（用于特定信息验证）

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            sort_by: 排序方式 (general=综合, time_descending=最新, popularity_descending=最热)

        Returns:
            笔记列表
        """
        logger.info(f"🔍 Searching notes with keyword: {keyword} (sort: {sort_by})...")

        url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
        all_notes = []
        page = 1

        while len(all_notes) < limit:
            params = {
                "keyword": keyword,
                "page": page,
                "page_size": min(20, limit - len(all_notes)),
                "search_id": hashlib.md5(f"{keyword}{page}".encode()).hexdigest(),
                "sort": sort_by,
            }

            data = await self._make_request(url, params)
            if not data or "data" not in data:
                break

            items = data.get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                note_card = item.get("note_card", {})
                user = note_card.get("user", {})
                interact_info = note_card.get("interact_info", {})

                # 提取图片
                image_list = note_card.get("image_list", [])
                images = [
                    img.get("url_default")
                    for img in image_list
                    if img.get("url_default")
                ]

                # 提取视频
                video = None
                video_info = note_card.get("video", {})
                if video_info:
                    video = video_info.get("consumer", {}).get("origin_video_key")

                # 提取实体
                entities = []
                tag_list = note_card.get("tag_list", [])
                for tag in tag_list:
                    tag_name = tag.get("name", "")
                    if tag_name:
                        entities.append(f"#{tag_name}")

                raw_data = {
                    "url": f"https://www.xiaohongshu.com/explore/{note_card.get('note_id', '')}",
                    "text": note_card.get("display_title", "")
                    or note_card.get("title", ""),
                    "images": images,
                    "video": video,
                    "created_at": datetime.fromtimestamp(
                        note_card.get("time", 0) / 1000
                    ).isoformat()
                    if note_card.get("time")
                    else datetime.utcnow().isoformat(),
                    "author_id": user.get("user_id"),
                    "author_name": user.get("nickname"),
                    "followers": 0,
                    "account_age_days": None,
                    "likes": interact_info.get("liked_count", 0),
                    "comments": interact_info.get("comment_count", 0),
                    "shares": interact_info.get("share_count", 0),
                    "entities": entities,
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["note_id"] = note_card.get("note_id")
                standardized["metadata"]["note_type"] = note_card.get("type")
                standardized["metadata"]["search_keyword"] = keyword
                all_notes.append(standardized)

            page += 1

            # 避免过度请求
            await asyncio.sleep(0.5)

            # 如果返回的结果少于请求数量,说明已经到底
            if len(items) < params["page_size"]:
                break

        if not all_notes:
            public_notes = await self._search_public_site_index(keyword=keyword, limit=limit)
            if public_notes:
                logger.info(
                    f"✅ Xiaohongshu public search fallback returned {len(public_notes)} notes"
                )
                return public_notes[:limit]

        logger.info(f"✅ Found {len(all_notes)} notes for keyword: {keyword}")
        return all_notes[:limit]

    async def _search_public_site_index(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """无登录态兜底：使用公开搜索索引抓取小红书链接。"""
        kw = (keyword or "").strip()
        if not kw:
            return []
        await self.rate_limit_wait()
        queries = [
            f"site:xiaohongshu.com/discovery/item {kw}",
            f"site:xiaohongshu.com/explore {kw}",
            f"site:xiaohongshu.com {kw}",
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
                    # 网络环境可能被 DDG 反爬 202 空结果，转用 jina 代理抓取同一搜索页。
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
            logger.warning(f"⚠️ Xiaohongshu public search fallback failed: {e}")
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
            note_id = self._extract_note_id_from_url(target_url)
            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "xhs_public_search",
                "author_name": "XHS Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["note_id"] = note_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "xiaohongshu_public_search"
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
            note_id = self._extract_note_id_from_url(target_url)
            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "xhs_public_search",
                "author_name": "XHS Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["note_id"] = note_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "xiaohongshu_public_search"
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
            if host.endswith("xhslink.com"):
                return True
            if host not in {"www.xiaohongshu.com", "xiaohongshu.com"}:
                return False
            return "/discovery/item/" in path or "/explore/" in path
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

    def _extract_note_id_from_url(self, url: str) -> Optional[str]:
        try:
            parsed = urllib.parse.urlparse(url)
            parts = [p for p in parsed.path.split("/") if p]
            if not parts:
                return None
            if "explore" in parts:
                idx = parts.index("explore")
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

    async def extract_text_from_image(self, image_url: str) -> Optional[str]:
        """
        从图片中提取文字（OCR）

        Args:
            image_url: 图片URL

        Returns:
            提取的文字
        """
        logger.info(f"🔍 Extracting text from image: {image_url}")

        try:
            # 使用第三方OCR服务（示例：百度OCR, 阿里云OCR等）
            # 这里提供一个简化的实现框架

            # 1. 下载图片
            if not self.session:
                self._init_session()
            if not self.session:
                return None

            async with self.session.get(image_url) as response:
                if response.status != 200:
                    return None
                image_data = await response.read()

            # 2. 调用OCR API（需要配置相应的API密钥）
            # 示例: 使用百度OCR
            # from aip import AipOcr
            # app_id = os.getenv("BAIDU_OCR_APP_ID")
            # api_key = os.getenv("BAIDU_OCR_API_KEY")
            # secret_key = os.getenv("BAIDU_OCR_SECRET_KEY")
            # client = AipOcr(app_id, api_key, secret_key)
            # result = client.basicGeneral(image_data)
            # text = "\n".join([word["words"] for word in result.get("words_result", [])])

            # 简化版: 返回占位符
            logger.warning("⚠️ OCR功能需要配置第三方OCR服务（百度/阿里云/腾讯云）")
            return "[OCR功能未配置]"

        except Exception as e:
            logger.error(f"❌ OCR extraction failed: {e}")
            return None

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
