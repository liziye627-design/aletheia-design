"""
Investigation 结果汇总与报告渲染相关函数。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.config import settings
from services.external.bocha_search import BochaSearchProvider
from services.external.google_news_search import GoogleNewsSearchProvider
from services.external.searxng_search import SearxngSearchProvider
from services.investigation_helpers import (
    _build_level,
    _keyword_relevance_score,
    _normalize_url,
    _safe_float,
)
from utils.logging import logger


def build_dual_profile_result(
    *,
    enhanced_score: float,
    cross_score: float,
    agent_score: float,
    score_breakdown: Dict[str, Any],
    insufficient: bool,
) -> Dict[str, Any]:
    base = enhanced_score * 0.35 + cross_score * 0.25 + agent_score * 0.40
    coverage = _safe_float(score_breakdown.get("platform_coverage_score"), 0.0)
    specificity = _safe_float(score_breakdown.get("evidence_specificity_score"), 0.0)
    consensus = _safe_float(score_breakdown.get("model_consensus_score"), 0.0)

    tog = max(0.0, min(1.0, base * 0.55 + coverage * 0.2 + specificity * 0.25))
    tob = max(0.0, min(1.0, base * 0.6 + coverage * 0.25 + consensus * 0.15))
    if insufficient:
        tog = min(0.45, tog)
        tob = min(0.45, tob)
    return {
        "tog_result": {"score": round(tog, 4), "level": _build_level(tog)},
        "tob_result": {"score": round(tob, 4), "level": _build_level(tob)},
        "combined_result": {
            "score": round((tog + tob) / 2, 4),
            "level": _build_level((tog + tob) / 2),
        },
    }


def determine_result_status(
    *,
    multi_agent_status: str,
    valid_evidence_count: int,
    target_valid_evidence_min: int,
    live_evidence_count: int,
    live_evidence_target: int,
    platforms_with_data: int,
    min_platforms_with_data: int,
    steps: List[Dict[str, Any]],
) -> str:
    if multi_agent_status == "insufficient_evidence":
        if (
            valid_evidence_count < target_valid_evidence_min
            or platforms_with_data < min_platforms_with_data
        ):
            return "insufficient_evidence"
        return "partial"

    if (
        valid_evidence_count < target_valid_evidence_min
        or platforms_with_data < min_platforms_with_data
    ):
        return "insufficient_evidence"

    if live_evidence_target > 0 and live_evidence_count < live_evidence_target:
        return "partial"

    if any(step.get("status") in {"failed", "partial"} for step in steps):
        return "partial"

    return "complete"


def _parse_domains(raw: str) -> List[str]:
    values = [x.strip().lower() for x in str(raw or "").split(",")]
    return [x for x in values if x]


def _extract_domain(url_value: str) -> str:
    url = str(url_value or "").strip()
    if not url:
        return ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_domain_allowed(domain: str, allowed_domains: List[str]) -> bool:
    host = str(domain or "").strip().lower()
    if not host:
        return False
    for domain_row in allowed_domains:
        dom = str(domain_row or "").strip().lower()
        if not dom:
            continue
        if host == dom or host.endswith(f".{dom}"):
            return True
    return False


def _extract_query_entity(query: str) -> str:
    text = str(query or "").strip()
    if not text:
        return ""
    cjk_parts = re.findall(r"[\u4e00-\u9fff]{2,12}", text)
    if not cjk_parts:
        return ""

    trigger_words = (
        "退役",
        "辟谣",
        "回应",
        "宣布",
        "否认",
        "确认",
        "去世",
        "逝世",
        "被抓",
        "处罚",
    )
    stop_tail = ("吗", "么", "嘛", "呢", "吧", "啊", "了", "是否", "是不是")

    best = ""
    for part in cjk_parts:
        candidate = part
        for tw in trigger_words:
            idx = candidate.find(tw)
            if idx > 0:
                candidate = candidate[:idx]
                break
        for tail in stop_tail:
            if candidate.endswith(tail):
                candidate = candidate[: -len(tail)]
        candidate = candidate.strip()
        if len(candidate) >= 2 and len(candidate) > len(best):
            best = candidate
    return best


def _entity_hit(text: str, entity: str) -> bool:
    if not entity:
        return True
    return entity in str(text or "")


def _extract_event_hints(query: str) -> List[str]:
    text = str(query or "").strip()
    if not text:
        return []
    trigger_words = (
        "退役",
        "官宣",
        "辟谣",
        "回应",
        "宣布",
        "否认",
        "确认",
        "去世",
        "逝世",
        "复出",
        "被抓",
        "处罚",
        "通报",
        "事故",
        "裁员",
        "停产",
    )
    out: List[str] = []
    for word in trigger_words:
        if word in text and word not in out:
            out.append(word)
    return out


def _event_hint_hit(text: str, hints: List[str]) -> bool:
    if not hints:
        return True
    body = str(text or "")
    return any(h in body for h in hints)


def _provider_chain_from_settings() -> List[str]:
    chain_raw = str(
        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_PROVIDER_CHAIN", "")
    ).strip()
    single = str(
        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_PROVIDER", "google_news_rss")
    ).strip()
    rows = [
        x.strip().lower()
        for x in (chain_raw if chain_raw else single).split(",")
        if x.strip()
    ]
    if not rows:
        rows = ["google_news_rss"]
    return list(dict.fromkeys(rows))


def _build_search_providers() -> List[tuple[str, Any]]:
    out: List[tuple[str, Any]] = []
    for provider_name in _provider_chain_from_settings():
        if provider_name == "google_news_rss":
            out.append((provider_name, GoogleNewsSearchProvider()))
            continue
        if provider_name in {"bocha_web", "bocha", "bocha_api"}:
            provider = BochaSearchProvider()
            if provider.enabled:
                out.append(("bocha_web", provider))
            else:
                logger.warning("bocha provider configured but api key is empty")
            continue
        if provider_name == "searxng":
            provider = SearxngSearchProvider()
            if provider.enabled:
                out.append((provider_name, provider))
            else:
                logger.warning("searxng provider configured but base url is empty")
            continue
        logger.warning("unsupported external search provider: %s", provider_name)
    return out


async def check_external_sources(
    keyword: str,
    *,
    allowed_domains: Optional[List[str]] = None,
    limit: Optional[int] = None,
    whitelist_only: bool = False,
) -> List[Dict[str, Any]]:
    query = str(keyword or "").strip()
    if not query:
        return []
    if not bool(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_ENABLED", True)):
        return []

    configured_domains = _parse_domains(
        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_ALLOWED_DOMAINS", "")
    )
    scoped_domains = [
        str(x).strip().lower()
        for x in (allowed_domains or configured_domains)
        if str(x).strip()
    ]
    # `limit` 按“每个 provider 的上限”理解，避免第一个 provider 吃满后后续 provider 不再执行。
    max_results_per_provider = max(
        1,
        int(
            limit
            if limit is not None
            else getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS", 20)
        ),
    )
    per_provider_limit = max(
        1,
        int(
            getattr(
                settings,
                "INVESTIGATION_EXTERNAL_SEARCH_PER_PROVIDER_LIMIT",
                max_results_per_provider,
            )
        ),
    )
    per_provider_limit = min(per_provider_limit, max_results_per_provider)
    min_relevance = max(
        0.0,
        min(
            1.0,
            float(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MIN_RELEVANCE", 0.15)),
        ),
    )
    require_entity_hit = bool(
        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_ENTITY_HIT", True)
    )
    require_event_hint_hit = bool(
        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_REQUIRE_EVENT_HINT_HIT", False)
    )
    entity = _extract_query_entity(query) if require_entity_hit else ""
    event_hints = _extract_event_hints(query) if require_event_hint_hit else []
    providers = _build_search_providers()
    if not providers:
        return []
    max_total_results = max(
        1,
        int(
            getattr(
                settings,
                "INVESTIGATION_EXTERNAL_SEARCH_MAX_TOTAL_RESULTS",
                max_results_per_provider * max(1, len(providers)),
            )
        ),
    )

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for provider_name, provider in providers:
        try:
            rows = await provider.search_news(
                query=query,
                limit=per_provider_limit,
                allowed_domains=scoped_domains,
            )
        except Exception as exc:
            logger.warning(
                f"external provider failed ({provider_name}): {type(exc).__name__}"
            )
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            url = _normalize_url(str(item.get("url") or ""))
            if not url or url in seen:
                continue
            seen.add(url)
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            source_domain = (
                str(item.get("source_domain") or "").strip().lower()
                or _extract_domain(url)
            )
            domain_allowed = (
                _is_domain_allowed(source_domain, scoped_domains) if scoped_domains else True
            )
            if whitelist_only and not domain_allowed:
                continue
            relevance_score = _keyword_relevance_score(
                keyword=query,
                text_blob=f"{title}\n{summary}",
            )
            entity_hit = _entity_hit(f"{title}\n{summary}", entity)
            event_hit = _event_hint_hit(f"{title}\n{summary}", event_hints)
            if require_entity_hit and entity and not entity_hit:
                continue
            if require_event_hint_hit and event_hints and not event_hit:
                continue
            if float(relevance_score) < min_relevance:
                continue
            out.append(
                {
                    "source": str(
                        item.get("source_name")
                        or item.get("source")
                        or item.get("provider")
                        or "external_search"
                    ),
                    "source_name": str(item.get("source_name") or ""),
                    "provider": str(item.get("provider") or provider_name),
                    "url": url,
                    "title": title,
                    "summary": summary[:1200],
                    "query": str(item.get("query") or query),
                    "source_domain": source_domain,
                    "published_at": str(item.get("published_at") or ""),
                    "reachable": bool(item.get("reachable", True)),
                    "domain_allowed": bool(domain_allowed),
                    "relevance_score": float(relevance_score),
                    "entity_hit": bool(entity_hit),
                    "event_hint_hit": bool(event_hit),
                }
            )
            if len(out) >= max_total_results:
                break
        if len(out) >= max_total_results:
            break
    return out


def _get_evidence_credibility_score(item: Dict[str, Any]) -> float:
    """计算证据的可信度得分，用于排序"""
    # 优先使用 source_tier (1=最高, 3=最低)
    tier = int(item.get("source_tier") or 3)
    tier_score = (4 - tier) / 3.0  # Tier1=1.0, Tier2=0.67, Tier3=0.33
    
    # 其次使用 credibility_score
    cred_score = _safe_float(item.get("credibility_score"), 0.5)
    
    # 再考虑相关性得分
    rel_score = _safe_float(item.get("relevance_score"), 0.5)
    
    # 综合得分：tier权重最高
    return tier_score * 0.5 + cred_score * 0.3 + rel_score * 0.2


def build_report_sections(
    *,
    template: Dict[str, Any],
    keyword: str,
    enhanced: Dict[str, Any],
    credibility: Dict[str, Any],
    multi_agent: Dict[str, Any],
    evidence_registry: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
    source_trace: Optional[Dict[str, Any]] = None,
    opinion_monitoring: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    section_defs = template.get("sections") or []
    final_score = _safe_float(enhanced.get("reasoning_chain", {}).get("final_score", 0))
    final_level = enhanced.get("reasoning_chain", {}).get("final_level", "UNCERTAIN")

    # 证据池优先：primary > background > 其他，避免背景条目挤占核心证据位
    external_evidence = [
        row
        for row in (evidence_registry or [])
        if isinstance(row, dict)
        and str(row.get("evidence_origin") or "external") == "external"
    ]
    primary_evidence = [
        row
        for row in external_evidence
        if str(row.get("evidence_class") or "background").lower() == "primary"
    ]
    background_evidence = [
        row
        for row in external_evidence
        if str(row.get("evidence_class") or "background").lower() == "background"
    ]
    other_evidence = [
        row
        for row in external_evidence
        if row not in primary_evidence and row not in background_evidence
    ]
    primary_sorted = sorted(primary_evidence, key=_get_evidence_credibility_score, reverse=True)
    background_sorted = sorted(background_evidence, key=_get_evidence_credibility_score, reverse=True)
    other_sorted = sorted(other_evidence, key=_get_evidence_credibility_score, reverse=True)
    top_evidence = (primary_sorted + background_sorted + other_sorted)[:8]
    
    ev_lines = []
    for item in top_evidence:
        tier = int(item.get("source_tier") or 3)
        eclass = str(item.get("evidence_class") or "background").lower()
        class_tag = "EVIDENCE" if eclass == "primary" else ("CONTEXT" if eclass == "background" else "NOISE")
        ev_lines.append(
            "- [{class_tag}][T{tier}] {source}: {snippet} | published_at={published_at} | mode={mode}".format(
                class_tag=class_tag,
                tier=tier,
                source=item.get("source_name"),
                snippet=(item.get("snippet") or "")[:100],
                published_at=item.get("published_at") or "unknown",
                mode=item.get("retrieval_mode") or "live",
            )
        )
    step_refs = [s.get("id") for s in steps]
    ev_ids = [item.get("id") for item in top_evidence]
    has_timeline_section = False
    has_suggestion_section = False

    for sec in section_defs:
        title = str(sec.get("title", ""))
        base_md = str(sec.get("markdown", "")).strip()
        rendered = base_md
        title_lower = title.lower()
        if "摘要" in title or "summary" in title_lower:
            digest_summary = (
                (multi_agent.get("llm_digest") or {}).get("summary")
                if isinstance(multi_agent.get("llm_digest"), dict)
                else ""
            )
            rendered = (
                f"关键词：{keyword}\n\n"
                f"最终可信度：{final_score:.2f}（{final_level}）\n\n"
                f"跨平台可信度：{_safe_float(credibility.get('credibility_score', 0)):.2f}\n\n"
                f"多Agent建议：{multi_agent.get('recommendation', 'N/A')}\n\n"
                f"低成本模型摘要：{digest_summary or 'N/A'}"
            )
        elif "证据" in title:
            rendered = "### 证据清单（按可信度排序）\n" + ("\n".join(ev_lines) if ev_lines else "暂无可展示证据")
        elif "时间线" in title or "timeline" in title_lower or "溯源" in title:
            has_timeline_section = True
            timeline_rows = list((source_trace or {}).get("timeline") or [])
            if timeline_rows:
                tl_lines = []
                for row in timeline_rows[:12]:
                    tl_lines.append(
                        "- {event_time} | {source} | T{tier} | {mode} | {url}".format(
                            event_time=str(row.get("event_time") or "unknown"),
                            source=str(row.get("source_name") or "unknown"),
                            tier=int(row.get("source_tier") or 3),
                            mode=str(row.get("retrieval_mode") or "live"),
                            url=str(row.get("url") or "no-url"),
                        )
                    )
                rendered = (
                    "### 最早信息流溯源\n"
                    f"- first_seen_at: {(source_trace or {}).get('first_seen_at') or 'unknown'}\n"
                    f"- earliest_published_at: {(source_trace or {}).get('earliest_published_at') or 'unknown'}\n"
                    f"- timeline_count: {int((source_trace or {}).get('timeline_count') or 0)}\n\n"
                    + "\n".join(tl_lines)
                )
            else:
                rendered = "### 最早信息流溯源\n暂无可排序时间证据"
        elif "建议" in title or "改进" in title or "improvement" in title_lower:
            has_suggestion_section = True
            rendered = _build_improvement_suggestions(
                final_score=final_score,
                final_level=final_level,
                multi_agent=multi_agent,
                evidence_registry=evidence_registry,
                steps=steps,
            )
        out.append(
            {
                "id": sec.get("id"),
                "title": title,
                "content_markdown": rendered,
                "evidence_ids": ev_ids,
                "step_refs": step_refs,
            }
        )
    if not has_timeline_section:
        timeline_rows = list((source_trace or {}).get("timeline") or [])
        if timeline_rows:
            tl_lines = []
            for row in timeline_rows[:10]:
                tl_lines.append(
                    "- {event_time} | {source} | T{tier} | {url}".format(
                        event_time=str(row.get("event_time") or "unknown"),
                        source=str(row.get("source_name") or "unknown"),
                        tier=int(row.get("source_tier") or 3),
                        url=str(row.get("url") or "no-url"),
                    )
                )
            out.append(
                {
                    "id": "source-timeline",
                    "title": "信息溯源时间线",
                    "content_markdown": (
                        "### 最早信息流溯源\n"
                        f"- first_seen_at: {(source_trace or {}).get('first_seen_at') or 'unknown'}\n"
                        f"- earliest_published_at: {(source_trace or {}).get('earliest_published_at') or 'unknown'}\n\n"
                        + "\n".join(tl_lines)
                    ),
                    "evidence_ids": [
                        row.get("evidence_id")
                        for row in timeline_rows[:10]
                        if row.get("evidence_id")
                    ],
                    "step_refs": step_refs,
                }
            )
    
    # 在底部添加改进建议章节
    if not has_suggestion_section:
        out.append(
            {
                "id": "improvement-suggestions",
                "title": "改进建议",
                "content_markdown": _build_improvement_suggestions(
                    final_score=final_score,
                    final_level=final_level,
                    multi_agent=multi_agent,
                    evidence_registry=evidence_registry,
                    steps=steps,
                ),
                "evidence_ids": [],
                "step_refs": step_refs,
            }
        )

    opinion = dict(opinion_monitoring or {})
    if opinion:
        suspicious_ratio = float(opinion.get("suspicious_ratio") or 0.0)
        suspicious_accounts = list(opinion.get("top_suspicious_accounts") or [])
        sample_comments = list(opinion.get("sample_comments") or [])
        lines = [
            "### 评论与水军风险",
            f"- total_comments: {int(opinion.get('total_comments') or 0)}",
            f"- unique_accounts: {int(opinion.get('unique_accounts_count') or 0)}",
            f"- suspicious_accounts: {int(opinion.get('suspicious_accounts_count') or 0)}",
            f"- suspicious_ratio: {round(suspicious_ratio * 100, 2)}%",
            f"- risk_level: {str(opinion.get('risk_level') or 'unknown').upper()}",
            f"- comment_target_reached: {bool(opinion.get('comment_target_reached'))}",
        ]
        if suspicious_accounts:
            lines.append("")
            lines.append("#### 可疑账号样本")
            for row in suspicious_accounts[:5]:
                lines.append(
                    "- {platform}/{user_id} | score={score} | comments={count}".format(
                        platform=str(row.get("platform") or "unknown"),
                        user_id=str(row.get("user_id") or "unknown"),
                        score=round(float(row.get("risk_score") or 0.0), 4),
                        count=int(row.get("comment_count") or 0),
                    )
                )
        if sample_comments:
            lines.append("")
            lines.append("#### 评论样本")
            for row in sample_comments[:5]:
                lines.append(
                    "- [{platform}] {author}: {text}".format(
                        platform=str(row.get("platform") or "unknown"),
                        author=str(row.get("author_name") or "unknown"),
                        text=str(row.get("content_text") or "")[:100],
                    )
                )
        out.append(
            {
                "id": "opinion-monitoring",
                "title": "舆情评论与水军风险",
                "content_markdown": "\n".join(lines),
                "evidence_ids": [],
                "step_refs": step_refs,
            }
        )
    return out


def _build_improvement_suggestions(
    *,
    final_score: float,
    final_level: str,
    multi_agent: Dict[str, Any],
    evidence_registry: List[Dict[str, Any]],
    steps: List[Dict[str, Any]],
) -> str:
    """构建改进建议章节"""
    suggestions = []
    
    # 1. 基于可信度得分的建议
    if final_score < 0.3:
        suggestions.append("- **可信度较低**：建议增加更多权威来源进行交叉验证")
    elif final_score < 0.6:
        suggestions.append("- **可信度中等**：建议补充官方渠道或主流媒体报道")
    else:
        suggestions.append("- **可信度较高**：证据充分，结论较为可靠")
    
    # 2. 基于证据层级分布的建议
    tier_counts = {1: 0, 2: 0, 3: 0}
    for ev in evidence_registry:
        tier = int(ev.get("source_tier") or 3)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    if tier_counts[1] == 0:
        suggestions.append("- **缺少Tier1权威来源**：建议补充新华社、央视等官方媒体来源")
    if tier_counts[1] + tier_counts[2] < 3:
        suggestions.append("- **权威来源不足**：建议增加主流媒体或官方账号的报道")
    
    # 3. 基于步骤状态的建议
    failed_steps = [s for s in steps if s.get("status") == "failed"]
    if failed_steps:
        step_names = [s.get("id", "未知步骤") for s in failed_steps[:3]]
        suggestions.append(f"- **部分步骤失败**：{', '.join(step_names)} 执行异常，建议检查相关配置")
    
    # 4. 多Agent建议
    agent_rec = multi_agent.get("recommendation", "")
    if agent_rec:
        suggestions.append(f"- **处置建议**：{agent_rec}")
    
    # 5. 证据数量建议
    if len(evidence_registry) < 10:
        suggestions.append("- **证据数量较少**：建议扩大搜索范围或增加关键词变体")
    
    if not suggestions:
        suggestions.append("- 当前核验结果较为完善，无需额外改进")
    
    return "### 改进建议\n\n" + "\n".join(suggestions)
