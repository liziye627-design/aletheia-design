# -*- coding: utf-8 -*-
"""
Kuaishou helper functions.
"""

import re


def parse_video_info_from_url(url: str):
    """Parse video ID from Kuaishou URL."""
    if url.isdigit():
        return url
    pattern = r'/short-video/([a-zA-Z0-9]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return url


def parse_creator_info_from_url(url: str):
    """Parse creator ID from Kuaishou URL."""
    if url.isdigit():
        return url
    pattern = r'/profile/([a-zA-Z0-9]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return url