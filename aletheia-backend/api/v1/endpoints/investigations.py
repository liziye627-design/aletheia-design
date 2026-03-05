"""
Investigation 编排 API
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from services.external.mediacrawler_process import get_mediacrawler_process_manager
from services.investigation_engine import (
    get_investigation_manager,
    get_investigation_orchestrator,
)
from services.investigation_preview import build_preview
from services.layer1_perception.crawler_manager import get_crawler_manager
from services.publish_suggestions import build_geo_report_content, build_publish_suggestions
from services.insights.mindmap_generator import build_mindmap_from_run
from services.insights.common_analysis import build_common_analysis_from_run
from services.insights.value_mining_engine import build_value_insights
from services.insights.content_generation_engine import generate_article
from core.sqlite_database import get_sqlite_db
from uuid import uuid4

router = APIRouter()


class InvestigationRunRequest(BaseModel):
    claim: str = Field(..., min_length=1, max_length=5000)
    keyword: Optional[str] = Field(default=None, max_length=256)
    human_notes: Optional[str] = Field(default=None, max_length=2000)
    platforms: Optional[List[str]] = None
    mode: Literal["dual", "enhanced", "search"] = "dual"
    audience_profile: Literal["tob", "tog", "both"] = "both"
    report_template_id: str = "deep-research-report"
    limit_per_platform: int = Field(default=40, ge=1, le=100)
    target_valid_evidence_min: int = Field(default=80, ge=10, le=2000)
    live_evidence_target: int = Field(default=20, ge=0, le=2000)
    quality_mode: Literal["strict", "balanced"] = "balanced"
    max_runtime_sec: int = Field(default=180, ge=30, le=600)
    min_platforms_with_data: int = Field(default=4, ge=1, le=40)
    free_source_only: bool = True
    source_strategy: Literal["auto", "stable_mixed_v1", "full"] = "auto"
    source_profile: Literal["stable_mixed_v1", "full"] = "stable_mixed_v1"
    strict_pipeline: Literal["staged_strict", "full_strict"] = "staged_strict"
    use_mediacrawler: Optional[bool] = None
    mediacrawler_platforms: Optional[
        List[Literal["weibo", "xiaohongshu", "douyin", "zhihu"]]
    ] = None
    mediacrawler_force_run: Optional[bool] = None
    mediacrawler_timeout_sec: Optional[int] = Field(default=None, ge=20, le=600)
    enable_cached_evidence: bool = True
    phase1_target_valid_evidence: int = Field(default=30, ge=10, le=1000)
    phase1_deadline_sec: int = Field(default=70, ge=10, le=600)
    phase1_live_rescue_timeout_sec: int = Field(default=12, ge=3, le=120)
    max_live_rescue_rounds: int = Field(default=3, ge=1, le=10)
    force_live_before_cache: bool = True
    max_concurrent_platforms_fast: int = Field(default=6, ge=1, le=20)
    max_concurrent_platforms_fill: int = Field(default=4, ge=1, le=20)
    enhanced_reasoning_timeout_sec: Optional[int] = Field(default=None, ge=3, le=180)
    enable_network_precheck: Optional[bool] = None
    network_precheck_timeout_sec: Optional[float] = Field(default=None, ge=0.5, le=10.0)
    network_precheck_fail_ratio_threshold: Optional[float] = Field(default=None, ge=0.3, le=1.0)
    network_precheck_hosts: Optional[List[str]] = None
    enable_opinion_monitoring: bool = True
    opinion_comment_target: int = Field(default=120, ge=20, le=2000)
    opinion_comment_limit_per_post: int = Field(default=40, ge=5, le=200)
    opinion_max_posts_per_platform: int = Field(default=2, ge=1, le=10)
    opinion_max_platforms: int = Field(default=6, ge=1, le=12)
    allow_synthetic_comments: bool = False
    iteration_enabled: Optional[bool] = None
    iteration_rounds: Optional[int] = Field(default=None, ge=1, le=6)
    iteration_max_queries: Optional[int] = Field(default=None, ge=1, le=8)
    confirmed_preview_id: Optional[str] = Field(default=None, max_length=64)
    confirmed_claims: Optional[List[str]] = None
    confirmed_platforms: Optional[List[str]] = None

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode_aliases(cls, value):
        if value is None:
            return value
        normalized = str(value).strip().lower()
        aliases = {
            "enhanced_reasoning": "enhanced",
            "enhanced-mode": "enhanced",
            "dual_mode": "dual",
            "dual-mode": "dual",
            "search_first": "search",
            "search-priority": "search",
        }
        return aliases.get(normalized, normalized)


class InvestigationRunAccepted(BaseModel):
    run_id: str
    accepted_at: str
    initial_status: str


class InvestigationPreviewRequest(BaseModel):
    claim: str = Field(..., min_length=1, max_length=5000)
    keyword: Optional[str] = Field(default=None, max_length=256)
    platforms: Optional[List[str]] = None
    mode: Literal["dual", "enhanced", "search"] = "dual"
    source_strategy: Literal["auto", "stable_mixed_v1", "full"] = "auto"


class PreviewClaimDraft(BaseModel):
    claim_id: str
    text: str
    type: str
    confidence: float
    editable: bool = True


class PreviewSearchTask(BaseModel):
    task_id: str
    query: str
    preferred_tiers: List[int] = Field(default_factory=list)
    fallback_tiers: List[int] = Field(default_factory=list)
    blocked_tiers: List[int] = Field(default_factory=list)
    platforms: List[str] = Field(default_factory=list)


class PreviewIntentDecomposition(BaseModel):
    core_claim: str
    keyword: str
    claims: List[PreviewClaimDraft] = Field(default_factory=list)
    tiered_platforms: Dict[str, List[str]] = Field(default_factory=dict)
    platform_tiers: Dict[str, int] = Field(default_factory=dict)
    search_tasks: List[PreviewSearchTask] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)


class InvestigationPreviewResponse(BaseModel):
    preview_id: str
    status: Literal["ready", "degraded"]
    intent_summary: str
    event_type: str
    domain: str
    claims_draft: List[PreviewClaimDraft]
    source_plan: Dict[str, Any]
    risk_notes: List[str]
    fallback_reason: Optional[str] = None
    expires_at: str
    intent_decomposition: Optional[PreviewIntentDecomposition] = None
    search_tasks: List[PreviewSearchTask] = Field(default_factory=list)


class InvestigationProbeRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=256)
    platforms: Optional[List[str]] = None
    limit_per_platform: int = Field(default=8, ge=1, le=50)
    rounds: int = Field(default=3, ge=1, le=10)


class PublishSuggestionItem(BaseModel):
    title: str
    text: str
    hashtags: List[str] = Field(default_factory=list)
    angle: Optional[str] = None


class PublishSuggestionResponse(BaseModel):
    tweet_suggestions: List[PublishSuggestionItem]
    mindmap_mermaid: str
    creative_directions: List[str]
    hotspot_benefits: List[str]
    generated_at: Optional[str] = None


class InsightArticleRequest(BaseModel):
    value_direction: Optional[str] = None
    template_type: str = "insight"
    platform: str = "weibo"


@router.post("/preview", response_model=InvestigationPreviewResponse)
async def preview_investigation(request: InvestigationPreviewRequest):
    manager = get_investigation_manager()
    preview_result = await build_preview(request.model_dump())
    preview_record = await manager.create_preview(
        payload=request.model_dump(),
        preview_result=preview_result,
    )
    return InvestigationPreviewResponse(
        preview_id=str(preview_record.get("preview_id") or ""),
        status=str(preview_result.get("status") or "degraded"),
        intent_summary=str(preview_result.get("intent_summary") or ""),
        event_type=str(preview_result.get("event_type") or "generic_claim"),
        domain=str(preview_result.get("domain") or "general_news"),
        claims_draft=list(preview_result.get("claims_draft") or []),
        source_plan=dict(preview_result.get("source_plan") or {}),
        risk_notes=[str(x) for x in list(preview_result.get("risk_notes") or [])],
        fallback_reason=(
            str(preview_result.get("fallback_reason"))
            if preview_result.get("fallback_reason")
            else None
        ),
        expires_at=str(preview_record.get("expires_at") or ""),
        intent_decomposition=(
            preview_result.get("intent_decomposition")
            if isinstance(preview_result.get("intent_decomposition"), dict)
            else None
        ),
        search_tasks=list(preview_result.get("search_tasks") or []),
    )


@router.post("/run", response_model=InvestigationRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def run_investigation(request: InvestigationRunRequest):
    manager = get_investigation_manager()
    orchestrator = get_investigation_orchestrator()
    payload = request.model_dump()
    preview_id = str(payload.get("confirmed_preview_id") or "").strip()
    if preview_id:
        preview = manager.get_preview(preview_id)
        if not preview:
            raise HTTPException(
                status_code=422,
                detail="PREVIEW_EXPIRED",
            )
        manager.mark_preview_confirmed(preview_id)
        confirmed_claims = [
            str(x).strip()
            for x in list(payload.get("confirmed_claims") or [])
            if str(x).strip()
        ]
        confirmed_platforms = [
            str(x).strip()
            for x in list(payload.get("confirmed_platforms") or [])
            if str(x).strip()
        ]
        if confirmed_claims:
            payload["claim"] = "\n".join(confirmed_claims)
        if confirmed_platforms:
            payload["platforms"] = confirmed_platforms
        payload["preview_context"] = {
            "preview_id": preview_id,
            "preview_created_at": preview.get("created_at"),
            "preview_expires_at": preview.get("expires_at"),
            "confirmed_claim_count": len(confirmed_claims),
            "confirmed_platform_count": len(confirmed_platforms),
            "preview_status": preview.get("status"),
        }

    run = await manager.create_run(payload)
    run_id = run["run_id"]
    run["request"]["accepted_at"] = run["accepted_at"]

    async def _guarded_execute():
        budget_sec = max(30, int(run["request"].get("max_runtime_sec") or 180))
        timeout_sec = budget_sec + 30
        try:
            await asyncio.wait_for(
                orchestrator.execute(run_id=run_id, req=run["request"]),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            await manager.append_event(
                run_id,
                "warning",
                {
                    "code": "RUN_TIMEOUT_WATCHDOG",
                    "message": (
                        f"run exceeded watchdog timeout ({timeout_sec}s), force terminated"
                    ),
                },
            )
            await manager.append_event(
                run_id,
                "run_failed",
                {
                    "run_id": run_id,
                    "error": f"RUN_TIMEOUT_WATCHDOG({timeout_sec}s)",
                },
            )
            await manager.set_status(
                run_id,
                "failed",
                error=f"RUN_TIMEOUT_WATCHDOG({timeout_sec}s)",
            )

    # 异步执行，不阻塞请求
    asyncio.create_task(_guarded_execute())
    return InvestigationRunAccepted(
        run_id=run_id,
        accepted_at=run["accepted_at"],
        initial_status=run["status"],
    )


@router.get("/diagnostics/sources")
async def list_investigation_sources():
    crawlers = get_crawler_manager()
    platform_domains = crawlers.get_all_platform_domains()
    reason_stats = crawlers.get_platform_reason_stats()
    health_snapshot = crawlers.get_platform_health_snapshot()
    source_matrix = (
        crawlers.get_platform_source_matrix()
        if hasattr(crawlers, "get_platform_source_matrix")
        else {}
    )
    available_platforms = sorted(list(getattr(crawlers, "crawlers", {}).keys()))
    return {
        "available_platforms": available_platforms,
        "platform_count": len(available_platforms),
        "platform_domains": platform_domains,
        "platform_health_snapshot": health_snapshot,
        "platform_reason_stats": reason_stats,
        "platform_health_matrix": source_matrix,
    }


@router.post("/diagnostics/probe")
async def probe_investigation_sources(request: InvestigationProbeRequest):
    crawlers = get_crawler_manager()
    available_platforms = set(getattr(crawlers, "crawlers", {}).keys())
    if request.platforms:
        platforms = request.platforms
    else:
        stable_defaults = (
            crawlers.get_source_profile_platforms("stable_mixed_v1")
            if hasattr(crawlers, "get_source_profile_platforms")
            else []
        )
        platforms = stable_defaults or sorted(list(available_platforms))
    platforms = [p for p in platforms if p in available_platforms]
    if not platforms:
        raise HTTPException(status_code=400, detail="No valid platforms to probe")

    rounds = max(1, int(request.rounds))
    round_results: List[Dict[str, Dict[str, Any]]] = []
    for _ in range(rounds):
        round_results.append(
            await crawlers.search_across_platforms_verbose(
                keyword=request.keyword,
                platforms=platforms,
                limit_per_platform=request.limit_per_platform,
            )
        )

    merged_probe: Dict[str, Dict[str, Any]] = {}
    total_items = 0
    platforms_with_data = 0
    reason_counter: Counter[str] = Counter()
    issue_platforms: List[Dict[str, Any]] = []
    for platform in platforms:
        statuses = []
        elapsed_ms_samples = []
        total_platform_items = 0
        reason_stats: Counter[str] = Counter()
        success_rounds = 0
        latest_row: Dict[str, Any] = {}
        for round_probe in round_results:
            row = (round_probe or {}).get(platform) or {}
            latest_row = row
            status = str(row.get("status") or "unknown")
            reason_code = str(row.get("reason_code") or "UNKNOWN")
            items_collected = int(row.get("items_collected") or 0)
            elapsed_ms = int(row.get("elapsed_ms") or 0)

            statuses.append(status)
            elapsed_ms_samples.append(elapsed_ms)
            total_platform_items += items_collected
            reason_stats[reason_code] += 1
            if items_collected > 0:
                success_rounds += 1

        elapsed_sorted = sorted(elapsed_ms_samples)
        p50 = elapsed_sorted[len(elapsed_sorted) // 2] if elapsed_sorted else 0
        p95 = (
            elapsed_sorted[min(len(elapsed_sorted) - 1, int(len(elapsed_sorted) * 0.95))]
            if elapsed_sorted
            else 0
        )

        top_reason = reason_stats.most_common(1)[0][0] if reason_stats else "UNKNOWN"
        final_status = "ok" if success_rounds > 0 else str(latest_row.get("status") or "unknown")
        merged_probe[platform] = {
            "platform": platform,
            "status": final_status,
            "reason_code": top_reason,
            "reason_stats": dict(reason_stats),
            "items_collected": int(total_platform_items),
            "success_rounds": int(success_rounds),
            "rounds": rounds,
            "elapsed_ms_p50": int(p50),
            "elapsed_ms_p95": int(p95),
            "last_message": latest_row.get("message", ""),
        }

        total_items += int(total_platform_items)
        if total_platform_items > 0:
            platforms_with_data += 1

        reason_counter[top_reason] += 1
        if final_status != "ok" or total_platform_items <= 0:
            issue_platforms.append(
                {
                    "platform": platform,
                    "status": final_status,
                    "reason_code": top_reason,
                    "items_collected": int(total_platform_items),
                    "success_rounds": int(success_rounds),
                    "rounds": rounds,
                    "elapsed_ms_p95": int(p95),
                    "message": latest_row.get("message", ""),
                }
            )
    return {
        "keyword": request.keyword,
        "platforms": platforms,
        "limit_per_platform": request.limit_per_platform,
        "rounds": rounds,
        "platforms_with_data": platforms_with_data,
        "total_items": total_items,
        "reason_stats": dict(reason_counter),
        "issue_platforms": issue_platforms,
        "probe": merged_probe,
        "raw_rounds": round_results,
    }


@router.get("/diagnostics/health-matrix")
async def get_investigation_source_health_matrix():
    crawlers = get_crawler_manager()
    matrix = (
        crawlers.get_platform_source_matrix()
        if hasattr(crawlers, "get_platform_source_matrix")
        else {}
    )
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "platform_count": len(matrix),
        "platform_health_matrix": matrix,
    }


@router.get("/diagnostics/mediacrawler")
async def get_investigation_mediacrawler_diagnostics():
    manager = get_mediacrawler_process_manager()
    return await manager.diagnostics()


@router.get("/health")
async def get_investigation_health():
    manager = get_investigation_manager()
    runs = list((manager._runs or {}).values()) if hasattr(manager, "_runs") else []
    status_counter: Counter[str] = Counter()
    for row in runs:
        status_counter[str(row.get("status") or "unknown")] += 1
    preview_metrics = (
        manager.get_preview_metrics() if hasattr(manager, "get_preview_metrics") else {}
    )
    return {
        "ok": True,
        "service": "investigations",
        "run_count": len(runs),
        "status_breakdown": dict(status_counter),
        "preview_metrics": preview_metrics,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/{run_id}")
async def get_investigation_result(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")

    if run.get("result"):
        result = dict(run["result"] or {})
        acq = dict(result.get("acquisition_report") or {})
        if result.get("valid_evidence_count") is None:
            result["valid_evidence_count"] = int(acq.get("valid_evidence_count") or 0)
        if result.get("live_evidence_count") is None:
            result["live_evidence_count"] = int(acq.get("live_evidence_count") or 0)
        if result.get("cached_evidence_count") is None:
            result["cached_evidence_count"] = int(acq.get("cached_evidence_count") or 0)

        if result.get("duration_sec") is None:
            accepted_at = result.get("accepted_at")
            completed_at = result.get("completed_at")
            duration_sec = None
            if accepted_at and completed_at:
                try:
                    started = datetime.fromisoformat(str(accepted_at))
                    finished = datetime.fromisoformat(str(completed_at))
                    duration_sec = max(
                        0.0,
                        round((finished - started).total_seconds(), 3),
                    )
                except Exception:
                    duration_sec = None
            result["duration_sec"] = duration_sec

        if not result.get("status"):
            result["status"] = run.get("status", "unknown")

        if not isinstance(result.get("claim_analysis"), dict):
            result["claim_analysis"] = {
                "claims": [],
                "review_queue": [],
                "claim_reasoning": [],
                "matrix_summary": {
                    "tier1_count": 0,
                    "tier2_count": 0,
                    "tier3_count": 0,
                    "tier4_count": 0,
                },
                "run_verdict": "UNCERTAIN",
                "summary": {},
            }
        elif not isinstance(result.get("claim_analysis", {}).get("claim_reasoning"), list):
            result["claim_analysis"]["claim_reasoning"] = []
        if not isinstance(result.get("source_plan"), dict):
            result["source_plan"] = {
                "event_type": "generic_claim",
                "domain": "general_news",
                "domain_keywords": [],
                "plan_version": "manual_default",
                "selection_confidence": 0.0,
                "must_have_platforms": [],
                "candidate_platforms": [],
                "excluded_platforms": [],
                "selected_platforms": [],
                "selection_reasons": [],
                "risk_notes": [],
            }
        else:
            result["source_plan"].setdefault("domain_keywords", [])
            result["source_plan"].setdefault("plan_version", "auto_v2_precision")
            result["source_plan"].setdefault("selection_confidence", 0.0)
        if not isinstance(result.get("opinion_monitoring"), dict):
            result["opinion_monitoring"] = {
                "status": "NOT_RUN",
                "discovery_mode": "reuse_search_results",
                "synthetic_comment_mode": False,
                "keyword": result.get("search", {}).get("keyword") if isinstance(result.get("search"), dict) else "",
                "comment_target": 120,
                "total_comments": 0,
                "real_comment_count": 0,
                "synthetic_comment_count": 0,
                "sidecar_comment_count": 0,
                "sidecar_failures": [],
                "real_comment_ratio": 0.0,
                "real_comment_target_reached": False,
                "unique_accounts_count": 0,
                "suspicious_accounts_count": 0,
                "suspicious_ratio": 0.0,
                "risk_level": "unknown",
                "risk_flags": [],
                "comment_target_reached": False,
                "top_suspicious_accounts": [],
                "sample_comments": [],
                "summary_text": "评论监测尚未执行。",
            }
        result.setdefault("acquisition_report", {})
        result["acquisition_report"].setdefault(
            "external_evidence_count",
            int(result.get("valid_evidence_count") or 0),
        )
        result["acquisition_report"].setdefault("derived_evidence_count", 0)
        result["acquisition_report"].setdefault("synthetic_context_count", 0)
        result["acquisition_report"].setdefault(
            "external_primary_count",
            int(result["acquisition_report"].get("primary_count") or 0),
        )
        result["acquisition_report"].setdefault(
            "external_background_count",
            int(result["acquisition_report"].get("background_count") or 0),
        )
        result["acquisition_report"].setdefault(
            "external_noise_count",
            int(result["acquisition_report"].get("noise_count") or 0),
        )
        result["acquisition_report"].setdefault("mediacrawler_live_count", 0)
        result["acquisition_report"].setdefault("native_live_count", 0)
        result["acquisition_report"].setdefault("mediacrawler_platforms_hit", [])
        result["acquisition_report"].setdefault("mediacrawler_failures", [])
        result["opinion_monitoring"].setdefault("sidecar_comment_count", 0)
        result["opinion_monitoring"].setdefault("sidecar_failures", [])
        result["opinion_monitoring"].setdefault(
            "real_comment_count", int(result["opinion_monitoring"].get("total_comments") or 0)
        )
        result["opinion_monitoring"].setdefault("synthetic_comment_count", 0)
        result["opinion_monitoring"].setdefault(
            "real_comment_ratio",
            round(
                float(result["opinion_monitoring"].get("real_comment_count") or 0)
                / float(max(1, int(result["opinion_monitoring"].get("total_comments") or 0))),
                4,
            ),
        )
        result["opinion_monitoring"].setdefault(
            "real_comment_target_reached",
            bool(
                int(result["opinion_monitoring"].get("real_comment_count") or 0)
                >= int(result["opinion_monitoring"].get("comment_target") or 0)
            ),
        )
        if not isinstance(result.get("step_summaries"), list):
            result["step_summaries"] = []

        nde = result.get("no_data_explainer")
        if isinstance(nde, dict) and not nde.get("platform_errors"):
            nde["platform_errors"] = (
                acq.get("platform_reason_stats", {}).get("by_platform")
                or {"unknown": ["crawler_empty"]}
            )
        return result
    return {
        "run_id": run_id,
        "status": run.get("status", "unknown"),
        "accepted_at": run.get("accepted_at"),
        "updated_at": run.get("updated_at"),
        "steps": run.get("steps", []),
        "message": "run is not completed yet",
        "error": run.get("error"),
    }


@router.get("/{run_id}/stream")
async def stream_investigation_events(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")

    async def event_gen():
        async for event in manager.stream(run_id):
            payload = event.get("payload", {})
            line = (
                f"id: {event.get('id')}\n"
                f"event: {event.get('type')}\n"
                f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            )
            yield line

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/{run_id}/publish/suggestions", response_model=PublishSuggestionResponse)
async def generate_publish_suggestions(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if not run.get("result"):
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")

    payload = await build_publish_suggestions(run)
    return PublishSuggestionResponse(**payload)


@router.post("/{run_id}/publish/geo-report")
async def generate_geo_report(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    result = run.get("result")
    if not result:
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")

    from api.v1.endpoints.reports import GenerateReportRequest, generate_report

    geo_payload = await build_geo_report_content(run)
    credibility_score = 0.6
    if isinstance(result.get("credibility_score"), (int, float)):
        credibility_score = float(result.get("credibility_score"))

    report_request = GenerateReportRequest(
        title=str(geo_payload.get("title") or f"GEO 新闻报告 {run_id}"),
        content=str(geo_payload.get("content") or ""),
        credibility_score=credibility_score,
        tags=[f"run_{run_id}", "geo-report"],
        sources=[],
    )
    return await generate_report(report_request)


@router.post("/{run_id}/mindmap")
async def generate_insight_mindmap(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if not run.get("result"):
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")
    mindmap = build_mindmap_from_run(run)
    get_sqlite_db().save_insight_mindmap(run_id, mindmap)
    return mindmap


@router.post("/{run_id}/analysis/common")
async def generate_common_analysis(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if not run.get("result"):
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")
    report = build_common_analysis_from_run(run)
    get_sqlite_db().save_insight_common_analysis(run_id, report)
    return report


@router.post("/{run_id}/value-insights")
async def generate_value_insights(run_id: str):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if not run.get("result"):
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")
    mindmap = get_sqlite_db().get_insight_mindmap(run_id)
    mindmap_payload = (mindmap or {}).get("payload_json") or build_mindmap_from_run(run)
    common_analysis = get_sqlite_db().get_insight_common_analysis(run_id)
    common_payload = (common_analysis or {}).get("payload_json") or build_common_analysis_from_run(run)
    insights = build_value_insights(run=run, mindmap=mindmap_payload, common_analysis=common_payload)
    get_sqlite_db().save_insight_value_insights(run_id, insights)
    return insights


@router.post("/{run_id}/generate-article")
async def generate_insight_article(run_id: str, req: InsightArticleRequest):
    manager = get_investigation_manager()
    run = manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Investigation run not found")
    if not run.get("result"):
        raise HTTPException(status_code=400, detail="Investigation is not completed yet")
    value_insights = get_sqlite_db().get_insight_value_insights(run_id)
    insight_payload = (value_insights or {}).get("payload_json") or {}
    candidates = list(insight_payload.get("potential_value_insights") or [])
    selected = None
    if req.value_direction:
        for item in candidates:
            if str(item.get("value_direction") or "") == req.value_direction:
                selected = item
                break
    if selected is None and candidates:
        selected = candidates[0]
    if selected is None:
        selected = {"value_direction": req.value_direction or "潜在价值方向"}

    article = generate_article(
        run=run,
        value_insight=selected,
        template_type=req.template_type,
        platform=req.platform,
    )
    article_id = article.get("article_id") or f"article_{uuid4().hex[:8]}"
    get_sqlite_db().save_insight_article(article_id, run_id, article)
    return {"article_id": article_id, **article}
