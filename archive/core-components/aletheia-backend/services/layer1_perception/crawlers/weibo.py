"""
微博爬虫实现
"""

import asyncio
import json
import re
import urllib.parse
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from services.layer1_perception.crawlers.base import BaseCrawler
from services.account_pool import get_account_pool_manager
from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env


_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ WeiboCrawler disable httpx trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


class WeiboCrawler(BaseCrawler):
    """微博爬虫"""

    def __init__(self):
        super().__init__(platform_name="weibo", rate_limit=settings.WEIBO_RATE_LIMIT)

        self.ua = UserAgent()
        self.session: Optional[httpx.AsyncClient] = None
        self.account_pool = get_account_pool_manager()

        # 微博API端点
        self.hot_search_url = "https://weibo.com/ajax/side/hotSearch"
        self.user_posts_url = "https://weibo.com/ajax/statuses/mymblog"
        self.comments_url = "https://weibo.com/ajax/statuses/buildComments"
        self.public_search_url = "https://html.duckduckgo.com/html/"

    async def _get_session(self) -> httpx.AsyncClient:
        """获取或创建HTTP会话"""
        if self.session is None:
            headers = {
                "User-Agent": self.ua.random,
                "Referer": "https://weibo.com",
            }

            self.session = httpx.AsyncClient(
                headers=headers,
                timeout=30.0,
                follow_redirects=True,
                trust_env=_HTTPX_TRUST_ENV,
            )

        return self.session

    def _request_attempt_budget(self) -> int:
        pool = self.account_pool.get_pool("weibo")
        if pool is None:
            return 1
        return max(1, min(3, pool.size()))

    async def _request_with_account_rotation(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        对 401/403/429 做账号轮转重试，减少单 Cookie 失效导致的平台级失败。
        """
        session = await self._get_session()
        attempts = self._request_attempt_budget()
        last_response: Optional[httpx.Response] = None
        last_exc: Optional[Exception] = None

        for _ in range(attempts):
            cookie = self.account_pool.acquire_cookie("weibo") or str(
                getattr(settings, "WEIBO_COOKIES", "") or ""
            ).strip()
            headers = {"Cookie": cookie} if cookie else None
            try:
                resp = await session.get(url, params=params, headers=headers)
                last_response = resp
                status = int(resp.status_code)
                if status < 400:
                    self.account_pool.mark_success("weibo", cookie)
                    return resp
                if status in {401, 403, 429}:
                    self.account_pool.mark_failure(
                        "weibo", cookie, reason=f"status_{status}"
                    )
                    continue
                return resp
            except Exception as exc:
                last_exc = exc
                self.account_pool.mark_failure(
                    "weibo", cookie, reason=type(exc).__name__
                )

        if last_response is not None:
            return last_response
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("weibo request failed without response")

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取微博热搜

        Returns:
            [
                {
                    "rank": 1,
                    "keyword": "话题名称",
                    "hot_value": 1234567,
                    "url": "https://s.weibo.com/weibo?q=%23....",
                    "category": "社会"
                },
                ...
            ]
        """
        await self.rate_limit_wait()

        logger.info(f"🔍 Fetching Weibo hot search (limit={limit})")

        try:
            response = await self._request_with_account_rotation(self.hot_search_url)
            response.raise_for_status()

            data = response.json()

            if data.get("ok") != 1:
                logger.error(f"❌ Weibo API error: {data}")
                return []

            hot_list = data.get("data", {}).get("realtime", [])

            results = []
            for idx, item in enumerate(hot_list[:limit], 1):
                keyword = item.get("word", "")
                hot_value = item.get("num", 0)

                # 构造标准化数据
                standardized = {
                    "url": f"https://s.weibo.com/weibo?q=%23{keyword}%23",
                    "text": keyword,
                    "author_id": "weibo_hot_search",
                    "author_name": "微博热搜",
                    "created_at": item.get("onboard_time"),
                    "likes": hot_value,  # 用热度值模拟点赞数
                    "comments": 0,
                    "shares": 0,
                    "followers": 1000000,  # 假设微博热搜有100万关注
                    "entities": [keyword],
                    "extra": {
                        "rank": idx,
                        "hot_value": hot_value,
                        "category": item.get("category", "综合"),
                        "icon": item.get("icon"),
                        "label": item.get("label_name"),
                    },
                }

                results.append(self.standardize_item(standardized))

            logger.info(f"✅ Fetched {len(results)} hot topics from Weibo")
            return results

        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP error when fetching Weibo hot search: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching Weibo hot search: {e}", exc_info=True)
            return []

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户微博

        Args:
            user_id: 微博用户ID
            limit: 返回数量

        Returns:
            用户微博列表
        """
        await self.rate_limit_wait()

        logger.info(f"🔍 Fetching posts for Weibo user {user_id}")

        try:
            params = {
                "uid": user_id,
                "page": 1,
                "feature": 0,
            }

            response = await self._request_with_account_rotation(
                self.user_posts_url,
                params=params,
            )
            response.raise_for_status()

            data = response.json()

            if data.get("ok") != 1:
                logger.error(f"❌ Weibo API error: {data}")
                return []

            posts = data.get("data", {}).get("list", [])

            results = []
            for post in posts[:limit]:
                # 解析微博内容
                text = post.get("text_raw", "") or self._clean_html(
                    post.get("text", "")
                )

                # 提取图片
                pic_infos = post.get("pic_infos", {})
                images = [
                    info.get("large", {}).get("url") for info in pic_infos.values()
                ]

                # 提取视频
                video = None
                page_info = post.get("page_info", {})
                if page_info.get("type") == "video":
                    video = page_info.get("urls", {}).get(
                        "mp4_720p_mp4"
                    ) or page_info.get("urls", {}).get("mp4_hd_mp4")

                # 用户信息
                user = post.get("user", {})

                standardized = {
                    "url": f"https://weibo.com/{user_id}/{post.get('id')}",
                    "text": text,
                    "images": images,
                    "video": video,
                    "author_id": str(user.get("id")),
                    "author_name": user.get("screen_name"),
                    "created_at": post.get("created_at"),
                    "likes": post.get("attitudes_count", 0),
                    "comments": post.get("comments_count", 0),
                    "shares": post.get("reposts_count", 0),
                    "followers": user.get("followers_count", 0),
                    "entities": self._extract_entities(text),
                }

                results.append(self.standardize_item(standardized))

            logger.info(f"✅ Fetched {len(results)} posts for user {user_id}")
            return results

        except Exception as e:
            logger.error(f"❌ Error fetching user posts: {e}", exc_info=True)
            return []

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取微博评论

        Args:
            post_id: 微博ID
            limit: 返回数量

        Returns:
            评论列表
        """
        await self.rate_limit_wait()

        logger.info(f"🔍 Fetching comments for Weibo post {post_id}")

        try:
            params = {
                "id": post_id,
                "is_show_bulletin": 2,
                "count": limit,
            }

            response = await self._request_with_account_rotation(
                self.comments_url,
                params=params,
            )
            response.raise_for_status()

            data = response.json()

            if data.get("ok") != 1:
                logger.error(f"❌ Weibo API error: {data}")
                return []

            comments = data.get("data", [])

            results = []
            for comment in comments:
                user = comment.get("user", {})

                standardized = {
                    "url": f"https://weibo.com/comment/{comment.get('id')}",
                    "text": comment.get("text_raw", "")
                    or self._clean_html(comment.get("text", "")),
                    "author_id": str(user.get("id")),
                    "author_name": user.get("screen_name"),
                    "created_at": comment.get("created_at"),
                    "likes": comment.get("like_counts", 0),
                    "comments": 0,
                    "shares": 0,
                    "followers": user.get("followers_count", 0),
                    "entities": [],
                }

                results.append(self.standardize_item(standardized))

            logger.info(f"✅ Fetched {len(results)} comments for post {post_id}")
            return results

        except Exception as e:
            logger.error(f"❌ Error fetching comments: {e}", exc_info=True)
            return []

    async def search_weibo(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        微博关键词搜索兜底实现。
        优先走免登录公开搜索索引（site:weibo.com），失败时回退热搜筛选。
        """
        keyword = (keyword or "").strip()
        if keyword and bool(getattr(settings, "WEIBO_ENABLE_PUBLIC_SEARCH", True)):
            public_results = await self._search_public_site_index(keyword=keyword, limit=limit)
            if public_results:
                logger.info(f"✅ Weibo public search fetched {len(public_results)} items for '{keyword}'")
                return public_results

        topics = await self.fetch_hot_topics(limit=max(limit * 3, limit))
        if not keyword:
            return topics[:limit]

        kw = keyword.strip().lower()
        matched = []
        for item in topics:
            text = str(item.get("content_text", "")).lower()
            if kw in text:
                matched.append(item)
        if matched:
            return matched[:limit]

        if keyword and not bool(
            getattr(settings, "WEIBO_SEARCH_ALLOW_HOT_FALLBACK", False)
        ):
            logger.warning(
                "weibo: no keyword match from public search/hot filter, skip internal hot fallback"
            )
            return []

        fallback = topics[:limit]
        for item in fallback:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            metadata["keyword_match"] = False
            metadata["retrieval_mode"] = "hot_fallback"
            item["metadata"] = metadata
        return fallback

    async def _search_public_site_index(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """通过公开搜索索引抓取微博链接（无需微博登录态）。"""
        await self.rate_limit_wait()
        if not keyword:
            return []

        try:
            query = f"site:weibo.com {keyword}"
            response = await self._request_with_account_rotation(
                self.public_search_url,
                params={"q": query},
            )
            response.raise_for_status()
            return self._parse_public_search_results(
                html=response.text,
                keyword=keyword,
                limit=limit,
            )
        except Exception as e:
            logger.warning(f"⚠️ Weibo public search failed: {e}")
            return []

    def _parse_public_search_results(
        self,
        html: str,
        keyword: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """解析公开搜索结果为统一微博证据结构。"""
        soup = BeautifulSoup(html or "", "html.parser")
        rows = soup.select(".result")
        if not rows:
            rows = soup.select(".web-result")

        results: List[Dict[str, Any]] = []
        for row in rows:
            title_el = row.select_one("a.result__a")
            snippet_el = row.select_one(".result__snippet")
            if title_el is None:
                continue

            raw_href = str(title_el.get("href") or "").strip()
            target_url = self._decode_public_search_url(raw_href)
            if not target_url:
                continue
            host = (urllib.parse.urlparse(target_url).hostname or "").lower()
            if "weibo.com" not in host and "weibo.cn" not in host:
                continue

            title = title_el.get_text(" ", strip=True)
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            text = " ".join(part for part in [title, snippet] if part).strip()
            if not text:
                continue

            score = self._keyword_match_score(keyword, text)
            post_id = self._extract_weibo_post_id_from_url(target_url)
            standardized = {
                "url": target_url,
                "text": text,
                "author_id": "weibo_public_search",
                "author_name": "Weibo Public Search",
                "created_at": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "followers": 0,
                "entities": self._extract_entities(text),
            }
            item = self.standardize_item(standardized)
            metadata = (
                item.get("metadata")
                if isinstance(item.get("metadata"), dict)
                else {}
            )
            metadata["keyword_match"] = bool(score >= 0.2)
            metadata["keyword_match_score"] = score
            metadata["retrieval_mode"] = "weibo_public_search"
            metadata["provider"] = "native_public_search"
            metadata["post_id"] = post_id
            metadata["search_engine"] = "duckduckgo"
            item["metadata"] = metadata
            results.append(item)
            if len(results) >= int(limit):
                break
        return results

    def _decode_public_search_url(self, href: str) -> str:
        """从公开搜索跳转链接中提取真实目标链接。"""
        if not href:
            return ""
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in (parsed.hostname or ""):
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("uddg"):
                return urllib.parse.unquote(qs["uddg"][0])
        return href

    def _extract_weibo_post_id_from_url(self, url: str) -> Optional[str]:
        """从微博URL中提取可用于评论抓取的帖子ID。"""
        try:
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            if "id" in query and query["id"]:
                return query["id"][0]
            path_parts = [part for part in parsed.path.split("/") if part]
            if path_parts:
                candidate = path_parts[-1]
                candidate = candidate.split("?")[0]
                if candidate and candidate not in {"show", "detail", "p"}:
                    return candidate
        except Exception:
            return None
        return None

    def _keyword_match_score(self, keyword: str, text: str) -> float:
        """计算关键词命中分数（兼容中文短语）。"""
        kw = (keyword or "").strip().lower()
        content = (text or "").strip().lower()
        if not kw or not content:
            return 0.0
        if kw in content:
            return 1.0

        tokens = [tok for tok in re.split(r"\s+", kw) if tok]
        if not tokens:
            return 0.0
        hits = sum(1 for tok in tokens if tok in content)
        score = hits / max(1, len(tokens))

        compact_kw = "".join(tokens)
        compact_content = re.sub(r"\s+", "", content)
        if compact_kw and compact_kw in compact_content:
            score = max(score, 1.0)
        return round(score, 4)

    def _clean_html(self, html_text: str) -> str:
        """清理HTML标签"""
        if not html_text:
            return ""
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text()

    def _extract_entities(self, text: str) -> List[str]:
        """提取实体(话题、@用户等)"""
        entities = []

        # 提取话题 #话题名#
        topics = re.findall(r"#([^#]+)#", text)
        entities.extend(topics)

        # 提取@用户
        mentions = re.findall(r"@([^\s:：]+)", text)
        entities.extend(mentions)

        return list(set(entities))  # 去重

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.aclose()
        await super().close()


# 测试代码
async def test_weibo_crawler():
    """测试微博爬虫"""
    crawler = WeiboCrawler()

    try:
        # 测试热搜
        hot_topics = await crawler.fetch_hot_topics(limit=10)
        print(f"\n📊 Hot Topics ({len(hot_topics)}):")
        for topic in hot_topics[:3]:
            print(
                f"  - {topic['content_text']} (热度: {topic['metadata'].get('likes', 0)})"
            )

        # 如果有Cookie,可以测试用户微博
        # user_posts = await crawler.fetch_user_posts("1234567890", limit=5)

    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(test_weibo_crawler())
