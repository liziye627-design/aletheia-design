# -*- coding: utf-8 -*-
"""
Douyin field definitions.
"""

from enum import Enum


class SearchChannelType(Enum):
    """Search channel type."""
    GENERAL = "aweme_general"
    VIDEO = "aweme_video_web"
    USER = "aweme_user_web"
    LIVE = "aweme_live"


class SearchSortType(Enum):
    """Search sort type."""
    GENERAL = 0
    MOST_LIKE = 1
    LATEST = 2


class PublishTimeType(Enum):
    """Publish time type."""
    UNLIMITED = 0
    ONE_DAY = 1
    ONE_WEEK = 7
    SIX_MONTH = 180