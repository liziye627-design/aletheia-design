#!/usr/bin/env python3
"""
测试BilibiliAgent - 无需cookies的B站爬虫

完全模拟真实用户行为，无需任何认证！

使用方法:
    python test_bilibili_agent.py
"""

import asyncio
from services.layer1_perception.agents.bilibili_agent import BilibiliAgent


async def main():
    """测试B站Agent"""

    print("=" * 70)
    print("🤖 B站Agent测试 - 无需Cookies")
    print("=" * 70)

    # 初始化Agent（可以看到浏览器）
    async with BilibiliAgent(headless=False) as agent:
        # 测试1: 搜索视频
        print("\n【测试1】搜索视频...")
        videos = await agent.search_videos(keyword="人工智能", limit=10)

        print(f"\n找到 {len(videos)} 个视频:")
        for i, video in enumerate(videos[:5], 1):
            print(f"{i}. {video['title']}")
            print(f"   UP主: {video['author']} | 播放: {video['views']}")
            print(f"   链接: {video['url']}\n")

        # 测试2: 获取热门视频
        print("\n【测试2】获取热门视频...")
        hot_videos = await agent.get_hot_videos(limit=5)

        print(f"\n热门视频 ({len(hot_videos)} 个):")
        for i, video in enumerate(hot_videos, 1):
            print(f"{i}. {video['title']}")
            print(f"   UP主: {video['author']} | 播放: {video['views']}\n")

        # 测试3: 获取视频详情
        if videos:
            print("\n【测试3】获取视频详情...")
            first_video_url = videos[0]["url"]
            detail = await agent.get_video_detail(first_video_url)

            print(f"\n视频详情:")
            print(f"标题: {detail.get('title', 'N/A')}")
            print(f"UP主: {detail.get('author', 'N/A')}")
            print(f"播放: {detail.get('views', 0)}")
            print(f"弹幕: {detail.get('danmaku_count', 0)}")
            print(f"发布: {detail.get('publish_date', 'N/A')}")
            print(f"标签: {', '.join(detail.get('tags', []))}")
            print(f"简介: {detail.get('description', 'N/A')[:100]}...")

        # 测试4: 标准化输出
        print("\n【测试4】标准化输出格式...")
        standardized = await agent.search_and_standardize(keyword="机器学习", limit=5)

        print(f"\n标准化数据 ({len(standardized)} 个):")
        for item in standardized:
            print(f"• {item['title']}")
            print(f"  平台: {item['platform']} | 作者: {item['author']}")
            print(f"  播放: {item['metadata']['views']}\n")

    print("=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
