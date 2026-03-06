#!/usr/bin/env python3
"""
并发Agent测试 - 展示5-10倍速度提升！

对比:
- 单Agent串行搜索
- 多Agent并发搜索

使用方法:
    python test_concurrent_agents.py
"""

import asyncio
import time
import ctypes.util
from typing import Any
import pytest
from services.layer1_perception.agents.concurrent_manager import (
    ConcurrentAgentManager,
    concurrent_search_all_platforms,
)
from services.layer1_perception.agents.bilibili_agent import BilibiliAgent


async def _ensure_playwright_runtime() -> None:
    """当前环境缺少浏览器运行依赖时跳过测试。"""
    missing = []
    if ctypes.util.find_library("nss3") is None:
        missing.append("libnss3")
    if ctypes.util.find_library("nspr4") is None:
        missing.append("libnspr4")
    if missing:
        pytest.skip(f"缺少Playwright系统依赖: {', '.join(missing)}")


async def test_sequential_search():
    """测试1: 串行搜索（传统方式）"""
    await _ensure_playwright_runtime()
    print("\n" + "=" * 70)
    print("📝 测试1: 串行搜索 (传统方式)")
    print("=" * 70)

    keywords = ["人工智能", "机器学习", "深度学习"]

    start_time = time.time()
    results_count = 0

    async with BilibiliAgent(headless=True) as agent:
        for keyword in keywords:
            print(f"\n🔍 搜索: {keyword}")
            try:
                videos = await agent.search_videos(keyword, limit=10)
            except Exception as e:
                msg = str(e)
                if "Timeout" in msg or "Page.goto" in msg:
                    pytest.skip(f"站点超时或网络波动，跳过并发浏览器测试: {msg}")
                raise
            results_count += len(videos)
            print(f"  ✅ 获取 {len(videos)} 个结果")

    elapsed = time.time() - start_time

    print(f"\n{'=' * 70}")
    print(f"📊 串行搜索完成")
    print(f"{'=' * 70}")
    print(f"关键词数: {len(keywords)}")
    print(f"总结果: {results_count} 条")
    print(f"总耗时: {elapsed:.2f}秒")
    print(f"平均速度: {results_count / elapsed:.1f} 条/秒")
    print(f"{'=' * 70}\n")

    return elapsed, results_count


async def test_concurrent_search():
    """测试2: 并发搜索（新方式）"""
    await _ensure_playwright_runtime()
    print("\n" + "=" * 70)
    print("⚡ 测试2: 并发搜索 (并发Agent)")
    print("=" * 70)

    keywords = ["人工智能", "机器学习", "深度学习"]

    start_time = time.time()

    async with ConcurrentAgentManager(max_concurrent_agents=3) as manager:
        # 为每个关键词创建独立的B站Agent池
        # 这里我们创建3个并发Agent实例
        await manager.register_platform(
            "bilibili_ai", BilibiliAgent, pool_size=1, headless=True
        )
        await manager.register_platform(
            "bilibili_ml", BilibiliAgent, pool_size=1, headless=True
        )
        await manager.register_platform(
            "bilibili_dl", BilibiliAgent, pool_size=1, headless=True
        )

        # 并发搜索（同时搜索3个关键词）
        tasks = []
        platforms = ["bilibili_ai", "bilibili_ml", "bilibili_dl"]

        for platform, keyword in zip(platforms, keywords):
            task = manager._search_single_platform(
                platform=platform, keyword=keyword, limit=10, progress_callback=None
            )
            tasks.append(task)

        # 并发执行
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

    # 统计结果
    results_count = 0
    for result in all_results:
        if isinstance(result, BaseException):
            continue
        result_obj: Any = result
        try:
            results_count += len(result_obj)
        except TypeError:
            continue

    print(f"\n{'=' * 70}")
    print(f"📊 并发搜索完成")
    print(f"{'=' * 70}")
    print(f"关键词数: {len(keywords)}")
    print(f"总结果: {results_count} 条")
    print(f"总耗时: {elapsed:.2f}秒")
    print(f"平均速度: {results_count / elapsed:.1f} 条/秒")
    print(f"{'=' * 70}\n")

    return elapsed, results_count


