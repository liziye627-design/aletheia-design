# -*- coding: utf-8 -*-
"""
Zhihu helper functions.
"""

import re
from typing import Dict, List, Optional

from .models import ZhihuContent, ZhihuCreator


ANSWER_PATTERN = r"zhihu\.com/question/\d+/answer/\d+"
ARTICLE_PATTERN = r"zhuanlan\.zhihu\.com/p/\d+"
VIDEO_PATTERN = r"video\.zhihu\.com/\?zvideoId=\d+"


def judge_zhihu_url(url: str) -> str:
    """Judge content type from URL."""
    if re.search(ANSWER_PATTERN, url):
        return "answer"
    elif re.search(ARTICLE_PATTERN, url):
        return "article"
    elif re.search(VIDEO_PATTERN, url):
        return "video"
    return "unknown"


class ZhihuExtractor:
    """Extract data from Zhihu API responses."""

    def extract_content_from_search(self, data: Dict) -> Optional[ZhihuContent]:
        """Extract content from search result."""
        if not data:
            return None

        content_type = data.get("type", "")
        content_id = data.get("id", "")

        if content_type == "answer":
            return ZhihuContent(
                content_id=str(content_id),
                content_type="answer",
                title=data.get("question", {}).get("title", ""),
                text=data.get("excerpt", ""),
                author=data.get("author", {}),
            )
        elif content_type == "article":
            return ZhihuContent(
                content_id=str(content_id),
                content_type="article",
                title=data.get("title", ""),
                text=data.get("excerpt", ""),
                author=data.get("author", {}),
            )

        return None

    def extract_creator_from_response(self, data: Dict) -> Optional[ZhihuCreator]:
        """Extract creator info from response."""
        if not data:
            return None

        return ZhihuCreator(
            creator_id=str(data.get("id", "")),
            name=data.get("name", ""),
            url_token=data.get("url_token", ""),
        )