#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RSS Source Health Checker
RSS源健康检查工具

功能:
1. 测试所有RSS源的可用性
2. 记录响应时间和内容条目数
3. 生成可用的源列表
"""

import asyncio
import time
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
import yaml
import httpx
import feedparser
from pathlib import Path


@dataclass
class SourceHealth:
    """源健康状态"""
    source_id: str
    name: str
    url: str
    category: str
    is_healthy: bool = False
    response_time_ms: float = 0.0
    entry_count: int = 0
    error_message: str = ""
    last_checked: str = ""


class RSSHealthChecker:
    """RSS源健康检查器"""

    def __init__(
        self,
        sources_path: str = "config/sources.yaml",
        timeout: float = 15.0,
        max_concurrent: int = 10
    ):
        self.sources_path = sources_path
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.sources: List[Dict[str, Any]] = []
        self.results: List[SourceHealth] = []

    def load_sources(self):
        """加载源配置"""
        with open(self.sources_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self.sources = []
        for group in data.get("groups", []):
            group_id = group.get("group_id", "")
            group_name = group.get("name", "")
            for src in group.get("sources", []):
                src["group_id"] = group_id
                src["group_name"] = group_name
                self.sources.append(src)

        print(f"Loaded {len(self.sources)} sources from {self.sources_path}")

    async def check_source(
        self,
        client: httpx.AsyncClient,
        source: Dict[str, Any]
    ) -> SourceHealth:
        """检查单个源"""
        health = SourceHealth(
            source_id=source.get("source_id", ""),
            name=source.get("name", ""),
            url=source.get("url", ""),
            category=source.get("category", ""),
            last_checked=datetime.now().isoformat()
        )

        if not health.url:
            health.error_message = "No URL configured"
            return health

        # 跳过非RSS入口页面
        if health.url.endswith("/") and not health.url.endswith(".xml") and not health.url.endswith(".rss"):
            health.error_message = "Skipped: index page, not RSS feed"
            return health

        try:
            start_time = time.time()
            response = await client.get(health.url, follow_redirects=True)
            elapsed_ms = (time.time() - start_time) * 1000
            health.response_time_ms = round(elapsed_ms, 2)

            if response.status_code != 200:
                health.error_message = f"HTTP {response.status_code}"
                return health

            # 解析RSS
            feed = feedparser.parse(response.text)

            if feed.bozo and feed.bozo_exception:
                health.error_message = f"Parse error: {type(feed.bozo_exception).__name__}"
                return health

            entries = list(getattr(feed, "entries", []) or [])
            health.entry_count = len(entries)
            health.is_healthy = len(entries) > 0

            if not health.is_healthy:
                health.error_message = "No entries found"

        except httpx.TimeoutException:
            health.error_message = "Timeout"
        except httpx.ConnectError:
            health.error_message = "Connection failed"
        except Exception as e:
            health.error_message = f"Error: {type(e).__name__}"
        finally:
            health.last_checked = datetime.now().isoformat()

        return health

    async def check_all_sources(self) -> List[SourceHealth]:
        """检查所有源"""
        self.load_sources()

        timeout = httpx.Timeout(self.timeout, connect=5.0)
        sem = asyncio.Semaphore(self.max_concurrent)

        async def _worker(client: httpx.AsyncClient, source: Dict[str, Any]):
            async with sem:
                return await self.check_source(client, source)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            tasks = [_worker(client, src) for src in self.sources]
            self.results = await asyncio.gather(*tasks)

        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """生成报告"""
        healthy = [r for r in self.results if r.is_healthy]
        unhealthy = [r for r in self.results if not r.is_healthy]

        # 按响应时间排序
        healthy.sort(key=lambda x: x.response_time_ms)

        report = {
            "summary": {
                "total_sources": len(self.results),
                "healthy_count": len(healthy),
                "unhealthy_count": len(unhealthy),
                "health_rate": round(len(healthy) / max(1, len(self.results)) * 100, 2),
                "checked_at": datetime.now().isoformat()
            },
            "healthy_sources": [
                {
                    "source_id": r.source_id,
                    "name": r.name,
                    "url": r.url,
                    "category": r.category,
                    "response_time_ms": r.response_time_ms,
                    "entry_count": r.entry_count
                }
                for r in healthy
            ],
            "unhealthy_sources": [
                {
                    "source_id": r.source_id,
                    "name": r.name,
                    "url": r.url,
                    "error": r.error_message
                }
                for r in unhealthy
            ]
        }

        return report

    def save_working_sources(self, output_path: str):
        """保存可用的源配置"""
        healthy = [r for r in self.results if r.is_healthy]

        # 按原格式重构
        groups = {}
        for r in healthy:
            # 从原始源获取分组信息
            src = next((s for s in self.sources if s.get("source_id") == r.source_id), None)
            if src:
                group_id = src.get("group_id", "other")
                if group_id not in groups:
                    groups[group_id] = {
                        "group_id": group_id,
                        "name": src.get("group_name", ""),
                        "sources": []
                    }
                groups[group_id]["sources"].append({
                    "source_id": r.source_id,
                    "name": r.name,
                    "category": r.category,
                    "url": r.url,
                    "priority": src.get("priority", 5)
                })

        output = {
            "version": 1,
            "generated_at": datetime.now().isoformat(),
            "groups": list(groups.values())
        }

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(output, f, allow_unicode=True, default_flow_style=False)

        print(f"Saved {len(healthy)} working sources to {output_path}")


async def main():
    """主函数"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="RSS Source Health Checker")
    parser.add_argument(
        "--config",
        default="config/sources.yaml",
        help="Path to sources.yaml"
    )
    parser.add_argument(
        "--output",
        default="config/sources.working.yaml",
        help="Output path for working sources"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Request timeout in seconds"
    )
    args = parser.parse_args()

    checker = RSSHealthChecker(
        sources_path=args.config,
        timeout=args.timeout
    )

    print("=" * 60)
    print("RSS Source Health Check")
    print("=" * 60)

    results = await checker.check_all_sources()
    report = checker.generate_report()

    # 打印摘要
    print("\n📊 Summary:")
    print(f"  Total: {report['summary']['total_sources']}")
    print(f"  Healthy: {report['summary']['healthy_count']}")
    print(f"  Unhealthy: {report['summary']['unhealthy_count']}")
    print(f"  Health Rate: {report['summary']['health_rate']}%")

    # 打印健康的源
    print("\n✅ Healthy Sources (Top 20 by response time):")
    for src in report["healthy_sources"][:20]:
        print(f"  [{src['response_time_ms']:>6.0f}ms] {src['name']} ({src['entry_count']} entries)")

    # 打印失败的源
    print("\n❌ Unhealthy Sources:")
    for src in report["unhealthy_sources"][:20]:
        print(f"  {src['name']}: {src['error']}")

    # 保存报告
    report_path = "docs/rss-health-report.json"
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Report saved to {report_path}")

    # 保存可用的源
    checker.save_working_sources(args.output)

    return report


if __name__ == "__main__":
    asyncio.run(main())