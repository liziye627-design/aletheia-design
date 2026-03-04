# -*- coding: utf-8 -*-
"""
Weibo helper functions.
"""

from typing import Dict, List


def filter_search_result_card(cards: List[Dict]) -> List[Dict]:
    """Filter search result cards to get valid notes."""
    if not cards:
        return []
    note_list = []
    for card in cards:
        if card.get("card_type") == 9:
            note_list.append(card)
    return note_list