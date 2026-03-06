"""
BilibiliAgent - B站专用搜索Agent

无需cookies/API keys，完全模拟真实用户浏览行为

功能:
- 搜索视频
- 获取热门视频
- 提取视频详情
- 处理无限滚动
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from .browser_agent import BrowserAgent


class BilibiliAgent(BrowserAgent):
    """
    B站专用Agent

    特点:
    - 无需登录
    - 模拟真实用户
    - 处理动态加载
    - 反检测优化
    """

    BASE_URL = "https://www.bilibili.com"
    SEARCH_URL = "https://search.bilibili.com/all"

    def __init__(self, **kwargs):
        """初始化B站Agent"""
        super().__init__(**kwargs)

        # B站特定配置
        self.viewport_size = {"width": 1920, "height": 1080}

    async def search_videos(
        self,
        keyword: str,
        limit: int = 20,
        sort_type: str = "default",  # default, newest, most_played
    ) -> List[Dict[str, Any]]:
        """
        搜索B站视频

        Args:
            keyword: 搜索关键词
            limit: 获取数量
            sort_type: 排序方式

        Returns:
            标准化的视频数据列表
        """
        print(f"\n🔍 在B站搜索: {keyword}")

        # 1. 构建搜索URL
        search_url = f"{self.SEARCH_URL}?keyword={keyword}"
        if sort_type == "newest":
            search_url += "&order=pubdate"
        elif sort_type == "most_played":
            search_url += "&order=click"

        # 2. 导航到搜索页
        await self.navigate(search_url)

        # 3. 等待视频列表加载
        await self.wait_for_selector(".video-list", timeout=10000)
        await self.random_delay(1, 2)

        # 4. 滚动加载更多内容
        videos = []
        scroll_count = 0
        max_scrolls = (limit // 20) + 2  # 每次滚动约加载20个

        while len(videos) < limit and scroll_count < max_scrolls:
            # 提取当前页面的视频
            new_videos = await self._extract_video_cards()

            # 去重添加
            for video in new_videos:
                if video not in videos and len(videos) < limit:
                    videos.append(video)

            # 滚动加载更多
            if len(videos) < limit:
                await self.human_scroll()
                scroll_count += 1
                await self.random_delay(1.5, 2.5)  # 等待加载

        print(f"✅ 成功获取 {len(videos)} 个视频")
        return videos[:limit]

    async def get_hot_videos(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取B站热门视频

        Args:
            limit: 获取数量

        Returns:
            热门视频列表
        """
        print(f"\n🔥 获取B站热门视频")

        # 导航到热门页
        await self.navigate(f"{self.BASE_URL}/v/popular/all")

        # 等待视频列表加载
        await self.wait_for_selector(".video-card", timeout=10000)
        await self.random_delay(1, 2)

        # 滚动获取更多
        videos = []
        scroll_count = 0

        while len(videos) < limit and scroll_count < 5:
            new_videos = await self._extract_popular_cards()

            for video in new_videos:
                if video not in videos and len(videos) < limit:
                    videos.append(video)

            if len(videos) < limit:
                await self.human_scroll()
                scroll_count += 1
                await self.random_delay(1.5, 2.5)

        print(f"✅ 成功获取 {len(videos)} 个热门视频")
        return videos[:limit]

    async def get_video_detail(self, video_url: str) -> Dict[str, Any]:
        """
        获取视频详情

        Args:
            video_url: 视频URL (完整URL或BV号)

        Returns:
            视频详细信息
        """
        # 处理BV号
        if not video_url.startswith("http"):
            video_url = f"{self.BASE_URL}/video/{video_url}"

        print(f"\n📹 获取视频详情: {video_url}")

        # 导航到视频页
        await self.navigate(video_url)

        # 等待视频信息加载
        await self.wait_for_selector(".video-info-title", timeout=10000)
        await self.random_delay(1, 2)

        # 提取详细信息
        detail = await self._extract_video_detail()

        print(f"✅ 视频详情获取完成")
        return detail

    # ==================== 内部提取方法 ====================

    async def _extract_video_cards(self) -> List[Dict[str, Any]]:
        """提取搜索结果页的视频卡片"""
        cards = await self.page.query_selector_all(".video-list .bili-video-card")

        videos = []
        for card in cards:
            try:
                # 提取标题
                title_elem = await card.query_selector(".bili-video-card__info--tit")
                title = await title_elem.get_attribute("title") if title_elem else ""

                # 提取URL
                link_elem = await card.query_selector("a")
                url = await link_elem.get_attribute("href") if link_elem else ""
                if url and not url.startswith("http"):
                    url = f"https:{url}"

                # 提取UP主
                author_elem = await card.query_selector(
                    ".bili-video-card__info--author"
                )
                author = await author_elem.inner_text() if author_elem else ""

                # 提取播放量
                view_elem = await card.query_selector(
                    ".bili-video-card__stats--item:first-child"
                )
                views = await view_elem.inner_text() if view_elem else "0"

                # 提取时长
                duration_elem = await card.query_selector(
                    ".bili-video-card__stats--dur"
                )
                duration = await duration_elem.inner_text() if duration_elem else ""

                video = {
                    "platform": "bilibili",
                    "title": title.strip(),
                    "url": url,
                    "author": author.strip(),
                    "views": self._parse_views(views),
                    "duration": duration.strip(),
                    "crawl_time": datetime.now().isoformat(),
                }

                if title and url:  # 只添加有效数据
                    videos.append(video)

            except Exception as e:
                print(f"⚠️ 提取视频卡片失败: {e}")
                continue

        return videos

    async def _extract_popular_cards(self) -> List[Dict[str, Any]]:
        """提取热门页的视频卡片"""
        cards = await self.page.query_selector_all(".video-card")

        videos = []
        for card in cards:
            try:
                # 提取标题
                title_elem = await card.query_selector(".video-name")
                title = await title_elem.get_attribute("title") if title_elem else ""

                # 提取URL
                link_elem = await card.query_selector("a")
                url = await link_elem.get_attribute("href") if link_elem else ""
                if url and not url.startswith("http"):
                    url = f"https:{url}"

                # 提取UP主
                author_elem = await card.query_selector(".up-name")
                author = await author_elem.inner_text() if author_elem else ""

                # 提取播放量
                view_elem = await card.query_selector(".play-text")
                views = await view_elem.inner_text() if view_elem else "0"

                video = {
                    "platform": "bilibili",
                    "title": title.strip(),
                    "url": url,
                    "author": author.strip(),
                    "views": self._parse_views(views),
                    "crawl_time": datetime.now().isoformat(),
                }

                if title and url:
                    videos.append(video)

            except Exception as e:
                print(f"⚠️ 提取热门视频卡片失败: {e}")
                continue

        return videos

    async def _extract_video_detail(self) -> Dict[str, Any]:
        """提取视频详情页信息"""
        try:
            # 标题
            title_elem = await self.page.query_selector(".video-info-title")
            title = await title_elem.inner_text() if title_elem else ""

            # UP主
            author_elem = await self.page.query_selector(".up-name")
            author = await author_elem.inner_text() if author_elem else ""

            # 播放量
            view_elem = await self.page.query_selector(".view-text")
            views = await view_elem.inner_text() if view_elem else "0"

            # 弹幕数
            danmu_elem = await self.page.query_selector(".dm-text")
            danmaku = await danmu_elem.inner_text() if danmu_elem else "0"

            # 发布时间
            pubdate_elem = await self.page.query_selector(".pubdate-text")
            publish_date = await pubdate_elem.inner_text() if pubdate_elem else ""

            # 简介
            desc_elem = await self.page.query_selector(".desc-info-text")
            description = await desc_elem.inner_text() if desc_elem else ""

            # 标签
            tag_elems = await self.page.query_selector_all(".tag-panel .tag")
            tags = []
            for tag_elem in tag_elems:
                tag = await tag_elem.inner_text()
                tags.append(tag.strip())

            return {
                "platform": "bilibili",
                "title": title.strip(),
                "url": self.page.url,
                "author": author.strip(),
                "views": self._parse_views(views),
                "danmaku_count": self._parse_views(danmaku),
                "publish_date": publish_date.strip(),
                "description": description.strip(),
                "tags": tags,
                "crawl_time": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"❌ 提取视频详情失败: {e}")
            return {}

    # ==================== 辅助方法 ====================

    def _parse_views(self, view_text: str) -> int:
        """
        解析播放量文本为数字

        例如: "1.2万" -> 12000, "100.5万" -> 1005000
        """
        view_text = view_text.strip()

        try:
            if "万" in view_text:
                num = float(view_text.replace("万", ""))
                return int(num * 10000)
            elif "亿" in view_text:
                num = float(view_text.replace("亿", ""))
                return int(num * 100000000)
            else:
                # 移除非数字字符
                num_str = "".join(c for c in view_text if c.isdigit() or c == ".")
                return int(float(num_str)) if num_str else 0
        except:
            return 0

    async def search_and_standardize(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索并标准化为Aletheia格式

        Returns:
            标准化的数据格式（与爬虫系统统一）
        """
        videos = await self.search_videos(keyword, limit)

        # 标准化为统一格式
        standardized = []
        for video in videos:
            item = {
                "platform": "bilibili",
                "title": video.get("title", ""),
                "content": f"UP主: {video.get('author', '')}",
                "url": video.get("url", ""),
                "author": video.get("author", ""),
                "publish_time": video.get("crawl_time", ""),
                "metadata": {
                    "views": video.get("views", 0),
                    "duration": video.get("duration", ""),
                    "platform_type": "video",
                },
                "entities": [keyword],
                "crawl_time": video.get("crawl_time", ""),
            }
            standardized.append(item)

        return standardized


# 导出
__all__ = ["BilibiliAgent"]
