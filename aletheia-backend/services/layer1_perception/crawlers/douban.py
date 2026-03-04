"""
豆瓣爬虫 - 电影/书籍/音乐/评论社区数据采集
"""

import os
import re
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from .base import BaseCrawler
from utils.logging import logger


class DoubanCrawler(BaseCrawler):
    """豆瓣爬虫（电影、书籍、音乐、小组讨论）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 2,  # 豆瓣速率限制较严格: 2 req/s
    ):
        """
        初始化豆瓣爬虫

        Args:
            cookies: 豆瓣登录Cookies（可选，但强烈建议使用）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="douban", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("DOUBAN_COOKIES", "")
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.douban.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            if self.cookies:
                headers["Cookie"] = self.cookies

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ Douban crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Douban session deferred (no running event loop during init)"
                )
            else:
                raise
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    async def _make_request(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[str]:
        """
        发起HTTP请求

        Args:
            url: 请求URL
            params: 查询参数

        Returns:
            响应HTML文本
        """
        await self.rate_limit_wait()

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        try:
            async with self.session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    return await self._make_request(url, params)
                elif response.status == 403:
                    logger.error(
                        "❌ Access forbidden. Cookies may be invalid or expired."
                    )
                    return None
                else:
                    logger.error(f"❌ Douban error: {response.status}")
                    return None

        except asyncio.TimeoutError:
            logger.error("❌ Request timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Request failed: {e}")
            return None

    async def _make_api_request(
        self, url: str, params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        发起API请求（JSON响应）

        Args:
            url: API URL
            params: 查询参数

        Returns:
            JSON数据
        """
        await self.rate_limit_wait()

        if not self.session:
            self._init_session()
        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        try:
            async with self.session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning("⚠️ Rate limit hit. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    return await self._make_api_request(url, params)
                else:
                    logger.error(f"❌ Douban API error: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"❌ API request failed: {e}")
            return None

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取豆瓣热门话题（豆瓣广场热门动态）

        Args:
            limit: 返回数量限制

        Returns:
            热门话题列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Douban...")

        # 豆瓣广场API
        url = "https://m.douban.com/rexxar/api/v2/timeline/statuses"
        params = {
            "count": min(limit, 50),
            "ck": "",  # 登录后会有ck参数
        }

        data = await self._make_api_request(url, params)
        if not data or "activities" not in data:
            logger.warning("⚠️ No hot topics found")
            return []

        activities = data.get("activities", [])
        results = []

        for activity in activities[:limit]:
            target = activity.get("target", {})
            target_type = activity.get("target_type", "")
            author = activity.get("author", {})

            # 提取内容文本
            text = ""
            images = []
            video = None
            url_link = ""

            if target_type == "status":
                # 广播/状态更新
                text = target.get("text", "")
                reshared_status = target.get("reshared_status")
                if reshared_status:
                    text += f"\n转发: {reshared_status.get('text', '')}"

                # 提取图片
                photos = target.get("photos", [])
                for photo in photos:
                    img_url = photo.get("large", {}).get("url", "")
                    if img_url:
                        images.append(img_url)

                url_link = f"https://www.douban.com/people/{author.get('uid', '')}/status/{target.get('id', '')}"

            elif target_type in ["movie", "book", "music"]:
                # 影音书评
                text = target.get("comment", "")
                rating = target.get("rating", {}).get("value", 0)
                text = f"[评分: {rating}/5] {text}"

                card = target.get("card", {})
                images = [card.get("pic", {}).get("large", "")]
                url_link = card.get("url", "")

            elif target_type == "rec":
                # 推荐
                text = target.get("title", "")
                abstract = target.get("abstract", "")
                text = f"{text}\n{abstract}"
                url_link = target.get("url", "")

            # 提取话题标签
            entities = []
            hashtags = re.findall(r"#([^#]+)#", text)
            entities.extend([f"#{tag.strip()}" for tag in hashtags])

            # 账户年龄
            create_time = author.get("reg_time")
            account_age_days = None
            if create_time:
                try:
                    reg_date = datetime.strptime(create_time, "%Y-%m-%d")
                    account_age_days = (datetime.now() - reg_date).days
                except Exception:
                    pass

            raw_data = {
                "url": url_link
                or f"https://www.douban.com/people/{author.get('uid', '')}",
                "text": text,
                "images": images,
                "video": video,
                "created_at": target.get("created_at", datetime.utcnow().isoformat()),
                "author_id": author.get("uid"),
                "author_name": author.get("name"),
                "followers": 0,  # API不返回粉丝数
                "account_age_days": account_age_days,
                "likes": target.get("like_count", 0),
                "comments": target.get("comments_count", 0),
                "shares": target.get("reshares_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["activity_type"] = target_type
            standardized["metadata"]["activity_id"] = activity.get("id")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot topics from Douban")
        return results[:limit]

    async def search_groups(
        self, keyword: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        搜索豆瓣小组讨论

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            小组讨论列表
        """
        logger.info(f"🔍 Searching Douban groups for: {keyword}...")

        url = "https://www.douban.com/group/search"
        params = {
            "q": keyword,
            "cat": "1013",  # 小组讨论分类
        }

        html = await self._make_request(url, params)
        if not html:
            logger.warning(f"⚠️ No search results found for: {keyword}")
            return []

        # 使用BeautifulSoup解析HTML
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error(
                "❌ BeautifulSoup not installed. Install with: pip install beautifulsoup4"
            )
            return []

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # 提取搜索结果
        search_results = soup.find_all("div", class_="result")

        for result in search_results[:limit]:
            title_tag = result.find("h3")
            if not title_tag:
                continue

            link_tag = title_tag.find("a")
            title = link_tag.get_text(strip=True) if link_tag else ""
            url_link = link_tag.get("href", "") if link_tag else ""

            # 提取摘要
            content_div = result.find("div", class_="content")
            text = content_div.get_text(strip=True) if content_div else ""

            # 提取作者信息
            author_tag = result.find("span", class_="pl")
            author_name = ""
            if author_tag:
                author_text = author_tag.get_text()
                author_match = re.search(r"作者:\s*(\S+)", author_text)
                if author_match:
                    author_name = author_match.group(1)

            # 提取时间
            time_tag = result.find("span", class_="time")
            created_at = datetime.utcnow().isoformat()
            if time_tag:
                time_text = time_tag.get_text(strip=True)
                # 解析相对时间（如"3小时前"）
                # 这里简化处理，实际需要更复杂的时间解析
                created_at = datetime.utcnow().isoformat()

            raw_data = {
                "url": url_link,
                "text": f"{title}\n{text}",
                "images": [],
                "video": None,
                "created_at": created_at,
                "author_id": "",
                "author_name": author_name,
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [f"#{keyword}"],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["search_keyword"] = keyword
            standardized["metadata"]["source_type"] = "group"
            results.append(standardized)

        logger.info(f"✅ Found {len(results)} group discussions for: {keyword}")
        return results[:limit]

    async def search_movies(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索豆瓣电影

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            电影列表
        """
        logger.info(f"🔍 Searching Douban movies for: {keyword}...")

        url = "https://movie.douban.com/j/subject_suggest"
        params = {
            "q": keyword,
        }

        data = await self._make_api_request(url, params)
        if not data:
            logger.warning(f"⚠️ No movie results found for: {keyword}")
            return []

        results = []
        for movie in data[:limit]:
            title = movie.get("title", "")
            sub_title = movie.get("sub_title", "")
            year = movie.get("year", "")

            text = f"{title} ({year})"
            if sub_title:
                text += f" - {sub_title}"

            url_link = f"https://movie.douban.com/subject/{movie.get('id', '')}/"
            images = [movie.get("img", "")]

            raw_data = {
                "url": url_link,
                "text": text,
                "images": images,
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "douban_movie",
                "author_name": "豆瓣电影",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [f"#{keyword}"],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["movie_id"] = movie.get("id")
            standardized["metadata"]["year"] = year
            standardized["metadata"]["search_keyword"] = keyword
            results.append(standardized)

        logger.info(f"✅ Found {len(results)} movies for: {keyword}")
        return results[:limit]

    async def fetch_movie_reviews(
        self, movie_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取电影的热门影评

        Args:
            movie_id: 电影ID
            limit: 返回数量限制

        Returns:
            影评列表
        """
        logger.info(f"🔍 Fetching {limit} reviews for movie {movie_id}...")

        url = f"https://movie.douban.com/subject/{movie_id}/reviews"
        html = await self._make_request(url)

        if not html:
            logger.warning(f"⚠️ No reviews found for movie {movie_id}")
            return []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("❌ BeautifulSoup not installed")
            return []

        soup = BeautifulSoup(html, "html.parser")
        results = []

        # 提取影评列表
        review_items = soup.find_all("div", class_="review-item")

        for item in review_items[:limit]:
            # 提取标题
            header = item.find("header", class_="main-hd")
            title_tag = header.find("a") if header else None
            title = title_tag.get_text(strip=True) if title_tag else ""
            url_link = title_tag.get("href", "") if title_tag else ""

            # 提取作者
            author_tag = item.find("a", class_="name")
            author_name = author_tag.get_text(strip=True) if author_tag else ""

            # 提取评分
            rating_tag = item.find("span", class_=re.compile("allstar"))
            rating = 0
            if rating_tag:
                rating_class = rating_tag.get("class", [])
                for cls in rating_class:
                    if "allstar" in cls:
                        match = re.search(r"allstar(\d)", cls)
                        if match:
                            rating = int(match.group(1))

            # 提取内容
            content_div = item.find("div", class_="short-content")
            text = content_div.get_text(strip=True) if content_div else ""
            text = f"[评分: {rating}/5] {title}\n{text}"

            # 提取统计数据
            vote_tag = item.find("span", class_="votes")
            likes = int(vote_tag.get_text(strip=True)) if vote_tag else 0

            # 提取时间
            time_tag = item.find("span", class_="main-meta")
            created_at = datetime.utcnow().isoformat()
            if time_tag:
                time_text = time_tag.get_text(strip=True)
                # 这里简化处理
                created_at = datetime.utcnow().isoformat()

            raw_data = {
                "url": url_link,
                "text": text,
                "images": [],
                "video": None,
                "created_at": created_at,
                "author_id": "",
                "author_name": author_name,
                "followers": 0,
                "account_age_days": None,
                "likes": likes,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["movie_id"] = movie_id
            standardized["metadata"]["rating"] = rating
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} reviews for movie {movie_id}")
        return results[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户的广播动态

        Args:
            user_id: 用户ID
            limit: 返回数量限制

        Returns:
            用户动态列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        url = f"https://m.douban.com/rexxar/api/v2/user/{user_id}/statuses"
        params = {
            "count": min(limit, 50),
        }

        data = await self._make_api_request(url, params)
        if not data or "statuses" not in data:
            logger.warning(f"⚠️ No posts found for user {user_id}")
            return []

        statuses = data.get("statuses", [])
        results = []

        for status in statuses[:limit]:
            text = status.get("text", "")

            # 提取图片
            images = []
            photos = status.get("photos", [])
            for photo in photos:
                img_url = photo.get("large", {}).get("url", "")
                if img_url:
                    images.append(img_url)

            # 提取话题标签
            entities = []
            hashtags = re.findall(r"#([^#]+)#", text)
            entities.extend([f"#{tag.strip()}" for tag in hashtags])

            raw_data = {
                "url": f"https://www.douban.com/people/{user_id}/status/{status.get('id', '')}",
                "text": text,
                "images": images,
                "video": None,
                "created_at": status.get("created_at", datetime.utcnow().isoformat()),
                "author_id": user_id,
                "author_name": status.get("user", {}).get("name", ""),
                "followers": 0,
                "account_age_days": None,
                "likes": status.get("like_count", 0),
                "comments": status.get("comments_count", 0),
                "shares": status.get("reshares_count", 0),
                "entities": entities,
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["status_id"] = status.get("id")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} posts from user {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取广播的评论

        Args:
            post_id: 广播ID
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for post {post_id}...")

        url = f"https://m.douban.com/rexxar/api/v2/status/{post_id}/comments"
        params = {
            "count": min(limit, 50),
        }

        data = await self._make_api_request(url, params)
        if not data or "comments" not in data:
            logger.warning(f"⚠️ No comments found for post {post_id}")
            return []

        comments = data.get("comments", [])
        results = []

        for comment in comments[:limit]:
            author = comment.get("author", {})

            raw_data = {
                "url": f"https://www.douban.com/people/{author.get('uid', '')}/",
                "text": comment.get("text", ""),
                "images": [],
                "video": None,
                "created_at": comment.get("create_time", datetime.utcnow().isoformat()),
                "author_id": author.get("uid"),
                "author_name": author.get("name"),
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["comment_id"] = comment.get("id")
            standardized["metadata"]["status_id"] = post_id
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} comments for post {post_id}")
        return results[:limit]

    async def close(self):
        """关闭爬虫,释放资源"""
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        await super().close()
