#!/usr/bin/env python3
"""
无需认证爬虫测试脚本

测试所有无需cookies/API keys的数据源（26个）

使用方法:
    python test_no_auth_crawlers.py
"""

import asyncio
import sys
from datetime import datetime
from services.layer1_perception.crawler_manager import CrawlerManager


async def test_no_auth_sources():
    """测试所有无需认证的数据源"""

    print("=" * 70)
    print("🌐 无需认证数据源测试")
    print("=" * 70)
    print(f"时间: {datetime.now().isoformat()}")
    print(f"测试数据源: 26个（官方信源17 + 新闻媒体6 + 学术数据集3）\n")

    # 初始化管理器（不提供任何凭证）
    manager = CrawlerManager()

    results = {"total": 0, "success": 0, "failed": 0, "details": []}

    # ==================== 测试官方信源 ====================
    print("=" * 70)
    print("📰 官方信源测试 (17个)")
    print("=" * 70)

    official_sources = [
        ("xinhua", "新华网"),
        ("peoples_daily", "人民网"),
        ("china_gov", "国务院官网"),
        ("samr", "市监总局"),
        ("csrc", "证监会"),
        ("nhc", "卫健委"),
        ("mem", "应急管理部"),
        ("mps", "公安部"),
        ("supreme_court", "最高法"),
        ("supreme_procuratorate", "最高检"),
        ("who", "WHO"),
        ("cdc", "CDC"),
        ("un_news", "UN News"),
        ("world_bank", "World Bank"),
        ("sec", "SEC"),
        ("fca_uk", "FCA UK"),
        ("eu_open_data", "EU Open Data"),
    ]

    for platform, name in official_sources:
        results["total"] += 1
        try:
            print(f"\n{results['total']}. {name} ({platform})...")

            crawler = manager.get_crawler(platform)
            items = await crawler.fetch_latest(limit=3)

            if items:
                results["success"] += 1
                print(f"   ✅ 成功获取 {len(items)} 条数据")

                # 显示第一条标题
                if items:
                    title = items[0].get("title", "N/A")[:60]
                    print(f"   示例: {title}...")

                results["details"].append(
                    {
                        "platform": platform,
                        "name": name,
                        "status": "success",
                        "count": len(items),
                    }
                )
            else:
                results["failed"] += 1
                print(f"   ❌ 未获取到数据")
                results["details"].append(
                    {
                        "platform": platform,
                        "name": name,
                        "status": "no_data",
                        "count": 0,
                    }
                )

        except Exception as e:
            results["failed"] += 1
            print(f"   ❌ 失败: {str(e)[:80]}")
            results["details"].append(
                {
                    "platform": platform,
                    "name": name,
                    "status": "error",
                    "error": str(e)[:100],
                }
            )

    # ==================== 测试新闻媒体 ====================
    print("\n" + "=" * 70)
    print("📡 新闻媒体测试 (6个)")
    print("=" * 70)

    news_media = [
        ("reuters", "Reuters"),
        ("ap_news", "AP News"),
        ("bbc", "BBC"),
        ("guardian", "Guardian"),
        ("caixin", "财新网"),
        ("the_paper", "澎湃新闻"),
    ]

    for platform, name in news_media:
        results["total"] += 1
        try:
            print(f"\n{results['total']}. {name} ({platform})...")

            crawler = manager.get_crawler(platform)
            items = await crawler.fetch_latest(limit=3)

            if items:
                results["success"] += 1
                print(f"   ✅ 成功获取 {len(items)} 条新闻")

                if items:
                    title = items[0].get("title", "N/A")[:60]
                    print(f"   示例: {title}...")

                results["details"].append(
                    {
                        "platform": platform,
                        "name": name,
                        "status": "success",
                        "count": len(items),
                    }
                )
            else:
                results["failed"] += 1
                print(f"   ❌ 未获取到数据")
                results["details"].append(
                    {
                        "platform": platform,
                        "name": name,
                        "status": "no_data",
                        "count": 0,
                    }
                )

        except Exception as e:
            results["failed"] += 1
            print(f"   ❌ 失败: {str(e)[:80]}")
            results["details"].append(
                {
                    "platform": platform,
                    "name": name,
                    "status": "error",
                    "error": str(e)[:100],
                }
            )

    # ==================== 测试学术数据集 ====================
    print("\n" + "=" * 70)
    print("🎓 学术数据集测试 (3个)")
    print("=" * 70)

    # GDELT
    results["total"] += 1
    try:
        print(f"\n{results['total']}. GDELT Project...")

        gdelt = manager.get_crawler("gdelt")
        events = await gdelt.search_events(query="technology", max_records=3)

        if events:
            results["success"] += 1
            print(f"   ✅ 成功获取 {len(events)} 条事件")

            if events:
                title = events[0].get("title", "N/A")[:60]
                print(f"   示例: {title}...")

            results["details"].append(
                {
                    "platform": "gdelt",
                    "name": "GDELT Project",
                    "status": "success",
                    "count": len(events),
                }
            )
        else:
            results["failed"] += 1
            print(f"   ❌ 未获取到数据")

    except Exception as e:
        results["failed"] += 1
        print(f"   ❌ 失败: {str(e)[:80]}")
        results["details"].append(
            {
                "platform": "gdelt",
                "name": "GDELT Project",
                "status": "error",
                "error": str(e)[:100],
            }
        )

    # OpenAlex
    results["total"] += 1
    try:
        print(f"\n{results['total']}. OpenAlex...")

        openalex = manager.get_crawler("openalex")
        papers = await openalex.search_works(query="artificial intelligence", limit=3)

        if papers:
            results["success"] += 1
            print(f"   ✅ 成功获取 {len(papers)} 篇论文")

            if papers:
                title = papers[0].get("title", "N/A")[:60]
                print(f"   示例: {title}...")

            results["details"].append(
                {
                    "platform": "openalex",
                    "name": "OpenAlex",
                    "status": "success",
                    "count": len(papers),
                }
            )
        else:
            results["failed"] += 1
            print(f"   ❌ 未获取到数据")

    except Exception as e:
        results["failed"] += 1
        print(f"   ❌ 失败: {str(e)[:80]}")
        results["details"].append(
            {
                "platform": "openalex",
                "name": "OpenAlex",
                "status": "error",
                "error": str(e)[:100],
            }
        )

    # Common Crawl
    results["total"] += 1
    try:
        print(f"\n{results['total']}. Common Crawl...")

        cc = manager.get_crawler("common_crawl")
        indexes = await cc.get_available_indexes()

        if indexes:
            results["success"] += 1
            print(f"   ✅ 成功获取 {len(indexes)} 个索引")
            print(f"   最新索引: {indexes[0] if indexes else 'N/A'}")

            results["details"].append(
                {
                    "platform": "common_crawl",
                    "name": "Common Crawl",
                    "status": "success",
                    "count": len(indexes),
                }
            )
        else:
            results["failed"] += 1
            print(f"   ❌ 未获取到索引")

    except Exception as e:
        results["failed"] += 1
        print(f"   ❌ 失败: {str(e)[:80]}")
        results["details"].append(
            {
                "platform": "common_crawl",
                "name": "Common Crawl",
                "status": "error",
                "error": str(e)[:100],
            }
        )

    # ==================== 关闭连接 ====================
    await manager.close_all()

    # ==================== 打印摘要 ====================
    print("\n" + "=" * 70)
    print("📊 测试摘要")
    print("=" * 70)

    success_rate = (
        (results["success"] / results["total"] * 100) if results["total"] > 0 else 0
    )

    print(f"\n总测试数: {results['total']}")
    print(f"✅ 成功: {results['success']} ({success_rate:.1f}%)")
    print(f"❌ 失败: {results['failed']}")

    # 失败列表
    if results["failed"] > 0:
        print("\n" + "=" * 70)
        print("❌ 失败的数据源:")
        print("=" * 70)

        for detail in results["details"]:
            if detail["status"] in ["error", "no_data"]:
                print(f"\n• {detail['name']} ({detail['platform']})")
                if "error" in detail:
                    print(f"  错误: {detail['error']}")

    # 成功列表
    if results["success"] > 0:
        print("\n" + "=" * 70)
        print("✅ 可用的数据源:")
        print("=" * 70)

        for detail in results["details"]:
            if detail["status"] == "success":
                print(f"• {detail['name']:30} ({detail['count']} 条数据)")

    print("\n" + "=" * 70)

    if success_rate >= 80:
        print("🎉 测试通过！大部分数据源可正常使用")
        print("=" * 70)
        print("\n✅ 你现在可以使用这些数据源，无需任何凭证！")
        return True
    elif success_rate >= 50:
        print("⚠️ 部分数据源可用，建议检查失败原因")
        print("=" * 70)
        return False
    else:
        print("❌ 大部分数据源失败，请检查网络连接或配置")
        print("=" * 70)
        return False


async def main():
    """主函数"""
    try:
        success = await test_no_auth_sources()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
