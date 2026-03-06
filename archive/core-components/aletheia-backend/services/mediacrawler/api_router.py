# -*- coding: utf-8 -*-
"""
MediaCrawler API Router

Provides REST API endpoints for crawler management.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.mediacrawler.manager import (
    CrawlerManager,
    CrawlerStatus,
    get_crawler_manager,
)

router = APIRouter()


# Request/Response Models
class StartCrawlerRequest(BaseModel):
    """Request model for starting a crawler."""
    platform: str = Field(..., description="Platform identifier (e.g., 'xhs', 'wb', 'zhihu')")
    keywords: List[str] = Field(..., description="Search keywords")
    headless: bool = Field(True, description="Run in headless mode")
    enable_comments: bool = Field(False, description="Enable comment crawling")


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    task_id: str
    platform: str
    keywords: List[str]
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    result_count: int = 0


class PlatformInfo(BaseModel):
    """Platform information model."""
    id: str
    name: str
    supported: bool = True


# API Endpoints
@router.get("/platforms", response_model=List[PlatformInfo])
async def list_platforms():
    """
    List all supported platforms.

    Returns a list of platform identifiers and their display names.
    """
    manager = get_crawler_manager()
    platform_ids = manager.list_platforms()

    platform_names = {
        "xhs": "XiaoHongShu (小红书)",
        "dy": "Douyin (抖音)",
        "bili": "Bilibili (B站)",
        "wb": "Weibo (微博)",
        "zhihu": "Zhihu (知乎)",
        "ks": "Kuaishou (快手)",
        "tieba": "Tieba (贴吧)",
    }

    platforms = []
    for pid in platform_ids:
        platforms.append(PlatformInfo(
            id=pid,
            name=platform_names.get(pid, pid),
            supported=True,
        ))

    # Add all known platforms even if not yet registered
    for pid, name in platform_names.items():
        if pid not in platform_ids:
            platforms.append(PlatformInfo(
                id=pid,
                name=name,
                supported=False,
            ))

    return platforms


@router.post("/start", response_model=TaskStatusResponse)
async def start_crawler(request: StartCrawlerRequest):
    """
    Start a crawler task.

    Initiates a crawler for the specified platform with the given keywords.

    Args:
        request: StartCrawlerRequest with platform, keywords, and options

    Returns:
        Task status information

    Raises:
        HTTPException: If platform is not supported or task creation fails
    """
    manager = get_crawler_manager()

    try:
        task_id = await manager.start_crawler(
            platform=request.platform,
            keywords=request.keywords,
            config={
                "headless": request.headless,
                "enable_comments": request.enable_comments,
            },
        )

        status = manager.get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=500, detail="Failed to create task")

        return TaskStatusResponse(**status)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crawler: {e}")


@router.post("/stop/{task_id}", response_model=TaskStatusResponse)
async def stop_crawler(task_id: str):
    """
    Stop a running crawler task.

    Args:
        task_id: Task identifier

    Returns:
        Updated task status

    Raises:
        HTTPException: If task not found or stop fails
    """
    manager = get_crawler_manager()

    success = await manager.stop_crawler(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or not running")

    status = manager.get_task_status(task_id)
    return TaskStatusResponse(**status)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a crawler task.

    Args:
        task_id: Task identifier

    Returns:
        Task status information

    Raises:
        HTTPException: If task not found
    """
    manager = get_crawler_manager()

    status = manager.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(**status)


@router.get("/tasks", response_model=List[TaskStatusResponse])
async def list_tasks(
    status: Optional[str] = None,
):
    """
    List all crawler tasks.

    Args:
        status: Filter by status (optional)

    Returns:
        List of task status information
    """
    manager = get_crawler_manager()

    filter_status = None
    if status:
        try:
            filter_status = CrawlerStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    tasks = manager.list_tasks(status=filter_status)
    return [TaskStatusResponse(**t) for t in tasks]


@router.get("/data/files")
async def list_data_files():
    """
    List available data files from crawler runs.

    Returns a list of data files that have been generated by crawler tasks.
    """
    import os
    from pathlib import Path

    # Look for data files in the standard output directory
    data_dir = Path("data/crawler")
    if not data_dir.exists():
        return {"files": []}

    files = []
    for file_path in data_dir.glob("**/*.json"):
        stat = file_path.stat()
        files.append({
            "name": file_path.name,
            "path": str(file_path.relative_to(data_dir)),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })

    return {"files": files}