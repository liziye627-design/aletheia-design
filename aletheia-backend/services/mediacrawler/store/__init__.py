# -*- coding: utf-8 -*-
"""
Storage Module

Contains storage implementations for different backends.
"""

from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from .base import AbstractStore
from .json_store import JsonStore
from .csv_store import CsvStore


class BaseStore(ABC):
    """Abstract base class for storage implementations."""

    @abstractmethod
    async def store_content(self, content_item: Dict[str, Any]) -> bool:
        """Store a content item."""
        pass

    @abstractmethod
    async def store_comment(self, comment_item: Dict[str, Any]) -> bool:
        """Store a comment item."""
        pass

    @abstractmethod
    async def get_contents(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get stored contents."""
        pass

    @abstractmethod
    async def get_comments(self, content_id: str) -> List[Dict[str, Any]]:
        """Get comments for a content item."""
        pass


class MemoryStore(BaseStore):
    """In-memory storage implementation for testing."""

    def __init__(self):
        self._contents: Dict[str, Dict[str, Any]] = {}
        self._comments: Dict[str, List[Dict[str, Any]]] = {}

    async def store_content(self, content_item: Dict[str, Any]) -> bool:
        content_id = content_item.get("id") or content_item.get("note_id") or str(len(self._contents))
        self._contents[content_id] = content_item
        return True

    async def store_comment(self, comment_item: Dict[str, Any]) -> bool:
        content_id = comment_item.get("content_id") or comment_item.get("note_id")
        if content_id not in self._comments:
            self._comments[content_id] = []
        self._comments[content_id].append(comment_item)
        return True

    async def get_contents(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._contents.values())[:limit]

    async def get_comments(self, content_id: str) -> List[Dict[str, Any]]:
        return self._comments.get(content_id, [])


# Storage factory
_stores: Dict[str, BaseStore] = {}


def get_store(platform: str, store_type: str = "memory", output_dir: str = "data") -> BaseStore:
    """
    Get or create a store for a platform.

    Args:
        platform: Platform name (xhs, douyin, bilibili, etc.)
        store_type: Type of store (memory, json, csv)
        output_dir: Output directory for file-based stores
    """
    store_key = f"{platform}_{store_type}"
    if store_key not in _stores:
        if store_type == "json":
            _stores[store_key] = JsonStore(output_dir=output_dir, platform=platform)
        elif store_type == "csv":
            _stores[store_key] = CsvStore(output_dir=output_dir, platform=platform)
        else:
            _stores[store_key] = MemoryStore()
    return _stores[store_key]


__all__ = [
    "AbstractStore",
    "BaseStore",
    "MemoryStore",
    "JsonStore",
    "CsvStore",
    "get_store"
]