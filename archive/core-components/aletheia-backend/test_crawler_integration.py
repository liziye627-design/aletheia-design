"""
爬虫系统集成测试

测试所有爬虫的基本功能:
1. 初始化测试
2. 热门话题获取测试
3. 搜索功能测试
4. 健康检查测试
5. 跨平台聚合测试

使用方法:
    python test_crawler_integration.py
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, List, Any

# 导入爬虫管理器
from services.layer1_perception.crawler_manager import CrawlerManager


class CrawlerIntegrationTest:
    """爬虫系统集成测试类"""

    def __init__(self):
        """初始化测试环境"""
        self.manager = None
        self.test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

    def log_test(self, name: str, status: str, message: str = ""):
        """记录测试结果"""
        self.test_results["total"] += 1
        self.test_results[status] += 1

        status_emoji = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}

        result = {
            "name": name,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        self.test_results["details"].append(result)
        print(f"{status_emoji.get(status, '❓')} {name}: {message}")

    async def test_crawler_initialization(self):
        """测试1: 爬虫管理器初始化"""
        print("\n" + "=" * 60)
        print("测试1: 爬虫管理器初始化")
        print("=" * 60)

        try:
            # 从环境变量读取凭证 (如果有)
            self.manager = CrawlerManager(
                weibo_cookies=os.getenv("WEIBO_COOKIES"),
                twitter_bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
                xhs_cookies=os.getenv("XHS_COOKIES"),
                douyin_cookies=os.getenv("DOUYIN_COOKIES"),
                zhihu_cookies=os.getenv("ZHIHU_COOKIES"),
                bilibili_cookies=os.getenv("BILIBILI_COOKIES"),
                kuaishou_cookies=os.getenv("KUAISHOU_COOKIES"),
                douban_cookies=os.getenv("DOUBAN_COOKIES"),
                reddit_client_id=os.getenv("REDDIT_CLIENT_ID"),
                reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
                github_token=os.getenv("GITHUB_TOKEN"),
                stackoverflow_api_key=os.getenv("STACKOVERFLOW_API_KEY"),
                openalex_email=os.getenv("OPENALEX_EMAIL", "test@aletheia.ai"),
            )

            platform_count = len(self.manager.crawlers)
            self.log_test(
                "初始化爬虫管理器", "passed", f"成功初始化 {platform_count} 个爬虫"
            )

            # 列出所有可用爬虫
            print(f"\n可用爬虫列表 ({platform_count}个):")
            for i, platform in enumerate(sorted(self.manager.crawlers.keys()), 1):
                print(f"  {i}. {platform}")

        except Exception as e:
            self.log_test("初始化爬虫管理器", "failed", f"初始化失败: {e}")
            raise

    async def test_official_sources(self):
        """测试2: 官方信源爬虫"""
        print("\n" + "=" * 60)
        print("测试2: 官方信源爬虫 (不需要凭证)")
        print("=" * 60)

        # 测试中国官方信源
        china_official = ["xinhua", "peoples_daily", "china_gov"]

        for platform in china_official:
            if platform not in self.manager.crawlers:
                self.log_test(f"{platform} - 官方信源", "skipped", "爬虫未初始化")
                continue

            try:
                crawler = self.manager.get_crawler(platform)
                results = await crawler.fetch_latest(limit=3)

                if results:
                    self.log_test(
                        f"{platform} - 获取最新文章",
                        "passed",
                        f"获取 {len(results)} 篇文章",
                    )
                    # 显示第一篇文章标题
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test(
                        f"{platform} - 获取最新文章", "failed", "未获取到数据"
                    )

            except Exception as e:
                self.log_test(
                    f"{platform} - 获取最新文章", "failed", f"错误: {str(e)[:100]}"
                )

    async def test_news_media(self):
        """测试3: 新闻媒体RSS爬虫"""
        print("\n" + "=" * 60)
        print("测试3: 新闻媒体RSS爬虫 (不需要凭证)")
        print("=" * 60)

        news_platforms = ["reuters", "ap_news", "bbc", "guardian"]

        for platform in news_platforms:
            if platform not in self.manager.crawlers:
                self.log_test(f"{platform} - RSS订阅", "skipped", "爬虫未初始化")
                continue

            try:
                crawler = self.manager.get_crawler(platform)
                results = await crawler.fetch_latest(limit=3)

                if results:
                    self.log_test(
                        f"{platform} - RSS订阅", "passed", f"获取 {len(results)} 篇新闻"
                    )
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test(f"{platform} - RSS订阅", "failed", "未获取到数据")

            except Exception as e:
                self.log_test(
                    f"{platform} - RSS订阅", "failed", f"错误: {str(e)[:100]}"
                )

    async def test_academic_datasets(self):
        """测试4: 学术数据集爬虫"""
        print("\n" + "=" * 60)
        print("测试4: 学术数据集爬虫 (不需要凭证)")
        print("=" * 60)

        # 测试GDELT
        if "gdelt" in self.manager.crawlers:
            try:
                crawler = self.manager.get_crawler("gdelt")
                results = await crawler.search_events(
                    query="climate change", max_records=3
                )

                if results:
                    self.log_test(
                        "GDELT - 事件搜索", "passed", f"获取 {len(results)} 条事件"
                    )
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test("GDELT - 事件搜索", "failed", "未获取到数据")
            except Exception as e:
                self.log_test("GDELT - 事件搜索", "failed", f"错误: {str(e)[:100]}")

        # 测试OpenAlex
        if "openalex" in self.manager.crawlers:
            try:
                crawler = self.manager.get_crawler("openalex")
                results = await crawler.search_works(
                    query="artificial intelligence", limit=3
                )

                if results:
                    self.log_test(
                        "OpenAlex - 学术论文搜索",
                        "passed",
                        f"获取 {len(results)} 篇论文",
                    )
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test("OpenAlex - 学术论文搜索", "failed", "未获取到数据")
            except Exception as e:
                self.log_test(
                    "OpenAlex - 学术论文搜索", "failed", f"错误: {str(e)[:100]}"
                )

        # 测试Common Crawl
        if "common_crawl" in self.manager.crawlers:
            try:
                crawler = self.manager.get_crawler("common_crawl")
                # 获取可用索引
                indexes = await crawler.get_available_indexes()

                if indexes:
                    self.log_test(
                        "Common Crawl - 索引列表",
                        "passed",
                        f"获取 {len(indexes)} 个索引",
                    )
                    print(f"    最新索引: {indexes[0] if indexes else 'N/A'}")
                else:
                    self.log_test("Common Crawl - 索引列表", "failed", "未获取到索引")
            except Exception as e:
                self.log_test(
                    "Common Crawl - 索引列表", "failed", f"错误: {str(e)[:100]}"
                )

    async def test_community_platforms(self):
        """测试5: 社区论坛爬虫"""
        print("\n" + "=" * 60)
        print("测试5: 社区论坛爬虫")
        print("=" * 60)

        # 测试GitHub (不需要token也可以工作，但有速率限制)
        if "github" in self.manager.crawlers:
            try:
                crawler = self.manager.get_crawler("github")
                results = await crawler.fetch_events(limit=3)

                if results:
                    self.log_test(
                        "GitHub - 公开事件", "passed", f"获取 {len(results)} 条事件"
                    )
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test("GitHub - 公开事件", "failed", "未获取到数据")
            except Exception as e:
                self.log_test("GitHub - 公开事件", "failed", f"错误: {str(e)[:100]}")

        # 测试Stack Overflow
        if "stackoverflow" in self.manager.crawlers:
            try:
                crawler = self.manager.get_crawler("stackoverflow")
                results = await crawler.fetch_hot_questions(limit=3)

                if results:
                    self.log_test(
                        "Stack Overflow - 热门问题",
                        "passed",
                        f"获取 {len(results)} 个问题",
                    )
                    if results:
                        print(f"    示例: {results[0].get('title', 'N/A')[:50]}...")
                else:
                    self.log_test("Stack Overflow - 热门问题", "failed", "未获取到数据")
            except Exception as e:
                self.log_test(
                    "Stack Overflow - 热门问题", "failed", f"错误: {str(e)[:100]}"
                )

    async def test_health_checks(self):
        """测试6: 健康检查"""
        print("\n" + "=" * 60)
        print("测试6: 爬虫健康检查")
        print("=" * 60)

        for platform, crawler in self.manager.crawlers.items():
            # 检查爬虫是否有health_check方法
            if hasattr(crawler, "health_check"):
                try:
                    health = await crawler.health_check()
                    status = "passed" if health.get("healthy", False) else "failed"
                    self.log_test(
                        f"{platform} - 健康检查",
                        status,
                        f"状态: {health.get('status', 'unknown')}",
                    )
                except Exception as e:
                    self.log_test(
                        f"{platform} - 健康检查", "failed", f"错误: {str(e)[:50]}"
                    )
            else:
                # 如果没有health_check方法，跳过
                self.log_test(f"{platform} - 健康检查", "skipped", "无健康检查方法")

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print("测试摘要")
        print("=" * 60)

        total = self.test_results["total"]
        passed = self.test_results["passed"]
        failed = self.test_results["failed"]
        skipped = self.test_results["skipped"]

        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"总测试数: {total}")
        print(f"✅ 通过: {passed} ({pass_rate:.1f}%)")
        print(f"❌ 失败: {failed}")
        print(f"⏭️ 跳过: {skipped}")

        if failed > 0:
            print("\n失败的测试:")
            for detail in self.test_results["details"]:
                if detail["status"] == "failed":
                    print(f"  ❌ {detail['name']}: {detail['message']}")

        print("\n" + "=" * 60)

        # 返回是否所有测试通过
        return failed == 0

    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始爬虫系统集成测试")
        print(f"时间: {datetime.now().isoformat()}")

        try:
            # 运行所有测试
            await self.test_crawler_initialization()
            await self.test_official_sources()
            await self.test_news_media()
            await self.test_academic_datasets()
            await self.test_community_platforms()
            await self.test_health_checks()

        except Exception as e:
            print(f"\n❌ 测试过程中发生严重错误: {e}")

        finally:
            # 关闭所有爬虫
            if self.manager:
                await self.manager.close_all()

        # 打印摘要
        success = self.print_summary()

        return success


async def main():
    """主函数"""
    tester = CrawlerIntegrationTest()
    success = await tester.run_all_tests()

    # 根据测试结果设置退出码
    exit(0 if success else 1)


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
