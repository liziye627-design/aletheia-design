"""
Mine potential value directions from mindmap + analysis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def _pick_support_source(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    sorted_evidence = sorted(
        [card for card in evidence if isinstance(card, dict)],
        key=lambda x: int(x.get("source_tier") or 3),
    )
    if not sorted_evidence:
        return {}
    return sorted_evidence[0]


def _score_level(score: int) -> str:
    if score >= 7:
        return "S"
    if score >= 5:
        return "A"
    if score >= 3:
        return "B"
    return "C"


def build_value_insights(
    *,
    run: Dict[str, Any],
    mindmap: Dict[str, Any],
    common_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    result = run.get("result") or {}
    evidence = [
        card
        for card in (result.get("evidence_registry") or [])
        if isinstance(card, dict)
    ]
    uncovered = list(mindmap.get("uncovered_directions") or [])
    if not uncovered:
        uncovered = [
            "行业/领域影响分析",
            "后续趋势与风险预判",
            "历史背景与同类事件对比",
        ]

    insights: List[Dict[str, Any]] = []
    for direction in uncovered[:6]:
        support = _pick_support_source(evidence)
        tier = int(support.get("source_tier") or 3) if support else 3
        score = 2 + max(0, 4 - tier)
        if "官方" in direction:
            score += 2
        if "趋势" in direction or "风险" in direction:
            score += 1
        level = _score_level(score)
        insights.append(
            {
                "value_level": level,
                "value_direction": direction,
                "blank_description": f"头部内容在{direction}方向覆盖不足，仍存在权威解读空白。",
                "support_source": {
                    "source_tier": tier,
                    "source_content": str(support.get("snippet") or "")[:120],
                    "trace_id": (support.get("trace") or {}).get("anchor")
                    if isinstance(support.get("trace"), dict)
                    else "",
                    "original_url": support.get("url") if support else "",
                },
                "user_demand": "用户关注该方向的长期影响与可执行建议。",
                "spread_potential": "具备实用价值与政策关联，易于形成传播。",
                "core_viewpoints": [
                    f"{direction}的核心风险点",
                    "官方口径与市场反应的差异",
                    "可执行的应对建议",
                ],
            }
        )

    return {
        "potential_value_insights": insights,
        "mining_summary": "已输出高价值方向清单，优先选择S/A级落地。",
        "generated_at": datetime.utcnow().isoformat(),
        "common_analysis_ref": common_analysis.get("summary", ""),
    }
