# -*- coding: utf-8 -*-
"""
XiaoHongShu data models.
"""

from pydantic import BaseModel, Field


class NoteUrlInfo(BaseModel):
    """Note URL information parsed from Xiaohongshu note URL."""
    note_id: str = Field(title="Note ID")
    xsec_token: str = Field(title="XSEC token")
    xsec_source: str = Field(title="XSEC source")


class CreatorUrlInfo(BaseModel):
    """Creator URL information parsed from Xiaohongshu creator homepage URL."""
    user_id: str = Field(title="User ID (creator ID)")
    xsec_token: str = Field(default="", title="XSEC token")
    xsec_source: str = Field(default="", title="XSEC source")