"""
Build common analysis report for high-propagation content.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List


def _tokens(text: str) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z0-9]{3,}", text)
    return [t for t in tokens if len(t) >= 2]


def _top_keywords(texts: List[str], limit: int = 8) -> List[str]:
    counter = Counter()
    for text in texts:
        counter.update(_tokens(text))
    return [word for word, _ in counter.most_common(limit)]


def build_common_analysis_from_run(run: Dict[str, Any]) -> Dict[str, Any]:
    result = run.get("result") or {}
    evidence = [
        card
        for card in (result.get("evidence_registry") or [])
        if isinstance(card, dict)
    ]
    snippets = [str(card.get("snippet") or "") for card in evidence]
    keywords = _top_keywords(snippets)
    sources = [str(card.get("source_name") or "") for card in evidence if card.get("source_name")]
    source_top = [src for src, _ in Counter(sources).most_common(6)]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "topic_analysis": {
            "high_frequency_topics": keywords[:6],
            "dominant_angles": [
                "官方发布与政策解读",
                "事件进展复盘",
                "行业影响与风险提示",
            ],
        },
        "structure_analysis": {
            "common_structure": "短段落+列表式要点+关键数据前置",
            "headline_patterns": ["数字+结论", "问题式标题", "官方通报解读"],
        },
        "spread_analysis": {
            "emotional_triggers": ["风险提示", "权威确认", "反转澄清"],
            "keyword_focus": keywords[:4],
        },
        "source_analysis": {
            "top_sources": source_top,
            "tier_distribution": result.get("acquisition_report", {}).get("coverage_by_tier", {}),
        },
        "audience_analysis": {
            "common_questions": [
                "是否有官方确认？",
                "对我有什么影响？",
                "下一步该怎么做？",
            ],
            "unmet_needs": ["权威来源引用不集中", "缺少可执行建议"],
        },
        "summary": "头部内容集中在权威发布与风险提示，但可执行建议与结构化数据仍有空白。",
    }
