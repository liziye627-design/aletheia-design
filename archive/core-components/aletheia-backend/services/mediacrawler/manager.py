# -*- coding: utf-8 -*-
"""
Crawler Manager

Manages crawler lifecycle, configuration, and execution.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from loguru import logger

from services.mediacrawler.factory import CrawlerFactory
from services.mediacrawler.base_crawler import AbstractCrawler


class CrawlerStatus(str, Enum):
    """Crawler status enumeration."""
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class CrawlerTask:
    """Represents a crawler task."""
    task_id: str
    platform: str
    keywords: List[str]
    status: CrawlerStatus = CrawlerStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result_count: int = 0
    config: Dict[str, Any] = field(default_factory=dict)


class CrawlerManager:
    """
    Manages crawler lifecycle and task execution.

    Provides a unified interface for starting, stopping, and monitoring
    crawler tasks across multiple platforms.
    """

    def __init__(self, max_concurrent_tasks: int = 3):
        """
        Initialize the crawler manager.

        Args:
            max_concurrent_tasks: Maximum number of concurrent crawler tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self._tasks: Dict[str, CrawlerTask] = {}
        self._crawlers: Dict[str, AbstractCrawler] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._task_counter = 0

    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        self._task_counter += 1
        return f"task_{self._task_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    async def start_crawler(
        self,
        platform: str,
        keywords: List[str],
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a crawler task.

        Args:
            platform: Platform identifier (e.g., 'xhs', 'wb', 'zhihu')
            keywords: Search keywords
            config: Optional crawler configuration

        Returns:
            Task ID

        Raises:
            ValueError: If platform is not supported
            RuntimeError: If max concurrent tasks reached
        """
        # Validate platform
        if platform not in CrawlerFactory.list_platforms():
            raise ValueError(f"Unsupported platform: {platform}")

        # Create task
        task_id = self._generate_task_id()
        task = CrawlerTask(
            task_id=task_id,
            platform=platform,
            keywords=keywords,
            config=config or {},
        )
        self._tasks[task_id] = task

        # Start crawler in background
        asyncio.create_task(self._run_crawler(task_id))

        logger.info(f"Started crawler task {task_id} for platform {platform}")
        return task_id

    async def _run_crawler(self, task_id: str):
        """
        Run a crawler task.

        Args:
            task_id: Task identifier
        """
        task = self._tasks.get(task_id)
        if not task:
            return

        async with self._semaphore:
            task.status = CrawlerStatus.RUNNING
            task.started_at = datetime.now()

            try:
                # Create crawler instance
                crawler = CrawlerFactory.create_crawler(task.platform)
                self._crawlers[task_id] = crawler

                # Configure crawler
                if hasattr(crawler, "set_keywords"):
                    crawler.set_keywords(task.keywords)
                if hasattr(crawler, "set_config"):
                    crawler.set_config(task.config)

                # Run crawler
                await crawler.start()

                task.status = CrawlerStatus.COMPLETED
                task.completed_at = datetime.now()
                logger.info(f"Crawler task {task_id} completed successfully")

            except Exception as e:
                task.status = CrawlerStatus.ERROR
                task.error_message = str(e)
                task.completed_at = datetime.now()
                logger.error(f"Crawler task {task_id} failed: {e}")

            finally:
                self._crawlers.pop(task_id, None)

    async def stop_crawler(self, task_id: str) -> bool:
        """
        Stop a running crawler task.

        Args:
            task_id: Task identifier

        Returns:
            True if stopped successfully
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        if task.status != CrawlerStatus.RUNNING:
            return False

        task.status = CrawlerStatus.STOPPING

        # Try to stop the crawler
        crawler = self._crawlers.get(task_id)
        if crawler and hasattr(crawler, "stop"):
            try:
                await crawler.stop()
            except Exception as e:
                logger.warning(f"Error stopping crawler {task_id}: {e}")

        task.status = CrawlerStatus.COMPLETED
        task.completed_at = datetime.now()
        return True

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a crawler task.

        Args:
            task_id: Task identifier

        Returns:
            Task status dictionary or None if not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "platform": task.platform,
            "keywords": task.keywords,
            "status": task.status.value,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "result_count": task.result_count,
        }

    def list_tasks(self, status: Optional[CrawlerStatus] = None) -> List[Dict[str, Any]]:
        """
        List all crawler tasks.

        Args:
            status: Filter by status (optional)

        Returns:
            List of task status dictionaries
        """
        tasks = []
        for task in self._tasks.values():
            if status and task.status != status:
                continue
            tasks.append(self.get_task_status(task.task_id))
        return tasks

    def list_platforms(self) -> List[str]:
        """List all supported platforms."""
        return CrawlerFactory.list_platforms()


# Global manager instance
_manager: Optional[CrawlerManager] = None


def get_crawler_manager() -> CrawlerManager:
    """Get the global CrawlerManager instance."""
    global _manager
    if _manager is None:
        _manager = CrawlerManager()
    return _manager