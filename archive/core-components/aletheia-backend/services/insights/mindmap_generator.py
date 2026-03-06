"""
Generate structured mindmap data from investigation runs.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List


DEFAULT_DIRECTIONS = [
    "事件进展与最新动态",
    "官方发布与政策解读",
    "涉事主体回应与声明",
    "行业/领域影响分析",
    "专家/专业机构解读",
    "社会舆论与受众反馈",
    "历史背景与同类事件对比",
    "后续趋势与风险预判",
]


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _classify_direction(text: str) -> str:
    if re.search(r"官方|通告|公告|政策|法规|监管|发布", text):
        return "官方发布与政策解读"
    if re.search(r"回应|声明|表态|澄清|致歉", text):
        return "涉事主体回应与声明"
    if re.search(r"专家|研究|报告|数据|调研|分析", text):
        return "专家/专业机构解读"
    if re.search(r"影响|风险|冲击|趋势|预警", text):
        return "行业/领域影响分析"
    if re.search(r"历史|此前|回顾|同类|往年", text):
        return "历史背景与同类事件对比"
    if re.search(r"舆论|评论|热议|网友|反馈", text):
        return "社会舆论与受众反馈"
    if re.search(r"未来|预判|展望|长期", text):
        return "后续趋势与风险预判"
    return "事件进展与最新动态"


def build_mindmap_from_run(run: Dict[str, Any]) -> Dict[str, Any]:
    result = run.get("result") or {}
    request = run.get("request") or {}
    root_topic = _clean_text(
        (result.get("search") or {}).get("keyword")
        or request.get("keyword")
        or request.get("claim")
        or "待分析主题"
    )
    evidence = [
        card
        for card in (result.get("evidence_registry") or [])
        if isinstance(card, dict)
    ]

    buckets: Dict[str, List[Dict[str, Any]]] = {d: [] for d in DEFAULT_DIRECTIONS}
    for card in evidence:
        snippet = _clean_text(card.get("snippet") or card.get("summary") or "")
        direction = _classify_direction(snippet)
        trace = card.get("trace") if isinstance(card.get("trace"), dict) else {}
        buckets.setdefault(direction, []).append(
            {
                "news_id": _clean_text(card.get("id") or "unknown"),
                "source_tier": int(card.get("source_tier") or 3),
                "trace_id": _clean_text(trace.get("anchor") or ""),
                "core_argument": snippet[:140],
                "key_data": _clean_text(card.get("published_at") or ""),
                "core_case": _clean_text(card.get("source_name") or card.get("source_platform") or ""),
                "publish_time": _clean_text(card.get("published_at") or ""),
                "original_url": _clean_text(card.get("url") or ""),
            }
        )

    mindmap_structure: List[Dict[str, Any]] = []
    for direction in DEFAULT_DIRECTIONS:
        items = buckets.get(direction, [])
        mindmap_structure.append(
            {
                "direction_name": direction,
                "direction_desc": f"{direction}相关资讯 {len(items)} 条",
                "news_list": items[:8],
            }
        )

    uncovered = [d for d, items in buckets.items() if not items]

    mermaid_lines = ["mindmap", f"  root(({root_topic[:24]}))"]
    for direction in DEFAULT_DIRECTIONS:
        mermaid_lines.append(f"    {direction}")
        for item in (buckets.get(direction) or [])[:3]:
            label = _clean_text(item.get("core_argument") or item.get("core_case"))
            if label:
                mermaid_lines.append(f"      {label[:18]}")

    return {
        "root_topic": root_topic,
        "mindmap_structure": mindmap_structure,
        "uncovered_directions": uncovered,
        "mindmap_mermaid": "\n".join(mermaid_lines),
        "generated_at": datetime.utcnow().isoformat(),
    }