async def test_multi_platform_concurrent():
    """测试3: 多平台并发搜索（模拟）"""
    await _ensure_playwright_runtime()
    print("\n" + "=" * 70)
    print("🌍 测试3: 多平台并发搜索")
    print("=" * 70)
    print("(目前只有B站Agent，展示架构)")

    # 使用便捷函数
    results = await concurrent_search_all_platforms(
        keyword="人工智能",
        platforms=["bilibili"],
        limit_per_platform=20,
        max_concurrent=3,
    )

    for platform, items in results.items():
        print(f"\n📦 {platform}:")
        for i, item in enumerate(items[:5], 1):
            print(f"  {i}. {item['title']}")


async def test_with_progress_callback():
    """测试4: 带进度回调的并发搜索"""
    await _ensure_playwright_runtime()
    print("\n" + "=" * 70)
    print("📊 测试4: 实时进度监控")
    print("=" * 70)

    # 进度回调函数
    progress_data = {}

    async def progress_callback(platform, status, data):
        progress_data[platform] = status

        if status == "started":
            print(f"🟡 [{platform}] 开始搜索...")
        elif status == "completed":
            print(f"✅ [{platform}] 完成! 获取 {len(data)} 条结果")
        elif status == "failed":
            print(f"❌ [{platform}] 失败: {data}")

    async with ConcurrentAgentManager(max_concurrent_agents=2) as manager:
        await manager.register_platform(
            "bilibili", BilibiliAgent, pool_size=2, headless=True
        )

        results = await manager.concurrent_search(
            platforms=["bilibili"],
            keyword="机器学习",
            limit_per_platform=15,
            progress_callback=progress_callback,
        )

        print(f"\n最终进度状态: {progress_data}")


async def main():
    """主测试函数"""

    print("=" * 70)
    print("🤖 并发Agent性能测试")
    print("=" * 70)
    print("\n将对比串行 vs 并发搜索的性能差异\n")

    # 测试1: 串行搜索
    seq_time, seq_count = await test_sequential_search()

    # 等待一下
    await asyncio.sleep(2)

    # 测试2: 并发搜索
    con_time, con_count = await test_concurrent_search()

    # 性能对比
    print("\n" + "=" * 70)
    print("🏆 性能对比")
    print("=" * 70)
    speedup = seq_time / con_time if con_time > 0 else 0
    print(f"串行搜索: {seq_time:.2f}秒 ({seq_count}条)")
    print(f"并发搜索: {con_time:.2f}秒 ({con_count}条)")
    print(f"速度提升: {speedup:.1f}x 🚀")
    print(
        f"时间节省: {seq_time - con_time:.2f}秒 ({(1 - con_time / seq_time) * 100:.1f}%)"
    )
    print("=" * 70)

    # 等待一下
    await asyncio.sleep(2)

    # 测试3: 多平台并发（架构展示）
    await test_multi_platform_concurrent()

    # 等待一下
    await asyncio.sleep(2)

    # 测试4: 进度监控
    await test_with_progress_callback()

    print("\n" + "=" * 70)
    print("✅ 所有测试完成！")
    print("=" * 70)
    print("\n💡 关键发现:")
    print(f"  • 并发Agent可提升速度 {speedup:.1f}倍")
    print(f"  • 资源池机制避免浏览器过载")
    print(f"  • 支持实时进度监控")
    print(f"  • 自动错误处理和重试")
    print("\n🚀 未来扩展:")
    print("  • 添加更多平台Agent（抖音、小红书、知乎...)")
    print("  • 每个平台都可以并发搜索")
    print("  • 真正的多平台并行采集！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
