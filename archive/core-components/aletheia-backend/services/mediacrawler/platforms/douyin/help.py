# -*- coding: utf-8 -*-
"""
Douyin helper functions.
"""

import random
import re
from typing import Optional, Dict

from playwright.async_api import Page

from .models import VideoUrlInfo, CreatorUrlInfo


def get_web_id() -> str:
    """Generate random webid for Douyin API."""
    def e(t):
        if t is not None:
            return str(t ^ (int(16 * random.random()) >> (t // 4)))
        else:
            return ''.join(
                [str(int(1e7)), '-', str(int(1e3)), '-', str(int(4e3)), '-', str(int(8e3)), '-', str(int(1e11))]
            )

    web_id = ''.join(
        e(int(x)) if x in '018' else x for x in e(None)
    )
    return web_id.replace('-', '')[:19]


async def get_a_bogus(url: str, params: str, post_data: dict, user_agent: str, page: Page = None) -> str:
    """
    Get a_bogus parameter for Douyin API signature.
    Note: This requires the douyin.js file for proper signing.
    """
    # Placeholder - in production, this would call the JS sign function
    # For now, return empty string (API may work without it in some cases)
    return ""


def extract_url_params_to_dict(url: str) -> Dict[str, str]:
    """Extract URL query parameters to dictionary."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {k: v[0] if len(v) == 1 else v for k, v in params.items()}


def parse_video_info_from_url(url: str) -> VideoUrlInfo:
    """
    Parse video ID from Douyin video URL.

    Supports:
        1. Normal video link: https://www.douyin.com/video/7525082444551310602
        2. Link with modal_id parameter
        3. Short link: https://v.douyin.com/iF12345ABC/
        4. Pure ID: 7525082444551310602
    """
    # If it's a pure numeric ID
    if url.isdigit():
        return VideoUrlInfo(aweme_id=url, url_type="normal")

    # Check if it's a short link
    if "v.douyin.com" in url or (url.startswith("http") and len(url) < 50 and "video" not in url):
        return VideoUrlInfo(aweme_id="", url_type="short")

    # Try to extract modal_id from URL parameters
    params = extract_url_params_to_dict(url)
    modal_id = params.get("modal_id")
    if modal_id:
        return VideoUrlInfo(aweme_id=modal_id, url_type="modal")

    # Extract ID from standard video URL: /video/number
    video_pattern = r'/video/(\d+)'
    match = re.search(video_pattern, url)
    if match:
        aweme_id = match.group(1)
        return VideoUrlInfo(aweme_id=aweme_id, url_type="normal")

    raise ValueError(f"Unable to parse video ID from URL: {url}")


def parse_creator_info_from_url(url: str) -> CreatorUrlInfo:
    """
    Parse creator ID (sec_user_id) from Douyin creator homepage URL.

    Supports:
        1. Creator homepage: https://www.douyin.com/user/MS4wLjABAAAA...
        2. Pure ID: MS4wLjABAAAA...
    """
    # If it's a pure ID format
    if url.startswith("MS4wLjABAAAA") or (not url.startswith("http") and "douyin.com" not in url):
        return CreatorUrlInfo(sec_user_id=url)

    # Extract sec_user_id from creator homepage URL: /user/xxx
    user_pattern = r'/user/([^/?]+)'
    match = re.search(user_pattern, url)
    if match:
        sec_user_id = match.group(1)
        return CreatorUrlInfo(sec_user_id=sec_user_id)

    raise ValueError(f"Unable to parse creator ID from URL: {url}")