# -*- coding: utf-8 -*-
"""
CSV Store Implementation.
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import AbstractStore


class CsvStore(AbstractStore):
    """Store data in CSV files."""

    def __init__(
        self,
        output_dir: str = "data",
        platform: str = "unknown",
    ):
        self.output_dir = Path(output_dir)
        self.platform = platform
        self._ensure_dirs()
        self._content_fields = [
            "note_id", "aweme_id", "video_id", "content_id", "tiezi_id",
            "title", "desc", "content", "author", "created_at", "stored_at"
        ]
        self._comment_fields = [
            "comment_id", "content_id", "user_id", "user_name", "content",
            "like_count", "created_at", "stored_at"
        ]
        self._creator_fields = [
            "user_id", "creator_id", "id", "name", "desc", "fans_count",
            "follow_count", "created_at", "stored_at"
        ]

    def _ensure_dirs(self):
        """Ensure output directories exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_content_file(self) -> Path:
        """Get path for content CSV file."""
        return self.output_dir / f"{self.platform}_contents.csv"

    def _get_comments_file(self) -> Path:
        """Get path for comments CSV file."""
        return self.output_dir / f"{self.platform}_comments.csv"

    def _get_creators_file(self) -> Path:
        """Get path for creators CSV file."""
        return self.output_dir / f"{self.platform}_creators.csv"

    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '_') -> Dict:
        """Flatten nested dictionary."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            elif isinstance(v, list):
                items.append((new_key, json.dumps(v, ensure_ascii=False)))
            else:
                items.append((new_key, v))
        return dict(items)

    def _write_csv_row(self, file_path: Path, row: Dict, fieldnames: List[str]):
        """Write a row to CSV file."""
        file_exists = file_path.exists()

        # Flatten the row
        flat_row = self._flatten_dict(row)

        with open(file_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(flat_row)

    async def store_content(self, content_item: Dict[str, Any]) -> bool:
        """Store content data to CSV file."""
        try:
            content_item["stored_at"] = datetime.now().isoformat()
            self._write_csv_row(self._get_content_file(), content_item, self._content_fields)
            return True
        except Exception as e:
            print(f"[CsvStore.store_content] Error: {e}")
            return False

    async def store_comment(self, comment_item: Dict[str, Any]) -> bool:
        """Store comment data to CSV file."""
        try:
            comment_item["stored_at"] = datetime.now().isoformat()
            self._write_csv_row(self._get_comments_file(), comment_item, self._comment_fields)
            return True
        except Exception as e:
            print(f"[CsvStore.store_comment] Error: {e}")
            return False

    async def store_creator(self, creator: Dict[str, Any]) -> bool:
        """Store creator data to CSV file."""
        try:
            creator["stored_at"] = datetime.now().isoformat()
            self._write_csv_row(self._get_creators_file(), creator, self._creator_fields)
            return True
        except Exception as e:
            print(f"[CsvStore.store_creator] Error: {e}")
            return False


import json