"""
ConcurrentAgentManager - 并发Agent管理器

核心功能:
1. Agent资源池管理（避免资源耗尽）
2. 并发搜索调度
3. 结果聚合
4. 错误处理和重试

优势:
- 多平台并行搜索，速度提升5-10倍
- 智能资源管理，避免系统过载
- 自动失败重试
- 实时进度监控
"""

import asyncio
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from collections import defaultdict
import traceback

from .browser_agent import BrowserAgent
from .bilibili_agent import BilibiliAgent


class AgentPool:
    """
    Agent资源池

    管理多个Agent实例，避免同时启动过多浏览器导致资源耗尽
    """

    def __init__(self, agent_class, pool_size: int = 3, **agent_kwargs):
        """
        初始化Agent池

        Args:
            agent_class: Agent类
            pool_size: 池大小（同时运行的Agent数量）
            agent_kwargs: Agent初始化参数
        """
        self.agent_class = agent_class
        self.pool_size = pool_size
        self.agent_kwargs = agent_kwargs

        # 可用Agent队列
        self.available_agents: asyncio.Queue = asyncio.Queue(maxsize=pool_size)

        # 统计
        self.stats = {
            "created": 0,
            "acquired": 0,
            "released": 0,
            "errors": 0,
        }

    async def start(self):
        """启动Agent池"""
        print(f"🚀 启动Agent池 (大小: {self.pool_size})")

        for i in range(self.pool_size):
            agent = self.agent_class(**self.agent_kwargs)
            await agent.start()
            await self.available_agents.put(agent)
            self.stats["created"] += 1
            print(f"  ✅ Agent {i + 1}/{self.pool_size} 已创建")

    async def acquire(self) -> Any:
        """获取一个可用Agent"""
        agent = await self.available_agents.get()
        self.stats["acquired"] += 1
        return agent

    async def release(self, agent: Any):
        """释放Agent回池"""
        await self.available_agents.put(agent)
        self.stats["released"] += 1

    async def close(self):
        """关闭所有Agent"""
        print(f"🛑 关闭Agent池...")

        agents = []
        while not self.available_agents.empty():
            agent = await self.available_agents.get()
            agents.append(agent)

        for agent in agents:
            try:
                await agent.close()
            except Exception as e:
                print(f"⚠️ 关闭Agent失败: {e}")

        print(f"📊 Agent池统计: {self.stats}")

    async def __aenter__(self):
        """上下文管理器"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        await self.close()


class ConcurrentAgentManager:
    """
    并发Agent管理器

    核心功能:
    1. 多平台并发搜索
    2. 智能资源管理
    3. 结果聚合
    4. 错误处理
    """

    def __init__(
        self,
        max_concurrent_agents: int = 3,
        enable_retry: bool = True,
        max_retries: int = 2,
    ):
        """
        初始化并发管理器

        Args:
            max_concurrent_agents: 最大并发Agent数量
            enable_retry: 是否启用重试
            max_retries: 最大重试次数
        """
        self.max_concurrent_agents = max_concurrent_agents
        self.enable_retry = enable_retry
        self.max_retries = max_retries

        # Agent池字典 {platform: AgentPool}
        self.agent_pools: Dict[str, AgentPool] = {}

        # 统计
        self.stats = {
            "total_searches": 0,
            "successful": 0,
            "failed": 0,
            "total_results": 0,
            "total_time": 0.0,
        }
        self.last_platform_diagnostics: Dict[str, Dict[str, Any]] = {}

    def _normalize_diagnostics(self, platform: str, diag: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(diag or {})
        reason = str(row.get("reason") or "")
        reason_low = reason.lower()
        if row.get("blocked") is True:
            reason_code = "BLOCKED"
            suggestion = "use_storage_state_or_degrade"
        elif row.get("selector_miss") is True:
            reason_code = "SELECTOR_MISS"
            suggestion = "update_selectors_or_text_fallback"
        elif row.get("empty_result") is True:
            reason_code = "EMPTY_RESULT"
            suggestion = "expand_query_or_use_fallback"
        elif "timeout" in reason_low:
            reason_code = "CRAWLER_TIMEOUT"
            suggestion = "reduce_concurrency_or_retry"
        elif "captcha" in reason_low or "verify" in reason_low:
            reason_code = "BLOCKED"
            suggestion = "use_storage_state_or_degrade"
        elif reason:
            reason_code = "ERROR"
            suggestion = "check_platform_agent"
        else:
            reason_code = "OK"
            suggestion = "none"
        row.setdefault("platform", platform)
        row["reason_code"] = reason_code
        row["suggested_action"] = suggestion
        return row

    async def register_platform(
        self, platform: str, agent_class, pool_size: int = None, **agent_kwargs
    ):
        """
        注册平台Agent

        Args:
            platform: 平台名称
            agent_class: Agent类
            pool_size: 池大小（默认使用max_concurrent_agents）
            agent_kwargs: Agent初始化参数
        """
        if pool_size is None:
            pool_size = self.max_concurrent_agents

        pool = AgentPool(agent_class=agent_class, pool_size=pool_size, **agent_kwargs)

        await pool.start()
        self.agent_pools[platform] = pool

        print(f"✅ 平台 '{platform}' 已注册 (池大小: {pool_size})")

    async def concurrent_search(
        self,
        platforms: List[str],
        keyword: str,
        limit_per_platform: int = 20,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        并发搜索多个平台

        Args:
            platforms: 平台列表
            keyword: 搜索关键词
            limit_per_platform: 每个平台返回数量
            progress_callback: 进度回调函数(platform, status, data)

        Returns:
            {platform: [results]}
        """
        print(f"\n{'=' * 70}")
        print(f"🚀 并发搜索启动")
        print(f"{'=' * 70}")
        print(f"关键词: {keyword}")
        print(f"平台数: {len(platforms)}")
        print(f"每平台数量: {limit_per_platform}")
        print(f"并发度: {self.max_concurrent_agents}")
        print(f"{'=' * 70}\n")

        start_time = datetime.now()

        # 创建并发任务
        tasks = []
        for platform in platforms:
            if platform not in self.agent_pools:
                print(f"⚠️ 平台 '{platform}' 未注册，跳过")
                continue

            task = self._search_single_platform(
                platform=platform,
                keyword=keyword,
                limit=limit_per_platform,
                progress_callback=progress_callback,
            )
            tasks.append(task)

        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 整理结果
        search_results = {}
        for i, platform in enumerate([p for p in platforms if p in self.agent_pools]):
            if isinstance(results[i], Exception):
                print(f"❌ {platform}: 搜索失败 - {results[i]}")
                search_results[platform] = []
                self.stats["failed"] += 1
            else:
                search_results[platform] = results[i]
                self.stats["successful"] += 1
                self.stats["total_results"] += len(results[i])

        # 统计
        elapsed = (datetime.now() - start_time).total_seconds()
        self.stats["total_searches"] += 1
        self.stats["total_time"] += elapsed

        # 打印摘要
        total_results = sum(len(r) for r in search_results.values())
        print(f"\n{'=' * 70}")
        print(f"📊 并发搜索完成")
        print(f"{'=' * 70}")
        print(f"✅ 成功平台: {self.stats['successful']}")
        print(f"❌ 失败平台: {self.stats['failed']}")
        print(f"📦 总结果数: {total_results}")
        print(f"⏱️  总耗时: {elapsed:.2f}秒")
        print(f"⚡ 平均速度: {total_results / elapsed:.1f} 条/秒")
        print(f"{'=' * 70}\n")

        return search_results

    async def _search_single_platform(
        self,
        platform: str,
        keyword: str,
        limit: int,
        progress_callback: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        在单个平台搜索（带重试）

        Args:
            platform: 平台名称
            keyword: 关键词
            limit: 数量
            progress_callback: 进度回调

        Returns:
            结果列表
        """
        retries = 0
        last_error = None

        while retries <= (self.max_retries if self.enable_retry else 0):
            try:
                # 通知开始
                if progress_callback:
                    await progress_callback(platform, "started", None)

                # 从池获取Agent
                pool = self.agent_pools[platform]
                agent = await pool.acquire()

                try:
                    # 执行搜索
                    print(f"🔍 [{platform}] 开始搜索 '{keyword}'...")

                    # 调用Agent的search方法
                    if hasattr(agent, "search_and_standardize"):
                        results = await agent.search_and_standardize(keyword, limit)
                    elif hasattr(agent, "search_videos"):
                        videos = await agent.search_videos(keyword, limit)
                        results = self._standardize_results(platform, videos)
                    elif hasattr(agent, "search_notes"):
                        notes = await agent.search_notes(keyword, limit)
                        results = self._standardize_results(platform, notes)
                    elif hasattr(agent, "search_questions"):
                        questions = await agent.search_questions(keyword, limit)
                        results = self._standardize_results(platform, questions)
                    elif hasattr(agent, "search_answers"):
                        answers = await agent.search_answers(keyword, limit)
                        results = self._standardize_results(platform, answers)
                    else:
                        raise NotImplementedError(f"Agent没有实现搜索方法")

                    print(f"✅ [{platform}] 成功获取 {len(results)} 条结果")

                    diag = getattr(agent, "last_diagnostics", {}) or {}
                    if len(results) == 0 and not diag.get("reason"):
                        diag = {
                            **diag,
                            "empty_result": True,
                            "reason": "empty_result:no_items",
                        }
                    self.last_platform_diagnostics[platform] = self._normalize_diagnostics(platform, diag)

                    # 通知完成
                    if progress_callback:
                        await progress_callback(platform, "completed", results)

                    return results

                finally:
                    # 释放Agent回池
                    await pool.release(agent)

            except Exception as e:
                last_error = e
                retries += 1

                if retries <= self.max_retries and self.enable_retry:
                    print(
                        f"⚠️ [{platform}] 搜索失败，重试 {retries}/{self.max_retries}..."
                    )
                    await asyncio.sleep(2 * retries)  # 指数退避
                else:
                    print(f"❌ [{platform}] 搜索失败: {e}")
                    self.last_platform_diagnostics[platform] = {
                        **self._normalize_diagnostics(
                            platform,
                            {
                                "blocked": False,
                                "selector_miss": False,
                                "empty_result": False,
                                "reason": f"error:{str(e)}",
                            },
                        )
                    }
                    if progress_callback:
                        await progress_callback(platform, "failed", str(e))
                    raise

        raise last_error

    def _standardize_results(
        self, platform: str, raw_results: List[Dict]
    ) -> List[Dict[str, Any]]:
        """标准化结果格式"""
        standardized = []

        for item in raw_results:
            standard_item = {
                "platform": platform,
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "url": item.get("url", ""),
                "author": item.get("author", ""),
                "publish_time": item.get("publish_time", ""),
                "metadata": item.get("metadata", {}),
                "entities": item.get("entities", []),
                "crawl_time": datetime.now().isoformat(),
            }
            standardized.append(standard_item)

        return standardized

    async def aggregate_results(
        self,
        search_results: Dict[str, List[Dict]],
        sort_by: str = "relevance",  # relevance, time, popularity
    ) -> List[Dict[str, Any]]:
        """
        聚合多平台结果

        Args:
            search_results: 搜索结果字典
            sort_by: 排序方式

        Returns:
            聚合并排序的结果列表
        """
        all_results = []

        for platform, results in search_results.items():
            all_results.extend(results)

        # 排序
        if sort_by == "time":
            all_results.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
        elif sort_by == "popularity":
            all_results.sort(
                key=lambda x: x.get("metadata", {}).get("views", 0), reverse=True
            )

        return all_results

    async def close_all(self):
        """关闭所有Agent池"""
        print(f"\n🛑 关闭所有Agent池...")

        for platform, pool in self.agent_pools.items():
            try:
                await pool.close()
            except Exception as e:
                print(f"⚠️ 关闭 {platform} Agent池失败: {e}")

        print(f"\n📊 总体统计:")
        print(f"  总搜索次数: {self.stats['total_searches']}")
        print(f"  成功: {self.stats['successful']}")
        print(f"  失败: {self.stats['failed']}")
        print(f"  总结果数: {self.stats['total_results']}")
        print(f"  总耗时: {self.stats['total_time']:.2f}秒")
        if self.stats["total_time"] > 0:
            print(
                f"  平均速度: {self.stats['total_results'] / self.stats['total_time']:.1f} 条/秒"
            )

    async def __aenter__(self):
        """上下文管理器"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        await self.close_all()


# 便捷函数
async def concurrent_search_all_platforms(
    keyword: str,
    platforms: List[str] = None,
    limit_per_platform: int = 20,
    max_concurrent: int = 3,
) -> Dict[str, List[Dict]]:
    """
    并发搜索所有平台的便捷函数

    Args:
        keyword: 搜索关键词
        platforms: 平台列表（默认["bilibili"]，未来扩展）
        limit_per_platform: 每平台数量
        max_concurrent: 最大并发数

    Returns:
        搜索结果字典
    """
    if platforms is None:
        platforms = ["bilibili"]  # 默认只搜索B站

    async with ConcurrentAgentManager(max_concurrent_agents=max_concurrent) as manager:
        # 注册平台
        if "bilibili" in platforms:
            await manager.register_platform(
                "bilibili",
                BilibiliAgent,
                headless=True,  # 并发时使用无头模式
            )

        # 并发搜索
        results = await manager.concurrent_search(
            platforms=platforms,
            keyword=keyword,
            limit_per_platform=limit_per_platform,
        )

        return results


# 导出
__all__ = [
    "AgentPool",
    "ConcurrentAgentManager",
    "concurrent_search_all_platforms",
]
