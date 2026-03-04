"""
Evidence Version Management Module.
证据版本链管理模块

Implements content version tracking for:
- Detecting updates and corrections
- Maintaining version history
- Generating diff summaries

Author: Aletheia Team
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import difflib
import re
import structlog

logger = structlog.get_logger()


class ChangeType(str, Enum):
    """Types of content changes"""
    CREATED = "created"
    UPDATED = "updated"
    CORRECTED = "corrected"
    RETRACTED = "retracted"
    DELETED = "deleted"
    RESTORED = "restored"


@dataclass
class ContentDiff:
    """
    Content difference between two versions.
    两个版本之间的内容差异
    """
    title_changed: bool = False
    title_old: Optional[str] = None
    title_new: Optional[str] = None

    content_similarity: float = 0.0  # 0.0-1.0
    content_added_chars: int = 0
    content_removed_chars: int = 0
    content_added_lines: int = 0
    content_removed_lines: int = 0

    # Detected changes
    detected_changes: List[str] = field(default_factory=list)

    # Detected signals
    has_correction_notice: bool = False
    has_retraction_notice: bool = False
    has_update_notice: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title_changed": self.title_changed,
            "title_old": self.title_old,
            "title_new": self.title_new,
            "content_similarity": self.content_similarity,
            "content_added_chars": self.content_added_chars,
            "content_removed_chars": self.content_removed_chars,
            "content_added_lines": self.content_added_lines,
            "content_removed_lines": self.content_removed_lines,
            "detected_changes": self.detected_changes,
            "has_correction_notice": self.has_correction_notice,
            "has_retraction_notice": self.has_retraction_notice,
            "has_update_notice": self.has_update_notice,
        }


@dataclass
class VersionRecord:
    """
    Record of a single version of an evidence document.
    证据文档的单个版本记录
    """
    version_id: str  # Unique version identifier
    doc_id: str  # Stable document ID
    captured_at: datetime

    # Chain links
    prev_version_id: Optional[str] = None
    next_version_id: Optional[str] = None

    # Content hashes
    url_hash: str = ""
    content_hash: str = ""

    # Snapshot reference
    snapshot_uri: Optional[str] = None

    # Content at this version
    title: Optional[str] = None
    content_text: Optional[str] = None

    # Changes from previous version
    diff: Optional[ContentDiff] = None
    change_type: ChangeType = ChangeType.CREATED

    # Metadata
    crawl_source: str = ""
    http_status: int = 200
    content_length: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "doc_id": self.doc_id,
            "captured_at": self.captured_at.isoformat(),
            "prev_version_id": self.prev_version_id,
            "next_version_id": self.next_version_id,
            "url_hash": self.url_hash,
            "content_hash": self.content_hash,
            "snapshot_uri": self.snapshot_uri,
            "title": self.title,
            "change_type": self.change_type.value,
            "diff": self.diff.to_dict() if self.diff else None,
            "crawl_source": self.crawl_source,
            "http_status": self.http_status,
            "content_length": self.content_length,
        }


class VersionManager:
    """
    Manages evidence document version history.
    证据文档版本历史管理器
    """

    # Keywords indicating corrections/retractions
    CORRECTION_KEYWORDS = [
        "更正", "勘误", "纠正", "修正",
        "更正声明", "勘误声明",
        "correction", "corrected",
    ]

    RETRACTION_KEYWORDS = [
        "撤回", "撤销", "删除", "撤稿",
        "撤回声明", "撤销声明",
        "retraction", "retracted", "withdrawn",
    ]

    UPDATE_KEYWORDS = [
        "更新", "修订", "修改",
        "update", "updated", "revised",
    ]

    def __init__(self):
        # In-memory storage (replace with database in production)
        self._versions: Dict[str, VersionRecord] = {}  # version_id -> VersionRecord
        self._doc_versions: Dict[str, List[str]] = {}  # doc_id -> [version_ids]
        self._latest_version: Dict[str, str] = {}  # doc_id -> latest_version_id

    def create_version(
        self,
        doc_id: str,
        title: Optional[str],
        content_text: Optional[str],
        url_hash: str,
        content_hash: str,
        snapshot_uri: Optional[str] = None,
        crawl_source: str = "",
        http_status: int = 200,
    ) -> VersionRecord:
        """
        Create a new version of an evidence document.
        创建证据文档的新版本

        Args:
            doc_id: Stable document ID
            title: Document title
            content_text: Document content
            url_hash: Hash of normalized URL
            content_hash: Hash of normalized content
            snapshot_uri: URI to raw snapshot
            crawl_source: Source of the crawl
            http_status: HTTP status code

        Returns:
            VersionRecord for the new version
        """
        # Generate version ID
        version_id = self._generate_version_id(doc_id)

        # Get previous version
        prev_version_id = self._latest_version.get(doc_id)

        # Create version record
        version = VersionRecord(
            version_id=version_id,
            doc_id=doc_id,
            captured_at=datetime.utcnow(),
            prev_version_id=prev_version_id,
            url_hash=url_hash,
            content_hash=content_hash,
            snapshot_uri=snapshot_uri,
            title=title,
            content_text=content_text,
            crawl_source=crawl_source,
            http_status=http_status,
            content_length=len(content_text) if content_text else 0,
        )

        # Calculate diff from previous version
        if prev_version_id:
            prev_version = self._versions.get(prev_version_id)
            if prev_version:
                version.diff = self._calculate_diff(
                    prev_version.title,
                    prev_version.content_text,
                    title,
                    content_text,
                )
                version.change_type = self._determine_change_type(version.diff, http_status)

                # Update previous version's next link
                prev_version.next_version_id = version_id
        else:
            # First version
            version.change_type = ChangeType.CREATED

        # Store version
        self._versions[version_id] = version

        # Update doc versions index
        if doc_id not in self._doc_versions:
            self._doc_versions[doc_id] = []
        self._doc_versions[doc_id].append(version_id)

        # Update latest version pointer
        self._latest_version[doc_id] = version_id

        logger.info(
            "version_created",
            doc_id=doc_id,
            version_id=version_id,
            change_type=version.change_type.value,
        )

        return version

    def get_version(self, version_id: str) -> Optional[VersionRecord]:
        """Get a specific version by ID"""
        return self._versions.get(version_id)

    def get_latest_version(self, doc_id: str) -> Optional[VersionRecord]:
        """Get the latest version of a document"""
        version_id = self._latest_version.get(doc_id)
        if version_id:
            return self._versions.get(version_id)
        return None

    def get_version_history(self, doc_id: str) -> List[VersionRecord]:
        """
        Get full version history for a document.
        获取文档的完整版本历史
        """
        version_ids = self._doc_versions.get(doc_id, [])
        return [self._versions[vid] for vid in version_ids if vid in self._versions]

    def get_version_chain(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Get version chain with summaries.
        获取带摘要的版本链
        """
        history = self.get_version_history(doc_id)
        chain = []

        for version in history:
            summary = {
                "version_id": version.version_id,
                "captured_at": version.captured_at.isoformat(),
                "change_type": version.change_type.value,
                "title": version.title,
                "content_length": version.content_length,
            }

            if version.diff:
                summary["diff_summary"] = {
                    "title_changed": version.diff.title_changed,
                    "content_similarity": version.diff.content_similarity,
                    "detected_changes": version.diff.detected_changes,
                }

            chain.append(summary)

        return chain

    def detect_update_signals(
        self,
        content: str,
        title: str = "",
    ) -> Dict[str, bool]:
        """
        Detect update signals in content.
        检测内容中的更新信号
        """
        combined_text = f"{title} {content}".lower()

        return {
            "has_correction_notice": self._contains_keywords(combined_text, self.CORRECTION_KEYWORDS),
            "has_retraction_notice": self._contains_keywords(combined_text, self.RETRACTION_KEYWORDS),
            "has_update_notice": self._contains_keywords(combined_text, self.UPDATE_KEYWORDS),
        }

    def _generate_version_id(self, doc_id: str) -> str:
        """Generate unique version ID"""
        timestamp = datetime.utcnow().isoformat()
        unique_str = f"{doc_id}:{timestamp}"
        hash_suffix = hashlib.sha256(unique_str.encode()).hexdigest()[:8]
        return f"{doc_id}:v{hash_suffix}"

    def _calculate_diff(
        self,
        old_title: Optional[str],
        old_content: Optional[str],
        new_title: Optional[str],
        new_content: Optional[str],
    ) -> ContentDiff:
        """Calculate difference between two versions"""
        diff = ContentDiff()

        # Title diff
        if old_title != new_title:
            diff.title_changed = True
            diff.title_old = old_title
            diff.title_new = new_title
            diff.detected_changes.append("title_changed")

        # Content diff
        if old_content and new_content:
            # Calculate similarity
            similarity = self._calculate_similarity(old_content, new_content)
            diff.content_similarity = similarity

            # Calculate character changes
            old_len = len(old_content)
            new_len = len(new_content)

            if new_len > old_len:
                diff.content_added_chars = new_len - old_len
                diff.detected_changes.append("content_added")
            elif new_len < old_len:
                diff.content_removed_chars = old_len - new_len
                diff.detected_changes.append("content_removed")

            # Calculate line changes
            old_lines = old_content.split("\n")
            new_lines = new_content.split("\n")

            matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
            for opcode in matcher.get_opcodes():
                tag, i1, i2, j1, j2 = opcode
                if tag == "insert":
                    diff.content_added_lines += j2 - j1
                elif tag == "delete":
                    diff.content_removed_lines += i2 - i1

        # Detect special signals in new content
        combined_new = f"{new_title or ''} {new_content or ''}"
        signals = self.detect_update_signals(combined_new)

        diff.has_correction_notice = signals["has_correction_notice"]
        diff.has_retraction_notice = signals["has_retraction_notice"]
        diff.has_update_notice = signals["has_update_notice"]

        if diff.has_correction_notice:
            diff.detected_changes.append("correction_notice")
        if diff.has_retraction_notice:
            diff.detected_changes.append("retraction_notice")
        if diff.has_update_notice:
            diff.detected_changes.append("update_notice")

        return diff

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using difflib"""
        if not text1 or not text2:
            return 0.0

        # Use SequenceMatcher for similarity
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return round(matcher.ratio(), 4)

    def _determine_change_type(
        self,
        diff: ContentDiff,
        http_status: int,
    ) -> ChangeType:
        """Determine the type of change"""
        # Check for deletion
        if http_status == 404 or http_status == 410:
            return ChangeType.DELETED

        # Check for retraction
        if diff.has_retraction_notice:
            return ChangeType.RETRACTED

        # Check for correction
        if diff.has_correction_notice:
            return ChangeType.CORRECTED

        # Check for significant update
        if diff.title_changed or diff.content_similarity < 0.95:
            return ChangeType.UPDATED

        # Minor or no change
        return ChangeType.UPDATED

    def _contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords"""
        text_lower = text.lower()
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get version manager statistics"""
        total_versions = len(self._versions)
        total_docs = len(self._doc_versions)

        # Count change types
        change_counts = {}
        for version in self._versions.values():
            ct = version.change_type.value
            change_counts[ct] = change_counts.get(ct, 0) + 1

        return {
            "total_documents": total_docs,
            "total_versions": total_versions,
            "versions_per_doc_avg": total_versions / total_docs if total_docs > 0 else 0,
            "change_type_distribution": change_counts,
        }


class VersionComparator:
    """
    Compare versions of evidence documents.
    证据文档版本比较器
    """

    def compare(
        self,
        version1: VersionRecord,
        version2: VersionRecord,
    ) -> Dict[str, Any]:
        """
        Compare two versions of a document.
        比较文档的两个版本
        """
        result = {
            "version1_id": version1.version_id,
            "version2_id": version2.version_id,
            "time_diff_seconds": (
                version2.captured_at - version1.captured_at
            ).total_seconds(),
        }

        # Title comparison
        if version1.title != version2.title:
            result["title_diff"] = {
                "old": version1.title,
                "new": version2.title,
            }

        # Content comparison
        if version1.content_text and version2.content_text:
            similarity = self._calculate_similarity(
                version1.content_text,
                version2.content_text,
            )
            result["content_similarity"] = similarity

            # Generate unified diff
            diff = self._generate_unified_diff(
                version1.content_text,
                version2.content_text,
            )
            result["diff_lines"] = len(diff.split("\n"))

        return result

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity"""
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return round(matcher.ratio(), 4)

    def _generate_unified_diff(
        self,
        text1: str,
        text2: str,
        context_lines: int = 3,
    ) -> str:
        """Generate unified diff"""
        lines1 = text1.splitlines(keepends=True)
        lines2 = text2.splitlines(keepends=True)

        diff = difflib.unified_diff(
            lines1,
            lines2,
            fromfile="version1",
            tofile="version2",
            n=context_lines,
        )

        return "".join(diff)


# Convenience functions
def create_version(
    doc_id: str,
    title: Optional[str],
    content_text: Optional[str],
    url_hash: str = "",
    content_hash: str = "",
) -> VersionRecord:
    """Convenience function to create a version"""
    manager = VersionManager()
    return manager.create_version(
        doc_id=doc_id,
        title=title,
        content_text=content_text,
        url_hash=url_hash,
        content_hash=content_hash,
    )


def detect_updates(content: str, title: str = "") -> Dict[str, bool]:
    """Convenience function to detect update signals"""
    manager = VersionManager()
    return manager.detect_update_signals(content, title)