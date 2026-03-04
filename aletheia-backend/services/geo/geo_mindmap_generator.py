"""
Generate GEO-specific mindmap from scan dataset.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

GEO_BRANCHES = [
    "事件/行业主线动态",
    "AI高频引用内容方向",
    "行业深度解读与专业分析",
    "用户高频需求与痛点方向",
    "已饱和竞争赛道",
    "未覆盖空白方向",
    "GEO核心机会点",
]


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def build_geo_mindmap(scan_payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = _clean_text(scan_payload.get("topic") or "GEO 主题")
    items = list(scan_payload.get("content_items") or [])
    rankings = list(scan_payload.get("source_rankings") or [])

    branches: Dict[str, List[Dict[str, Any]]] = {b: [] for b in GEO_BRANCHES}
    for idx, item in enumerate(items[:50]):
        branch = GEO_BRANCHES[idx % len(GEO_BRANCHES)]
        branches[branch].append(
            {
                "node_name": _clean_text(item.get("title") or item.get("snippet") or "内容节点")[:80],
                "core_argument": _clean_text(item.get("snippet") or "")[:120],
                "source_tier": "Tier2",
                "ai_cited": "true" if item.get("domain") else "false",
                "trace_id": "",
                "original_url": _clean_text(item.get("url") or ""),
            }
        )

    mindmap_structure = []
    for branch in GEO_BRANCHES:
        nodes = branches.get(branch, [])
        mindmap_structure.append(
            {
                "branch_name": branch,
                "branch_desc": f"{branch}节点 {len(nodes)} 条",
                "competition_saturation": "高" if branch == "已饱和竞争赛道" else "中",
                "ai_citation_frequency": "高" if branch == "AI高频引用内容方向" else "中",
                "node_list": nodes[:8],
                "is_blank_direction": "true" if branch == "未覆盖空白方向" else "false",
                "is_geo_opportunity": "true" if branch == "GEO核心机会点" else "false",
            }
        )

    mermaid_lines = ["mindmap", f"  root(({topic[:24]}))"]
    for branch in GEO_BRANCHES:
        mermaid_lines.append(f"    {branch}")
        for node in branches.get(branch, [])[:2]:
            label = _clean_text(node.get("node_name"))
            if label:
                mermaid_lines.append(f"      {label[:14]}")

    return {
        "root_topic": topic,
        "mindmap_structure": mindmap_structure,
        "geo_opportunity_summary": "GEO机会点需结合AI引用空白与权威信源占位评估。",
        "uncovered_directions": ["未覆盖空白方向"],
        "mindmap_mermaid": "\n".join(mermaid_lines),
        "generated_at": datetime.utcnow().isoformat(),
        "ai_source_rankings": rankings[:10],
    }
