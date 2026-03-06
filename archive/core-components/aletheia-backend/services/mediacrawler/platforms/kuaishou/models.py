# -*- coding: utf-8 -*-
"""
Kuaishou data models.
"""

from pydantic import BaseModel, Field


class VideoUrlInfo(BaseModel):
    """Video URL information."""
    video_id: str = Field(title="Video ID")


class CreatorUrlInfo(BaseModel):
    """Creator URL information."""
    creator_id: str = Field(title="Creator ID")