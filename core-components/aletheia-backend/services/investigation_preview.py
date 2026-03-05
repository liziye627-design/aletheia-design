"""
Investigation 预分析服务：
1) 主张草案
2) 选源计划预览
3) 风险提示
4) 意图摘要（SiliconFlow 统一处理）
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from core.config import settings
from services.investigation_claims import extract_claims
from services.layer1_perception.crawler_manager import get_crawler_manager
from services.llm.siliconflow_client import get_siliconflow_client
from services.source_planner import OFFICIAL_PLATFORMS, plan_sources
from services.source_tier_config import resolve_source_tier
from utils.logging import logger

SOCIAL_PLATFORMS = {"weibo", "xiaohongshu", "douyin", "zhihu", "twitter", "reddit"}


def _normalize_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for row in value:
        item = str(row or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def _derive_keyword(claim: str, keyword: str) -> str:
    kw = str(keyword or "").strip()
    if kw:
        return kw[:120]
    words = [x for x in str(claim or "").replace("\n", " ").split(" ") if x.strip()]
    if not words:
        return ""
    return " ".join(words[:6])[:120]


def _fallback_intent_summary(
    *,
    claim: str,
    source_plan: Dict[str, Any],
    risk_notes: List[str],
) -> str:
    selected = _normalize_list(source_plan.get("selected_platforms"))
    must = _normalize_list(source_plan.get("must_have_platforms"))
    domain = str(source_plan.get("domain") or "general_news")
    confidence = round(float(source_plan.get("selection_confidence") or 0.0), 2)
    risk = "；".join(risk_notes[:3]) if risk_notes else "暂无高风险提示"
    selected_text = "、".join(selected[:5]) if selected else "当前可用平台"
    must_text = "、".join(must[:4]) if must else "暂无硬性必选源"
    return (
        f"本次预分析将围绕“{str(claim or '').strip()[:120]}”进行核验，重点判断核心主张是否有权威来源直接确认、澄清或反证。"
        f"选源策略以 {domain} 领域为主，优先覆盖 {selected_text}，其中必选源为 {must_text}，当前选源置信度 {confidence}。"
        f"主要风险包括：{risk}。若遇到平台超时或结果稀疏，将降级为本地索引检索与证据不足提示，避免热榜替代结论。"
        "预期输出为可追溯证据清单、来源分层结论和待补充检索方向。"
    )


def _trim_to_natural_boundary(text: str, max_chars: int) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    clipped = value[:max_chars]
    boundary = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind("！"), clipped.rfind("？"))
    if boundary >= max_chars // 2:
        return clipped[: boundary + 1].strip()
    return clipped.rstrip("，,;； ") + "。"


def _normalize_intent_summary(
    *,
    summary: str,
    fallback_summary: str,
) -> str:
    min_chars = max(
        80,
        int(getattr(settings, "INVESTIGATION_PREVIEW_SUMMARY_MIN_CHARS", 160)),
    )
    max_chars = max(
        min_chars + 20,
        int(getattr(settings, "INVESTIGATION_PREVIEW_SUMMARY_MAX_CHARS", 260)),
    )
    text = str(summary or "").replace("\n", " ").strip()
    fallback = str(fallback_summary or "").replace("\n", " ").strip()
    if not text:
        text = fallback
    if len(text) < min_chars and fallback:
        if text and text[-1] not in {"。", "！", "？", "；"}:
            text += "。"
        merged = text if fallback in text else f"{text}{fallback}"
        text = merged
    return _trim_to_natural_boundary(text, max_chars)


def _to_claims_draft(claim_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    draft: List[Dict[str, Any]] = []
    for row in claim_rows:
        text = str(row.get("text") or "").strip()
        claim_type = str(row.get("type") or "generic_claim")
        confidence = 0.55
        if len(text) >= 24:
            confidence += 0.1
        if claim_type != "generic_claim":
            confidence += 0.15
        confidence = round(min(0.95, max(0.25, confidence)), 4)
        draft.append(
            {
                "claim_id": str(row.get("claim_id") or ""),
                "text": text,
                "type": claim_type,
                "confidence": confidence,
                "editable": True,
            }
        )
    return draft


def _manual_source_plan(
    *,
    source_strategy: str,
    available_platforms: List[str],
    crawlers: Any,
) -> Dict[str, Any]:
    selected: List[str] = []
    plan_version = "manual_default"
    if source_strategy == "full":
        selected = list(available_platforms)
        plan_version = "manual_full"
    elif source_strategy == "stable_mixed_v1":
        stable = (
            crawlers.get_source_profile_platforms("stable_mixed_v1")
            if hasattr(crawlers, "get_source_profile_platforms")
            else []
        )
        selected = [p for p in stable if p in available_platforms]
        plan_version = "manual_stable_mixed_v1"
    if not selected:
        selected = list(available_platforms)
    selected = selected[:8]
    return {
        "event_type": "generic_claim",
        "domain": "general_news",
        "domain_keywords": [],
        "plan_version": plan_version,
        "selection_confidence": 0.4 if selected else 0.1,
        "must_have_platforms": selected[: min(4, len(selected))],
        "candidate_platforms": selected,
        "excluded_platforms": [],
        "selected_platforms": selected,
        "official_floor_platforms": [],
        "official_selected_platforms": [p for p in selected if p in OFFICIAL_PLATFORMS],
        "official_selected_count": len([p for p in selected if p in OFFICIAL_PLATFORMS]),
        "selection_reasons": [f"source_strategy={source_strategy or 'manual'}"],
        "risk_notes": [],
    }


def _build_tiered_platforms(
    *,
    crawlers: Any,
    platforms: List[str],
) -> Dict[str, Any]:
    tier_map: Dict[str, int] = {}
    tiered = {"tier1": [], "tier2": [], "tier3": [], "unknown": []}
    for platform in platforms:
        domains = []
        if hasattr(crawlers, "get_platform_domains"):
            domains = list(crawlers.get_platform_domains(platform) or [])
        tiers = []
        for domain in domains or []:
            try:
                tiers.append(resolve_source_tier(domain).tier)
            except Exception:
                continue
        tier = min(tiers) if tiers else 3
        tier_map[platform] = tier
        if tier == 1:
            tiered["tier1"].append(platform)
        elif tier == 2:
            tiered["tier2"].append(platform)
        elif tier == 3:
            tiered["tier3"].append(platform)
        else:
            tiered["unknown"].append(platform)
    return {"tier_map": tier_map, "tiered": tiered}


def _build_intent_decomposition(
    *,
    claim: str,
    keyword: str,
    claims_draft: List[Dict[str, Any]],
    source_plan: Dict[str, Any],
    crawlers: Any,
    risk_notes: List[str],
) -> Dict[str, Any]:
    selected = _normalize_list(source_plan.get("selected_platforms"))
    tiered_info = _build_tiered_platforms(crawlers=crawlers, platforms=selected)
    tasks: List[Dict[str, Any]] = []
    for idx, row in enumerate(claims_draft or [], start=1):
        query = str(row.get("text") or claim).strip() or claim
        tasks.append(
            {
                "task_id": f"task_{idx:02d}",
                "query": query[:160],
                "preferred_tiers": [1, 2],
                "fallback_tiers": [2, 3],
                "blocked_tiers": [],
                "platforms": selected,
            }
        )
    if not tasks and claim:
        tasks.append(
            {
                "task_id": "task_01",
                "query": claim[:160],
                "preferred_tiers": [1, 2],
                "fallback_tiers": [2, 3],
                "blocked_tiers": [],
                "platforms": selected,
            }
        )
    return {
        "core_claim": claim,
        "keyword": keyword,
        "claims": claims_draft,
        "tiered_platforms": tiered_info.get("tiered"),
        "platform_tiers": tiered_info.get("tier_map"),
        "search_tasks": tasks,
        "risk_notes": risk_notes,
    }


def _build_risk_notes(
    *,
    claim: str,
    claims_draft: List[Dict[str, Any]],
    source_plan: Dict[str, Any],
) -> List[str]:
    notes: List[str] = []
    notes.extend([str(x) for x in list(source_plan.get("risk_notes") or []) if str(x).strip()])
    selected = _normalize_list(source_plan.get("selected_platforms"))
    official_selected = [p for p in selected if p in OFFICIAL_PLATFORMS]
    social_selected = [p for p in selected if p in SOCIAL_PLATFORMS]
    confidence = float(source_plan.get("selection_confidence") or 0.0)
    if not selected:
        notes.append("NO_AVAILABLE_PLATFORM")
    if len(official_selected) < min(2, len(selected)):
        notes.append("OFFICIAL_SOURCE_COVERAGE_LOW")
    if social_selected and len(social_selected) > max(2, len(official_selected) * 2):
        notes.append("SOCIAL_SOURCE_DOMINATES")
    if confidence < 0.45:
        notes.append("LOW_SELECTION_CONFIDENCE")
    if len(str(claim or "").strip()) < 10:
        notes.append("CLAIM_TOO_SHORT")
    if not claims_draft:
        notes.append("NO_CLAIM_DRAFT")
    dedup: List[str] = []
    for row in notes:
        item = str(row or "").strip()
        if item and item not in dedup:
            dedup.append(item)
    return dedup[:12]


async def build_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    claim = str((payload or {}).get("claim") or "").strip()
    keyword = _derive_keyword(claim, str((payload or {}).get("keyword") or ""))
    source_strategy = str((payload or {}).get("source_strategy") or "auto")
    requested_platforms = _normalize_list((payload or {}).get("platforms"))

    crawlers = get_crawler_manager()
    all_available = sorted(list(getattr(crawlers, "crawlers", {}).keys()))
    if requested_platforms:
        available_platforms = [p for p in requested_platforms if p in all_available]
    else:
        available_platforms = list(all_available)

    platform_health_snapshot = (
        crawlers.get_platform_health_snapshot()
        if hasattr(crawlers, "get_platform_health_snapshot")
        else {}
    )
    platform_health_matrix = (
        crawlers.get_platform_source_matrix()
        if hasattr(crawlers, "get_platform_source_matrix")
        else {}
    )

    if source_strategy == "auto":
        source_plan = plan_sources(
            claim=claim,
            keyword=keyword,
            available_platforms=available_platforms,
            platform_health_snapshot=platform_health_snapshot,
            platform_health_matrix=platform_health_matrix,
        )
    else:
        source_plan = _manual_source_plan(
            source_strategy=source_strategy,
            available_platforms=available_platforms,
            crawlers=crawlers,
        )

    claims = extract_claims(
        claim,
        keyword=keyword,
        max_claims=int(getattr(settings, "INVESTIGATION_PREVIEW_MAX_CLAIMS", 6)),
    )
    claims_draft = _to_claims_draft(claims)
    risk_notes = _build_risk_notes(
        claim=claim,
        claims_draft=claims_draft,
        source_plan=source_plan,
    )
    enable_decomposition = payload.get("enable_intent_decomposition")
    if enable_decomposition is None:
        enable_decomposition = bool(
            getattr(settings, "INVESTIGATION_PREVIEW_DECOMPOSITION_ENABLED", False)
        )
    intent_decomposition: Dict[str, Any] | None = None
    search_tasks: List[Dict[str, Any]] = []
    if enable_decomposition:
        intent_decomposition = _build_intent_decomposition(
            claim=claim,
            keyword=keyword,
            claims_draft=claims_draft,
            source_plan=source_plan,
            crawlers=crawlers,
            risk_notes=risk_notes,
        )
        search_tasks = list(intent_decomposition.get("search_tasks") or [])

    status = "ready"
    fallback_reason = None
    fallback_summary = _fallback_intent_summary(
        claim=claim,
        source_plan=source_plan,
        risk_notes=risk_notes,
    )
    intent_summary = fallback_summary
    try:
        timeout_sec = max(
            1,
            int(getattr(settings, "INVESTIGATION_PREVIEW_LLM_TIMEOUT_SEC", 4)),
        )
        client = get_siliconflow_client()
        intent_summary = await asyncio.wait_for(
            client.summarize_intent_preview(
                claim=claim,
                keyword=keyword,
                claims_draft=claims_draft,
                source_plan=source_plan,
                risk_notes=risk_notes,
            ),
            timeout=timeout_sec,
        )
    except Exception as exc:
        status = "degraded"
        fallback_reason = f"PREVIEW_LLM_UNAVAILABLE:{type(exc).__name__}"
        logger.warning(f"preview llm fallback: {exc}")

    if not intent_summary.strip():
        status = "degraded"
        fallback_reason = fallback_reason or "PREVIEW_EMPTY_SUMMARY"
        intent_summary = fallback_summary

    intent_summary = _normalize_intent_summary(
        summary=intent_summary,
        fallback_summary=fallback_summary,
    )

    return {
        "status": status,
        "intent_summary": intent_summary.strip(),
        "event_type": str(source_plan.get("event_type") or "generic_claim"),
        "domain": str(source_plan.get("domain") or "general_news"),
        "claims_draft": claims_draft,
        "source_plan": source_plan,
        "intent_decomposition": intent_decomposition,
        "search_tasks": search_tasks,
        "risk_notes": risk_notes,
        "fallback_reason": fallback_reason,
        "available_platforms": available_platforms,
    }
