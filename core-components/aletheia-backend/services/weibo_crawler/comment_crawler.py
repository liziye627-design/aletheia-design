# -*- coding: utf-8 -*-
"""
Weibo Comment Crawler
微博评论爬虫 - 基于移动端网页爬取

参考: stay-leave/weibo-public-opinion-analysis

核心功能:
- 爬取微博评论数据（用户ID、用户名、评论内容、时间）
- 支持多线程爬取
- 自动处理分页
- Cookie池管理
"""

import re
import time
import random
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import aiohttp
from loguru import logger


@dataclass
class WeiboComment:
    """微博评论数据结构"""
    comment_id: str = ""
    user_id: str = ""
    user_name: str = ""
    content: str = ""
    publish_time: str = ""
    like_count: int = 0
    reply_count: int = 0
    is_reply: bool = False
    reply_to_user: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlerConfig:
    """爬虫配置"""
    max_pages: int = 50  # 最大爬取页数
    request_delay: float = 2.0  # 请求间隔(秒)
    retry_times: int = 3  # 重试次数
    retry_delay: float = 5.0  # 重试间隔
    timeout: int = 30  # 请求超时
    use_proxy: bool = False  # 是否使用代理
    cookies: List[str] = field(default_factory=list)  # Cookie池


class WeiboCommentCrawler:
    """
    微博评论爬虫

    使用移动端网页接口爬取评论数据
    URL格式: https://weibo.cn/comment/{bid}?uid={uid}&rl=1&page={page}
    """

    # 移动端评论页面URL
    COMMENT_URL = "https://weibo.cn/comment/{bid}?uid={uid}&rl=1&page={page}"

    # 移动端API接口
    API_COMMENT_URL = "https://weibo.cn/ajax/statuses/buildComments"

    # 请求头模板
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    def __init__(self, config: Optional[CrawlerConfig] = None):
        """初始化爬虫"""
        self.config = config or CrawlerConfig()
        self._cookie_index = 0
        self._session: Optional[aiohttp.ClientSession] = None
        logger.info(f"WeiboCommentCrawler initialized with max_pages={self.config.max_pages}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.HEADERS.copy(),
            )
        return self._session

    def _get_cookie(self) -> Optional[str]:
        """从Cookie池获取Cookie"""
        if not self.config.cookies:
            return None
        cookie = self.config.cookies[self._cookie_index]
        self._cookie_index = (self._cookie_index + 1) % len(self.config.cookies)
        return cookie

    async def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict] = None
    ) -> Optional[str]:
        """
        带重试的HTTP请求

        Args:
            url: 请求URL
            params: 请求参数

        Returns:
            响应文本或None
        """
        session = await self._get_session()
        headers = self.HEADERS.copy()

        # 添加Cookie
        cookie = self._get_cookie()
        if cookie:
            headers["Cookie"] = cookie

        for attempt in range(self.config.retry_times):
            try:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        # 请求过于频繁，等待更长时间
                        wait_time = self.config.retry_delay * (attempt + 2)
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(f"Request failed with status {response.status}")

            except asyncio.TimeoutError:
                logger.warning(f"Request timeout, attempt {attempt + 1}")
            except Exception as e:
                logger.error(f"Request error: {e}")

            if attempt < self.config.retry_times - 1:
                await asyncio.sleep(self.config.retry_delay)

        return None

    def _parse_comment_html(self, html: str) -> List[WeiboComment]:
        """
        解析评论HTML页面

        Args:
            html: HTML文本

        Returns:
            评论列表
        """
        comments = []

        # 匹配评论块
        comment_pattern = r'<div class="c" id="C_\d+">(.*?)</div>'
        comment_blocks = re.findall(comment_pattern, html, re.DOTALL)

        for block in comment_blocks:
            try:
                comment = WeiboComment()

                # 提取用户ID (从举报链接)
                user_id_match = re.search(r'fuid=(\d+)', block)
                if user_id_match:
                    comment.user_id = user_id_match.group(1)

                # 提取用户名
                user_name_match = re.search(r'<a href="[^"]*">([^<]+)</a>', block)
                if user_name_match:
                    comment.user_name = user_name_match.group(1).strip()

                # 提取评论内容
                content_match = re.search(r'<span class="ctt">(.+?)</span>', block, re.DOTALL)
                if content_match:
                    content = content_match.group(1)
                    # 清理HTML标签
                    content = re.sub(r'<[^>]+>', '', content)
                    comment.content = content.strip()

                # 提取时间
                time_match = re.search(r'<span class="ct">(.+?)</span>', block)
                if time_match:
                    comment.publish_time = time_match.group(1).strip()

                # 检查是否是回复
                if "回复@" in block:
                    comment.is_reply = True
                    reply_match = re.search(r'回复@([^:：]+)', block)
                    if reply_match:
                        comment.reply_to_user = reply_match.group(1).strip()

                # 生成评论ID
                comment.comment_id = f"{comment.user_id}_{int(time.time() * 1000)}"

                if comment.user_id and comment.content:
                    comments.append(comment)

            except Exception as e:
                logger.debug(f"Parse comment error: {e}")
                continue

        return comments

    def _parse_page_count(self, html: str) -> int:
        """
        解析评论总页数

        Args:
            html: HTML文本

        Returns:
            总页数
        """
        # 匹配分页信息
        page_pattern = r'/comment/[^"]+\?page=(\d+)'
        pages = re.findall(page_pattern, html)
        if pages:
            return max(int(p) for p in pages)
        return 1

    async def crawl_comments(
        self,
        weibo_id: str,
        user_id: str,
        max_pages: Optional[int] = None
    ) -> List[WeiboComment]:
        """
        爬取微博评论

        Args:
            weibo_id: 微博ID (bid)
            user_id: 微博作者ID
            max_pages: 最大爬取页数 (None使用配置值)

        Returns:
            评论列表
        """
        max_pages = max_pages or self.config.max_pages
        all_comments = []

        logger.info(f"Starting to crawl comments for weibo {weibo_id}")

        # 先获取第一页，确定总页数
        first_url = self.COMMENT_URL.format(bid=weibo_id, uid=user_id, page=1)
        first_html = await self._request_with_retry(first_url)

        if not first_html:
            logger.error(f"Failed to fetch first page for weibo {weibo_id}")
            return all_comments

        # 解析第一页
        first_comments = self._parse_comment_html(first_html)
        all_comments.extend(first_comments)
        logger.info(f"Page 1: found {len(first_comments)} comments")

        # 获取总页数
        total_pages = self._parse_page_count(first_html)
        actual_pages = min(total_pages, max_pages)
        logger.info(f"Total pages: {total_pages}, will crawl {actual_pages} pages")

        # 爬取剩余页面
        for page in range(2, actual_pages + 1):
            # 随机延迟
            delay = self.config.request_delay + random.uniform(0, 1)
            await asyncio.sleep(delay)

            url = self.COMMENT_URL.format(bid=weibo_id, uid=user_id, page=page)
            html = await self._request_with_retry(url)

            if html:
                comments = self._parse_comment_html(html)
                all_comments.extend(comments)
                logger.info(f"Page {page}: found {len(comments)} comments")
            else:
                logger.warning(f"Failed to fetch page {page}")

        logger.info(f"Finished crawling {len(all_comments)} comments for weibo {weibo_id}")
        return all_comments

    async def crawl_comments_batch(
        self,
        weibo_list: List[Dict[str, str]],
        max_pages_per_weibo: int = 10
    ) -> Dict[str, List[WeiboComment]]:
        """
        批量爬取多条微博的评论

        Args:
            weibo_list: 微博列表，每项包含 weibo_id 和 user_id
            max_pages_per_weibo: 每条微博最大爬取页数

        Returns:
            微博ID到评论列表的映射
        """
        results = {}

        for item in weibo_list:
            weibo_id = item.get("weibo_id") or item.get("bid")
            user_id = item.get("user_id") or item.get("uid")

            if not weibo_id or not user_id:
                logger.warning(f"Invalid weibo item: {item}")
                continue

            comments = await self.crawl_comments(weibo_id, user_id, max_pages_per_weibo)
            results[weibo_id] = comments

            # 微博间延迟
            await asyncio.sleep(self.config.request_delay * 2)

        return results

    def to_dict_list(self, comments: List[WeiboComment]) -> List[Dict[str, Any]]:
        """将评论列表转换为字典列表"""
        return [
            {
                "comment_id": c.comment_id,
                "user_id": c.user_id,
                "user_name": c.user_name,
                "content": c.content,
                "publish_time": c.publish_time,
                "like_count": c.like_count,
                "reply_count": c.reply_count,
                "is_reply": c.is_reply,
                "reply_to_user": c.reply_to_user,
            }
            for c in comments
        ]

    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 同步包装函数
def crawl_weibo_comments_sync(
    weibo_id: str,
    user_id: str,
    cookies: Optional[List[str]] = None,
    max_pages: int = 10
) -> List[Dict[str, Any]]:
    """
    同步爬取微博评论

    Args:
        weibo_id: 微博ID
        user_id: 作者ID
        cookies: Cookie列表
        max_pages: 最大页数

    Returns:
        评论字典列表
    """
    config = CrawlerConfig(
        max_pages=max_pages,
        cookies=cookies or [],
    )

    async def _crawl():
        async with WeiboCommentCrawler(config) as crawler:
            comments = await crawler.crawl_comments(weibo_id, user_id)
            return crawler.to_dict_list(comments)

    return asyncio.run(_crawl())