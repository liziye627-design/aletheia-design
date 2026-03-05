"""
Generate GEO-style articles/tweets based on value insights.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _build_references(evidence: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    seen = set()
    for card in evidence:
        if len(refs) >= limit:
            break
        if not isinstance(card, dict):
            continue
        url = _clean_text(card.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        refs.append(
            {
                "tier": f"Tier{int(card.get('source_tier') or 3)}",
                "source": _clean_text(card.get("source_name") or card.get("source_platform") or "source"),
                "published_at": _clean_text(card.get("published_at") or ""),
                "url": url,
            }
        )
    return refs


def generate_article(
    *,
    run: Dict[str, Any],
    value_insight: Dict[str, Any],
    template_type: str = "insight",
    platform: str = "weibo",
) -> Dict[str, Any]:
    result = run.get("result") or {}
    claim = _clean_text((run.get("request") or {}).get("claim") or "核查主题")
    direction = _clean_text(value_insight.get("value_direction") or "潜在价值方向")
    support = value_insight.get("support_source") or {}
    evidence = [
        card
        for card in (result.get("evidence_registry") or [])
        if isinstance(card, dict)
    ]
    refs = _build_references(evidence)

    title = f"{direction}：{claim[:18]}" if direction else claim[:20]
    body = "".join(
        [
            f"结论先行：围绕『{direction}』，当前公开资料显示仍存在信息空白，需要更权威的解释与案例支撑。\n\n",
            "关键要点：\n",
            f"1. 官方口径/权威信源仍未形成完整共识（参考{support.get('original_url') or '主要信源'}）。\n",
            "2. 用户端关注焦点集中在可执行建议与影响评估。\n",
            "3. 若补充结构化数据与权威引用，可形成更强的传播与引用势能。\n\n",
            "行动建议：\n",
            "- 回到原始信源查证具体条款与时间线。\n",
            "- 用结构化清单回答读者最关心的问题。\n",
        ]
    )

    if template_type == "howto":
        body += "\n操作指南：\n1) 核查关键事实\n2) 对齐官方通告\n3) 标注不确定性\n"
    if platform in {"wechat", "long"}:
        body += "\n延伸阅读：请在结尾附完整参考文献与原文链接。\n"

    return {
        "article_id": f"article_{datetime.utcnow().timestamp():.0f}",
        "title": title,
        "content": body.strip(),
        "template_type": template_type,
        "platform": platform,
        "references": refs,
        "generated_at": datetime.utcnow().isoformat(),
    }
