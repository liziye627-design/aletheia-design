"""
Mine GEO opportunities based on scan + mindmap.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def _score_to_level(score: int) -> str:
    if score >= 8:
        return "S"
    if score >= 6:
        return "A"
    if score >= 4:
        return "B"
    return "C"


def build_geo_opportunities(
    *,
    scan_payload: Dict[str, Any],
    mindmap_payload: Dict[str, Any],
) -> Dict[str, Any]:
    topic = scan_payload.get("topic") or "GEO主题"
    rankings = list(scan_payload.get("source_rankings") or [])
    mindmap_branches = list(mindmap_payload.get("mindmap_structure") or [])

    opportunities: List[Dict[str, Any]] = []
    for idx, branch in enumerate(mindmap_branches):
        if branch.get("is_geo_opportunity") != "true" and branch.get("is_blank_direction") != "true":
            continue
        score = 5 + (1 if branch.get("ai_citation_frequency") == "低" else 0)
        level = _score_to_level(score)
        opportunities.append(
            {
                "opportunity_id": f"geo_opp_{idx+1}",
                "topic": topic,
                "direction": branch.get("branch_name"),
                "level": level,
                "score": score,
                "ai_gap": "AI引用空白" if branch.get("is_blank_direction") == "true" else "AI引用不足",
                "authority_support": rankings[:3],
                "priority_reason": "权威信源可占位，竞争饱和度低。",
                "generated_at": datetime.utcnow().isoformat(),
            }
        )

    if not opportunities:
        opportunities.append(
            {
                "opportunity_id": "geo_opp_fallback",
                "topic": topic,
                "direction": "GEO机会补位",
                "level": "B",
                "score": 4,
                "ai_gap": "暂无明确空白，建议补充权威数据",
                "authority_support": rankings[:3],
                "priority_reason": "以权威总结和结构化数据抢占AI引用。",
                "generated_at": datetime.utcnow().isoformat(),
            }
        )

    return {
        "topic": topic,
        "opportunities": opportunities,
        "generated_at": datetime.utcnow().isoformat(),
    }
