# -*- coding: utf-8 -*-
"""
Bilibili data models.
"""

from pydantic import BaseModel, Field


class VideoUrlInfo(BaseModel):
    """Video URL information parsed from Bilibili video URL."""
    video_id: str = Field(title="Video ID (BV number)")


class CreatorUrlInfo(BaseModel):
    """Creator URL information parsed from Bilibili creator space URL."""
    creator_id: str = Field(title="Creator ID (UID)")