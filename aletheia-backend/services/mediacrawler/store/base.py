# -*- coding: utf-8 -*-
"""
MediaCrawler Base Store.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AbstractStore(ABC):
    """Abstract base class for data storage."""

    @abstractmethod
    async def store_content(self, content_item: Dict[str, Any]) -> bool:
        """
        Store content data.

        Args:
            content_item: Content data to store

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def store_comment(self, comment_item: Dict[str, Any]) -> bool:
        """
        Store comment data.

        Args:
            comment_item: Comment data to store

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def store_creator(self, creator: Dict[str, Any]) -> bool:
        """
        Store creator data.

        Args:
            creator: Creator data to store

        Returns:
            True if successful, False otherwise
        """
        pass

    async def batch_store_comments(
        self,
        content_id: str,
        comments: List[Dict[str, Any]]
    ) -> int:
        """
        Batch store comments.

        Args:
            content_id: ID of the content
            comments: List of comments to store

        Returns:
            Number of successfully stored comments
        """
        count = 0
        for comment in comments:
            comment["content_id"] = content_id
            if await self.store_comment(comment):
                count += 1
        return count

    async def store_media(
        self,
        content_id: str,
        media_data: bytes,
        media_type: str,
        filename: str
    ) -> bool:
        """
        Store media file.

        Args:
            content_id: ID of the content
            media_data: Media file data
            media_type: Type of media (image, video)
            filename: Filename to save as

        Returns:
            True if successful, False otherwise
        """
        # Default implementation - override in subclasses
        return False