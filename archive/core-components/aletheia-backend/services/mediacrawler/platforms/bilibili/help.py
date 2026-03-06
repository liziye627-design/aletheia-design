# -*- coding: utf-8 -*-
"""
Bilibili helper functions and WBI signature.
"""

import re
import time
import urllib.parse
from hashlib import md5
from typing import Dict, Tuple

from .models import VideoUrlInfo, CreatorUrlInfo


class BilibiliSign:
    """Bilibili WBI signature generator."""

    def __init__(self, img_key: str, sub_key: str):
        self.img_key = img_key
        self.sub_key = sub_key
        self.map_table = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]

    def get_salt(self) -> str:
        """Get the salted key."""
        salt = ""
        mixin_key = self.img_key + self.sub_key
        for mt in self.map_table:
            salt += mixin_key[mt]
        return salt[:32]

    def sign(self, req_data: Dict) -> Dict:
        """
        Sign request parameters with WBI signature.

        Args:
            req_data: Request parameters dictionary

        Returns:
            Signed parameters dictionary
        """
        current_ts = int(time.time())
        req_data.update({"wts": current_ts})
        req_data = dict(sorted(req_data.items()))
        req_data = {
            # Filter "!'()*" characters from values
            k: ''.join(filter(lambda ch: ch not in "!'()*", str(v)))
            for k, v in req_data.items()
        }
        query = urllib.parse.urlencode(req_data)
        salt = self.get_salt()
        wbi_sign = md5((query + salt).encode()).hexdigest()
        req_data['w_rid'] = wbi_sign
        return req_data


def get_unix_timestamp() -> int:
    """Get current Unix timestamp."""
    return int(time.time())


def parse_video_info_from_url(url: str) -> VideoUrlInfo:
    """
    Parse video ID from Bilibili video URL.

    Supports:
        - https://www.bilibili.com/video/BV1dwuKzmE26/?spm_id_from=...
        - https://www.bilibili.com/video/BV1d54y1g7db
        - BV1d54y1g7db (direct BV number)
    """
    # If the input is already a BV number
    if url.startswith("BV"):
        return VideoUrlInfo(video_id=url)

    # Use regex to extract BV number
    bv_pattern = r'/video/(BV[a-zA-Z0-9]+)'
    match = re.search(bv_pattern, url)

    if match:
        video_id = match.group(1)
        return VideoUrlInfo(video_id=video_id)

    raise ValueError(f"Unable to parse video ID from URL: {url}")


def parse_creator_info_from_url(url: str) -> CreatorUrlInfo:
    """
    Parse creator ID from Bilibili creator space URL.

    Supports:
        - https://space.bilibili.com/434377496?spm_id_from=...
        - https://space.bilibili.com/20813884
        - 434377496 (direct UID)
    """
    # If the input is already a numeric ID
    if url.isdigit():
        return CreatorUrlInfo(creator_id=url)

    # Use regex to extract UID
    uid_pattern = r'space\.bilibili\.com/(\d+)'
    match = re.search(uid_pattern, url)

    if match:
        creator_id = match.group(1)
        return CreatorUrlInfo(creator_id=creator_id)

    raise ValueError(f"Unable to parse creator ID from URL: {url}")