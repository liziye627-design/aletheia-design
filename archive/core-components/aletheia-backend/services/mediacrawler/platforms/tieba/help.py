# -*- coding: utf-8 -*-
"""
Tieba helper functions.
"""

import re


def parse_tiezi_info_from_url(url: str):
    """Parse tiezi ID from Tieba URL."""
    pattern = r'/p/(\d+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return url


def parse_forum_name_from_url(url: str):
    """Parse forum name from Tieba URL."""
    pattern = r'tieba\.baidu\.com/f\?kw=([^&]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return ""