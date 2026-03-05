# -*- coding: utf-8 -*-
"""
Kuaishou field definitions.
"""

from enum import Enum


class SearchType(Enum):
    """Kuaishou search type."""
    VIDEO = "video"
    USER = "user"
    TAG = "tag"