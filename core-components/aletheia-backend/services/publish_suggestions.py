"""
发布建议与 GEO 报告生成辅助。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.llm.llm_provider import LLMClient

logger = logging.getLogger(__name__)


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def _build_context(run: Dict[str, Any]) -> Dict[str, Any]:
    request = run.get("request") or {}
    result = run.get("result") or {}
    claim = _clean_text(request.get("claim") or result.get("claim") or "待核查主张")
    keyword = _clean_text(
        request.get("keyword")
        or (result.get("search") or {}).get("keyword")
        or claim[:24]
    )
    claim_analysis = result.get("claim_analysis") or {}
    verdict = _clean_text(claim_analysis.get("run_verdict") or "UNCERTAIN")
    acq = result.get("acquisition_report") or {}
    evidence_count = int(
        result.get("valid_evidence_count")
        or acq.get("external_evidence_count")
        or acq.get("valid_evidence_count")
        or 0
    )
    background_count = int(
        acq.get("external_background_count") or acq.get("background_count") or 0
    )
    noise_count = int(acq.get("external_noise_count") or acq.get("noise_count") or 0)
    source_plan = result.get("source_plan") or {}
    platforms = list(source_plan.get("selected_platforms") or [])
    summary = _clean_text(
        (result.get("public_verdict") or {}).get("explain")
        or (claim_analysis.get("summary") or {}).get("conclusion")
        or result.get("summary_text")
        or "暂无详细结论摘要。"
    )

    return {
        "claim": claim,
        "keyword": keyword,
        "verdict": verdict,
        "summary": summary,
        "evidence_count": evidence_count,
        "background_count": background_count,
        "noise_count": noise_count,
        "platforms": platforms,
    }


def _fallback_suggestions(context: Dict[str, Any]) -> Dict[str, Any]:
    headline = _clean_text(context.get("claim") or "核查结论")
    summary = _clean_text(context.get("summary") or "")
    verdict = _clean_text(context.get("verdict") or "UNCERTAIN")
    evidence_count = int(context.get("evidence_count") or 0)

    tweet_suggestions = [
        {
            "title": "结论先行",
            "text": f"{headline}｜核查结论：{verdict}。核心证据 {evidence_count} 条，重点结论如下：{summary[:60]}…",
            "hashtags": ["#事实核查", "#Aletheia"],
            "angle": "结论 + 证据数",
        },
        {
            "title": "证据结构",
            "text": f"我们将证据分为主证据/背景证据/噪音，当前主结论指向：{verdict}。如需复核，优先查看官方来源。",
            "hashtags": ["#证据链", "#信息核验"],
            "angle": "证据结构健康度",
        },
        {
            "title": "行动建议",
            "text": "发布前建议：对关键信息做横向检索、回到原始出处，若存在冲突请标注“需复核”。",
            "hashtags": ["#新闻编辑台", "#传播建议"],
            "angle": "编辑建议",
        },
    ]

    mindmap = "\n".join(
        [
            "mindmap",
            f"  root(({headline[:24]}))",
            f"    结论({verdict})",
            "      证据强度",
            f"        有效证据 {evidence_count} 条",
            "      风险提示",
            "        关注时效与冲突点",
            "    传播建议",
            "      明确来源",
            "      标注不确定",
        ]
    )

    return {
        "tweet_suggestions": tweet_suggestions,
        "mindmap_mermaid": mindmap,
        "creative_directions": [
            "用“事实-证据-结论”结构写成短评",
            "强调信息时效与关键缺口",
            "以读者可执行的核查步骤收尾",
        ],
        "hotspot_benefits": [
            "快速澄清争议，降低误传风险",
            "为读者提供可信核查路径",
            "提升平台公信力与内容质量",
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }


async def build_publish_suggestions(run: Dict[str, Any]) -> Dict[str, Any]:
    context = _build_context(run)
    llm = LLMClient()
    prompt = {
        "role": "user",
        "content": "\n".join(
            [
                "你是新闻编辑台的发布建议助手，请基于给定上下文输出 JSON：",
                "字段必须包含：tweet_suggestions(3条中文), mindmap_mermaid, creative_directions, hotspot_benefits。",
                "tweet_suggestions 每条包含 title,text,hashtags(数组),angle。",
                "mindmap_mermaid 用 Mermaid mindmap 语法。",
                "只输出 JSON，不要额外解释。",
                f"上下文：{json.dumps(context, ensure_ascii=False)}",
            ]
        ),
    }

    try:
        response = await llm.chat_completion([prompt], temperature=0.4, max_tokens=900)
        payload = _extract_json(response or "")
        if not payload:
            raise ValueError("LLM response not json")
        payload.setdefault("generated_at", datetime.utcnow().isoformat())
        return payload
    except Exception as exc:
        logger.warning("publish suggestions fallback: %s", exc)
        return _fallback_suggestions(context)


def _fallback_geo_report(context: Dict[str, Any]) -> str:
    headline = _clean_text(context.get("claim") or "核查主题")
    verdict = _clean_text(context.get("verdict") or "UNCERTAIN")
    summary = _clean_text(context.get("summary") or "")
    evidence_count = int(context.get("evidence_count") or 0)
    background_count = int(context.get("background_count") or 0)
    noise_count = int(context.get("noise_count") or 0)
    platforms = ", ".join(context.get("platforms") or []) or "未指定"

    lines = [
        f"标题：{headline}",
        "",
        "导语：本报告对以上主张进行了多平台采集与交叉核验，结论如下。",
        "",
        f"结论：{verdict}",
        f"证据概况：有效证据 {evidence_count} 条；背景证据 {background_count} 条；噪音 {noise_count} 条。",
        f"覆盖平台：{platforms}",
        "",
        "核心要点：",
        f"- 结论摘要：{summary}",
        "- 若存在冲突或证据不足，请标注“需复核”。",
        "",
        "可核查动作：",
        "- 优先回溯原始发布源与官方通告。",
        "- 交叉比对主流媒体与权威机构公开资料。",
    ]
    return "\n".join(lines)


async def build_geo_report_content(run: Dict[str, Any]) -> Dict[str, Any]:
    context = _build_context(run)
    llm = LLMClient()
    prompt = {
        "role": "user",
        "content": "\n".join(
            [
                "你是新闻编辑台的 GEO 报告撰写助手，请输出一份中文报告正文（纯文本）。",
                "要求：包含标题、导语、结论、证据概况、关键要点、可核查动作。",
                "控制在 800-1600 字之间。",
                f"上下文：{json.dumps(context, ensure_ascii=False)}",
            ]
        ),
    }
    try:
        response = await llm.chat_completion([prompt], temperature=0.5, max_tokens=1800)
        content = _clean_text(response, "")
        if not content:
            raise ValueError("empty content")
        return {
            "title": f"GEO 新闻报告：{_clean_text(context.get('keyword') or context.get('claim') or '核查主题')[:40]}",
            "content": content,
        }
    except Exception as exc:
        logger.warning("geo report fallback: %s", exc)
        return {
            "title": f"GEO 新闻报告：{_clean_text(context.get('keyword') or context.get('claim') or '核查主题')[:40]}",
            "content": _fallback_geo_report(context),
        }
