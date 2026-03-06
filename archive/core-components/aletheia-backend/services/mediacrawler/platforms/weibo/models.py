# -*- coding: utf-8 -*-
"""
Weibo data models.
"""

from pydantic import BaseModel, Field


class NoteUrlInfo(BaseModel):
    """Note URL information parsed from Weibo note URL."""
    note_id: str = Field(title="Note ID")


class CreatorUrlInfo(BaseModel):
    """Creator URL information parsed from Weibo creator URL."""
    creator_id: str = Field(title="Creator ID")