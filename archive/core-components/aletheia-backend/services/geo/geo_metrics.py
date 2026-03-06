"""
GEO metrics placeholder.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def build_geo_metrics(topic: str) -> Dict[str, Any]:
    return {
        "topic": topic,
        "ai_citation_rate": 0.42,
        "brand_mention_rate": 0.18,
        "ai_occupancy_rate": 0.12,
        "frontend_engagement": {
            "reads": 0,
            "likes": 0,
            "shares": 0,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
