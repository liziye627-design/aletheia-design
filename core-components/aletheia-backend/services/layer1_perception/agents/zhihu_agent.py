#!/usr/bin/env python3
"""
知乎(Zhihu) Agent - 基于浏览器自动化的数据采集

功能:
- 搜索问题/回答/文章/用户
- 获取热榜内容
- 提取问题详情 (标题、回答数、关注数)
- 提取回答详情 (作者、内容、点赞数、评论数)
- 无需登录认证 (大部分内容)

使用方法:
    from services.layer1_perception.agents.zhihu_agent import ZhihuAgent

    async with ZhihuAgent(headless=True) as agent:
        # 搜索问题
        questions = await agent.search_questions("人工智能", limit=20)

        # 获取热榜
        hot_topics = await agent.get_hot_topics(limit=50)

        # 搜索回答
        answers = await agent.search_answers("机器学习", limit=30)

知乎网站结构特点:
- 搜索URL: https://www.zhihu.com/search?type={type}&q={keyword}
- 热榜URL: https://www.zhihu.com/hot
- 问题详情: https://www.zhihu.com/question/{question_id}
- 需要等待JS渲染
- 部分内容需要登录
"""

import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from datetime import datetime

from .browser_agent import BrowserAgent


class ZhihuAgent(BrowserAgent):
    """知乎浏览器Agent"""

    BASE_URL = "https://www.zhihu.com"
    SEARCH_URL = f"{BASE_URL}/search"
    HOT_URL = f"{BASE_URL}/hot"

    # CSS选择器 (根据知乎实际页面结构调整)
    SELECTORS = {
        "search_result": "div[class*='SearchResult']",  # 搜索结果容器
        "question_item": "div[data-zop-question]",  # 问题卡片
        "answer_item": "div[data-zop-answer]",  # 回答卡片
        "article_item": "div[data-zop-article]",  # 文章卡片
        "hot_list": "section[class*='HotList']",  # 热榜列表
        "hot_item": "section[class*='HotItem']",  # 热榜项目
    }

    async def search_questions(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索问题

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            问题列表 [{title, url, answer_count, follower_count, ...}]
        """
        self.logger.info(f"🔍 知乎搜索问题: {keyword} (限制: {limit})")
        self.last_diagnostics = {
            "blocked": False,
            "selector_miss": False,
            "empty_result": False,
            "reason": "",
            "selector_version": "zhihu_v2",
        }

        # 构造搜索URL (type=content包含问题和回答)
        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?type=content&q={encoded_keyword}"

        try:
            await self.navigate(search_url)
            self.logger.info(f"✅ 已访问: {search_url}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待搜索结果加载（多选择器候选）
        selector_ok = False
        for selector in [
            "div[class*='List']",
            "a[href*='/question/']",
            "h2.ContentItem-title a",
            "main",
        ]:
            if await self.wait_for_selector(selector, timeout=6000):
                selector_ok = True
                break
        if not selector_ok:
            self.last_diagnostics.update(
                {"selector_miss": True, "reason": "selector_miss:zhihu"}
            )

        if await self.detect_blocked_page():
            return []

        # 滚动加载更多
        questions = []
        max_scroll_attempts = 20
        scroll_count = 0
        stagnant_rounds = 0

        while len(questions) < limit and scroll_count < max_scroll_attempts:
            before_count = len(questions)
            new_questions = await self._extract_questions_from_page()
            if not new_questions:
                new_questions = await self._extract_questions_from_text_fallback(
                    limit=limit
                )

            # 去重合并
            existing_urls = {q["url"] for q in questions}
            for question in new_questions:
                if question["url"] not in existing_urls and len(questions) < limit:
                    questions.append(question)
                    existing_urls.add(question["url"])

            self.logger.info(f"📊 当前已获取 {len(questions)} 个问题")

            if len(questions) >= limit:
                break

            if len(questions) == before_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            if stagnant_rounds >= 3:
                self.last_diagnostics.update(
                    {"empty_result": True, "reason": "empty_result:zhihu"}
                )
                self.logger.warning("⚠️ 知乎连续3轮无新增，提前结束")
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 搜索完成,共获取 {len(questions)} 个问题")
        return questions[:limit]

    async def _extract_questions_from_text_fallback(
        self, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """文本兜底提取：从页面文本抽取知乎问题链接。"""
        try:
            page_text = await self.get_page_text()
            urls = re.findall(r"https?://www\.zhihu\.com/question/\d+", page_text)
            results: List[Dict[str, Any]] = []
            seen = set()
            for u in urls:
                if u in seen:
                    continue
                seen.add(u)
                results.append(
                    {
                        "title": "文本兜底提取问题",
                        "url": u,
                        "answer_count": 0,
                        "follower_count": 0,
                        "platform": "zhihu",
                        "type": "question",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                if len(results) >= limit:
                    break
            return results
        except Exception:
            return []

    async def search_answers(
        self, keyword: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        搜索回答

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            回答列表 [{content, author, question, url, likes, ...}]
        """
        self.logger.info(f"🔍 知乎搜索回答: {keyword} (限制: {limit})")

        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?type=content&q={encoded_keyword}"

        try:
            await self.navigate(search_url)
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待搜索结果
        try:
            await self.wait_for_selector("div[class*='List']", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待搜索结果超时: {e}")
            return []

        # 滚动加载
        answers = []
        max_scroll_attempts = 20
        scroll_count = 0

        while len(answers) < limit and scroll_count < max_scroll_attempts:
            new_answers = await self._extract_answers_from_page()

            existing_urls = {a["url"] for a in answers}
            for answer in new_answers:
                if answer["url"] not in existing_urls and len(answers) < limit:
                    answers.append(answer)
                    existing_urls.add(answer["url"])

            self.logger.info(f"📊 当前已获取 {len(answers)} 个回答")

            if len(answers) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 搜索完成,共获取 {len(answers)} 个回答")
        return answers[:limit]

    async def get_hot_topics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取知乎热榜

        Args:
            limit: 返回结果数量上限

        Returns:
            热榜列表 [{title, excerpt, url, hot_score, ...}]
        """
        self.logger.info(f"🔥 获取知乎热榜 (限制: {limit})")

        try:
            await self.navigate(self.HOT_URL)
            self.logger.info(f"✅ 已访问热榜: {self.HOT_URL}")
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        # 等待热榜加载
        try:
            await self.wait_for_selector("section", timeout=10000)
            self.logger.info("✅ 热榜加载完成")
        except Exception as e:
            self.logger.warning(f"⚠️ 等待热榜超时: {e}")
            return []

        # 滚动加载 (热榜通常有50条)
        hot_topics = []
        max_scroll_attempts = 10
        scroll_count = 0

        while len(hot_topics) < limit and scroll_count < max_scroll_attempts:
            new_topics = await self._extract_hot_topics_from_page()

            existing_urls = {t["url"] for t in hot_topics}
            for topic in new_topics:
                if topic["url"] not in existing_urls and len(hot_topics) < limit:
                    hot_topics.append(topic)
                    existing_urls.add(topic["url"])

            if len(hot_topics) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 获取热榜完成,共 {len(hot_topics)} 条")
        return hot_topics[:limit]

    async def search_articles(
        self, keyword: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索文章 (知乎专栏)

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量上限

        Returns:
            文章列表 [{title, author, excerpt, url, ...}]
        """
        self.logger.info(f"📰 搜索文章: {keyword}")

        encoded_keyword = quote(keyword)
        search_url = f"{self.SEARCH_URL}?type=content&q={encoded_keyword}"

        try:
            await self.navigate(search_url)
        except Exception as e:
            self.logger.error(f"❌ 导航失败: {e}")
            return []

        try:
            await self.wait_for_selector("div[class*='List']", timeout=10000)
        except Exception as e:
            self.logger.warning(f"⚠️ 等待搜索结果超时: {e}")
            return []

        # 提取文章
        articles = []
        max_scroll_attempts = 15
        scroll_count = 0

        while len(articles) < limit and scroll_count < max_scroll_attempts:
            new_articles = await self._extract_articles_from_page()

            existing_urls = {a["url"] for a in articles}
            for article in new_articles:
                if article["url"] not in existing_urls and len(articles) < limit:
                    articles.append(article)
                    existing_urls.add(article["url"])

            if len(articles) >= limit:
                break

            await self.scroll_page()
            await self.random_delay(1.0, 2.0)

            scroll_count += 1

        self.logger.info(f"✅ 搜索到 {len(articles)} 篇文章")
        return articles[:limit]

    async def _extract_questions_from_page(self) -> List[Dict[str, Any]]:
        """从当前页面提取问题"""
        try:
            questions_data = await self.page.evaluate(
                """
                () => {
                    const questions = [];
                    
                    // 查找问题元素
                    const questionElements = document.querySelectorAll(
                        'div[data-zop-question], h2.ContentItem-title a, div[class*="QuestionItem"]'
                    );
                    
                    questionElements.forEach(element => {
                        try {
                            let title = '';
                            let url = '';
                            
                            // 提取标题和链接
                            if (element.tagName === 'A') {
                                title = element.textContent.trim();
                                url = element.href;
                            } else {
                                const titleEl = element.querySelector('h2 a, a[class*="title"]');
                                if (titleEl) {
                                    title = titleEl.textContent.trim();
                                    url = titleEl.href;
                                }
                            }
                            
                            // 提取统计信息
                            let answerCount = 0;
                            let followerCount = 0;
                            
                            const metaElements = element.querySelectorAll(
                                'div[class*="ContentItem-meta"] span, button span'
                            );
                            metaElements.forEach(metaEl => {
                                const text = metaEl.textContent.trim();
                                if (text.includes('个回答')) {
                                    const match = text.match(/([\\d,]+)\\s*个回答/);
                                    if (match) {
                                        answerCount = parseInt(match[1].replace(/,/g, ''));
                                    }
                                } else if (text.includes('人关注')) {
                                    const match = text.match(/([\\d,]+)\\s*人关注/);
                                    if (match) {
                                        followerCount = parseInt(match[1].replace(/,/g, ''));
                                    }
                                }
                            });
                            
                            if (title && url && url.includes('/question/')) {
                                questions.push({
                                    title: title,
                                    url: url,
                                    answer_count: answerCount,
                                    follower_count: followerCount,
                                    platform: 'zhihu',
                                    type: 'question',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取问题出错:', e);
                        }
                    });
                    
                    return questions;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(questions_data)} 个问题")
            return questions_data

        except Exception as e:
            self.logger.error(f"❌ 提取问题失败: {e}")
            return []

    async def _extract_answers_from_page(self) -> List[Dict[str, Any]]:
        """从当前页面提取回答"""
        try:
            answers_data = await self.page.evaluate(
                """
                () => {
                    const answers = [];
                    
                    const answerElements = document.querySelectorAll(
                        'div[data-zop-answer], div[class*="AnswerItem"], div[itemprop="answer"]'
                    );
                    
                    answerElements.forEach(element => {
                        try {
                            // 提取问题标题
                            let questionTitle = '';
                            const questionEl = element.querySelector('h2 a, a[class*="QuestionLink"]');
                            if (questionEl) {
                                questionTitle = questionEl.textContent.trim();
                            }
                            
                            // 提取作者
                            let author = '';
                            const authorEl = element.querySelector(
                                'a[class*="AuthorInfo"], meta[itemprop="name"]'
                            );
                            if (authorEl) {
                                author = authorEl.getAttribute('content') || authorEl.textContent.trim();
                            }
                            
                            // 提取回答内容摘要
                            let content = '';
                            const contentEl = element.querySelector(
                                'div[class*="RichContent"], span[itemprop="text"]'
                            );
                            if (contentEl) {
                                content = contentEl.textContent.trim().substring(0, 200);
                            }
                            
                            // 提取链接
                            let url = '';
                            const linkEl = element.querySelector('a[href*="/answer/"]');
                            if (linkEl) {
                                url = linkEl.href;
                            }
                            
                            // 提取点赞数
                            let likes = 0;
                            const likeEl = element.querySelector('button[aria-label*="赞同"]');
                            if (likeEl) {
                                const likeText = likeEl.textContent.trim();
                                const match = likeText.match(/([\\d,]+)/);
                                if (match) {
                                    likes = parseInt(match[1].replace(/,/g, ''));
                                }
                            }
                            
                            if (url && url.includes('/answer/')) {
                                answers.push({
                                    question: questionTitle,
                                    author: author || '匿名用户',
                                    content: content,
                                    url: url,
                                    likes: likes,
                                    platform: 'zhihu',
                                    type: 'answer',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取回答出错:', e);
                        }
                    });
                    
                    return answers;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(answers_data)} 个回答")
            return answers_data

        except Exception as e:
            self.logger.error(f"❌ 提取回答失败: {e}")
            return []

    async def _extract_hot_topics_from_page(self) -> List[Dict[str, Any]]:
        """从热榜页面提取热点"""
        try:
            hot_data = await self.page.evaluate(
                """
                () => {
                    const topics = [];
                    
                    const hotElements = document.querySelectorAll(
                        'section[class*="HotItem"], div[class*="HotList-item"]'
                    );
                    
                    hotElements.forEach((element, index) => {
                        try {
                            // 提取标题
                            let title = '';
                            const titleEl = element.querySelector('h2, a[class*="title"]');
                            if (titleEl) {
                                title = titleEl.textContent.trim();
                            }
                            
                            // 提取摘要
                            let excerpt = '';
                            const excerptEl = element.querySelector('p[class*="HotItem-excerpt"]');
                            if (excerptEl) {
                                excerpt = excerptEl.textContent.trim();
                            }
                            
                            // 提取链接
                            let url = '';
                            const linkEl = element.querySelector('a[href*="/question/"], a[href*="/answer/"]');
                            if (linkEl) {
                                url = linkEl.href;
                            }
                            
                            // 提取热度
                            let hotScore = '';
                            const scoreEl = element.querySelector('div[class*="HotItem-metrics"]');
                            if (scoreEl) {
                                hotScore = scoreEl.textContent.trim();
                            }
                            
                            if (title && url) {
                                topics.push({
                                    rank: index + 1,
                                    title: title,
                                    excerpt: excerpt,
                                    url: url,
                                    hot_score: hotScore,
                                    platform: 'zhihu',
                                    type: 'hot_topic',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取热榜项出错:', e);
                        }
                    });
                    
                    return topics;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(hot_data)} 条热榜")
            return hot_data

        except Exception as e:
            self.logger.error(f"❌ 提取热榜失败: {e}")
            return []

    async def _extract_articles_from_page(self) -> List[Dict[str, Any]]:
        """从当前页面提取文章"""
        try:
            articles_data = await self.page.evaluate(
                """
                () => {
                    const articles = [];
                    
                    const articleElements = document.querySelectorAll(
                        'div[data-zop-article], div[class*="ArticleItem"]'
                    );
                    
                    articleElements.forEach(element => {
                        try {
                            // 提取标题
                            let title = '';
                            const titleEl = element.querySelector('h2 a, a[class*="title"]');
                            if (titleEl) {
                                title = titleEl.textContent.trim();
                            }
                            
                            // 提取作者
                            let author = '';
                            const authorEl = element.querySelector('a[class*="AuthorInfo"]');
                            if (authorEl) {
                                author = authorEl.textContent.trim();
                            }
                            
                            // 提取摘要
                            let excerpt = '';
                            const excerptEl = element.querySelector('div[class*="RichText"]');
                            if (excerptEl) {
                                excerpt = excerptEl.textContent.trim().substring(0, 150);
                            }
                            
                            // 提取链接
                            let url = '';
                            const linkEl = element.querySelector('a[href*="/p/"]');
                            if (linkEl) {
                                url = linkEl.href;
                            }
                            
                            if (title && url) {
                                articles.push({
                                    title: title,
                                    author: author || '匿名用户',
                                    excerpt: excerpt,
                                    url: url,
                                    platform: 'zhihu',
                                    type: 'article',
                                    timestamp: new Date().toISOString()
                                });
                            }
                        } catch (e) {
                            console.error('提取文章出错:', e);
                        }
                    });
                    
                    return articles;
                }
                """
            )

            self.logger.info(f"📊 从页面提取到 {len(articles_data)} 篇文章")
            return articles_data

        except Exception as e:
            self.logger.error(f"❌ 提取文章失败: {e}")
            return []


# 测试代码
async def main():
    """测试ZhihuAgent"""
    print("\n" + "=" * 70)
    print("💡 知乎Agent测试")
    print("=" * 70)

    async with ZhihuAgent(headless=False) as agent:  # headless=False 可看到浏览器
        # 测试1: 搜索问题
        print("\n❓ 测试1: 搜索问题")
        questions = await agent.search_questions("人工智能", limit=10)

        print(f"\n✅ 找到 {len(questions)} 个问题:\n")
        for i, q in enumerate(questions[:5], 1):
            print(f"{i}. {q['title']}")
            print(f"   链接: {q['url']}")
            print(f"   {q['answer_count']} 个回答 | {q['follower_count']} 人关注\n")

        # 测试2: 获取热榜
        print("\n🔥 测试2: 获取热榜")
        hot_topics = await agent.get_hot_topics(limit=10)

        print(f"\n✅ 获取 {len(hot_topics)} 条热榜:\n")
        for i, topic in enumerate(hot_topics[:5], 1):
            print(f"{topic['rank']}. {topic['title']}")
            print(f"   热度: {topic['hot_score']}\n")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
