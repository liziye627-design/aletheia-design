# -*- coding: utf-8 -*-
"""
Tieba field definitions.
"""

from enum import Enum


class SearchType(Enum):
    """Tieba search type."""
    ALL = "all"
    THREAD = "thread"
    POST = "post"


class SortType(Enum):
    """Sort type."""
    DEFAULT = 0
    TIME_DESC = 1
    HOT = 2