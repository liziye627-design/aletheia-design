# -*- coding: utf-8 -*-
"""
Zhihu field definitions.
"""

from enum import Enum


class SearchType(Enum):
    """Zhihu search type."""
    CONTENT = "content"
    QUESTION = "question"
    ANSWER = "answer"
    ARTICLE = "article"
    PEOPLE = "people"


class ContentType(Enum):
    """Content type."""
    ANSWER = "answer"
    ARTICLE = "article"
    VIDEO = "video"