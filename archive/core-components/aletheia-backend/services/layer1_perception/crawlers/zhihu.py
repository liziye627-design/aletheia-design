"""
知乎爬虫 - 问答社区数据采集
"""

import os
import json
import re
import urllib.parse
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio

import httpx
from bs4 import BeautifulSoup

from .base import BaseCrawler
from core.config import settings
from services.account_pool import get_account_pool_manager
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
        f"⚠️ ZhihuCrawler disable proxy trust_env due unreachable local proxy: "
        f"{','.join(_BROKEN_LOCAL_PROXY)}"
    )

_HTTPX_TRUST_ENV, _HTTPX_BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", True)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _HTTPX_BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ ZhihuCrawler disable httpx trust_env due unreachable local proxy: "
        f"{','.join(_HTTPX_BROKEN_LOCAL_PROXY)}"
    )


class ZhihuCrawler(BaseCrawler):
    """知乎爬虫（使用非官方API）"""

    def __init__(
        self,
        cookies: Optional[str] = None,
        rate_limit: int = 10,  # 10 req/s
    ):
        """
        初始化知乎爬虫

        Args:
            cookies: 知乎登录Cookies（推荐，无Cookie限制较多）
            rate_limit: 速率限制(每秒请求数)
        """
        super().__init__(platform_name="zhihu", rate_limit=rate_limit)
        self.cookies = cookies or os.getenv("ZHIHU_COOKIES", "")
        self.account_pool = get_account_pool_manager()
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.zhihu.com/",
                "x-api-version": "3.0.91",  # 知乎API版本
                "x-app-za": "OS=Web",
            }

            self.session = aiohttp.ClientSession(
                headers=headers,
                trust_env=_AIOHTTP_TRUST_ENV,
            )
            logger.info("✅ Zhihu crawler session initialized")
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                logger.warning(
                    "⚠️ Zhihu session deferred (no running event loop during init)"
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

        attempts = self._request_attempt_budget()
        for attempt in range(attempts):
            cookie = self.account_pool.acquire_cookie("zhihu") or self.cookies
            headers = {"Cookie": cookie} if cookie else None
            try:
                async with self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=10,
                ) as response:
                    status = int(response.status)
                    if status == 200:
                        self.account_pool.mark_success("zhihu", cookie)
                        return await response.json()
                    if status == 429:
                        self.account_pool.mark_failure(
                            "zhihu",
                            cookie,
                            reason="status_429",
                        )
                        await asyncio.sleep(min(2 + attempt * 2, 8))
                        continue
                    if status in {401, 403}:
                        self.account_pool.mark_failure(
                            "zhihu",
                            cookie,
                            reason=f"status_{status}",
                        )
                        continue
                    body = await response.text()
                    logger.error(
                        f"❌ Zhihu API error: status={status}, url={url}, body={body[:200]}"
                    )
                    return None
            except Exception as e:
                self.account_pool.mark_failure("zhihu", cookie, reason=type(e).__name__)
                if attempt >= attempts - 1:
                    logger.error(
                        f"❌ Request failed: {type(e).__name__}: {e} (url={url})"
                    )
                    return None
        return None

    def _request_attempt_budget(self) -> int:
        pool = self.account_pool.get_pool("zhihu")
        if pool is None:
            return 1
        return max(1, min(3, pool.size()))

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取知乎热榜

        Args:
            limit: 返回数量限制

        Returns:
            热榜列表
        """
        logger.info(f"🔍 Fetching {limit} hot topics from Zhihu...")

        # 知乎热榜API
        url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
        params = {"limit": min(limit, 50)}

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            logger.warning("⚠️ No hot topics found")
            return []

        hot_list = data.get("data", [])
        results = []

        for item in hot_list:
            target = item.get("target", {})
            target_type = target.get("type")  # question/answer/article

            # 提取作者信息
            author = target.get("author", {})

            # 提取问题信息
            question = target.get("question", {}) if target_type == "answer" else target

            # 构建URL
            if target_type == "question":
                url = f"https://www.zhihu.com/question/{target.get('id')}"
            elif target_type == "answer":
                url = f"https://www.zhihu.com/question/{question.get('id')}/answer/{target.get('id')}"
            elif target_type == "article":
                url = f"https://www.zhihu.com/p/{target.get('id')}"
            else:
                url = "https://www.zhihu.com/"

            # 提取文本内容
            if target_type == "answer":
                text = f"{question.get('title', '')}\n\n{target.get('excerpt', '')}"
            elif target_type == "article":
                text = f"{target.get('title', '')}\n\n{target.get('excerpt', '')}"
            else:
                text = target.get("title", "")

            # 创建时间
            created_at = target.get("created_time")
            if created_at:
                created_at = datetime.fromtimestamp(created_at).isoformat()
            else:
                created_at = datetime.utcnow().isoformat()

            raw_data = {
                "url": url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": created_at,
                "author_id": author.get("id", ""),
                "author_name": author.get("name", ""),
                "followers": author.get("follower_count", 0),
                "account_age_days": None,  # 知乎API不直接提供
                "likes": target.get("voteup_count", 0),
                "comments": target.get("comment_count", 0),
                "shares": 0,  # 知乎API不提供分享数
                "entities": [],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["hot_rank"] = item.get("热度值", 0)
            standardized["metadata"]["content_type"] = target_type
            standardized["metadata"]["zhihu_id"] = target.get("id")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} hot topics from Zhihu")
        return results[:limit]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        抓取用户的回答和文章

        Args:
            user_id: 用户ID（url_token）
            limit: 返回数量限制

        Returns:
            用户内容列表
        """
        logger.info(f"🔍 Fetching {limit} posts from user {user_id}...")

        # 获取用户回答
        url = f"https://www.zhihu.com/api/v4/members/{user_id}/answers"
        params = {
            "include": "data[*].is_normal,content,voteup_count,comment_count,created_time,author",
            "offset": 0,
            "limit": min(limit, 20),
            "sort_by": "created",
        }

        data = await self._make_request(url, params)
        if not data or "data" not in data:
            logger.warning(f"⚠️ No posts found for user {user_id}")
            return []

        answers = data.get("data", [])
        results = []

        for answer in answers:
            author = answer.get("author", {})
            question = answer.get("question", {})

            # 创建时间
            created_at = answer.get("created_time")
            if created_at:
                created_at = datetime.fromtimestamp(created_at).isoformat()
            else:
                created_at = datetime.utcnow().isoformat()

            raw_data = {
                "url": f"https://www.zhihu.com/question/{question.get('id')}/answer/{answer.get('id')}",
                "text": f"{question.get('title', '')}\n\n{answer.get('excerpt', '')}",
                "images": [],
                "video": None,
                "created_at": created_at,
                "author_id": user_id,
                "author_name": author.get("name", ""),
                "followers": author.get("follower_count", 0),
                "account_age_days": None,
                "likes": answer.get("voteup_count", 0),
                "comments": answer.get("comment_count", 0),
                "shares": 0,
                "entities": [],
            }

            standardized = self.standardize_item(raw_data)
            standardized["metadata"]["content_type"] = "answer"
            standardized["metadata"]["zhihu_id"] = answer.get("id")
            standardized["metadata"]["question_id"] = question.get("id")
            results.append(standardized)

        logger.info(f"✅ Fetched {len(results)} posts from user {user_id}")
        return results[:limit]

    async def fetch_comments(
        self, post_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        抓取回答/文章的评论

        Args:
            post_id: 内容ID（answer_id或article_id）
            limit: 返回数量限制

        Returns:
            评论列表
        """
        logger.info(f"🔍 Fetching {limit} comments for post {post_id}...")

        # 知乎评论API（需要区分answer和article）
        url = f"https://www.zhihu.com/api/v4/answers/{post_id}/root_comments"
        params = {
            "order": "normal",
            "limit": min(20, limit),
            "offset": 0,
        }

        all_comments = []
        offset = 0

        while len(all_comments) < limit:
            params["offset"] = offset
            data = await self._make_request(url, params)

            if not data or "data" not in data:
                break

            comments = data.get("data", [])
            if not comments:
                break

            for comment in comments:
                author = comment.get("author", {}).get("member", {})

                # 创建时间
                created_at = comment.get("created_time")
                if created_at:
                    created_at = datetime.fromtimestamp(created_at).isoformat()
                else:
                    created_at = datetime.utcnow().isoformat()

                raw_data = {
                    "url": f"https://www.zhihu.com/answer/{post_id}?comment_id={comment.get('id')}",
                    "text": comment.get("content", ""),
                    "images": [],
                    "video": None,
                    "created_at": created_at,
                    "author_id": author.get("id", ""),
                    "author_name": author.get("name", ""),
                    "followers": 0,  # 评论API不返回粉丝数
                    "account_age_days": None,
                    "likes": comment.get("vote_count", 0),
                    "comments": comment.get("child_comment_count", 0),
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["comment_id"] = comment.get("id")
                standardized["metadata"]["answer_id"] = post_id
                all_comments.append(standardized)

                if len(all_comments) >= limit:
                    break

            offset += len(comments)

            # 检查是否还有更多
            if not data.get("paging", {}).get("is_end", True):
                await asyncio.sleep(0.5)
            else:
                break

        logger.info(f"✅ Fetched {len(all_comments)} comments for post {post_id}")
        return all_comments[:limit]

    async def search_content(
        self, keyword: str, limit: int = 50, search_type: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        搜索包含关键词的内容

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            search_type: 搜索类型 (content=综合, question=问题, answer=回答)

        Returns:
            搜索结果列表
        """
        logger.info(f"🔍 Searching {search_type} with keyword: {keyword}...")

        url = "https://www.zhihu.com/api/v4/search_v3"
        params = {
            "t": search_type,
            "q": keyword,
            "correction": 1,
            "offset": 0,
            "limit": min(20, limit),
        }

        all_results = []
        offset = 0

        while len(all_results) < limit:
            params["offset"] = offset
            data = await self._make_request(url, params)

            if not data or "data" not in data:
                break

            items = data.get("data", [])
            if not items:
                break

            for item in items:
                item_type = item.get("type")
                obj = item.get("object", {})

                if item_type == "search_result":
                    obj = item

                # 提取作者
                author = obj.get("author", {})

                # 提取问题（如果是回答）
                question = obj.get("question", {})

                # 构建URL
                if obj.get("type") == "answer":
                    url = f"https://www.zhihu.com/question/{question.get('id')}/answer/{obj.get('id')}"
                    text = f"{question.get('title', '')}\n\n{obj.get('excerpt', '')}"
                elif obj.get("type") == "article":
                    url = f"https://www.zhihu.com/p/{obj.get('id')}"
                    text = f"{obj.get('title', '')}\n\n{obj.get('excerpt', '')}"
                elif obj.get("type") == "question":
                    url = f"https://www.zhihu.com/question/{obj.get('id')}"
                    text = obj.get("title", "")
                else:
                    continue

                # 创建时间
                created_at = obj.get("created_time")
                if created_at:
                    created_at = datetime.fromtimestamp(created_at).isoformat()
                else:
                    created_at = datetime.utcnow().isoformat()

                raw_data = {
                    "url": url,
                    "text": text,
                    "images": [],
                    "video": None,
                    "created_at": created_at,
                    "author_id": author.get("id", ""),
                    "author_name": author.get("name", ""),
                    "followers": author.get("follower_count", 0),
                    "account_age_days": None,
                    "likes": obj.get("voteup_count", 0),
                    "comments": obj.get("comment_count", 0),
                    "shares": 0,
                    "entities": [],
                }

                standardized = self.standardize_item(raw_data)
                standardized["metadata"]["content_type"] = obj.get("type")
                standardized["metadata"]["zhihu_id"] = obj.get("id")
                standardized["metadata"]["search_keyword"] = keyword
                all_results.append(standardized)

            offset += len(items)
            await asyncio.sleep(0.5)

            # 检查是否还有更多
            if len(items) < params["limit"]:
                break

        if not all_results:
            public_items = await self._search_public_site_index(keyword=keyword, limit=limit)
            if public_items:
                logger.info(
                    f"✅ Zhihu public search fallback returned {len(public_items)} items"
                )
                return public_items[:limit]

        logger.info(f"✅ Found {len(all_results)} items for keyword: {keyword}")
        return all_results[:limit]

    async def _search_public_site_index(self, keyword: str, limit: int) -> List[Dict[str, Any]]:
        """无登录态兜底：使用公开搜索索引抓取知乎链接。"""
        kw = (keyword or "").strip()
        if not kw:
            return []
        await self.rate_limit_wait()
        queries = [
            f"site:zhihu.com/question {kw}",
            f"site:zhuanlan.zhihu.com/p {kw}",
            f"site:zhihu.com {kw}",
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
                trust_env=_HTTPX_TRUST_ENV,
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
            logger.warning(f"⚠️ Zhihu public search fallback failed: {e}")
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
            content_id = self._extract_zhihu_id_from_url(target_url)

            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "zhihu_public_search",
                "author_name": "Zhihu Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["zhihu_id"] = content_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "zhihu_public_search"
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
            content_id = self._extract_zhihu_id_from_url(target_url)
            raw_data = {
                "url": target_url,
                "text": text,
                "images": [],
                "video": None,
                "created_at": datetime.utcnow().isoformat(),
                "author_id": "zhihu_public_search",
                "author_name": "Zhihu Public Search",
                "followers": 0,
                "account_age_days": None,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "entities": [],
            }
            item = self.standardize_item(raw_data)
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            meta["zhihu_id"] = content_id
            meta["search_keyword"] = keyword
            meta["keyword_match"] = bool(score >= 0.2)
            meta["keyword_match_score"] = score
            meta["retrieval_mode"] = "zhihu_public_search"
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
            if host not in {"www.zhihu.com", "zhihu.com", "zhuanlan.zhihu.com"}:
                return False
            if host == "zhuanlan.zhihu.com":
                return path.startswith("/p/")
            return (
                "/question/" in path
                or "/answer/" in path
                or "/zvideo/" in path
                or "/zhuanlan/" in path
            )
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

    def _extract_zhihu_id_from_url(self, url: str) -> Optional[str]:
        try:
            parsed = urllib.parse.urlparse(url)
            parts = [p for p in parsed.path.split("/") if p]
            if not parts:
                return None
            if "question" in parts:
                idx = parts.index("question")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            if "answer" in parts:
                idx = parts.index("answer")
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
