# -*- coding: utf-8 -*-
"""
Tieba data models.
"""

from pydantic import BaseModel, Field


class TieziUrlInfo(BaseModel):
    """Tiezi URL information."""
    tiezi_id: str = Field(title="Tiezi ID")
    forum_name: str = Field(default="", title="Forum name")


class CreatorUrlInfo(BaseModel):
    """Creator URL information."""
    creator_id: str = Field(title="Creator ID")