# -*- coding: utf-8 -*-
"""
Bilibili field definitions.
"""

from enum import Enum


class SearchOrderType(Enum):
    """Search order type."""
    DEFAULT = ""  # Comprehensive sorting
    MOST_CLICK = "click"  # Most clicks
    LAST_PUBLISH = "pubdate"  # Latest published
    MOST_DANMU = "dm"  # Most danmu
    MOST_MARK = "stow"  # Most bookmarks


class CommentOrderType(Enum):
    """Comment order type."""
    DEFAULT = 0  # By popularity only
    MIXED = 1  # By popularity + time
    TIME = 2  # By time