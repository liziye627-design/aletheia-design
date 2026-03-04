"""
Generate GEO-native content with schema markup.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def build_geo_content(opportunity: Dict[str, Any]) -> Dict[str, Any]:
    topic = _clean_text(opportunity.get("topic") or "GEO主题")
    direction = _clean_text(opportunity.get("direction") or "机会方向")
    title = f"{direction}：{topic}的权威解读"
    body = "\n".join(
        [
            f"【结论】围绕{direction}，当前AI引用存在共识缺口，需用权威信源补位。",
            "\n【核心要点】",
            "1. 明确主张与权威来源对应关系。",
            "2. 用结构化清单输出关键数据。",
            "3. 在结尾加入可核查的行动建议。",
            "\n【品牌占位】",
            "- 将产品/解决方案与权威结论绑定，形成AI推荐路径。",
        ]
    )

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "datePublished": datetime.utcnow().isoformat(),
        "author": {"@type": "Organization", "name": "Aletheia"},
        "about": topic,
    }

    return {
        "title": title,
        "content": body,
        "schema_markup": json.dumps(schema, ensure_ascii=False),
        "generated_at": datetime.utcnow().isoformat(),
    }
