"""
官方来源爬虫 - 支持政府/监管/官媒等官方信息源
"""

import asyncio
import aiohttp
import feedparser
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urljoin, urlparse
import re
import hashlib
from bs4 import BeautifulSoup
from .base import BaseCrawler
from core.config import settings
from core.sqlite_database import get_sqlite_db
from utils.logging import logger
from utils.network_env import evaluate_trust_env
from utils.query_intent import extract_keyword_terms, score_keyword_relevance


_AIOHTTP_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "CRAWLER_TRUST_ENV", True)),
    auto_disable_local_proxy=bool(
        getattr(settings, "CRAWLER_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "CRAWLER_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ OfficialSources disable aiohttp trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


class OfficialSourceCrawler(BaseCrawler):
    """官方来源爬虫基类"""

    def __init__(
        self,
        source_name: str,
        source_url: str | List[str],
        source_type: str = "government",  # government, regulator, media, health, judicial
        access_method: str = "rss",  # rss, web, api
        rate_limit: int = 5,
    ):
        """
        初始化官方来源爬虫

        Args:
            source_name: 来源名称
            source_url: 来源URL
            source_type: 来源类型
            access_method: 访问方式 (rss/web/api)
            rate_limit: 速率限制
        """
        super().__init__(platform_name=f"official_{source_name}", rate_limit=rate_limit)
        self.source_name = source_name
        if isinstance(source_url, list):
            self.source_urls = [str(url).strip() for url in source_url if str(url).strip()]
        else:
            self.source_urls = [str(source_url).strip()] if str(source_url).strip() else []
        self.source_url = self.source_urls[0] if self.source_urls else ""
        self.source_type = source_type
        self.access_method = access_method
        self.source_id = self._derive_source_id()
        self._source_hints = self._build_source_hints()

    async def fetch_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        抓取官方来源内容

        Args:
            limit: 返回数量限制

        Returns:
            标准化数据列表
        """
        await self.rate_limit_wait()

        try:
            if self.access_method == "rss":
                return await self._fetch_rss(limit)
            elif self.access_method == "web":
                return await self._fetch_web(limit)
            else:
                logger.warning(f"Unsupported access method: {self.access_method}")
                return []
        except Exception as e:
            logger.error(f"❌ {self.source_name} fetch failed: {e}")
            return []

    async def _fetch_rss(self, limit: int) -> List[Dict[str, Any]]:
        """通过RSS获取内容 - 并行获取多个RSS源"""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            }

            async def fetch_single_rss(rss_url: str) -> tuple[str, List[Dict[str, Any]], Optional[str]]:
                """获取单个RSS源"""
                try:
                    async with aiohttp.ClientSession(trust_env=_AIOHTTP_TRUST_ENV) as session:
                        async with session.get(
                            rss_url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30),
                        ) as response:
                            content = await response.text()
                    feed = feedparser.parse(content)
                    if not getattr(feed, "entries", None):
                        return rss_url, [], "no_entries"
                    results = []
                    for entry in feed.entries[:limit]:
                        raw_data = {
                            "url": entry.get("link", ""),
                            "text": entry.get("title", "") + "\n" + entry.get("summary", ""),
                            "created_at": self._parse_date(entry.get("published", "")),
                            "author_name": self.source_name,
                            "author_id": self.source_name,
                            "followers": 0,
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                            "entities": [],
                        }
                        standardized = self.standardize_item(raw_data)
                        title = str(entry.get("title", "")).strip()
                        summary = str(entry.get("summary", "")).strip()
                        standardized["metadata"]["source_type"] = "official"
                        standardized["metadata"]["source_id"] = self.source_id
                        standardized["metadata"]["source_name"] = self.source_name
                        standardized["metadata"]["source_agency"] = self.source_name
                        standardized["metadata"]["source_category"] = self.source_type
                        standardized["metadata"]["rss_url"] = rss_url
                        standardized["title"] = title
                        standardized["description"] = summary
                        standardized["content"] = summary
                        standardized["published_at"] = raw_data.get("created_at")
                        results.append(standardized)
                    return rss_url, results, None
                except Exception as e:
                    return rss_url, [], f"{type(e).__name__}"

            # 并行获取所有RSS源
            tasks = [fetch_single_rss(rss_url) for rss_url in self.source_urls]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)

            # 收集结果
            all_results = []
            errors = []
            for result in results_list:
                if isinstance(result, Exception):
                    errors.append(f"Exception:{type(result).__name__}")
                    continue
                rss_url, items, error = result
                if error:
                    errors.append(f"{rss_url}:{error}")
                elif items:
                    all_results.extend(items)

            if all_results:
                logger.info(f"✅ {self.source_name} RSS: fetched {len(all_results)} items from {len(self.source_urls)} sources")
                return all_results[:limit]

            if errors:
                logger.warning(
                    f"⚠️ {self.source_name} RSS parallel fetch failed: {' | '.join(errors[:3])}"
                )
            return []

        except Exception as e:
            logger.error(f"❌ {self.source_name} RSS fetch error: {e}")
            return []

    async def _fetch_web(self, limit: int) -> List[Dict[str, Any]]:
        """通过网页抓取获取内容（需要自定义解析逻辑）"""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            }
            errors = []
            all_results: List[Dict[str, Any]] = []
            seen_urls_global: set[str] = set()
            for root_url in self.source_urls:
                try:
                    async with aiohttp.ClientSession(trust_env=_AIOHTTP_TRUST_ENV) as session:
                        async with session.get(
                            root_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            html = await response.text()

                    soup = BeautifulSoup(html, "html.parser")
                    results = []
                    root_host = (urlparse(root_url).hostname or "").lower()
                    for a in soup.find_all("a"):
                        href = str(a.get("href") or "").strip()
                        text = a.get_text(" ", strip=True)
                        if not href or not text or len(text) < 6:
                            continue
                        full_url = urljoin(root_url, href)
                        try:
                            parsed = urlparse(full_url)
                        except Exception:
                            continue
                        host = (parsed.hostname or "").lower()
                        path = (parsed.path or "").strip("/")
                        if parsed.scheme not in {"http", "https"} or not host or not path:
                            continue
                        if root_host and not (host == root_host or host.endswith(f".{root_host}")):
                            continue
                        if any(token in path.lower() for token in ["search", "index", "tag"]):
                            continue
                        if full_url in seen_urls_global:
                            continue
                        seen_urls_global.add(full_url)

                        raw_data = {
                            "url": full_url,
                            "text": text,
                            "created_at": datetime.utcnow().isoformat(),
                            "author_name": self.source_name,
                            "author_id": self.source_name,
                            "followers": 0,
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                            "entities": [],
                        }

                        standardized = self.standardize_item(raw_data)
                        standardized["metadata"]["source_type"] = "official"
                        standardized["metadata"]["source_id"] = self.source_id
                        standardized["metadata"]["source_name"] = self.source_name
                        standardized["metadata"]["source_agency"] = self.source_name
                        standardized["metadata"]["source_category"] = self.source_type
                        standardized["metadata"]["source_url"] = root_url
                        standardized["title"] = text
                        standardized["description"] = text
                        standardized["content"] = text
                        standardized["published_at"] = raw_data.get("created_at")
                        results.append(standardized)
                        if len(results) >= limit:
                            break

                    if results:
                        all_results.extend(results)
                        if len(all_results) >= limit:
                            break
                except Exception as web_err:
                    errors.append(f"{root_url}:{type(web_err).__name__}")
                    continue
            if all_results:
                logger.info(
                    f"✅ {self.source_name} Web: fetched {len(all_results)} items from {len(self.source_urls)} roots"
                )
                return all_results[:limit]
            if errors:
                logger.warning(
                    f"⚠️ {self.source_name} Web fallback failed: {' | '.join(errors[:3])}"
                )
            return []

        except Exception as e:
            logger.error(f"❌ {self.source_name} Web fetch error: {e}")
            return []

    def _parse_date(self, date_str: str) -> str:
        """解析日期字符串"""
        try:
            from dateutil import parser

            dt = parser.parse(date_str)
            return dt.isoformat()
        except:
            return datetime.utcnow().isoformat()

    async def search(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        搜索功能（部分官方来源支持）

        Args:
            keyword: 关键词
            limit: 返回数量限制

        Returns:
            标准化数据列表
        """
        kw = str(keyword or "").strip()
        if not kw or limit <= 0:
            return []

        local_first = bool(
            getattr(settings, "OFFICIAL_SOURCE_SEARCH_LOCAL_FIRST", True)
        )
        local_min_results = max(
            1, int(getattr(settings, "OFFICIAL_SOURCE_SEARCH_LOCAL_MIN_RESULTS", 2))
        )
        local_lookback_days = max(
            1, int(getattr(settings, "OFFICIAL_SOURCE_SEARCH_LOCAL_LOOKBACK_DAYS", 180))
        )
        fetch_multiplier = max(
            2, int(getattr(settings, "OFFICIAL_SOURCE_SEARCH_FETCH_MULTIPLIER", 8))
        )
        fetch_min_limit = max(
            20, int(getattr(settings, "OFFICIAL_SOURCE_SEARCH_FETCH_MIN_LIMIT", 60))
        )
        threshold = max(
            0.05, float(getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2))
        )
        write_enabled = bool(
            getattr(settings, "OFFICIAL_SOURCE_SEARCH_INDEX_WRITE_ENABLED", True)
        )
        write_max = max(
            1, int(getattr(settings, "OFFICIAL_SOURCE_SEARCH_INDEX_WRITE_MAX_ITEMS", 120))
        )

        scored: List[tuple[float, Dict[str, Any]]] = []
        seen_urls: set[str] = set()

        def _score_blob(item: Dict[str, Any]) -> float:
            blob = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("description") or ""),
                    str(item.get("content") or ""),
                    str(item.get("content_text") or ""),
                    str(item.get("url") or item.get("original_url") or ""),
                ]
            )
            return self._keyword_score(kw, blob)

        def _push_items(items: List[Dict[str, Any]], retrieval_mode: str) -> None:
            for item in list(items or []):
                if not isinstance(item, dict):
                    continue
                link = str(item.get("url") or item.get("original_url") or "").strip()
                if not link or link in seen_urls:
                    continue
                score = _score_blob(item)
                if score < threshold:
                    continue
                seen_urls.add(link)
                meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                meta.setdefault("source_type", "official")
                meta.setdefault("source_id", self.source_id)
                meta.setdefault("source_name", self.source_name)
                meta["keyword_match"] = True
                meta["keyword_match_score"] = round(float(score), 4)
                meta["retrieval_mode"] = retrieval_mode
                item["metadata"] = meta
                item.setdefault("title", str(meta.get("title") or "").strip())
                item.setdefault("description", str(meta.get("description") or "").strip())
                scored.append((score, item))

        local_limit = max(limit * 4, local_min_results * 3)
        if local_first:
            local_items = await self._search_local_index(
                keyword=kw, limit=local_limit, days=local_lookback_days
            )
            _push_items(local_items, "official_local_index")
            if len(scored) >= max(limit, local_min_results):
                scored.sort(key=lambda x: x[0], reverse=True)
                return [row for _, row in scored[:limit]]

        fetch_limit = max(limit * fetch_multiplier, fetch_min_limit)
        live_items = await self.fetch_hot_topics(limit=fetch_limit)
        if live_items and write_enabled:
            await self._persist_items_to_local_index(live_items[:write_max])
        _push_items(live_items, "official_live_filtered")

        if (not local_first) or len(scored) < limit:
            local_items = await self._search_local_index(
                keyword=kw,
                limit=max(limit * 4, local_limit),
                days=local_lookback_days,
            )
            _push_items(local_items, "official_local_index")

        if not scored:
            logger.warning(f"{self.source_name} search no matches after local+live pipeline")
            return []
        scored.sort(key=lambda x: x[0], reverse=True)
        return [row for _, row in scored[:limit]]

    async def fetch_user_posts(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """官方来源不支持用户维度"""
        logger.warning(f"{self.source_name} does not support user posts")
        return []

    async def fetch_comments(
        self, post_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """官方来源不支持评论"""
        logger.warning(f"{self.source_name} does not support comments")
        return []

    def _derive_source_id(self) -> str:
        name = str(self.source_name or "").lower()
        alias_map = {
            "samr": ["市场监督", "市场监管", "samr"],
            "csrc": ["证监会", "csrc"],
            "nhc": ["卫健", "卫生健康", "nhc"],
            "china_gov": ["国务院", "中国政府网", "gov.cn"],
            "xinhua": ["新华", "news.cn", "xinhuanet"],
            "peoples_daily": ["人民日报", "人民网", "people.com.cn", "people.cn"],
            "mem": ["应急管理", "mem.gov.cn"],
            "mps": ["公安部", "mps.gov.cn"],
            "supreme_court": ["人民法院", "court.gov.cn"],
            "supreme_procuratorate": ["检察院", "spp.gov.cn"],
            "who": ["who", "world health"],
            "cdc": ["cdc"],
            "un_news": ["un", "联合国"],
            "sec": ["sec", "securities and exchange"],
            "fca_uk": ["fca", "financial conduct"],
        }
        for source_id, hints in alias_map.items():
            if any(h.lower() in name for h in hints):
                return source_id

        if self.source_urls:
            host = (urlparse(self.source_urls[0]).hostname or "").lower()
            if host:
                parts = host.split(".")
                if len(parts) >= 3:
                    short = parts[-3]
                    if short:
                        return short
                if len(parts) >= 2:
                    return parts[-2]

        fallback = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
        return fallback or "official_source"

    def _build_source_hints(self) -> set[str]:
        hints: set[str] = {self.source_id.lower(), str(self.source_name or "").lower()}
        extra_hints = {
            "peoples_daily": {"people.com.cn", "people.cn", "人民日报", "人民网"},
            "xinhua": {"news.cn", "xinhuanet", "新华网"},
            "samr": {"samr.gov.cn", "市场监管", "市场监督"},
            "csrc": {"csrc.gov.cn", "证监会"},
            "nhc": {"nhc.gov.cn", "卫健委", "卫生健康"},
            "china_gov": {"gov.cn", "中国政府网", "国务院"},
            "mem": {"mem.gov.cn", "应急管理"},
            "mps": {"mps.gov.cn", "公安部"},
            "supreme_court": {"court.gov.cn", "人民法院"},
            "supreme_procuratorate": {"spp.gov.cn", "检察院"},
            "who": {"who.int", "world health organization"},
            "cdc": {"cdc.gov"},
            "un_news": {"news.un.org", "联合国"},
            "sec": {"sec.gov"},
            "fca_uk": {"fca.org.uk"},
        }
        hints.update(extra_hints.get(self.source_id, set()))
        for url in self.source_urls:
            parsed = urlparse(str(url))
            host = (parsed.hostname or "").lower()
            if host:
                hints.add(host)
        return {h for h in hints if h and len(h) >= 3}

    def _keyword_tokens(self, text: str) -> List[str]:
        return extract_keyword_terms(text, max_terms=24)

    def _keyword_score(self, keyword: str, blob: str) -> float:
        return score_keyword_relevance(keyword, blob)

    def _row_matches_source(self, row: Dict[str, Any]) -> bool:
        if not isinstance(row, dict):
            return False
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        blob = "\n".join(
            [
                str(row.get("source_id") or ""),
                str(row.get("source_name") or ""),
                str(row.get("link") or row.get("canonical_url") or ""),
                str(meta.get("source_url") or ""),
                str(meta.get("rss_url") or ""),
                str(meta.get("source_agency") or ""),
            ]
        ).lower()
        return any(hint.lower() in blob for hint in self._source_hints)

    def _build_item_from_local_row(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(row, dict):
            return None
        link = str(row.get("link") or row.get("canonical_url") or "").strip()
        if not link:
            return None
        title = str(row.get("title") or "").strip()
        summary = str(
            row.get("summary")
            or row.get("deep_summary")
            or row.get("fast_summary")
            or row.get("description")
            or ""
        ).strip()
        created_at = str(row.get("published_at") or row.get("retrieved_at") or "")
        raw_data = {
            "url": link,
            "text": f"{title}\n{summary}".strip(),
            "created_at": created_at or datetime.utcnow().isoformat(),
            "author_name": str(row.get("source_name") or self.source_name),
            "author_id": str(row.get("source_id") or self.source_id),
            "followers": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "entities": [],
        }
        item = self.standardize_item(raw_data)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        meta.update(
            {
                "source_type": "official",
                "source_id": str(row.get("source_id") or self.source_id),
                "source_name": str(row.get("source_name") or self.source_name),
                "source_agency": self.source_name,
                "source_category": self.source_type,
                "retrieval_mode": "official_local_index",
                "local_match_score": float((row.get("metadata") or {}).get("local_match_score", 0.0))
                if isinstance(row.get("metadata"), dict)
                else 0.0,
            }
        )
        item["metadata"] = meta
        item["title"] = title
        item["description"] = summary
        item["content"] = summary
        item["published_at"] = created_at or datetime.utcnow().isoformat()
        return item

    async def _search_local_index(
        self, *, keyword: str, limit: int, days: int
    ) -> List[Dict[str, Any]]:
        try:
            rows = await asyncio.to_thread(
                get_sqlite_db().search_rss_articles,
                keyword=keyword,
                limit=max(1, int(limit)),
                days=max(1, int(days)),
            )
        except Exception as exc:
            logger.warning(f"{self.source_name} local index search failed: {type(exc).__name__}")
            return []

        out: List[Dict[str, Any]] = []
        for row in list(rows or []):
            if not self._row_matches_source(row):
                continue
            item = self._build_item_from_local_row(row)
            if item is None:
                continue
            out.append(item)
            if len(out) >= limit:
                break
        if out:
            logger.info(
                f"✅ {self.source_name} local index hit: {len(out)} items (days={days})"
            )
        return out

    async def _persist_items_to_local_index(self, items: List[Dict[str, Any]]) -> None:
        if not items:
            return

        def _save() -> int:
            db = get_sqlite_db()
            inserted = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                link = str(item.get("original_url") or item.get("url") or "").strip()
                if not link:
                    continue
                title = str(item.get("title") or "").strip()
                summary = str(item.get("description") or item.get("content") or item.get("content_text") or "").strip()
                published_at = str(item.get("published_at") or "")
                meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                source_id = str(meta.get("source_id") or self.source_id)
                source_name = str(meta.get("source_name") or self.source_name)
                article_id = str(item.get("id") or "")
                if not article_id:
                    article_id = "rss_" + hashlib.md5(f"{source_id}:{link}".encode("utf-8")).hexdigest()
                article = {
                    "id": article_id,
                    "title": title,
                    "original_url": link,
                    "canonical_url": link,
                    "published_at": published_at or datetime.utcnow().isoformat(),
                    "retrieved_at": datetime.utcnow().isoformat(),
                    "description": summary,
                    "summary": summary,
                    "summary_level": "fast",
                    "category": self.source_type,
                    "metadata": {
                        **meta,
                        "source_id": source_id,
                        "source_name": source_name,
                        "source_type": "official",
                        "source_agency": self.source_name,
                        "source_category": self.source_type,
                    },
                }
                try:
                    db.save_rss_article(article)
                    inserted += 1
                except Exception:
                    continue
            return inserted

        try:
            inserted = await asyncio.to_thread(_save)
            if inserted > 0:
                logger.info(f"✅ {self.source_name} indexed {inserted} live items into local RSS index")
        except Exception as exc:
            logger.warning(f"{self.source_name} local index write failed: {type(exc).__name__}")


# 中国官方来源配置
CHINA_OFFICIAL_SOURCES = {
    "gov_cn": {
        "name": "国务院官网",
        "url": ["https://www.gov.cn/jsonTag/tp/rss.xml"],
        "type": "government",
        "method": "rss",
    },
    "samr": {
        "name": "国家市场监督管理总局",
        "url": "https://www.samr.gov.cn/",
        "type": "regulator",
        "method": "web",
    },
    "csrc": {
        "name": "中国证监会",
        "url": ["https://www.csrc.gov.cn/", "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml"],
        "type": "regulator",
        "method": "web",
    },
    "nhc": {
        "name": "国家卫健委",
        "url": ["https://www.nhc.gov.cn/", "https://www.nhc.gov.cn/yjb/list.shtml"],
        "type": "health",
        "method": "web",
    },
    "mem": {
        "name": "应急管理部",
        "url": "https://www.mem.gov.cn/",
        "type": "public_safety",
        "method": "web",
    },
    "mps": {
        "name": "公安部",
        "url": "https://www.mps.gov.cn/",
        "type": "public_safety",
        "method": "web",
    },
    "court": {
        "name": "最高人民法院",
        "url": "https://www.court.gov.cn/",
        "type": "judicial",
        "method": "web",
    },
    "spp": {
        "name": "最高人民检察院",
        "url": "https://www.spp.gov.cn/",
        "type": "judicial",
        "method": "web",
    },
    "xinhua": {
        "name": "新华网",
        "url": [
            "https://www.news.cn/politics/",
            "https://www.news.cn/world/",
        ],
        "type": "state_media",
        "method": "web",
    },
    "people": {
        "name": "人民网",
        "url": [
            "http://www.people.com.cn/rss/ywkx.xml",
            "http://www.people.com.cn/rss/politics.xml",
            "http://www.people.com.cn/rss/society.xml",
            "http://www.people.com.cn/rss/world.xml",
        ],
        "type": "state_media",
        "method": "rss",
    },
    "people_daily": {
        "name": "人民日报",
        "url": [
            "https://www.people.com.cn/rss/politics.xml",
            "https://www.people.com.cn/rss/world.xml",
            "https://www.people.com.cn/rss/ywkx.xml",
        ],
        "type": "state_media",
        "method": "rss",
    },
}

# 全球官方来源配置
GLOBAL_OFFICIAL_SOURCES = {
    "who": {
        "name": "WHO Newsroom",
        "url": [
            "https://www.who.int/news-room",
            "https://www.who.int/news",
        ],
        "type": "health",
        "method": "web",
    },
    "cdc": {
        "name": "CDC Press Releases",
        "url": [
            "https://www.cdc.gov/media/rss.xml",
            "https://tools.cdc.gov/podcasts/rss.asp?c=146",
        ],
        "type": "health",
        "method": "rss",
    },
    "un": {
        "name": "UN News",
        "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        "type": "international_org",
        "method": "rss",
    },
    "sec": {
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "type": "regulator",
        "method": "rss",
    },
    "fca": {
        "name": "FCA News",
        "url": ["https://www.fca.org.uk/news", "https://www.fca.org.uk/markets/market-news"],
        "type": "regulator",
        "method": "web",
    },
}


class OfficialSourcesManager:
    """官方来源管理器"""

    def __init__(self):
        self.crawlers = {}
        self._init_crawlers()

    def _init_crawlers(self):
        """初始化所有官方来源爬虫"""
        # 中国官方来源
        for key, config in CHINA_OFFICIAL_SOURCES.items():
            try:
                self.crawlers[f"official_{key}"] = OfficialSourceCrawler(
                    source_name=config["name"],
                    source_url=config["url"],
                    source_type=config["type"],
                    access_method=config["method"],
                )
                logger.info(f"✅ Official source initialized: {config['name']}")
            except Exception as e:
                logger.warning(f"⚠️ {config['name']} init failed: {e}")

        # 全球官方来源
        for key, config in GLOBAL_OFFICIAL_SOURCES.items():
            try:
                self.crawlers[f"official_{key}"] = OfficialSourceCrawler(
                    source_name=config["name"],
                    source_url=config["url"],
                    source_type=config["type"],
                    access_method=config["method"],
                )
                logger.info(f"✅ Official source initialized: {config['name']}")
            except Exception as e:
                logger.warning(f"⚠️ {config['name']} init failed: {e}")

    async def fetch_all_official_sources(
        self, limit_per_source: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """并行抓取所有官方来源"""
        tasks = {}
        for source_name, crawler in self.crawlers.items():
            tasks[source_name] = crawler.fetch_hot_topics(limit=limit_per_source)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        output = {}
        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"❌ {source_name} failed: {result}")
                output[source_name] = []
            else:
                output[source_name] = result

        return output

    def get_available_sources(self) -> List[str]:
        """获取可用的官方来源列表"""
        return list(self.crawlers.keys())
