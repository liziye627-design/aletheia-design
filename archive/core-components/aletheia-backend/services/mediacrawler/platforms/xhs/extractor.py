# -*- coding: utf-8 -*-
"""
XiaoHongShu HTML content extractor.
"""

import json
import re
from typing import Dict, Optional

import humps


class XiaoHongShuExtractor:
    """Extract data from XiaoHongShu HTML pages."""

    def extract_note_detail_from_html(self, note_id: str, html: str) -> Optional[Dict]:
        """
        Extract note details from HTML.

        Args:
            note_id: Note ID
            html: HTML string

        Returns:
            Note details dictionary or None
        """
        if "noteDetailMap" not in html:
            # Either a CAPTCHA appeared or the note doesn't exist
            return None

        state = re.findall(r"window.__INITIAL_STATE__=({.*})</script>", html)[
            0
        ].replace("undefined", '""')
        if state != "{}":
            note_dict = humps.decamelize(json.loads(state))
            return note_dict["note"]["note_detail_map"][note_id]["note"]
        return None

    def extract_creator_info_from_html(self, html: str) -> Optional[Dict]:
        """
        Extract user information from HTML.

        Args:
            html: HTML string

        Returns:
            User information dictionary or None
        """
        match = re.search(
            r"<script>window.__INITIAL_STATE__=(.+)<\/script>", html, re.M
        )
        if match is None:
            return None
        info = json.loads(match.group(1).replace(":undefined", ":null"), strict=False)
        if info is None:
            return None
        return info.get("user").get("userPageData")