# -*- coding: utf-8 -*-
"""
JSON Store Implementation.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import AbstractStore


class JsonStore(AbstractStore):
    """Store data in JSON files."""

    def __init__(
        self,
        output_dir: str = "data",
        platform: str = "unknown",
    ):
        self.output_dir = Path(output_dir)
        self.platform = platform
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Ensure output directories exist."""
        dirs = [
            self.output_dir,
            self.output_dir / self.platform / "contents",
            self.output_dir / self.platform / "comments",
            self.output_dir / self.platform / "creators",
            self.output_dir / self.platform / "media",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _get_content_file(self, content_id: str) -> Path:
        """Get path for content file."""
        return self.output_dir / self.platform / "contents" / f"{content_id}.json"

    def _get_comments_file(self, content_id: str) -> Path:
        """Get path for comments file."""
        return self.output_dir / self.platform / "comments" / f"{content_id}_comments.json"

    def _get_creator_file(self, creator_id: str) -> Path:
        """Get path for creator file."""
        return self.output_dir / self.platform / "creators" / f"{creator_id}.json"

    async def store_content(self, content_item: Dict[str, Any]) -> bool:
        """Store content data to JSON file."""
        try:
            content_id = content_item.get("note_id") or content_item.get("aweme_id") or content_item.get("video_id") or content_item.get("content_id") or content_item.get("tiezi_id") or "unknown"
            file_path = self._get_content_file(str(content_id))

            # Add timestamp
            content_item["stored_at"] = datetime.now().isoformat()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content_item, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[JsonStore.store_content] Error: {e}")
            return False

    async def store_comment(self, comment_item: Dict[str, Any]) -> bool:
        """Store comment data to JSON file."""
        try:
            content_id = comment_item.get("content_id", "unknown")
            file_path = self._get_comments_file(content_id)

            # Load existing comments or create new list
            comments = []
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    comments = json.load(f)

            # Add timestamp
            comment_item["stored_at"] = datetime.now().isoformat()
            comments.append(comment_item)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(comments, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[JsonStore.store_comment] Error: {e}")
            return False

    async def store_creator(self, creator: Dict[str, Any]) -> bool:
        """Store creator data to JSON file."""
        try:
            creator_id = creator.get("user_id") or creator.get("creator_id") or creator.get("id") or "unknown"
            file_path = self._get_creator_file(str(creator_id))

            # Add timestamp
            creator["stored_at"] = datetime.now().isoformat()

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(creator, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[JsonStore.store_creator] Error: {e}")
            return False

    async def store_media(
        self,
        content_id: str,
        media_data: bytes,
        media_type: str,
        filename: str
    ) -> bool:
        """Store media file."""
        try:
            media_dir = self.output_dir / self.platform / "media" / content_id
            media_dir.mkdir(parents=True, exist_ok=True)

            file_path = media_dir / filename
            with open(file_path, "wb") as f:
                f.write(media_data)

            return True
        except Exception as e:
            print(f"[JsonStore.store_media] Error: {e}")
            return False

    async def batch_store_comments(
        self,
        content_id: str,
        comments: List[Dict[str, Any]]
    ) -> int:
        """Batch store comments to JSON file."""
        try:
            file_path = self._get_comments_file(content_id)

            # Load existing comments or create new list
            existing = []
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)

            # Add timestamps and content_id
            timestamp = datetime.now().isoformat()
            for comment in comments:
                comment["content_id"] = content_id
                comment["stored_at"] = timestamp

            existing.extend(comments)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            return len(comments)
        except Exception as e:
            print(f"[JsonStore.batch_store_comments] Error: {e}")
            return 0