#!/usr/bin/env python3
"""
抖音(Douyin) Agent - 基于浏览器自动化的数据采集

功能:
- 搜索视频/用户
- 获取热门视频
- 提取视频详情 (标题、作者、播放量、点赞数、评论数)
- 无需登录认证

使用方法:
    from services.layer1_perception.agents.douyin_agent import DouyinAgent

    async with DouyinAgent(headless=True) as agent:
        # 搜索视频
        videos = await agent.search_videos("人工智能", limit=20)

        # 获取热门视频
        hot_videos = await agent.get_hot_videos(limit=30)

抖音网站结构特点:
- 搜索URL: https://www.douyin.com/search/{keyword}?type=video
- 视频卡片: class="ECsMe6R8"
- 无限滚动加载
- 需要等待JS渲染
"""

import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from datetime import datetime

from .browser_agent import BrowserAgent


class DouyinAgent(BrowserAgent):
    """抖音浏览器Agent"""

    BASE_URL = "https://www.douyin.com"
    SEARCH_URL = f"{BASE_URL}/search"

    # CSS选择器 (根据抖音实际页面结构调整)
    SELECTORS = {
        "video_list": "ul[data-e2e='search-result-list']",  # 视频列表容器
        "video_item": "li[data-e2e='search-result-item']",  # 单个视频卡片
        "video_title": "span[data-e2e='search-result-video-title']",  # 视频标题
        "video_author": "span[data-e2e='search-result-video-author']",  # 作者
        "video_stats": "span[data-e2e='video-stats']",  # 统计信息
        "video_link": "a[data-e2e='search-result-video-link']",  # 视频链接
        "hot_list": "div[class*='hot-list']",  # 热门列表
    }

    async def search_videos(
        self,
        keyword: str,
        limit: int = 20,
        search_type: str = "video",  # video, user, topic
    ) -> List[Dict[str, Any]]:
        """
        搜索视频

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限
            search_type: 搜索类型 (video/user/topic)

        Returns:
            视频列表 [{title, author, url, stats, ...}]
        """
        self.logger.info(f"🔍 抖音搜索: {keyword} (类型: {search_type}, 限制: {limit})")
        self.last_diagnostics = {
            "blocked": False,
            "selector_miss": False,
            "empty_result": False,
            "reason": "",
            "selector_version": "douyin_v2",
        }

        # 1. 构造搜索URL
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}/{encoded_keyword}?type={search_type}"

        # 2. 导航到搜索页
        try:
            await self.navigate(search_url)
            self.logger.info(f"✅ 已访问: {search_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 3. 等待页面加载（多选择器候选）
        selector_ok = False
        for selector in [
            self.SELECTORS["video_list"],
            "a[href*='/video/']",
            "div[class*='video-card']",
            "main",
        ]:
            if await self.wait_for_selector(selector, timeout=6000):
                selector_ok = True
                break
        if not selector_ok:
            self.last_diagnostics.update(
                {"selector_miss": True, "reason": "selector_miss:douyin"}
            )

        if await self.detect_blocked_page():
            return []

        # 4. 滚动加载更多内容
        videos = []
        max_scroll_attempts = 20  # 最多滚动20次
        scroll_count = 0
        stagnant_rounds = 0

        while len(videos) < limit and scroll_count < max_scroll_attempts:
            before_count = len(videos)
            # 提取当前页面的视频
            new_videos = await self._extract_videos_from_page()
            if not new_videos:
                new_videos = await self._extract_videos_from_text_fallback(limit=limit)

            # 合并新视频 (去重)
            existing_urls = {v["url"] for v in videos}
            for video in new_videos:
                if video["url"] not in existing_urls and len(videos) < limit:
                    videos.append(video)
                    existing_urls.add(video["url"])

            self.logger.info(f"📊 当前已获取 {len(videos)} 个视频")

            # 如果已经足够,提前结束
            if len(videos) >= limit:
                break

            if len(videos) == before_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            if stagnant_rounds >= 3:
                self.last_diagnostics.update(
                    {"empty_result": True, "reason": "empty_result:douyin"}
                )
                self.logger.warning("⚠️ 抖音连续3轮无新增，提前结束")
                break

            # 滚动加载更多
            await self.scroll_page()
            await self.random_delay(1.0, 2.0)  # 模拟人类浏览

            scroll_count += 1

        self.logger.info(f"✅ 搜索完成,共获取 {len(videos)} 个视频")
        return videos[:limit]

    async def _extract_videos_from_text_fallback(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """文本兜底提取：从页面文本抽取抖音视频链接。"""
        try:
            page_text = await self.get_page_text()
            urls = re.findall(r"https?://www\.douyin\.com/video/\d+", page_text)
            results: List[Dict[str, Any]] = []
            seen = set()
            for u in urls:
                if u in seen:
                    continue
                seen.add(u)
                results.append(
                    {
                        "title": "文本兜底提取视频",
                        "author": "unknown",
                        "url": u,
                        "stats": {"likes": 0, "comments": 0, "shares": 0},
                        "platform": "douyin",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return []

    async def get_hot_videos(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        获取抖音热门视频

        Args:
            limit: 返回结果数量上限

        Returns:
            热门视频列表
        """
        self.logger.info(f"🔥 获取抖音热门视频 (限制: {limit})")

        # 抖音热门页面
        hot_url = f"{self.BASE_URL}/hot"

        try:
            await self.navigate(hot_url)
            self.logger.info(f"✅ 已访问热门页: {hot_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待页面加载
        try:
            await self.wait_for_selector(self.SELECTORS["hot_list"], timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待热门列表超时: {e}")

        # 滚动加载
        videos = []
        max_scroll_attempts = 15
        scroll_count = 0

        while len(videos) < limit and scroll_count < max_scroll_attempts:
            new_videos = await self._extract_videos_from_page()

            existing_urls = {v["url"] for v in videos}
            for video in new_videos:
                if video["url"] not in existing_urls and len(videos) < limit:
                    videos.append(video)
                    existing_urls.add(video["url"])

            if len(videos) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 获取热门视频完成,共 {len(videos)} 个")
        return videos[:limit]

    async def get_user_videos(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取用户发布的视频

        Args:
            user_id: 用户ID (抖音号)
            limit: 返回结果数量上限

        Returns:
            用户视频列表
        """
        self.logger.info(f"👤 获取用户 {user_id} 的视频 (限制: {limit})")

        user_url = f"{self.BASE_URL}/user/{user_id}"

        try:
            await self.navigate(user_url)
            self.logger.info(f"✅ 已访问用户页: {user_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待视频列表
        try:
            await self.wait_for_selector("ul", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待用户视频列表超时: {e}")

        # 滚动加载
        videos = []
        max_scroll_attempts = 15
        scroll_count = 0

        while len(videos) < limit and scroll_count < max_scroll_attempts:
            new_videos = await self._extract_videos_from_page()

            existing_urls = {v["url"] for v in videos}
            for video in new_videos:
                if video["url"] not in existing_urls and len(videos) < limit:
                    videos.append(video)
                    existing_urls.add(video["url"])

            if len(videos) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 获取用户视频完成,共 {len(videos)} 个")
        return videos[:limit]

    async def _extract_videos_from_page(self) -> List[Dict[str, Any]]:
        """
        从当前页面提取视频信息

        Returns:
            视频列表
        """
        try:
            # 使用JavaScript提取视频数据
            videos_data = await self.page.evaluate(
                """
                () => {
                    const videos = [];
                    
                    // 尝试多种选择器策略
                    const videoElements = document.querySelectorAll(
                        'li[data-e2e="search-result-item"], div[class*="video-card"], a[href*="/video/"]'
                    );
                    
                    videoElements.forEach((element, index) => {
                        try {
                            // 提取标题
                            let title = '';
                            const titleEl = element.querySelector(
                                'span[data-e2e="search-result-video-title"], h4, p[class*="title"]'
                            );
                            if (titleEl) {
                                title = titleEl.textContent.trim();
                            }
                            
                            // 提取作者
                            let author = '';
                            const authorEl = element.querySelector(
                                'span[data-e2e="search-result-video-author"], p[class*="author"], a[class*="author"]'
                            );
                            if (authorEl) {
                                author = authorEl.textContent.trim();
                            }
                            
                            // 提取链接
                            let url = '';
                            const linkEl = element.querySelector('a[href*="/video/"]') || element;
                            if (linkEl && linkEl.href) {
                                url = linkEl.href;
                            }
                            
                            // 提取统计信息 (点赞、评论、转发)
                            let stats = {
                                likes: 0,
                                comments: 0,
                                shares: 0
                            };
                            
                            const statsElements = element.querySelectorAll(
                                'span[class*="count"], div[class*="stats"] span'
                            );
                            statsElements.forEach((statEl, idx) => {
                                const text = statEl.textContent.trim();
                                const match = text.match(/([\\d.]+)([万亿]?)/);
                                if (match) {
                                    let num = parseFloat(match[1]);
                                    if (match[2] === '万') num *= 10000;
                                    if (match[2] === '亿') num *= 100000000;
                                    
                                    if (idx === 0) stats.likes = num;
                                    else if (idx === 1) stats.comments = num;
                                    else if (idx === 2) stats.shares = num;
                                }
                            });
                            
                            // 只添加有效数据
                            if (title && url) {
                                videos.push({
                                    title: title,
                                    author: author || '未知作者',
                                    url: url,
                                    stats: stats,
                                    platform: 'douyin',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取视频信息出错:', e);
                        }
                    });
                    
                    return videos;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(videos_data)} 个视频")
            return videos_data

        except Exception as e:
            self.logger.error(f"❌ 提取视频数据失败: {e}")
            return []

    async def search_users(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索用户

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            用户列表 [{name, id, follower_count, ...}]
        """
        self.logger.info(f"👥 搜索用户: {keyword}")

        # 使用用户类型搜索
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}/{encoded_keyword}?type=user"

        try:
            await self.navigate(search_url)
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待用户列表
        try:
            await self.wait_for_selector("ul", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待用户列表超时: {e}")
            return []

        # 提取用户数据
        users_data = await self.page.evaluate(
            """
            () => {
                const users = [];
                const userElements = document.querySelectorAll(
                    'li[data-e2e="search-user-item"], div[class*="user-card"]'
                );
                
                userElements.forEach(element => {
                    try {
                        const nameEl = element.querySelector('p[class*="name"], h4');
                        const idEl = element.querySelector('p[class*="douyin-id"]');
                        const followerEl = element.querySelector('span[class*="follower"]');
                        
                        const name = nameEl ? nameEl.textContent.trim() : '';
                        const userId = idEl ? idEl.textContent.trim() : '';
                        const followers = followerEl ? followerEl.textContent.trim() : '0';
                        
                        if (name) {
                            users.push({
                                name: name,
                                id: userId,
                                follower_count: followers,
                                platform: 'douyin'
                            });
                        }
                    } catch (e) {
                        console.error('提取用户信息出错:', e);
                    }
                });
                
                return users;
            }
            """
        )

        self.logger.info(f"✅ 搜索到 {len(users_data)} 个用户")
        return users_data[:limit]


# 测试代码
async def main():
    """测试DouyinAgent"""
    print("\n" + "=" * 70)
    print("🎬 抖音Agent测试")
    print("=" * 70)

    async with DouyinAgent(headless=False) as agent:  # headless=False 可看到浏览器
        # 测试1: 搜索视频
        print("\n📹 测试1: 搜索视频")
        videos = await agent.search_videos("人工智能", limit=10)

        print(f"\n✅ 找到 {len(videos)} 个视频:\n")
        for i, video in enumerate(videos[:5], 1):
            print(f"{i}. {video['title']}")
            print(f"   作者: {video['author']}")
            print(f"   链接: {video['url']}")
            print(
                f"   统计: ❤️ {video['stats']['likes']} | 💬 {video['stats']['comments']}\n"
            )

        # 测试2: 获取热门视频
        print("\n🔥 测试2: 获取热门视频")
        hot_videos = await agent.get_hot_videos(limit=5)

        print(f"\n✅ 获取 {len(hot_videos)} 个热门视频:\n")
        for i, video in enumerate(hot_videos, 1):
            print(f"{i}. {video['title']}")
            print(f"   作者: {video['author']}\n")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
