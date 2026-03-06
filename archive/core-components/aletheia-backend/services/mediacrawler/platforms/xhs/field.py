# -*- coding: utf-8 -*-
"""
XiaoHongShu field definitions.
"""

from enum import Enum
from typing import NamedTuple


class FeedType(Enum):
    """XiaoHongShu feed types."""
    RECOMMEND = "homefeed_recommend"
    FASION = "homefeed.fashion_v3"
    FOOD = "homefeed.food_v3"
    COSMETICS = "homefeed.cosmetics_v3"
    MOVIE = "homefeed.movie_and_tv_v3"
    CAREER = "homefeed.career_v3"
    EMOTION = "homefeed.love_v3"
    HOURSE = "homefeed.household_product_v3"
    GAME = "homefeed.gaming_v3"
    TRAVEL = "homefeed.travel_v3"
    FITNESS = "homefeed.fitness_v3"


class NoteType(Enum):
    """Note types."""
    NORMAL = "normal"
    VIDEO = "video"


class SearchSortType(Enum):
    """Search sort type."""
    GENERAL = "general"
    MOST_POPULAR = "popularity_descending"
    LATEST = "time_descending"


class SearchNoteType(Enum):
    """Search note type."""
    ALL = 0
    VIDEO = 1
    IMAGE = 2


class Note(NamedTuple):
    """Note tuple."""
    note_id: str
    title: str
    desc: str
    type: str
    user: dict
    img_urls: list
    video_url: str
    tag_list: list
    at_user_list: list
    collected_count: str
    comment_count: str
    liked_count: str
    share_count: str
    time: int
    last_update_time: int