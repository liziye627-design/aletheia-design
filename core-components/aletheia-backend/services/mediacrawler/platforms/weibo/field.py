# -*- coding: utf-8 -*-
"""
Weibo field definitions.
"""

from enum import Enum


class SearchType(Enum):
    """Weibo search type."""
    DEFAULT = 0
    REAL_TIME = 1
    POPULAR = 2
    VIDEO = 3