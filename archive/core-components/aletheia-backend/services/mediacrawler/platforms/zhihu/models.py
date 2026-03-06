# -*- coding: utf-8 -*-
"""
Zhihu data models.
"""

from typing import Dict
from pydantic import BaseModel, Field


class ZhihuContent(BaseModel):
    """Zhihu content model."""
    content_id: str = Field(title="Content ID")
    content_type: str = Field(title="Content type: answer, article, video")
    title: str = Field(default="", title="Title")
    text: str = Field(default="", title="Text content")
    author: Dict = Field(default_factory=dict, title="Author info")

    class Config:
        extra = "allow"


class ZhihuCreator(BaseModel):
    """Zhihu creator model."""
    creator_id: str = Field(title="Creator ID")
    name: str = Field(default="", title="Name")
    url_token: str = Field(default="", title="URL token")

    class Config:
        extra = "allow"