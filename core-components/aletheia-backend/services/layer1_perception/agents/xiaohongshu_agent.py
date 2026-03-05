#!/usr/bin/env python3
"""
小红书(Xiaohongshu/RED) Agent - 基于浏览器自动化的数据采集

功能:
- 搜索笔记/商品/用户
- 获取热门笔记
- 提取笔记详情 (标题、作者、图片、点赞数、收藏数)
- 无需登录认证

使用方法:
    from services.layer1_perception.agents.xiaohongshu_agent import XiaohongshuAgent

    async with XiaohongshuAgent(headless=True) as agent:
        # 搜索笔记
        notes = await agent.search_notes("美妆测评", limit=20)

        # 获取热门笔记
        hot_notes = await agent.get_hot_notes(limit=30)

小红书网站结构特点:
- 搜索URL: https://www.xiaohongshu.com/search_result?keyword={keyword}
- 笔记卡片: class="note-item"
- 瀑布流布局
- 需要等待JS渲染
"""

import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from datetime import datetime

from .browser_agent import BrowserAgent


class XiaohongshuAgent(BrowserAgent):
    """小红书浏览器Agent"""

    BASE_URL = "https://www.xiaohongshu.com"
    SEARCH_URL = f"{BASE_URL}/search_result"

    # CSS选择器 (根据小红书实际页面结构调整)
    SELECTORS = {
        "note_list": "section[class*='note-list']",  # 笔记列表容器
        "note_item": "a[class*='note-item']",  # 单个笔记卡片
        "note_title": "span[class*='title']",  # 笔记标题
        "note_author": "span[class*='author']",  # 作者
        "note_stats": "span[class*='like-count']",  # 统计信息
        "note_image": "img[class*='cover']",  # 封面图
        "explore_feed": "section[class*='explore-feed']",  # 发现页信息流
    }

    async def search_notes(
        self,
        keyword: str,
        limit: int = 20,
        note_type: str = "all",  # all, video, image
    ) -> List[Dict[str, Any]]:
        """
        搜索笔记

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限
            note_type: 笔记类型 (all/video/image)

        Returns:
            笔记列表 [{title, author, url, likes, images, ...}]
        """
        self.logger.info(f"🔍 小红书搜索: {keyword} (类型: {note_type}, 限制: {limit})")
        self.last_diagnostics = {
            "blocked": False,
            "selector_miss": False,
            "empty_result": False,
            "reason": "",
            "selector_version": "xiaohongshu_v2",
        }

        # 1. 构造搜索URL
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?keyword={encoded_keyword}"

        if note_type != "all":
            search_url += f"&type={note_type}"

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
            "section",
            "a[href*='/explore/']",
            "a[href*='xiaohongshu.com/explore']",
            "div[class*='note']",
        ]:
            if await self.wait_for_selector(selector, timeout=6000):
                selector_ok = True
                break

        if not selector_ok:
            self.last_diagnostics.update(
                {"selector_miss": True, "reason": "selector_miss:xiaohongshu"}
            )

        if await self.detect_blocked_page():
            return []

        # 4. 滚动加载更多内容 (小红书是瀑布流布局)
        notes = []
        max_scroll_attempts = 20  # 最多滚动20次
        scroll_count = 0
        stagnant_rounds = 0

        while len(notes) < limit and scroll_count < max_scroll_attempts:
            before_count = len(notes)
            # 提取当前页面的笔记
            new_notes = await self._extract_notes_from_page()
            if not new_notes:
                new_notes = await self._extract_notes_from_text_fallback(limit=limit)

            # 合并新笔记 (去重)
            existing_urls = {n["url"] for n in notes}
            for note in new_notes:
                if note["url"] not in existing_urls and len(notes) < limit:
                    notes.append(note)
                    existing_urls.add(note["url"])

            self.logger.info(f"📊 当前已获取 {len(notes)} 条笔记")

            # 如果已经足够,提前结束
            if len(notes) >= limit:
                break

            if len(notes) == before_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 3:
                self.last_diagnostics.update(
                    {"empty_result": True, "reason": "empty_result:xiaohongshu"}
                )
                self.logger.warning("⚠️ 小红书连续3轮无新增，提前结束")
                break

            # 滚动加载更多 (瀑布流需要滚到底部)
            await self.scroll_page()
            await self.random_delay(1.5, 2.5)  # 小红书加载较慢

            scroll_count += 1

        self.logger.info(f"✅ 搜索完成,共获取 {len(notes)} 条笔记")
        return notes[:limit]

    async def _extract_notes_from_text_fallback(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """文本兜底提取：从页面文本中抽取小红书内容链接。"""
        try:
            page_text = await self.get_page_text()
            urls = re.findall(
                r"https?://www\.xiaohongshu\.com/explore/[A-Za-z0-9]+", page_text
            )
            results: List[Dict[str, Any]] = []
            seen = set()
            for u in urls:
                if u in seen:
                    continue
                seen.add(u)
                results.append(
                    {
                        "title": "文本兜底提取笔记",
                        "author": "unknown",
                        "url": u,
                        "cover_image": "",
                        "stats": {"likes": 0, "collects": 0, "comments": 0},
                        "platform": "xiaohongshu",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return []

    async def get_hot_notes(
        self, category: str = "all", limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        获取小红书热门笔记 (发现页)

        Args:
            category: 分类 (all/fashion/beauty/food/travel/...)
            limit: 返回结果数量上限

        Returns:
            热门笔记列表
        """
        self.logger.info(f"🔥 获取小红书热门笔记 (分类: {category}, 限制: {limit})")

        # 小红书发现页
        explore_url = f"{self.BASE_URL}/explore"

        if category != "all":
            explore_url += f"?category={category}"

        try:
            await self.navigate(explore_url)
            self.logger.info(f"✅ 已访问发现页: {explore_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待页面加载
        try:
            await self.wait_for_selector("section", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待发现页超时: {e}")

        # 滚动加载
        notes = []
        max_scroll_attempts = 20
        scroll_count = 0

        while len(notes) < limit and scroll_count < max_scroll_attempts:
            new_notes = await self._extract_notes_from_page()

            existing_urls = {n["url"] for n in notes}
            for note in new_notes:
                if note["url"] not in existing_urls and len(notes) < limit:
                    notes.append(note)
                    existing_urls.add(note["url"])

            if len(notes) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.5, 2.5)

            scroll_count += 1

        self.logger.info(f"✅ 获取热门笔记完成,共 {len(notes)} 条")
        return notes[:limit]

    async def get_user_notes(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取用户发布的笔记

        Args:
            user_id: 用户ID (小红书号)
            limit: 返回结果数量上限

        Returns:
            用户笔记列表
        """
        self.logger.info(f"👤 获取用户 {user_id} 的笔记 (限制: {limit})")

        user_url = f"{self.BASE_URL}/user/profile/{user_id}"

        try:
            await self.navigate(user_url)
            self.logger.info(f"✅ 已访问用户页: {user_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待用户笔记列表
        try:
            await self.wait_for_selector("section", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待用户笔记列表超时: {e}")

        # 滚动加载
        notes = []
        max_scroll_attempts = 15
        scroll_count = 0

        while len(notes) < limit and scroll_count < max_scroll_attempts:
            new_notes = await self._extract_notes_from_page()

            existing_urls = {n["url"] for n in notes}
            for note in new_notes:
                if note["url"] not in existing_urls and len(notes) < limit:
                    notes.append(note)
                    existing_urls.add(note["url"])

            if len(notes) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.5, 2.5)

            scroll_count += 1

        self.logger.info(f"✅ 获取用户笔记完成,共 {len(notes)} 条")
        return notes[:limit]

    async def _extract_notes_from_page(self) -> List[Dict[str, Any]]:
        """
        从当前页面提取笔记信息

        Returns:
            笔记列表
        """
        try:
            # 使用JavaScript提取笔记数据
            notes_data = await self.page.evaluate(
                """
                () => {
                    const notes = [];
                    
                    // 尝试多种选择器策略
                    const noteElements = document.querySelectorAll(
                        'a[class*="note-item"], a[href*="/explore/"], section a[href*="/discovery/item/"]'
                    );
                    
                    noteElements.forEach((element, index) => {
                        try {
                            // 提取标题
                            let title = '';
                            const titleEl = element.querySelector(
                                'span[class*="title"], p[class*="title"], div[class*="title"]'
                            );
                            if (titleEl) {
                                title = titleEl.textContent.trim();
                            }
                            
                            // 如果没有标题元素,尝试从alt或aria-label获取
                            if (!title) {
                                const imgEl = element.querySelector('img');
                                if (imgEl && imgEl.alt) {
                                    title = imgEl.alt;
                                }
                            }
                            
                            // 提取作者
                            let author = '';
                            const authorEl = element.querySelector(
                                'span[class*="author"], p[class*="name"], a[class*="user"]'
                            );
                            if (authorEl) {
                                author = authorEl.textContent.trim();
                            }
                            
                            // 提取链接
                            let url = '';
                            if (element.href) {
                                url = element.href;
                            }
                            
                            // 提取封面图
                            let cover_image = '';
                            const imgEl = element.querySelector('img');
                            if (imgEl && imgEl.src) {
                                cover_image = imgEl.src;
                            }
                            
                            // 提取统计信息 (点赞数)
                            let stats = {
                                likes: 0,
                                collects: 0,
                                comments: 0
                            };
                            
                            const statsElements = element.querySelectorAll(
                                'span[class*="like"], span[class*="count"]'
                            );
                            statsElements.forEach((statEl, idx) => {
                                const text = statEl.textContent.trim();
                                const match = text.match(/([\\d.]+)([万亿]?)/);
                                if (match) {
                                    let num = parseFloat(match[1]);
                                    if (match[2] === '万') num *= 10000;
                                    if (match[2] === '亿') num *= 100000000;
                                    
                                    if (idx === 0) stats.likes = num;
                                    else if (idx === 1) stats.collects = num;
                                    else if (idx === 2) stats.comments = num;
                                }
                            });
                            
                            // 只添加有效数据 (必须有链接)
                            if (url && url.includes('xiaohongshu.com')) {
                                notes.push({
                                    title: title || '无标题',
                                    author: author || '未知作者',
                                    url: url,
                                    cover_image: cover_image,
                                    stats: stats,
                                    platform: 'xiaohongshu',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取笔记信息出错:', e);
                        }
                    });
                    
                    return notes;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(notes_data)} 条笔记")
            return notes_data

        except Exception as e:
            self.logger.error(f"❌ 提取笔记数据失败: {e}")
            return []

    async def search_users(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索用户

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            用户列表 [{name, id, follower_count, note_count, ...}]
        """
        self.logger.info(f"👥 搜索用户: {keyword}")

        # 使用用户类型搜索
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?keyword={encoded_keyword}&type=user"

        try:
            await self.navigate(search_url)
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待用户列表
        try:
            await self.wait_for_selector("section", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待用户列表超时: {e}")
            return []

        # 提取用户数据
        users_data = await self.page.evaluate(
            """
            () => {
                const users = [];
                const userElements = document.querySelectorAll(
                    'div[class*="user-item"], a[class*="user-card"]'
                );
                
                userElements.forEach(element => {
                    try {
                        const nameEl = element.querySelector('p[class*="name"], span[class*="nickname"]');
                        const idEl = element.querySelector('p[class*="redId"], span[class*="id"]');
                        const followerEl = element.querySelector('span[class*="fans-count"]');
                        const noteCountEl = element.querySelector('span[class*="note-count"]');
                        
                        const name = nameEl ? nameEl.textContent.trim() : '';
                        const userId = idEl ? idEl.textContent.trim() : '';
                        const followers = followerEl ? followerEl.textContent.trim() : '0';
                        const noteCount = noteCountEl ? noteCountEl.textContent.trim() : '0';
                        
                        if (name) {
                            users.push({
                                name: name,
                                id: userId,
                                follower_count: followers,
                                note_count: noteCount,
                                platform: 'xiaohongshu'
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

    async def search_products(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索商品 (小红书商城)

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            商品列表 [{name, price, url, image, ...}]
        """
        self.logger.info(f"🛍️ 搜索商品: {keyword}")

        # 使用商品类型搜索
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?keyword={encoded_keyword}&type=goods"

        try:
            await self.navigate(search_url)
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待商品列表
        try:
            await self.wait_for_selector("section", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待商品列表超时: {e}")
            return []

        # 滚动加载
        products = []
        max_scroll_attempts = 10
        scroll_count = 0

        while len(products) < limit and scroll_count < max_scroll_attempts:
            # 提取商品数据
            new_products = await self.page.evaluate(
                """
                () => {
                    const products = [];
                    const productElements = document.querySelectorAll(
                        'a[class*="goods-item"], div[class*="product-card"]'
                    );
                    
                    productElements.forEach(element => {
                        try {
                            const nameEl = element.querySelector('p[class*="name"], span[class*="title"]');
                            const priceEl = element.querySelector('span[class*="price"]');
                            const imgEl = element.querySelector('img');
                            
                            const name = nameEl ? nameEl.textContent.trim() : '';
                            const price = priceEl ? priceEl.textContent.trim() : '';
                            const image = imgEl ? imgEl.src : '';
                            const url = element.href || '';
                            
                            if (name && url) {
                                products.push({
                                    name: name,
                                    price: price,
                                    url: url,
                                    image: image,
                                    platform: 'xiaohongshu'
                                });
                            }
                        } catch (e) {
                            console.error('提取商品信息出错:', e);
                        }
                    });
                    
                    return products;
                }
                """
            )

            # 合并去重
            existing_urls = {p["url"] for p in products}
            for product in new_products:
                if product["url"] not in existing_urls and len(products) < limit:
                    products.append(product)
                    existing_urls.add(product["url"])

            if len(products) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 搜索到 {len(products)} 个商品")
        return products[:limit]


# 测试代码
async def main():
    """测试XiaohongshuAgent"""
    print("\n" + "=" * 70)
    print("📕 小红书Agent测试")
    print("=" * 70)

    async with XiaohongshuAgent(headless=False) as agent:  # headless=False 可看到浏览器
        # 测试1: 搜索笔记
        print("\n📝 测试1: 搜索笔记")
        notes = await agent.search_notes("美妆测评", limit=10)

        print(f"\n✅ 找到 {len(notes)} 条笔记:\n")
        for i, note in enumerate(notes[:5], 1):
            print(f"{i}. {note['title']}")
            print(f"   作者: {note['author']}")
            print(f"   链接: {note['url']}")
            print(f"   点赞: ❤️ {note['stats']['likes']}\n")

        # 测试2: 获取热门笔记
        print("\n🔥 测试2: 获取热门笔记")
        hot_notes = await agent.get_hot_notes(limit=5)

        print(f"\n✅ 获取 {len(hot_notes)} 条热门笔记:\n")
        for i, note in enumerate(hot_notes, 1):
            print(f"{i}. {note['title']}")
            print(f"   作者: {note['author']}\n")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
