# -*- coding: utf-8 -*-
"""
Douyin data models.
"""

from pydantic import BaseModel, Field


class VideoUrlInfo(BaseModel):
    """Video URL information parsed from Douyin video URL."""
    aweme_id: str = Field(title="Video ID (aweme_id)")
    url_type: str = Field(default="normal", title="URL type: normal, modal, short")


class CreatorUrlInfo(BaseModel):
    """Creator URL information parsed from Douyin creator homepage URL."""
    sec_user_id: str = Field(title="User ID (sec_user_id)")