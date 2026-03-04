"""
Investigation 编排引擎
提供 run/stream/result 所需的运行时与执行逻辑
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx

from core.config import settings
from core.sqlite_database import get_sqlite_db
from services.investigation_helpers import (
    FALLBACK_STABLE_PLATFORMS,
    OFFICIAL_DOMAINS,
    STABLE_MIXED_PROFILE,
    _derive_keyword,
    _elapsed_ms,
    _extract_published_at,
    _httpx_trust_env_candidates,
    _keyword_relevance_score,
    _looks_like_specific_content_url,
    _normalize_url,
    _parse_datetime_like,
    _safe_float,
    _safe_int,
    _stable_hash,
    _tier_for_url,
    _to_utc_iso,
    _utc_now,
)
from services.investigation_reporting import (
    build_dual_profile_result,
    build_report_sections,
    check_external_sources,
    determine_result_status,
)
from services.source_planner import OFFICIAL_PLATFORMS
from services.investigation_claims import analyze_claims
from services.investigation_runtime import InvestigationRunManager
from services.layer1_perception.crawler_manager import get_crawler_manager
from services.layer2_memory.cross_platform_fusion import get_fusion_service
from services.layer3_reasoning.simple_cot_engine import analyze_intel_enhanced
from services.multi_agent_siliconflow import get_multi_agent_processor
from services.debate_reasoning import DebateReasoningEngine, generate_cot_display
from services.opinion_monitoring import analyze_opinion_monitoring
from services.report_template_service import get_report_template_service
from services.llm.siliconflow_client import get_siliconflow_client
from services.source_planner import plan_sources
from services.source_tier_config import resolve_source_tier
from utils.logging import logger
from utils.metrics import (
    analysis_duration_seconds,
    analysis_requests_total,
    investigation_cached_evidence_count,
    investigation_duration_seconds,
    investigation_live_evidence_count,
    investigation_target_reached_total,
    investigation_valid_evidence_count,
    manual_takeover_waiting_total,
)


class InvestigationOrchestrator:
    """调度现有后端能力，输出统一 InvestigationResult。"""

    def __init__(self, manager: InvestigationRunManager) -> None:
        self.manager = manager

    def _load_runtime_healthy_platforms(self) -> List[str]:
        report_path = str(
            getattr(
                settings,
                "INVESTIGATION_TRUSTED_HEALTH_REPORT_PATH",
                "docs/source-health-report-zh-core.json",
            )
        )
        min_success = float(
            getattr(settings, "INVESTIGATION_TRUSTED_MIN_SUCCESS_RATE", 0.34)
        )
        require_items = bool(
            getattr(settings, "INVESTIGATION_TRUSTED_REQUIRE_ITEMS", True)
        )
        try:
            p = Path(report_path)
            if not p.exists():
                return []
            payload = json.loads(p.read_text(encoding="utf-8"))
            probe = payload.get("probe") if isinstance(payload.get("probe"), dict) else {}
            out: List[str] = []
            for platform, row in probe.items():
                if not isinstance(row, dict):
                    continue
                rounds = max(1, int(row.get("rounds") or 1))
                # Evidence-first: a platform is "healthy" only when it can produce
                # query-relevant evidence, not just generic items.
                success = int(
                    row.get("evidence_success_rounds")
                    if row.get("evidence_success_rounds") is not None
                    else (row.get("success_rounds") or 0)
                )
                items = int(
                    row.get("evidence_items")
                    if row.get("evidence_items") is not None
                    else (row.get("items_collected") or 0)
                )
                rate = float(success) / float(rounds)
                if rate >= min_success and ((not require_items) or items > 0):
                    out.append(str(platform))
            return out
        except Exception as exc:
            logger.warning(f"load trusted health report failed: {type(exc).__name__}")
            return []

    def _is_zh_query(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))

    def _zh_background_platforms(self) -> set[str]:
        raw = str(
            getattr(
                settings,
                "INVESTIGATION_ZH_QUERY_BACKGROUND_PLATFORMS",
                "bbc,reuters,guardian,ap_news,who,un_news,sec,fca_uk,cdc",
            )
        )
        return {x.strip().lower() for x in raw.split(",") if x.strip()}

    def _build_allowed_domains(
        self, crawlers: Any, platforms: List[str], free_source_only: bool
    ) -> set[str]:
        allowed = set(OFFICIAL_DOMAINS)
        if hasattr(crawlers, "get_platform_domains"):
            for platform in platforms:
                for domain in (crawlers.get_platform_domains(platform) or []):
                    if domain:
                        allowed.add(str(domain).lower())
        if not free_source_only:
            return allowed
        return allowed

    def _is_domain_allowed(self, url: str, allowed_domains: set[str]) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in allowed_domains)

    def _external_search_allowed_domains(self, runtime_allowed_domains: set[str]) -> List[str]:
        configured = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_ALLOWED_DOMAINS", "")
        )
        configured_domains = [
            x.strip().lower() for x in configured.split(",") if x.strip()
        ]
        if configured_domains:
            return list(dict.fromkeys(configured_domains))
        return sorted(
            [
                str(domain).strip().lower()
                for domain in (runtime_allowed_domains or set())
                if str(domain).strip()
            ]
        )

    def _should_trigger_external_search(
        self,
        *,
        valid_evidence_count: int,
        platforms_with_data: int,
    ) -> tuple[bool, str]:
        mode = str(
            getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MODE", "adaptive")
        ).strip().lower()
        if mode in {"disabled", "off", "none"}:
            return False, "MODE_DISABLED"
        if mode in {"always", "supplement"}:
            return True, "MODE_ALWAYS"

        min_evidence = max(
            0,
            _safe_int(
                getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_TRIGGER_MIN_EVIDENCE", 120),
                120,
            ),
        )
        min_platforms = max(
            0,
            _safe_int(
                getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_TRIGGER_MIN_PLATFORMS", 4),
                4,
            ),
        )
        if valid_evidence_count < min_evidence:
            return True, "LOW_EVIDENCE"
        if platforms_with_data < min_platforms:
            return True, "LOW_PLATFORM_COVERAGE"
        return False, "ENOUGH_EVIDENCE"

    def _extract_item_text(self, item: Dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        rows = [
            str(item.get("title") or item.get("headline") or ""),
            str(item.get("content_text") or ""),
            str(item.get("content") or item.get("text") or item.get("summary") or ""),
            str(item.get("snippet") or ""),
            str(metadata.get("author_name") or metadata.get("author") or ""),
        ]
        return "\n".join(rows).strip()

    def _extract_item_url(self, item: Dict[str, Any]) -> str:
        if not isinstance(item, dict):
            return ""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        direct_keys = [
            "url",
            "source_url",
            "original_url",
            "link",
            "href",
            "uri",
            "article_url",
            "web_url",
            "permalink",
            "jump_url",
            "target_url",
        ]
        metadata_keys = [
            "source_url",
            "url",
            "link",
            "href",
            "article_url",
            "original_url",
            "rss_url",
        ]
        for key in direct_keys:
            normalized = _normalize_url(str(item.get(key) or ""))
            if normalized:
                return normalized
        for key in metadata_keys:
            normalized = _normalize_url(str(metadata.get(key) or ""))
            if normalized:
                return normalized
        return ""

    def _extract_query_entities(self, keyword: str) -> List[str]:
        """
        Extract entity-like anchors from query.
        Used as a hard gate to prevent unscoped hot/news feed pollution.
        """
        raw = str(keyword or "").strip().lower()
        if not raw:
            return []
        noise = [
            "退役",
            "宣布",
            "官宣",
            "回应",
            "辟谣",
            "去世",
            "是真的吗",
            "是否",
            "是不是",
            "吗",
            "呢",
            "最新",
            "消息",
            "新闻",
            "事件",
        ]
        cleaned = raw
        for token in noise:
            cleaned = cleaned.replace(token, " ")
        cands = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9._-]{2,}", cleaned)
        stop = {"官方", "通告", "公告", "报道", "新闻", "媒体", "消息", "事件"}
        cands = [x for x in cands if x not in stop]
        cands = sorted(set(cands), key=lambda x: len(x), reverse=True)
        return cands[:3]

    def _entity_gate_pass(self, keyword: str, text_blob: str) -> bool:
        if not bool(getattr(settings, "INVESTIGATION_ENTITY_GATE_ENABLED", True)):
            return True
        entities = self._extract_query_entities(keyword)
        if not entities:
            return True
        blob = str(text_blob or "").lower()
        return any(ent in blob for ent in entities)

    async def _apply_llm_semantic_gate(
        self,
        *,
        claim: str,
        keyword: str,
        rows: List[Dict[str, Any]],
        threshold: float,
        max_items: int,
        concurrency: int,
        timeout_sec: float,
        fallback_relevance: float,
    ) -> Dict[str, Any]:
        if not rows:
            return {"rows": rows, "stats": {"total": 0}}
        client = get_siliconflow_client()
        sem = asyncio.Semaphore(max(1, int(concurrency)))
        scored_count = 0
        passed_count = 0
        failed_count = 0
        candidates = sorted(
            rows,
            key=lambda x: float(x.get("relevance_score") or 0.0),
            reverse=True,
        )[: max(1, int(max_items))]
        candidate_ids = {id(r) for r in candidates}

        async def _score_row(row: Dict[str, Any]) -> None:
            nonlocal scored_count, failed_count
            async with sem:
                item = row.get("item") if isinstance(row.get("item"), dict) else {}
                text_blob = str(row.get("text_blob") or "") or self._extract_item_text(item)
                source = str(row.get("platform") or item.get("source_platform") or "unknown")
                try:
                    result = await asyncio.wait_for(
                        client.score_semantic_relevance(
                            claim=claim,
                            keyword=keyword,
                            evidence_text=text_blob,
                            source=source,
                        ),
                        timeout=max(3.0, float(timeout_sec)),
                    )
                    row["llm_semantic_score"] = float(result.get("semantic_score") or 0.0)
                    row["llm_semantic_match"] = bool(result.get("is_relevant"))
                    row["llm_semantic_reason"] = str(result.get("reason") or "")
                except asyncio.TimeoutError:
                    failed_count += 1
                    row["llm_semantic_score"] = None
                    row["llm_semantic_match"] = None
                    row["llm_semantic_reason"] = "timeout"
                except Exception as exc:
                    failed_count += 1
                    row["llm_semantic_score"] = None
                    row["llm_semantic_match"] = None
                    row["llm_semantic_reason"] = f"error:{exc}"
                scored_count += 1

        tasks = [asyncio.create_task(_score_row(row)) for row in candidates]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        filtered_rows: List[Dict[str, Any]] = []
        for row in rows:
            if id(row) in candidate_ids:
                score = row.get("llm_semantic_score")
                match = row.get("llm_semantic_match")
                if isinstance(score, (int, float)) and score >= float(threshold):
                    passed_count += 1
                    filtered_rows.append(row)
                    continue
                if match is False:
                    continue
            if bool(row.get("keyword_match")) and float(row.get("relevance_score") or 0.0) >= float(
                fallback_relevance
            ):
                row.setdefault("llm_semantic_score", row.get("relevance_score"))
                row.setdefault("llm_semantic_match", True)
                row.setdefault("llm_semantic_reason", "fallback_keyword_relevance")
                filtered_rows.append(row)

        fallback_used = False
        if not filtered_rows:
            fallback_used = True
            filtered_rows = sorted(
                rows,
                key=lambda x: float(x.get("relevance_score") or 0.0),
                reverse=True,
            )[: max(1, min(len(rows), 12))]

        stats = {
            "total": len(rows),
            "scored": scored_count,
            "passed": passed_count,
            "failed": failed_count,
            "filtered": max(0, len(rows) - len(filtered_rows)),
            "threshold": float(threshold),
            "max_items": int(max_items),
            "fallback_used": fallback_used,
        }
        return {"rows": filtered_rows, "stats": stats}

    async def _probe_urls(
        self, urls: List[str], timeout_sec: float, concurrency: int
    ) -> Dict[str, Dict[str, Any]]:
        async def _probe(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
            if not url:
                return {"reachable": False, "status_code": 0, "reason": "EMPTY_URL"}
            try:
                resp = await client.head(url)
                code = int(resp.status_code)
                if code >= 400 or code in (301, 302, 303, 307, 308):
                    resp = await client.get(url)
                    code = int(resp.status_code)
                if 200 <= code < 400:
                    return {"reachable": True, "status_code": code, "reason": "OK"}
                return {"reachable": False, "status_code": code, "reason": f"HTTP_{code}"}
            except httpx.TimeoutException:
                return {"reachable": False, "status_code": 0, "reason": "CRAWLER_TIMEOUT"}
            except Exception as exc:
                msg = str(exc or "")
                low = msg.lower()
                if (
                    "temporary failure in name resolution" in low
                    or "name or service not known" in low
                    or "nodename nor servname provided" in low
                    or "gaierror" in low
                ):
                    reason = "DNS_ERROR"
                elif ("tls" in low and "timeout" in low) or ("ssl handshake" in low):
                    reason = "TLS_TIMEOUT"
                elif (
                    "proxy" in low and "connect" in low
                ) or ("127.0.0.1:7897" in low and "connect" in low):
                    reason = "PROXY_UNREACHABLE"
                else:
                    reason = "UNREACHABLE"
                return {"reachable": False, "status_code": 0, "reason": reason}

        out: Dict[str, Dict[str, Any]] = {}
        if not urls:
            return out

        pending = list(dict.fromkeys([u for u in urls if u]))
        timeout = httpx.Timeout(timeout_sec, connect=max(1.0, min(timeout_sec, 3.0)))
        for trust_env in _httpx_trust_env_candidates():
            if not pending:
                break
            sem = asyncio.Semaphore(max(1, concurrency))
            partial: Dict[str, Dict[str, Any]] = {}
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                max_redirects=3,
                trust_env=trust_env,
            ) as client:
                async def _run(url: str):
                    async with sem:
                        row = await _probe(client, url)
                        row["trust_env"] = trust_env
                        partial[url] = row
                await asyncio.gather(*[_run(u) for u in pending], return_exceptions=True)
            for url in pending:
                row = partial.get(url) or {
                    "reachable": False,
                    "status_code": 0,
                    "reason": "UNREACHABLE",
                    "trust_env": trust_env,
                }
                prev = out.get(url)
                if prev is None or (not bool(prev.get("reachable")) and bool(row.get("reachable"))):
                    out[url] = row
            pending = [u for u in pending if not bool((out.get(u) or {}).get("reachable"))]
        return out

    def _build_validated_candidates(
        self,
        *,
        keyword: str,
        search_data: Dict[str, List[Dict[str, Any]]],
        allowed_domains: set[str],
        quality_mode: str,
        reachability_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        strict_mode = quality_mode == "strict"
        relevance_threshold = float(
            getattr(
                settings,
                "INVESTIGATION_RELEVANCE_THRESHOLD_STRICT" if strict_mode else "INVESTIGATION_RELEVANCE_THRESHOLD_BALANCED",
                0.2 if strict_mode else 0.1,
            )
        )
        relevance_floor = float(
            getattr(settings, "INVESTIGATION_RELEVANCE_FLOOR", 0.2)
        )
        relevance_threshold = max(relevance_threshold, relevance_floor)
        allow_low_relevance_rescue_globally = bool(
            getattr(settings, "INVESTIGATION_ALLOW_LOW_RELEVANCE_RESCUE", False)
        )
        seen_url: set[str] = set()
        seen_content_hash: set[str] = set()
        valid_items: List[Dict[str, Any]] = []
        low_relevance_candidates: List[Dict[str, Any]] = []
        invalid_items: List[Dict[str, Any]] = []
        reason_counter: Counter[str] = Counter()
        platform_valid_counter: Counter[str] = Counter()

        for platform, items in (search_data or {}).items():
            for item in (items or []):
                if not isinstance(item, dict):
                    reason_counter["INVALID_ITEM"] += 1
                    continue
                url = self._extract_item_url(item)
                text_blob = self._extract_item_text(item)
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                content_hash = _stable_hash(text_blob)
                trusted_tier = _tier_for_url(url) <= 2
                allow_low_relevance_rescue = (
                    allow_low_relevance_rescue_globally and trusted_tier
                )
                if not url:
                    reason_counter["EMPTY_URL"] += 1
                    invalid_items.append({"platform": platform, "url": "", "reason": "EMPTY_URL"})
                    continue
                if url in seen_url:
                    reason_counter["DUPLICATE_URL"] += 1
                    continue
                if content_hash in seen_content_hash:
                    reason_counter["DUPLICATE_CONTENT"] += 1
                    continue
                if not _looks_like_specific_content_url(url):
                    reason_counter["NON_SPECIFIC_URL"] += 1
                    if allow_low_relevance_rescue:
                        low_relevance_candidates.append(
                            {
                                "platform": platform,
                                "url": url,
                                "text_blob": text_blob,
                                "item": item,
                                "keyword_match": bool(metadata.get("keyword_match")),
                                "relevance_score": _keyword_relevance_score(
                                    keyword=keyword, text_blob=text_blob
                                ),
                                "reachable": bool((reachability_map.get(url) or {}).get("reachable")),
                                "reachability_reason": str(
                                    (reachability_map.get(url) or {}).get("reason") or "N/A"
                                ),
                                "low_relevance_fallback": True,
                            }
                        )
                    invalid_items.append({"platform": platform, "url": url, "reason": "NON_SPECIFIC_URL"})
                    continue
                if not self._is_domain_allowed(url, allowed_domains):
                    meta_source_domain = str(metadata.get("source_domain") or "").strip().lower()
                    url_host = ""
                    try:
                        url_host = (urlparse(url).hostname or "").lower()
                    except Exception:
                        url_host = ""
                    google_news_proxy_allowed = (
                        url_host in {"news.google.com", "news.googleusercontent.com"}
                        and bool(meta_source_domain)
                        and any(
                            meta_source_domain == d or meta_source_domain.endswith(f".{d}")
                            for d in allowed_domains
                        )
                    )
                    if google_news_proxy_allowed:
                        metadata["domain_routed_via"] = "google_news_rss"
                        item["metadata"] = metadata
                    else:
                        reason_counter["DOMAIN_NOT_ALLOWED"] += 1
                        invalid_items.append({"platform": platform, "url": url, "reason": "DOMAIN_NOT_ALLOWED"})
                        continue

                relevance_score = _keyword_relevance_score(keyword=keyword, text_blob=text_blob)
                keyword_match = bool(metadata.get("keyword_match")) or relevance_score >= relevance_threshold
                entity_pass = self._entity_gate_pass(keyword=keyword, text_blob=text_blob)
                if not entity_pass:
                    reason_counter["ENTITY_GATE_MISS"] += 1
                    invalid_items.append({"platform": platform, "url": url, "reason": "ENTITY_GATE_MISS"})
                    continue
                if not keyword_match:
                    if allow_low_relevance_rescue:
                        low_relevance_candidates.append(
                            {
                                "platform": platform,
                                "url": url,
                                "text_blob": text_blob,
                                "item": item,
                                "keyword_match": False,
                                "relevance_score": relevance_score,
                                "reachable": bool((reachability_map.get(url) or {}).get("reachable")),
                                "reachability_reason": str((reachability_map.get(url) or {}).get("reason") or "N/A"),
                                "low_relevance_fallback": True,
                            }
                        )
                    reason_counter["LOW_RELEVANCE"] += 1
                    invalid_items.append({"platform": platform, "url": url, "reason": "LOW_RELEVANCE"})
                    continue

                reachable = reachability_map.get(url, {})
                if strict_mode and not bool(reachable.get("reachable")):
                    reason = str(reachable.get("reason") or "UNREACHABLE")
                    reason_counter[reason] += 1
                    invalid_items.append({"platform": platform, "url": url, "reason": reason})
                    continue

                seen_url.add(url)
                seen_content_hash.add(content_hash)
                platform_valid_counter[platform] += 1
                valid_items.append(
                    {
                        "platform": platform,
                        "url": url,
                        "text_blob": text_blob,
                        "item": item,
                        "keyword_match": keyword_match,
                        "relevance_score": relevance_score,
                        "reachable": bool(reachable.get("reachable")),
                        "reachability_reason": str(reachable.get("reason") or "OK"),
                    }
                )

        valid_items.sort(key=lambda x: (x.get("relevance_score", 0.0), x.get("reachable", False)), reverse=True)
        return {
            "valid_items": valid_items,
            "low_relevance_candidates": low_relevance_candidates,
            "invalid_items": invalid_items,
            "reason_counter": dict(reason_counter),
            "platform_valid_counter": dict(platform_valid_counter),
            "deduplicated_count": len(seen_url),
        }

    def _to_evidence_card(
        self,
        keyword: str,
        row: Dict[str, Any],
        idx: int,
        source_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        item = row.get("item") if isinstance(row.get("item"), dict) else {}
        platform = str(row.get("platform") or item.get("source_platform") or "unknown")
        url = str(row.get("url") or "")
        snippet = str(item.get("title") or item.get("content_text") or item.get("content") or item.get("text") or "")[:500]
        attributed_source = self._infer_attributed_source(platform=platform, item=item, snippet=snippet)
        source_tier = _tier_for_url(url)
        if attributed_source != platform and source_tier > 2:
            source_tier = 2
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        retrieval_mode = str(metadata.get("retrieval_mode") or "live")
        published_at = _extract_published_at(item)
        collected_at = _utc_now()
        provisional = bool(row.get("provisional"))
        low_relevance_fallback = bool(row.get("low_relevance_fallback"))
        conf = 0.85 if row.get("reachable") else 0.5
        if provisional:
            conf = min(conf, 0.42)
        if low_relevance_fallback:
            conf = min(conf, 0.36)
        card = {
            "id": f"ev_search_{platform}_{idx}",
            "claim_ref": keyword,
            "source_tier": source_tier,
            "source_name": attributed_source,
            "source_platform": platform,
            "source_attribution": attributed_source if attributed_source != platform else "",
            "evidence_origin": "external",
            "url": url,
            "snippet": snippet,
            "stance": "unknown",
            "confidence": conf,
            "collected_at": collected_at,
            "published_at": published_at,
            "first_seen_at": published_at or collected_at,
            "retrieval_query": keyword,
            "validation_status": (
                "provisional_low_relevance"
                if low_relevance_fallback
                else (
                    "provisional"
                    if provisional
                    else ("reachable" if row.get("reachable") else "url_only")
                )
            ),
            "keyword_match": bool(row.get("keyword_match")),
            "entity_pass": bool(row.get("entity_pass", True)),
            "relevance_score": float(row.get("relevance_score") or 0.0),
            "drop_reason": str(row.get("drop_reason") or ""),
            "used_as_evidence": True,
            "retrieval_mode": retrieval_mode,
            "provider": str(metadata.get("provider") or "native"),
            "sidecar_task_id": str(metadata.get("sidecar_task_id") or ""),
            "post_id": str(metadata.get("post_id") or ""),
            "llm_semantic_score": row.get("llm_semantic_score"),
            "llm_semantic_match": row.get("llm_semantic_match"),
            "llm_semantic_reason": row.get("llm_semantic_reason"),
            "is_cached": False,
            "freshness_hours": 0.0,
            "cache_run_id": None,
        }
        card.update(self._infer_evidence_class(card=card, source_plan=source_plan, keyword=keyword))
        return card

    def _collect_search_hits(
        self,
        *,
        keyword: str,
        search_data: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for platform, items in (search_data or {}).items():
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                url = self._extract_item_url(item)
                title = str(
                    item.get("title")
                    or item.get("headline")
                    or item.get("content_text")
                    or item.get("text")
                    or ""
                ).strip()
                snippet = str(
                    item.get("summary")
                    or item.get("snippet")
                    or item.get("content")
                    or item.get("text")
                    or title
                ).strip()
                source_domain = str(metadata.get("source_domain") or "").strip().lower()
                if not source_domain and url:
                    try:
                        source_domain = (urlparse(url).hostname or "").lower().strip()
                    except Exception:
                        source_domain = ""
                hits.append(
                    {
                        "platform": str(platform or "unknown"),
                        "keyword": str(keyword or ""),
                        "url": str(url or ""),
                        "title": title[:500],
                        "snippet": snippet[:1200],
                        "source_name": str(item.get("source") or item.get("author") or platform),
                        "source_domain": source_domain,
                        "rank_position": int(idx),
                        "discovery_mode": str(metadata.get("search_source_mode") or "search"),
                        "discovery_tier": str(metadata.get("search_source_tier") or "B"),
                        "discovery_lang": str(metadata.get("search_source_lang") or ""),
                        "discovery_pool": str(metadata.get("search_source_pool") or "evidence"),
                        "drop_reason": "PENDING_VALIDATION",
                        "is_promoted": False,
                        "metadata": metadata,
                    }
                )
        return hits

    def _apply_search_hit_promotions(
        self,
        *,
        hits: List[Dict[str, Any]],
        invalid_items: List[Dict[str, Any]],
        valid_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []
        invalid_map: Dict[tuple[str, str], str] = {}
        for row in invalid_items or []:
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("platform") or "").strip().lower(),
                str(row.get("url") or "").strip(),
            )
            if not key[0] and not key[1]:
                continue
            reason = str(row.get("reason") or "INVALID").strip().upper() or "INVALID"
            if key not in invalid_map:
                invalid_map[key] = reason

        promoted_map: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in valid_rows or []:
            if not isinstance(row, dict):
                continue
            item = row.get("item") if isinstance(row.get("item"), dict) else {}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            key = (
                str(row.get("platform") or "").strip().lower(),
                str(row.get("url") or "").strip(),
            )
            promoted_map[key] = {
                "relevance_score": float(row.get("relevance_score") or 0.0),
                "keyword_match": bool(row.get("keyword_match")),
                "entity_pass": True,
                "provider": str(metadata.get("provider") or "native"),
                "retrieval_mode": str(metadata.get("retrieval_mode") or "live"),
            }

        normalized: List[Dict[str, Any]] = []
        for hit in hits:
            row = dict(hit or {})
            key = (
                str(row.get("platform") or "").strip().lower(),
                str(row.get("url") or "").strip(),
            )
            promoted = promoted_map.get(key)
            if promoted:
                row["is_promoted"] = True
                row["drop_reason"] = ""
                row["relevance_score"] = float(promoted.get("relevance_score") or 0.0)
                row["keyword_match"] = bool(promoted.get("keyword_match"))
                row["entity_pass"] = bool(promoted.get("entity_pass"))
                row["provider"] = str(promoted.get("provider") or "native")
                row["retrieval_mode"] = str(promoted.get("retrieval_mode") or "live")
            else:
                row["is_promoted"] = False
                row["drop_reason"] = invalid_map.get(key, "NOT_PROMOTED")
                row.setdefault("relevance_score", 0.0)
                row.setdefault("keyword_match", False)
                row.setdefault("entity_pass", False)
            normalized.append(row)
        return normalized

    def _build_evidence_docs(self, evidence_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for card in evidence_cards or []:
            if not isinstance(card, dict):
                continue
            docs.append(
                {
                    "id": str(card.get("id") or ""),
                    "source_name": str(card.get("source_name") or ""),
                    "source_platform": str(card.get("source_platform") or ""),
                    "source_domain": str(card.get("source_domain") or ""),
                    "url": str(card.get("url") or ""),
                    "title": str(card.get("title") or "")[:500],
                    "snippet": str(card.get("snippet") or "")[:1600],
                    "source_tier": int(card.get("source_tier") or 3),
                    "confidence": float(card.get("confidence") or 0.0),
                    "relevance_score": float(card.get("relevance_score") or 0.0),
                    "keyword_match": bool(card.get("keyword_match")),
                    "entity_pass": bool(card.get("entity_pass", True)),
                    "validation_status": str(card.get("validation_status") or ""),
                    "retrieval_mode": str(card.get("retrieval_mode") or "live"),
                    "evidence_class": str(card.get("evidence_class") or "background"),
                    "provider": str(card.get("provider") or "native"),
                }
            )
        return docs

    def _infer_attributed_source(
        self,
        *,
        platform: str,
        item: Dict[str, Any],
        snippet: str,
    ) -> str:
        base_platform = str(platform or "unknown").strip().lower() or "unknown"
        blob = " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("content_text") or ""),
                str(item.get("content") or ""),
                str(item.get("text") or ""),
                str(item.get("author") or ""),
                str(item.get("publisher") or ""),
                str(item.get("source") or ""),
                str(snippet or ""),
            ]
        ).lower()
        if not blob:
            return base_platform

        alias_map = [
            ("xinhua", ("新华社", "新华网", "xinhuanet", "news.cn")),
            ("peoples_daily", ("人民日报", "人民网", "people.cn")),
            ("reuters", ("reuters", "路透")),
            ("bbc", ("bbc", "英国广播公司")),
            ("guardian", ("guardian", "卫报")),
            ("ap_news", ("ap news", "associated press", "美联社")),
            ("caixin", ("财新", "caixin")),
            ("the_paper", ("澎湃", "thepaper.cn", "the paper")),
            ("who", ("who", "world health organization", "世界卫生组织")),
        ]
        for source_name, aliases in alias_map:
            for alias in aliases:
                if str(alias).lower() in blob:
                    return source_name
        return base_platform

    def _infer_evidence_origin(self, card: Dict[str, Any]) -> str:
        source_name = str(card.get("source_name") or "").strip().lower()
        retrieval_mode = str(card.get("retrieval_mode") or "").strip().lower()
        validation_status = str(card.get("validation_status") or "").strip().lower()
        if source_name == "reasoning_chain" or retrieval_mode == "reasoning":
            return "derived_reasoning"
        if validation_status.startswith("synthetic") or retrieval_mode.startswith("synthetic"):
            return "synthetic_context"
        return "external"

    def _infer_evidence_class(
        self,
        *,
        card: Dict[str, Any],
        source_plan: Optional[Dict[str, Any]],
        keyword: str,
    ) -> Dict[str, Any]:
        platform = str(card.get("source_name") or "").strip()
        tier = int(card.get("source_tier") or 3)
        relevance = float(card.get("relevance_score") or 0.0)
        keyword_match = bool(card.get("keyword_match"))
        retrieval_mode = str(card.get("retrieval_mode") or "")
        validation_status = str(card.get("validation_status") or "")

        must_have = set(source_plan.get("must_have_platforms") or []) if isinstance(source_plan, dict) else set()
        excluded = set(source_plan.get("excluded_platforms") or []) if isinstance(source_plan, dict) else set()
        in_must = platform in must_have
        in_excluded = platform in excluded

        score = relevance
        if keyword_match:
            score += 0.25
        if tier <= 2:
            score += 0.18
        if in_must:
            score += 0.16
        if in_excluded:
            score -= 0.3
        if retrieval_mode in {"hot_fallback", "rss_emergency_fallback", "web_search_fallback"}:
            score -= 0.12
        if "low_relevance" in validation_status:
            score -= 0.14
        score = max(0.0, min(1.0, score))

        low_quality_status = {
            "invalid",
            "unreachable",
            "discarded",
            "provisional_low_relevance",
            "url_only",
        }
        passes_signal = bool(keyword_match) or relevance >= 0.45
        status_low_quality = validation_status in low_quality_status

        is_fallback_mode = retrieval_mode in {
            "hot_fallback",
            "rss_emergency_fallback",
            "web_search_fallback",
            "context_fallback",
        }

        if in_excluded and score < 0.55:
            evidence_class = "noise"
            reason = "excluded_source_low_domain_match"
        elif is_fallback_mode and passes_signal and (not status_low_quality):
            # 兜底检索通常噪声较高，但在“高层级+高相关+命中词明确”场景允许晋升主证据，
            # 避免出现真实事件下 primary=0 导致结论长期卡死。
            can_promote_fallback = (
                (not in_excluded)
                and tier <= 2
                and bool(keyword_match)
                and relevance >= 0.55
                and validation_status in {"reachable", "valid", "provisional", "provisional_reachable"}
            )
            if can_promote_fallback:
                evidence_class = "primary"
                reason = "high_tier_fallback_promoted"
            else:
                evidence_class = "background"
                reason = "fallback_mode_background"
        elif passes_signal and (not status_low_quality) and (not in_excluded):
            evidence_class = "primary"
            reason = "primary_signal_passed"
        elif in_must and tier <= 2 and score >= 0.15:
            evidence_class = "background"
            reason = "must_have_low_signal_background"
        elif tier <= 2 and retrieval_mode in {"hot_fallback", "rss_emergency_fallback", "web_search_fallback"} and score >= 0.06:
            evidence_class = "background"
            reason = "high_tier_fallback_background"
        elif score < 0.12:
            evidence_class = "noise"
            reason = "low_signal_noise"
        else:
            evidence_class = "background"
            reason = "fallback_or_context"

        # 当关键词过短时，避免把不相关热点误提为主证据
        if (
            len(_derive_keyword(claim=keyword, keyword=keyword)) <= 14
            and evidence_class == "primary"
            and relevance < 0.25
        ):
            evidence_class = "background"
            reason = "broad_keyword_guardrail"

        # 中文事实核查默认不把国际泛媒体作为主证据，只允许进入背景池。
        if (
            evidence_class == "primary"
            and bool(getattr(settings, "INVESTIGATION_LANGUAGE_ROUTING_ENABLED", True))
            and self._is_zh_query(keyword)
            and platform.strip().lower() in self._zh_background_platforms()
        ):
            evidence_class = "background"
            reason = "zh_query_background_pool"

        return {
            "evidence_class": evidence_class,
            "selection_reason": reason,
            "domain_match_score": round(score, 4),
        }

    def _apply_evidence_stratification(
        self,
        *,
        evidence_cards: List[Dict[str, Any]],
        source_plan: Optional[Dict[str, Any]],
        keyword: str,
    ) -> None:
        for row in evidence_cards:
            if not isinstance(row, dict):
                continue
            row["evidence_origin"] = self._infer_evidence_origin(row)
            enriched = self._infer_evidence_class(card=row, source_plan=source_plan, keyword=keyword)
            row["evidence_class"] = enriched["evidence_class"]
            row["selection_reason"] = enriched["selection_reason"]
            row["domain_match_score"] = enriched["domain_match_score"]

    def _partition_external_evidence_cards(
        self, evidence_cards: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Split external evidence into evidence/context/noise pools.
        evidence_pool: primary class, can be used for conclusions.
        context_pool: background class, context-only.
        noise_pool: low-signal items kept only for diagnostics.
        """
        pools = {
            "evidence_pool": [],
            "context_pool": [],
            "noise_pool": [],
        }
        for card in evidence_cards or []:
            if not isinstance(card, dict):
                continue
            if str(card.get("evidence_origin") or "external") != "external":
                continue
            cls = str(card.get("evidence_class") or "background").strip().lower()
            if cls == "primary":
                pools["evidence_pool"].append(card)
            elif cls == "noise":
                pools["noise_pool"].append(card)
            else:
                pools["context_pool"].append(card)
        return pools

    def _extract_domain(self, url_value: str) -> str:
        url = str(url_value or "").strip()
        if not url:
            return ""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            host = parsed.netloc or ""
        except Exception:
            host = ""
        host = host.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        if ":" in host:
            host = host.split(":", 1)[0]
        return host

    def _attach_traceable_fields(
        self,
        *,
        evidence_cards: List[Dict[str, Any]],
        crawlers: Any,
    ) -> None:
        for row in evidence_cards:
            if not isinstance(row, dict):
                continue
            url_value = str(row.get("url") or "").strip()
            domain = self._extract_domain(url_value)
            if not domain:
                platform = str(row.get("source_name") or row.get("platform") or "")
                if platform and hasattr(crawlers, "get_platform_domains"):
                    domains = crawlers.get_platform_domains(platform) or []
                    if domains:
                        domain = self._extract_domain(domains[0])
            if domain:
                tier_info = resolve_source_tier(domain)
                row.setdefault("source_domain", domain)
                row.setdefault(
                    "source_tier_config",
                    {
                        "tier": tier_info.tier,
                        "trust_score": tier_info.trust_score,
                        "matched_pattern": tier_info.matched_pattern,
                        "match_type": tier_info.match_type,
                        "rules": tier_info.rules,
                        "config_version": tier_info.config_version,
                    },
                )
                if not row.get("source_tier"):
                    row["source_tier"] = tier_info.tier

            snippet = str(row.get("snippet") or row.get("summary") or "").strip()
            trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
            trace.setdefault("excerpt", snippet[:220] if snippet else "")
            trace.setdefault("anchor", _stable_hash(f"{url_value}|{snippet[:160]}") if (url_value or snippet) else "")
            trace.setdefault("snapshot_hash", None)
            trace.setdefault("snapshot_url", None)
            row["trace"] = trace

    def _build_source_trace(
        self, evidence_cards: List[Dict[str, Any]], limit: int = 40
    ) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        earliest_published: Optional[datetime] = None
        first_seen: Optional[datetime] = None
        latest_event: Optional[datetime] = None

        for card in evidence_cards:
            if not isinstance(card, dict):
                continue
            source_name = str(card.get("source_name") or "").strip().lower()
            retrieval_mode = str(card.get("retrieval_mode") or "").strip().lower()
            evidence_origin = str(card.get("evidence_origin") or "external").strip().lower()
            url_value = str(card.get("url") or "").strip()
            # 溯源时间线聚焦“可回溯外部证据”，排除推理链衍生片段。
            if evidence_origin != "external" or source_name == "reasoning_chain" or retrieval_mode == "reasoning":
                continue
            if not url_value:
                continue
            key = _normalize_url(str(card.get("url") or ""))
            if not key:
                key = _stable_hash(
                    f"{card.get('source_name','')}|{str(card.get('snippet') or '')[:180]}"
                )
            if key in seen_keys:
                continue
            seen_keys.add(key)

            published_dt = _parse_datetime_like(card.get("published_at"))
            first_seen_dt = _parse_datetime_like(card.get("first_seen_at"))
            collected_dt = _parse_datetime_like(card.get("collected_at"))
            event_dt = published_dt or first_seen_dt or collected_dt
            if event_dt is None:
                continue
            if latest_event is None or event_dt > latest_event:
                latest_event = event_dt

            if published_dt is not None and (
                earliest_published is None or published_dt < earliest_published
            ):
                earliest_published = published_dt
            if first_seen_dt is not None and (first_seen is None or first_seen_dt < first_seen):
                first_seen = first_seen_dt
            if first_seen is None and event_dt is not None:
                first_seen = event_dt

            timeline.append(
                {
                    "evidence_id": card.get("id"),
                    "source_name": card.get("source_name"),
                    "source_tier": int(card.get("source_tier") or 3),
                    "url": card.get("url"),
                    "event_time": _to_utc_iso(event_dt),
                    "published_at": _to_utc_iso(published_dt)
                    if published_dt is not None
                    else card.get("published_at"),
                    "first_seen_at": _to_utc_iso(first_seen_dt)
                    if first_seen_dt is not None
                    else card.get("first_seen_at"),
                    "collected_at": card.get("collected_at"),
                    "retrieval_mode": card.get("retrieval_mode"),
                    "is_cached": bool(card.get("is_cached")),
                    "confidence": float(card.get("confidence") or 0.0),
                    "snippet": str(card.get("snippet") or "")[:220],
                }
            )

        timeline.sort(
            key=lambda x: _parse_datetime_like(x.get("event_time")) or datetime.max
        )
        compact = timeline[: max(1, int(limit))]
        for idx, row in enumerate(compact, start=1):
            row["rank"] = idx

        return {
            "first_seen_at": _to_utc_iso(first_seen) if first_seen is not None else None,
            "earliest_published_at": _to_utc_iso(earliest_published)
            if earliest_published is not None
            else None,
            "latest_event_at": _to_utc_iso(latest_event) if latest_event is not None else None,
            "timeline_count": len(timeline),
            "timeline": compact,
        }

    def _build_debug_summary(
        self,
        *,
        result_status: str,
        data_quality_flags: List[str],
        acquisition_report: Dict[str, Any],
        claim_analysis: Dict[str, Any],
        no_data_explainer: Optional[Dict[str, Any]],
        source_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        reasons.extend([str(x) for x in (data_quality_flags or []) if str(x)])
        if isinstance(no_data_explainer, dict):
            reason_code = str(no_data_explainer.get("reason_code") or "")
            if reason_code:
                reasons.append(reason_code)
        review_queue = list((claim_analysis or {}).get("review_queue") or [])
        claim_verdict = str((claim_analysis or {}).get("run_verdict") or "UNCERTAIN")
        return {
            "status": str(result_status or "unknown"),
            "claim_verdict": claim_verdict,
            "review_queue_count": len(review_queue),
            "reasons": sorted(list(dict.fromkeys(reasons))),
            "evidence": {
                "valid_evidence_count": int(acquisition_report.get("external_evidence_count") or 0),
                "primary_count": int(acquisition_report.get("primary_count") or 0),
                "background_count": int(acquisition_report.get("background_count") or 0),
                "noise_count": int(acquisition_report.get("noise_count") or 0),
                "platforms_with_data": int(acquisition_report.get("platforms_with_data") or 0),
                "platform_coverage": float(acquisition_report.get("platforms_with_data") or 0)
                / float(max(1, len(source_plan.get("selected_platforms") or []))),
            },
            "tier_coverage": acquisition_report.get("coverage_by_tier") or {},
            "next_queries": (
                list(no_data_explainer.get("next_queries") or [])
                if isinstance(no_data_explainer, dict)
                else []
            ),
        }

    def _build_iteration_plan(
        self,
        *,
        keyword: str,
        claim: str,
        claim_analysis: Dict[str, Any],
        data_quality_flags: List[str],
        source_plan: Dict[str, Any],
        available_platforms: List[str],
        max_queries: int,
    ) -> Dict[str, Any]:
        queries: List[str] = []
        flags = {str(x) for x in (data_quality_flags or []) if str(x)}
        review_queue = list((claim_analysis or {}).get("review_queue") or [])
        review_reasons = {
            str(reason)
            for item in review_queue
            if isinstance(item, dict)
            for reason in (item.get("reasons") or [])
        }

        keyword = str(keyword or "").strip()
        claim = str(claim or "").strip()
        if keyword:
            queries.append(keyword)
        if claim and claim != keyword:
            queries.append(claim[:120])
        if flags & {"INSUFFICIENT_VALID_EVIDENCE", "LOW_PLATFORM_COVERAGE"}:
            if keyword:
                queries.extend(
                    [
                        f"{keyword} 官方 通告",
                        f"{keyword} 官方 公告",
                        f"{keyword} 官方 通报",
                        f"{keyword} site:gov.cn",
                        f"{keyword} site:news.cn",
                    ]
                )
        if any("CONFLICT" in r or "REVIEW_REQUIRED" in r for r in review_reasons):
            if keyword:
                queries.extend(
                    [
                        f"{keyword} 澄清",
                        f"{keyword} 官方 说明",
                        f"{keyword} 权威 发布",
                    ]
                )
        if keyword and "TIME_UNKNOWN" in flags:
            queries.append(f"{keyword} 最新")

        seen: set[str] = set()
        deduped: List[str] = []
        for q in queries:
            qn = str(q or "").strip()
            if not qn or qn in seen:
                continue
            seen.add(qn)
            deduped.append(qn)
            if len(deduped) >= max(1, int(max_queries)):
                break

        tiered = source_plan.get("tiered_pools") or {}
        platforms = list(dict.fromkeys(tiered.get("tier1") or []))
        if not platforms:
            platforms = list(source_plan.get("must_have_platforms") or [])
        if not platforms:
            platforms = list(source_plan.get("selected_platforms") or [])
        if available_platforms:
            platforms = [p for p in platforms if p in available_platforms]

        return {
            "queries": deduped,
            "platforms": platforms,
            "reason_codes": sorted(list(flags | review_reasons)),
        }

    def _step_title(self, step_id: str) -> str:
        mapping = {
            "source_planning": "自动选源规划",
            "network_precheck": "网络预检",
            "enhanced_reasoning": "增强推理",
            "multiplatform_search": "多平台检索与过滤",
            "cross_platform_credibility": "跨平台可信度评估",
            "multi_agent": "多 Agent 综合",
            "external_sources": "外部权威源校验",
            "claim_analysis": "主张级判定",
            "reflection_iteration": "反思迭代补证",
            "opinion_monitoring": "评论与水军风险监测",
            "report_template_render": "报告模板渲染",
        }
        key = str(step_id or "").strip()
        if key in mapping:
            return mapping[key]
        return key.replace("_", " ").strip() or "未知步骤"

    def _collect_link_rows(
        self, rows: List[Dict[str, Any]], *, limit: int = 6
    ) -> List[Dict[str, str]]:
        links: List[Dict[str, str]] = []
        seen: set[str] = set()
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            url = _normalize_url(str(row.get("url") or ""))
            if not url or url in seen:
                continue
            seen.add(url)
            source = str(row.get("source_name") or row.get("platform") or "").strip()
            snippet = str(row.get("snippet") or row.get("summary") or "").strip()
            label = source or "source"
            if snippet:
                label = f"{label}: {snippet[:70]}"
            links.append({"label": label[:140], "url": url})
            if len(links) >= max(1, int(limit)):
                break
        return links

    def _collect_codes(self, *groups: Any, limit: int = 12) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for group in groups:
            if isinstance(group, (str, int, float)):
                key = str(group).strip()
                if key and key not in seen:
                    seen.add(key)
                    out.append(key)
                continue
            if not isinstance(group, list):
                continue
            for item in group:
                key = str(item or "").strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(key)
                if len(out) >= max(1, int(limit)):
                    return out
        return out

    def _build_step_summaries(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        steps = list(result.get("steps") or [])
        if not steps:
            return []

        enhanced = dict(result.get("enhanced") or {})
        credibility = dict(result.get("credibility") or {})
        multi_agent = dict(result.get("agent_outputs") or {})
        external_sources = list(result.get("external_sources") or [])
        evidence_registry = list(result.get("evidence_registry") or [])
        claim_analysis = dict(result.get("claim_analysis") or {})
        opinion_monitoring = dict(result.get("opinion_monitoring") or {})
        source_trace = dict(result.get("source_trace") or {})
        source_plan = dict(result.get("source_plan") or {})
        acquisition_report = dict(result.get("acquisition_report") or {})
        quality_summary = dict(result.get("quality_summary") or {})
        data_quality_flags = [str(x) for x in list(result.get("data_quality_flags") or []) if x]
        report_template = dict(result.get("report_template") or {})
        report_sections = list(result.get("report_sections") or [])
        no_data_explainer = result.get("no_data_explainer") if isinstance(result.get("no_data_explainer"), dict) else {}
        network_precheck = dict(result.get("network_precheck") or {})

        search_like_cards = [
            card
            for card in evidence_registry
            if isinstance(card, dict)
            and str(card.get("retrieval_mode") or "") not in {"reasoning", "cached_evidence"}
        ]
        timeline_links = self._collect_link_rows(list(source_trace.get("timeline") or []), limit=6)

        step_summaries: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps, start=1):
            step_id = str(step.get("id") or f"step_{idx}")
            status = str(step.get("status") or "unknown")
            title = self._step_title(step_id)
            links: List[Dict[str, str]] = []
            codes: List[str] = []
            metrics: Dict[str, Any] = {}
            summary_text = f"{title}执行状态：{status}。"

            if step_id == "source_planning":
                selected = list(source_plan.get("selected_platforms") or [])
                must_have = list(source_plan.get("must_have_platforms") or [])
                excluded = list(source_plan.get("excluded_platforms") or [])
                summary_text = (
                    f"自动选源完成：域={source_plan.get('domain') or 'general'}，"
                    f"必选 {len(must_have)} 个，实际选择 {len(selected)} 个。"
                )
                links = self._collect_link_rows(
                    [
                        {
                            "source_name": "selected_platform",
                            "url": f"https://www.google.com/search?q={quote_plus(str(p))}",
                            "snippet": p,
                        }
                        for p in selected[:6]
                    ],
                    limit=6,
                )
                codes = self._collect_codes(
                    source_plan.get("selection_reasons") or [],
                    source_plan.get("risk_notes") or [],
                    [f"EXCLUDED_{str(p).upper()}" for p in excluded[:4]],
                )
                metrics = {
                    "event_type": source_plan.get("event_type"),
                    "domain": source_plan.get("domain"),
                    "selected_platform_count": len(selected),
                    "must_have_platform_count": len(must_have),
                }
            elif step_id == "network_precheck":
                checked = int(network_precheck.get("checked") or 0)
                reachable = int(network_precheck.get("reachable_count") or 0)
                fail_ratio = round(float(network_precheck.get("fail_ratio") or 0.0), 4)
                summary_text = (
                    f"网络预检完成，探测主机 {checked} 个，可达 {reachable} 个，失败率 "
                    f"{round(fail_ratio * 100, 1)}%。"
                )
                details = list(network_precheck.get("details") or [])
                pre_links: List[Dict[str, Any]] = []
                for row in details:
                    if not isinstance(row, dict):
                        continue
                    host = str(row.get("host") or "").strip()
                    if not host:
                        continue
                    pre_links.append(
                        {
                            "source_name": "network_precheck",
                            "url": f"https://{host}",
                            "snippet": str(row.get("error") or ("reachable" if row.get("reachable") else "unreachable")),
                        }
                    )
                links = self._collect_link_rows(pre_links, limit=6)
                codes = self._collect_codes(
                    [f for f in data_quality_flags if f.startswith("NETWORK_PRECHECK")],
                    [str(row.get("error") or "") for row in details if isinstance(row, dict) and row.get("error")],
                )
                metrics = {
                    "checked": checked,
                    "reachable_count": reachable,
                    "fail_ratio": fail_ratio,
                }
            elif step_id == "enhanced_reasoning":
                chain = dict(enhanced.get("reasoning_chain") or {})
                final_score = round(float(chain.get("final_score") or 0.0), 4)
                final_level = str(chain.get("final_level") or "UNKNOWN")
                chain_steps = len(list(chain.get("steps") or []))
                risk_flags = list(chain.get("risk_flags") or [])
                summary_text = (
                    f"完成增强推理，生成 {chain_steps} 个推理子步骤，结论等级 {final_level}，"
                    f"得分 {round(final_score * 100, 1)}%。"
                )
                links = timeline_links[:3]
                codes = self._collect_codes(
                    risk_flags,
                    [f for f in data_quality_flags if f.startswith("ENHANCED_REASONING")],
                )
                metrics = {
                    "final_score": final_score,
                    "final_level": final_level,
                    "reasoning_step_count": chain_steps,
                }
            elif step_id == "multiplatform_search":
                valid_count = int(acquisition_report.get("valid_evidence_count") or 0)
                raw_count = int(acquisition_report.get("raw_collected_count") or 0)
                live_count = int(acquisition_report.get("live_evidence_count") or 0)
                cached_count = int(acquisition_report.get("cached_evidence_count") or 0)
                platforms_with_data = int(acquisition_report.get("platforms_with_data") or 0)
                summary_text = (
                    f"完成多平台检索，原始抓取 {raw_count} 条，验证后有效证据 {valid_count} 条，"
                    f"其中实时 {live_count} 条、缓存 {cached_count} 条，覆盖平台 {platforms_with_data} 个。"
                )
                links = self._collect_link_rows(search_like_cards, limit=8) or timeline_links
                reason_stats = (
                    dict(acquisition_report.get("platform_reason_stats") or {}).get("by_reason")
                    or {}
                )
                reason_codes = sorted(
                    [str(code) for code in reason_stats.keys() if code],
                    key=lambda code: -_safe_int(reason_stats.get(code), 0),
                )[:6]
                codes = self._collect_codes(
                    reason_codes,
                    [
                        f
                        for f in data_quality_flags
                        if f.startswith("SEARCH_")
                        or f.startswith("URL_PROBE")
                        or f.startswith("LIVE_")
                        or f.startswith("TARGET_EVIDENCE")
                        or f.startswith("LOW_PLATFORM")
                        or f.startswith("VALIDATION_")
                        or f.startswith("FALLBACK_")
                        or f.startswith("PROVISIONAL_")
                        or f.startswith("PLATFORM_")
                    ],
                )
                metrics = {
                    "raw_collected_count": raw_count,
                    "valid_evidence_count": valid_count,
                    "live_evidence_count": live_count,
                    "cached_evidence_count": cached_count,
                    "platforms_with_data": platforms_with_data,
                    "keyword_match_ratio": round(float(quality_summary.get("keyword_match_ratio") or 0.0), 4),
                    "reachable_ratio": round(float(quality_summary.get("reachable_ratio") or 0.0), 4),
                }
            elif step_id == "cross_platform_credibility":
                credibility_score = round(float(credibility.get("credibility_score") or 0.0), 4)
                anomalies = list(credibility.get("anomalies") or [])
                summary_text = (
                    f"完成跨平台可信度评估，可信度得分 {round(credibility_score * 100, 1)}%，"
                    f"识别异常 {len(anomalies)} 条。"
                )
                links = timeline_links[:4]
                anomaly_codes = [
                    str(item.get("type") or item.get("name") or "")
                    for item in anomalies
                    if isinstance(item, dict)
                ]
                codes = self._collect_codes(
                    anomaly_codes,
                    [str(credibility.get("status") or "")],
                    [f for f in data_quality_flags if f.startswith("CREDIBILITY_")],
                )
                metrics = {
                    "credibility_score": credibility_score,
                    "anomaly_count": len(anomalies),
                }
            elif step_id == "multi_agent":
                overall = round(float(multi_agent.get("overall_credibility") or 0.0), 4)
                consensus = list(multi_agent.get("consensus_points") or [])
                conflicts = list(multi_agent.get("conflicts") or [])
                recommendation = str(multi_agent.get("recommendation") or "").strip()
                digest = dict(multi_agent.get("llm_digest") or {})
                digest_summary = str(digest.get("summary") or "").strip()
                summary_text = (
                    f"完成多 Agent 综合，综合可信度 {round(overall * 100, 1)}%，"
                    f"共识 {len(consensus)} 条、冲突 {len(conflicts)} 条。"
                )
                if recommendation:
                    summary_text = f"{summary_text} 建议：{recommendation[:100]}"
                if digest_summary:
                    summary_text = f"{summary_text} 摘要：{digest_summary[:120]}"
                links = self._collect_link_rows(search_like_cards, limit=6) or timeline_links
                codes = self._collect_codes(
                    list(multi_agent.get("risk_flags") or []),
                    list(digest.get("gaps") or []),
                    [f for f in data_quality_flags if f.startswith("MULTI_AGENT")],
                )
                metrics = {
                    "overall_credibility": overall,
                    "consensus_count": len(consensus),
                    "conflict_count": len(conflicts),
                }
            elif step_id == "external_sources":
                reachable_count = sum(
                    1 for row in external_sources if isinstance(row, dict) and bool(row.get("reachable"))
                )
                promoted_count = sum(
                    1
                    for row in external_sources
                    if isinstance(row, dict) and bool(row.get("used_as_evidence"))
                )
                summary_text = (
                    f"外部权威源校验完成，命中 {len(external_sources)} 条，"
                    f"可达 {reachable_count} 条，入证据池 {promoted_count} 条。"
                )
                links = self._collect_link_rows(
                    [
                        {
                            "source_name": row.get("source"),
                            "url": row.get("url"),
                            "snippet": row.get("summary"),
                        }
                        for row in external_sources
                        if isinstance(row, dict)
                    ],
                    limit=8,
                )
                codes = self._collect_codes(
                    [
                        str(row.get("drop_reason") or "")
                        for row in external_sources
                        if isinstance(row, dict) and row.get("drop_reason")
                    ],
                    [f for f in data_quality_flags if f.startswith("EXTERNAL_SOURCES")],
                )
                metrics = {
                    "source_count": len(external_sources),
                    "reachable_count": reachable_count,
                    "promoted_count": promoted_count,
                }
            elif step_id == "claim_analysis":
                claims = list(claim_analysis.get("claims") or [])
                review_queue = list(claim_analysis.get("review_queue") or [])
                run_verdict = str(claim_analysis.get("run_verdict") or "UNCERTAIN")
                summary_text = (
                    f"主张级分析完成，识别主张 {len(claims)} 条，复核队列 {len(review_queue)} 条，"
                    f"运行结论 {run_verdict}。"
                )
                linked_rows: List[Dict[str, Any]] = []
                gate_codes: List[str] = []
                for claim_row in claims:
                    if not isinstance(claim_row, dict):
                        continue
                    linked_rows.extend(list(claim_row.get("linked_evidence") or []))
                    gate_codes.extend([str(code) for code in list(claim_row.get("gate_reasons") or []) if code])
                links = self._collect_link_rows(linked_rows, limit=8) or timeline_links
                factcheck_status = str(
                    (claim_analysis.get("factcheck") or {}).get("status") or "FACTCHECK_UNKNOWN"
                )
                codes = self._collect_codes(
                    gate_codes,
                    [factcheck_status],
                    [f for f in data_quality_flags if f.startswith("CLAIM_")],
                )
                metrics = {
                    "claim_count": len(claims),
                    "review_queue_count": len(review_queue),
                    "run_verdict": run_verdict,
                }
            elif step_id == "opinion_monitoring":
                total_comments = int(opinion_monitoring.get("total_comments") or 0)
                suspicious_ratio = round(
                    float(opinion_monitoring.get("suspicious_ratio") or 0.0), 4
                )
                suspicious_count = int(opinion_monitoring.get("suspicious_accounts_count") or 0)
                unique_accounts = int(opinion_monitoring.get("unique_accounts_count") or 0)
                risk_level = str(opinion_monitoring.get("risk_level") or "unknown").upper()
                summary_text = (
                    f"评论与水军风险监测完成，评论 {total_comments} 条，账号 {unique_accounts} 个，"
                    f"可疑账号 {suspicious_count} 个（{round(suspicious_ratio * 100, 1)}%），"
                    f"风险等级 {risk_level}。"
                )
                links = self._collect_link_rows(
                    list(opinion_monitoring.get("sample_comments") or []),
                    limit=8,
                ) or timeline_links
                codes = self._collect_codes(
                    list(opinion_monitoring.get("risk_flags") or []),
                    [f for f in data_quality_flags if f.startswith("OPINION_") or f.startswith("BOT_")],
                )
                metrics = {
                    "total_comments": total_comments,
                    "unique_accounts_count": unique_accounts,
                    "suspicious_accounts_count": suspicious_count,
                    "suspicious_ratio": suspicious_ratio,
                    "comment_target_reached": bool(opinion_monitoring.get("comment_target_reached")),
                    "risk_level": risk_level,
                }
            elif step_id == "report_template_render":
                template_id = str(report_template.get("template_id") or "unknown")
                summary_text = (
                    f"报告模板渲染完成，模板 {template_id}，章节 {len(report_sections)} 个，"
                    f"可追溯时间线 {int(source_trace.get('timeline_count') or 0)} 条。"
                )
                links = timeline_links
                codes = self._collect_codes(
                    [f for f in data_quality_flags if f.startswith("REPORT_")],
                    [str(result.get("status") or "unknown").upper()],
                )
                metrics = {
                    "section_count": len(report_sections),
                    "timeline_count": int(source_trace.get("timeline_count") or 0),
                    "template_id": template_id,
                }
            else:
                links = timeline_links[:3]
                codes = self._collect_codes(data_quality_flags[:6])

            if not links and no_data_explainer:
                nde_queries = [
                    {
                        "source_name": "next_query",
                        "url": f"https://www.google.com/search?q={quote_plus(str(q))}",
                        "snippet": q,
                    }
                    for q in list(no_data_explainer.get("next_queries") or [])[:3]
                ]
                links = self._collect_link_rows(nde_queries, limit=3)
            if not codes:
                codes = ["OK" if status == "success" else f"STEP_{status.upper()}"]
            step_summaries.append(
                {
                    "step_index": idx,
                    "step_id": step_id,
                    "title": title,
                    "status": status,
                    "summary_text": summary_text,
                    "links": links,
                    "codes": codes,
                    "metrics": metrics,
                }
            )
        return step_summaries

    async def _emit_data_progress(
        self,
        run_id: str,
        *,
        valid_evidence_count: int,
        raw_collected_count: int,
        platforms_with_data: int,
        target_valid_evidence_min: int,
        started_at: str,
        live_evidence_count: int = 0,
        cached_evidence_count: int = 0,
    ) -> None:
        await self.manager.append_event(
            run_id,
            "data_progress",
            {
                "valid_evidence_count": int(valid_evidence_count),
                "raw_collected_count": int(raw_collected_count),
                "platforms_with_data": int(platforms_with_data),
                "elapsed_ms": _elapsed_ms(started_at),
                "target_valid_evidence_min": int(target_valid_evidence_min),
                "live_evidence_count": int(live_evidence_count),
                "cached_evidence_count": int(cached_evidence_count),
            },
        )

    def _impact_for_platform_status(
        self,
        *,
        status: str,
        reason_code: str,
        items_collected: int,
    ) -> str:
        if int(items_collected or 0) > 0:
            return "low"
        status_l = str(status or "").lower()
        reason_l = str(reason_code or "").upper()
        if status_l in {"timeout", "circuit_open", "error"}:
            return "high"
        if reason_l in {
            "CRAWLER_TIMEOUT",
            "DNS_ERROR",
            "PROXY_UNREACHABLE",
            "LOGIN_REQUIRED",
            "CAPTCHA_REQUIRED",
            "BLOCKED",
            "SELECTOR_MISS",
        }:
            return "high"
        if "FALLBACK" in reason_l:
            return "medium"
        return "medium"

    async def _search_round(
        self,
        *,
        run_id: str,
        crawlers: Any,
        keyword: str,
        platforms: List[str],
        limit_per_platform: int,
        max_concurrency: Optional[int] = None,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
        progress_started_at: Optional[str] = None,
        progress_target_valid_evidence_min: Optional[int] = None,
        progress_emit_every: Optional[int] = None,
        realtime_analysis_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        search_data: Dict[str, List[Dict[str, Any]]] = {}
        reason_stats: Dict[str, Dict[str, int]] = {}
        mediacrawler_platforms_hit: set[str] = set()
        mediacrawler_failures: List[Dict[str, Any]] = []
        if not platforms:
            return {
                "search_data": search_data,
                "reason_stats": reason_stats,
                "mediacrawler_platforms_hit": sorted(list(mediacrawler_platforms_hit)),
                "mediacrawler_failures": mediacrawler_failures,
            }

        default_concurrency = int(
            getattr(settings, "CRAWLER_SEARCH_MAX_CONCURRENCY", 8)
        )
        concurrency = max(
            1,
            min(
                len(platforms),
                int(max_concurrency or default_concurrency),
            ),
        )
        sem = asyncio.Semaphore(concurrency)
        normalize_reason = getattr(crawlers, "_normalize_reason_code", None)
        timeout_sec = float(getattr(settings, "CRAWLER_PLATFORM_SEARCH_TIMEOUT_SECONDS", 15.0))
        timeout_max = float(
            getattr(settings, "CRAWLER_PLATFORM_SEARCH_TIMEOUT_MAX_SECONDS", timeout_sec)
        )
        if timeout_max > 0:
            timeout_sec = min(timeout_sec, timeout_max)
        emit_every = max(1, int(progress_emit_every or 1))
        realtime = realtime_analysis_state or {}
        realtime_enabled = bool(realtime.get("enabled"))
        realtime_processor = realtime.get("processor")
        realtime_seen = realtime.get("seen")
        realtime_tasks = realtime.get("tasks")
        realtime_sem = realtime.get("sem")
        realtime_timeout_sec = realtime.get("timeout_sec")
        realtime_top_k = realtime.get("top_k")

        def _track_realtime_task(task: asyncio.Task) -> None:
            if isinstance(realtime_tasks, set):
                realtime_tasks.add(task)

            def _done(t: asyncio.Task) -> None:
                if isinstance(realtime_tasks, set):
                    realtime_tasks.discard(t)
                try:
                    t.result()
                except Exception as exc:
                    logger.warning(f"realtime platform analysis task failed: {exc!r}")

            task.add_done_callback(_done)

        async def _run_platform(platform: str) -> Dict[str, Any]:
            async with sem:
                started = time.monotonic()
                try:
                    row = await asyncio.wait_for(
                        crawlers.search_single_platform_verbose(
                            platform=platform,
                            keyword=keyword,
                            limit=limit_per_platform,
                            mediacrawler_options=mediacrawler_options,
                        ),
                        timeout=timeout_sec,
                    )
                    if isinstance(row, dict):
                        row.setdefault("platform", platform)
                        return row
                    raise RuntimeError("search_single_platform_verbose returned non-dict")
                except asyncio.TimeoutError:
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    return {
                        "platform": platform,
                        "items": [],
                        "status": "timeout",
                        "reason_code": "CRAWLER_TIMEOUT",
                        "message": "timeout",
                        "items_collected": 0,
                        "elapsed_ms": elapsed_ms,
                        "mediacrawler": {},
                    }
                except Exception as exc:
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    msg = str(exc)
                    reason = (
                        normalize_reason(msg) if callable(normalize_reason) else "CRAWLER_ERROR"
                    )
                    return {
                        "platform": platform,
                        "items": [],
                        "status": "error",
                        "reason_code": reason,
                        "message": msg,
                        "items_collected": 0,
                        "elapsed_ms": elapsed_ms,
                        "mediacrawler": {},
                    }

        tasks = [asyncio.create_task(_run_platform(platform)) for platform in platforms]
        completed = 0
        try:
            for task in asyncio.as_completed(tasks):
                row = await task
                if not isinstance(row, dict):
                    row = {
                        "platform": "unknown",
                        "items": [],
                        "status": "error",
                        "reason_code": "CRAWLER_ERROR",
                        "message": "invalid platform result",
                        "items_collected": 0,
                        "elapsed_ms": 0,
                        "mediacrawler": {},
                    }
                platform = str(row.get("platform") or "unknown")
                items = row.get("items") if isinstance(row, dict) else []
                if not isinstance(items, list):
                    items = []
                search_data[platform] = items
                reason = str((row or {}).get("reason_code") or "UNKNOWN")
                reason_stats.setdefault(platform, {})
                reason_stats[platform][reason] = reason_stats[platform].get(reason, 0) + 1
                await self.manager.append_event(
                    run_id,
                    "platform_status",
                    {
                        "platform": platform,
                        "status": (row or {}).get("status", "error"),
                        "reason_code": reason,
                        "items_collected": len(items),
                        "elapsed_ms": int((row or {}).get("elapsed_ms", 0) or 0),
                        "impact_on_verdict": self._impact_for_platform_status(
                            status=(row or {}).get("status", "error"),
                            reason_code=reason,
                            items_collected=len(items),
                        ),
                    },
                )
                sidecar = dict((row or {}).get("mediacrawler") or {})
                if sidecar:
                    if int(sidecar.get("mediacrawler_count") or 0) > 0:
                        mediacrawler_platforms_hit.add(str(platform))
                    await self.manager.append_event(
                        run_id,
                        "mediacrawler_platform_done",
                        {
                            "run_id": run_id,
                            "platform": platform,
                            "triggered": bool(sidecar.get("triggered")),
                            "trigger_reason": sidecar.get("trigger_reason"),
                            "native_count": int(sidecar.get("native_count") or 0),
                            "mediacrawler_count": int(sidecar.get("mediacrawler_count") or 0),
                            "merged_count": int(sidecar.get("merged_count") or 0),
                            "task_id": sidecar.get("task_id"),
                        },
                    )
                    if bool(sidecar.get("degraded")):
                        mediacrawler_failures.append(
                            {
                                "platform": platform,
                                "reason": sidecar.get("error") or "MEDIACRAWLER_DEGRADED",
                                "trigger_reason": sidecar.get("trigger_reason"),
                            }
                        )
                        await self.manager.append_event(
                            run_id,
                            "mediacrawler_degraded",
                            {
                                "run_id": run_id,
                                "platform": platform,
                                "reason": sidecar.get("error") or "MEDIACRAWLER_DEGRADED",
                                "trigger_reason": sidecar.get("trigger_reason"),
                                "impact_scope": {
                                    "lost_posts": int(sidecar.get("mediacrawler_count") or 0),
                                    "native_available": int(sidecar.get("native_count") or 0),
                                    "merged_available": int(sidecar.get("merged_count") or 0),
                                },
                            },
                        )
                if reason in {
                    "BLOCKED",
                    "SELECTOR_MISS",
                    "CAPTCHA_REQUIRED",
                    "LOGIN_REQUIRED",
                }:
                    try:
                        manual_takeover_waiting_total.labels(
                            platform=platform, reason_code=reason
                        ).inc()
                    except Exception:
                        pass
                    await self.manager.append_event(
                        run_id,
                        "manual_takeover_waiting",
                        {
                            "platform": platform,
                            "reason_code": reason,
                            "message": f"{platform} 命中验证/选择器阻断，建议人工接管后继续。",
                        },
                    )
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "MANUAL_TAKEOVER_WAITING",
                            "platform": platform,
                            "message": f"{platform} 需要人工接管（{reason}）",
                        },
                    )
                if (
                    realtime_enabled
                    and realtime_processor
                    and isinstance(items, list)
                    and items
                    and isinstance(realtime_seen, set)
                    and platform not in realtime_seen
                ):
                    realtime_seen.add(platform)

                    async def _run_realtime_analysis(
                        platform_name: str, platform_items: List[Dict[str, Any]]
                    ) -> None:
                        if isinstance(realtime_sem, asyncio.Semaphore):
                            async with realtime_sem:
                                result = await realtime_processor.analyze_platform_realtime(
                                    keyword=keyword,
                                    platform=platform_name,
                                    items=platform_items,
                                    top_k=realtime_top_k,
                                    timeout_sec=realtime_timeout_sec,
                                )
                        else:
                            result = await realtime_processor.analyze_platform_realtime(
                                keyword=keyword,
                                platform=platform_name,
                                items=platform_items,
                                top_k=realtime_top_k,
                                timeout_sec=realtime_timeout_sec,
                            )
                        analysis = result.get("analysis") if isinstance(result, dict) else {}
                        await self.manager.append_event(
                            run_id,
                            "platform_analysis_ready",
                            {
                                "platform": platform_name,
                                "score": float((analysis or {}).get("credibility_score", 0.0) or 0.0),
                                "risk_flags": (analysis or {}).get("risk_flags", []),
                                "summary": (analysis or {}).get("summary", ""),
                                "sentiment": (analysis or {}).get("sentiment", "neutral"),
                                "post_count": len(platform_items),
                                "sampled_count": int((result.get("metadata") or {}).get("sampled_count", 0)),
                                "fallback": bool(result.get("fallback")),
                            },
                        )

                    task = asyncio.create_task(
                        _run_realtime_analysis(platform, list(items))
                    )
                    _track_realtime_task(task)
                completed += 1
                if (
                    progress_started_at
                    and progress_target_valid_evidence_min is not None
                    and completed % emit_every == 0
                ):
                    raw_collected_count = sum(len(items or []) for items in search_data.values())
                    platforms_with_data = sum(1 for items in search_data.values() if (items or []))
                    await self._emit_data_progress(
                        run_id=run_id,
                        valid_evidence_count=0,
                        raw_collected_count=raw_collected_count,
                        platforms_with_data=platforms_with_data,
                        target_valid_evidence_min=int(progress_target_valid_evidence_min),
                        started_at=progress_started_at,
                        live_evidence_count=0,
                        cached_evidence_count=0,
                    )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "search_data": search_data,
            "reason_stats": reason_stats,
            "mediacrawler_platforms_hit": sorted(list(mediacrawler_platforms_hit)),
            "mediacrawler_failures": mediacrawler_failures,
        }

    def _split_platform_pools(
        self,
        *,
        crawlers: Any,
        source_profile: str,
        available_platforms: List[str],
        must_have_platforms: Optional[List[str]] = None,
    ) -> Dict[str, List[str]]:
        must_have = [p for p in (must_have_platforms or []) if p in available_platforms]

        def _promote_must_have(
            stable_pool: List[str],
            experimental_pool: List[str],
        ) -> Dict[str, List[str]]:
            if not must_have:
                return {
                    "stable_pool": stable_pool,
                    "experimental_pool": experimental_pool,
                }
            ordered_stable: List[str] = []
            seen: set[str] = set()
            for p in must_have + stable_pool:
                if p in seen:
                    continue
                seen.add(p)
                ordered_stable.append(p)
            ordered_experimental = [
                p for p in experimental_pool if p not in seen
            ]
            return {
                "stable_pool": ordered_stable,
                "experimental_pool": ordered_experimental,
            }

        if source_profile == "full":
            return {"stable_pool": list(available_platforms), "experimental_pool": []}
        if hasattr(crawlers, "split_platform_pools"):
            pools = crawlers.split_platform_pools(
                requested_platforms=available_platforms,
                profile=source_profile,
            )
            stable_pool = [p for p in (pools.get("stable_pool") or []) if p in available_platforms]
            experimental_pool = [p for p in (pools.get("experimental_pool") or []) if p in available_platforms]
            if stable_pool:
                return _promote_must_have(stable_pool, experimental_pool)
        stable_seed = [p for p in STABLE_MIXED_PROFILE if p in available_platforms]
        if not stable_seed:
            stable_seed = list(available_platforms[: min(6, len(available_platforms))])
        experimental = [p for p in available_platforms if p not in stable_seed]
        return _promote_must_have(stable_seed, experimental)

    def _get_platform_tier(self, *, crawlers: Any, platform: str) -> int:
        domains = []
        if hasattr(crawlers, "get_platform_domains"):
            domains = list(crawlers.get_platform_domains(platform) or [])
        tiers: List[int] = []
        for domain in domains or []:
            try:
                tiers.append(resolve_source_tier(domain).tier)
            except Exception:
                continue
        if tiers:
            return min(tiers)
        return 3

    def _build_tiered_pools(
        self,
        *,
        crawlers: Any,
        available_platforms: List[str],
        must_have_platforms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        tier1: List[str] = []
        tier2: List[str] = []
        tier3: List[str] = []
        tier_map: Dict[str, int] = {}
        for platform in available_platforms:
            tier = self._get_platform_tier(crawlers=crawlers, platform=platform)
            tier_map[platform] = tier
            if tier == 1:
                tier1.append(platform)
            elif tier == 2:
                tier2.append(platform)
            else:
                tier3.append(platform)

        must_have = [p for p in (must_have_platforms or []) if p in available_platforms]
        for p in must_have:
            if p not in tier1 and p not in tier2:
                tier1.append(p)
            if p in tier3:
                tier3.remove(p)

        return {
            "tier1_pool": tier1,
            "tier2_pool": tier2,
            "tier3_pool": tier3,
            "tier_map": tier_map,
        }

    def _build_staged_validated_candidates(
        self,
        *,
        keyword: str,
        search_data: Dict[str, List[Dict[str, Any]]],
        allowed_domains: set[str],
        candidate_top_n: int,
        final_top_m: int,
        reachability_map: Dict[str, Dict[str, Any]],
        min_low_relevance_accept: int = 3,
        min_platform_coverage: int = 2,
    ) -> Dict[str, Any]:
        gather = self._build_validated_candidates(
            keyword=keyword,
            search_data=search_data,
            allowed_domains=allowed_domains,
            quality_mode="balanced",
            reachability_map={},
        )
        candidates = list(gather.get("valid_items") or [])[: max(1, int(candidate_top_n))]
        strict_valid: List[Dict[str, Any]] = []
        provisional_valid: List[Dict[str, Any]] = []
        strict_invalid: List[Dict[str, Any]] = list(gather.get("invalid_items") or [])
        reason_counter: Counter[str] = Counter(gather.get("reason_counter") or {})
        platform_valid_counter: Counter[str] = Counter()
        seen_url: set[str] = set()
        for row in candidates:
            url = _normalize_url(str(row.get("url") or ""))
            if not url or url in seen_url:
                continue
            seen_url.add(url)
            reachable = reachability_map.get(url, {})
            item = row.get("item") if isinstance(row.get("item"), dict) else {}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            retrieval_mode = str(metadata.get("retrieval_mode") or "").lower()
            trusted_tier = _tier_for_url(url) <= 2
            probe_checked = bool(reachable)
            if not bool(reachable.get("reachable")):
                reason = str(reachable.get("reason") or "UNREACHABLE")
                reason_counter[reason] += 1
                strict_invalid.append(
                    {"platform": row.get("platform"), "url": url, "reason": reason}
                )
                # staged strict下，URL探测缺失/超时时保留可信域名的实时证据，避免 live 证据被清零
                allow_provisional = False
                if retrieval_mode in {
                    "rss_emergency_fallback",
                    "web_search_fallback",
                    "hot_fallback",
                    "live",
                } and trusted_tier:
                    allow_provisional = True
                if (
                    not probe_checked
                    or reason in {"UNREACHABLE", "CRAWLER_TIMEOUT", "PROBE_ERROR"}
                ) and trusted_tier:
                    allow_provisional = True
                if allow_provisional:
                    row_p = dict(row)
                    row_p["reachable"] = False
                    row_p["reachability_reason"] = reason
                    row_p["provisional"] = True
                    provisional_valid.append(row_p)
                    reason_counter["PROBE_FALLBACK_ACCEPTED"] += 1
                continue
            row2 = dict(row)
            row2["reachable"] = True
            row2["reachability_reason"] = str(reachable.get("reason") or "OK")
            strict_valid.append(row2)
            platform_valid_counter[str(row.get("platform") or "unknown")] += 1
        strict_valid.sort(
            key=lambda x: (x.get("relevance_score", 0.0), x.get("reachable", False)),
            reverse=True,
        )
        provisional_valid.sort(
            key=lambda x: x.get("relevance_score", 0.0),
            reverse=True,
        )
        final_rows = strict_valid[: max(1, int(final_top_m))]
        final_seen_urls = {
            _normalize_url(str(x.get("url") or "")) for x in final_rows if isinstance(x, dict)
        }
        if len(final_rows) < 3 and provisional_valid:
            need = min(max(3 - len(final_rows), 1), len(provisional_valid))
            target_size = len(final_rows) + need
            for _ in range(need):
                reason_counter["PROBE_FALLBACK_ACCEPTED"] += 1
            for row in provisional_valid:
                if len(final_rows) >= target_size or len(final_rows) >= max(3, int(final_top_m)):
                    break
                norm_url = _normalize_url(str(row.get("url") or ""))
                if norm_url and norm_url in final_seen_urls:
                    continue
                final_rows.append(row)
                if norm_url:
                    final_seen_urls.add(norm_url)
        if not final_rows and provisional_valid:
            fallback_limit = min(max(3, int(final_top_m // 4) or 3), len(provisional_valid))
            for _ in range(fallback_limit):
                reason_counter["PROBE_FALLBACK_ACCEPTED"] += 1
            final_rows = provisional_valid[:fallback_limit]
            final_seen_urls = {
                _normalize_url(str(x.get("url") or "")) for x in final_rows if isinstance(x, dict)
            }

        low_rel_candidates = list(gather.get("low_relevance_candidates") or [])
        low_rel_candidates.sort(
            key=lambda x: (x.get("relevance_score", 0.0), -_tier_for_url(str(x.get("url") or ""))),
            reverse=True,
        )
        target_floor = min(
            max(1, int(final_top_m)),
            max(3, int(min_low_relevance_accept)),
        )
        if len(final_rows) < target_floor and low_rel_candidates:
            need = min(target_floor - len(final_rows), len(low_rel_candidates))
            by_platform: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in low_rel_candidates:
                norm_url = _normalize_url(str(row.get("url") or ""))
                if norm_url and norm_url in final_seen_urls:
                    continue
                platform = str(row.get("platform") or "unknown")
                by_platform[platform].append(row)

            platform_order = sorted(
                list(by_platform.keys()),
                key=lambda p: float((by_platform.get(p) or [{}])[0].get("relevance_score", 0.0)),
                reverse=True,
            )

            accepted = 0
            while accepted < need and platform_order:
                progressed = False
                for platform in list(platform_order):
                    queue = by_platform.get(platform) or []
                    while queue:
                        row = queue.pop(0)
                        norm_url = _normalize_url(str(row.get("url") or ""))
                        if norm_url and norm_url in final_seen_urls:
                            continue
                        row2 = dict(row)
                        row2["provisional"] = True
                        row2["low_relevance_fallback"] = True
                        final_rows.append(row2)
                        if norm_url:
                            final_seen_urls.add(norm_url)
                        platform_valid_counter[str(row2.get("platform") or "unknown")] += 1
                        reason_counter["LOW_RELEVANCE_FALLBACK_ACCEPTED"] += 1
                        accepted += 1
                        progressed = True
                        break
                    if accepted >= need:
                        break
                    if not queue and platform in platform_order:
                        platform_order.remove(platform)
                if not progressed:
                    break
        coverage_target = min(
            max(1, int(min_platform_coverage)),
            len({str(row.get("platform") or "unknown") for row in low_rel_candidates}) or 1,
        )
        selected_platforms = {
            str(row.get("platform") or "unknown")
            for row in final_rows
            if isinstance(row, dict)
        }
        if len(selected_platforms) < coverage_target and low_rel_candidates:
            for row in low_rel_candidates:
                platform = str(row.get("platform") or "unknown")
                if platform in selected_platforms:
                    continue
                norm_url = _normalize_url(str(row.get("url") or ""))
                if norm_url and norm_url in final_seen_urls:
                    continue
                row2 = dict(row)
                row2["provisional"] = True
                row2["low_relevance_fallback"] = True
                final_rows.append(row2)
                if norm_url:
                    final_seen_urls.add(norm_url)
                selected_platforms.add(platform)
                platform_valid_counter[platform] += 1
                reason_counter["LOW_RELEVANCE_FALLBACK_ACCEPTED"] += 1
                reason_counter["PLATFORM_COVERAGE_TOPUP"] += 1
                if len(selected_platforms) >= coverage_target:
                    break
        return {
            "gather_count": len(gather.get("valid_items") or []),
            "candidate_count": len(candidates),
            "final_count": len(final_rows),
            "valid_items": final_rows,
            "invalid_items": strict_invalid,
            "reason_counter": dict(reason_counter),
            "platform_valid_counter": dict(platform_valid_counter),
            "deduplicated_count": len(seen_url),
        }

    def _interleave_rows_by_platform(
        self, rows: List[Dict[str, Any]], limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not rows:
            return []
        order_mode = str(
            getattr(settings, "INVESTIGATION_EVIDENCE_ORDER_MODE", "relevance_desc")
        ).strip().lower()
        if order_mode in {"relevance_desc", "relevance", "global_relevance"}:
            out = sorted(
                list(rows or []),
                key=lambda x: (
                    float(x.get("relevance_score", 0.0)),
                    bool(x.get("keyword_match")),
                    bool(x.get("reachable", False)),
                ),
                reverse=True,
            )
            if limit is not None:
                return out[: max(1, int(limit))]
            return out
        by_platform: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict):
                continue
            platform = str(row.get("platform") or "unknown")
            by_platform[platform].append(row)
        for queue in by_platform.values():
            queue.sort(key=lambda x: float(x.get("relevance_score", 0.0)), reverse=True)
        platform_order = sorted(
            list(by_platform.keys()),
            key=lambda p: (
                len(by_platform.get(p) or []),
                float((by_platform.get(p) or [{}])[0].get("relevance_score", 0.0)),
            ),
            reverse=True,
        )
        out: List[Dict[str, Any]] = []
        while platform_order:
            progressed = False
            for platform in list(platform_order):
                queue = by_platform.get(platform) or []
                if not queue:
                    if platform in platform_order:
                        platform_order.remove(platform)
                    continue
                out.append(queue.pop(0))
                progressed = True
                if limit is not None and len(out) >= max(1, int(limit)):
                    return out
            if not progressed:
                break
        return out

    def _merge_cached_evidence(
        self,
        *,
        keyword: str,
        run_id: str,
        existing_cards: List[Dict[str, Any]],
        cached_cards: List[Dict[str, Any]],
        max_add: int,
        source_plan: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = list(existing_cards)
        seen_url = {
            _normalize_url(str(card.get("url") or ""))
            for card in existing_cards
            if isinstance(card, dict)
        }
        excluded_platforms = {
            str(p).strip().lower()
            for p in list((source_plan or {}).get("excluded_platforms") or [])
            if str(p).strip()
        }
        min_cached_relevance = max(
            0.0,
            _safe_float(
                getattr(settings, "INVESTIGATION_CACHED_EVIDENCE_MIN_RELEVANCE", 0.12),
                0.12,
            ),
        )
        grouped_cards: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for card in cached_cards:
            if not isinstance(card, dict):
                continue
            source = str(
                card.get("source_name")
                or card.get("source")
                or card.get("platform")
                or "unknown"
            ).strip().lower()
            grouped_cards[source].append(card)

        # Round-robin merge by source to improve cached platform diversity.
        diversified_cards: List[Dict[str, Any]] = []
        source_keys = sorted(grouped_cards.keys(), key=lambda k: len(grouped_cards[k]), reverse=True)
        while source_keys and len(diversified_cards) < len(cached_cards):
            next_keys: List[str] = []
            for source in source_keys:
                bucket = grouped_cards.get(source) or []
                if bucket:
                    diversified_cards.append(bucket.pop(0))
                if bucket:
                    next_keys.append(source)
            source_keys = next_keys

        added = 0
        now_ts = datetime.utcnow().timestamp()
        for card in diversified_cards:
            if added >= max_add:
                break
            if not isinstance(card, dict):
                continue
            url = _normalize_url(str(card.get("url") or ""))
            if url and url in seen_url:
                continue
            if url:
                seen_url.add(url)
            out = dict(card)
            raw_text = " ".join(
                [
                    str(out.get("snippet") or ""),
                    str(out.get("title") or ""),
                    str(out.get("content_text") or out.get("content") or ""),
                ]
            ).strip()
            cache_relevance = max(
                _safe_float(out.get("relevance_score"), 0.0),
                _keyword_relevance_score(keyword=keyword, text_blob=raw_text),
            )
            cache_keyword_match = bool(out.get("keyword_match"))
            if not cache_keyword_match and cache_relevance < min_cached_relevance:
                continue
            source_name = str(
                out.get("source_name") or out.get("source") or out.get("platform") or "unknown"
            ).strip().lower()
            if source_name in excluded_platforms and cache_relevance < max(0.4, min_cached_relevance):
                continue
            out["is_cached"] = True
            out["retrieval_mode"] = "cached_evidence"
            out["claim_ref"] = out.get("claim_ref") or keyword
            out["cache_run_id"] = out.get("cache_run_id") or out.get("run_id")
            out["keyword_match"] = cache_keyword_match
            out["relevance_score"] = float(cache_relevance)
            out_meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
            published_dt = _parse_datetime_like(
                out.get("published_at")
                or out.get("timestamp")
                or out.get("created_at")
                or out_meta.get("published_at")
                or out_meta.get("timestamp")
                or out_meta.get("created_at")
            )
            raw_created = str(out.get("cache_created_at") or out.get("collected_at") or "")
            freshness_hours = 0.0
            try:
                if raw_created:
                    created_dt = datetime.fromisoformat(raw_created.replace("Z", ""))
                    freshness_hours = max(
                        0.0, (now_ts - created_dt.timestamp()) / 3600.0
                    )
            except Exception:
                freshness_hours = 0.0
            out["freshness_hours"] = round(float(freshness_hours), 2)
            if published_dt is not None:
                out["published_at"] = _to_utc_iso(published_dt)
            else:
                out["published_at"] = out.get("published_at")
            first_seen_dt = (
                _parse_datetime_like(out.get("first_seen_at"))
                or published_dt
                or _parse_datetime_like(raw_created)
                or _parse_datetime_like(out.get("collected_at"))
            )
            if first_seen_dt is not None:
                out["first_seen_at"] = _to_utc_iso(first_seen_dt)
            elif not out.get("first_seen_at"):
                out["first_seen_at"] = _utc_now()
            out["id"] = str(out.get("id") or f"ev_cached_{run_id}_{len(merged)+1}")
            merged.append(out)
            added += 1
        return merged

    def _build_quality_summary(
        self,
        *,
        valid_cards: List[Dict[str, Any]],
        raw_collected_count: int,
        invalid_count: int,
    ) -> Dict[str, Any]:
        if not valid_cards:
            return {
                "keyword_match_ratio": 0.0,
                "reachable_ratio": 0.0,
                "specific_url_ratio": 0.0,
                "domain_diversity": 0,
                "invalid_evidence_ratio": 1.0 if raw_collected_count else 0.0,
            }
        keyword_match = sum(1 for x in valid_cards if x.get("keyword_match"))
        reachable = sum(1 for x in valid_cards if x.get("validation_status") == "reachable")
        specific = sum(1 for x in valid_cards if _looks_like_specific_content_url(x.get("url", "")))
        hosts = {
            (urlparse(x.get("url", "")).hostname or "").lower()
            for x in valid_cards
            if x.get("url")
        }
        return {
            "keyword_match_ratio": round(keyword_match / max(1, len(valid_cards)), 4),
            "reachable_ratio": round(reachable / max(1, len(valid_cards)), 4),
            "specific_url_ratio": round(specific / max(1, len(valid_cards)), 4),
            "domain_diversity": len([h for h in hosts if h]),
            "invalid_evidence_ratio": round(invalid_count / max(1, raw_collected_count), 4),
        }

    def _resolve_network_precheck_hosts(self, req: Dict[str, Any]) -> List[str]:
        from_req = req.get("network_precheck_hosts")
        if isinstance(from_req, list):
            hosts = [str(x).strip() for x in from_req if str(x).strip()]
            if hosts:
                return list(dict.fromkeys(hosts))
        from_settings = str(
            getattr(
                settings,
                "INVESTIGATION_NETWORK_PRECHECK_HOSTS",
                "duckduckgo.com,feeds.bbci.co.uk,api.siliconflow.cn",
            )
        )
        hosts = [x.strip() for x in from_settings.split(",") if x.strip()]
        return list(dict.fromkeys(hosts))

    async def _network_precheck(
        self, hosts: List[str], timeout_sec: float
    ) -> Dict[str, Any]:
        async def _probe(host: str) -> Dict[str, Any]:
            row: Dict[str, Any] = {
                "host": host,
                "reachable": False,
                "dns_ok": False,
                "tcp_ok": False,
                "error": "",
            }
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(socket.gethostbyname, host), timeout=timeout_sec
                )
                row["dns_ok"] = True
            except Exception as exc:
                row["error"] = f"dns:{exc}"
                return row
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, 443), timeout=timeout_sec
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                row["tcp_ok"] = True
                row["reachable"] = True
                return row
            except Exception as exc:
                row["error"] = f"tcp:{exc}"
                return row

        checked_hosts = [h for h in hosts if h]
        if not checked_hosts:
            return {
                "hosts": [],
                "details": [],
                "checked": 0,
                "failed": 0,
                "fail_ratio": 0.0,
                "network_ok": True,
            }
        details = await asyncio.gather(*[_probe(h) for h in checked_hosts], return_exceptions=False)
        failed = sum(1 for row in details if not row.get("reachable"))
        checked = len(details)
        fail_ratio = float(failed) / float(max(1, checked))
        return {
            "hosts": checked_hosts,
            "details": details,
            "checked": checked,
            "failed": failed,
            "fail_ratio": round(fail_ratio, 4),
            "network_ok": failed == 0,
        }

    async def execute(self, run_id: str, req: Dict[str, Any]):
        run_started_at = _utc_now()
        await self.manager.set_status(run_id, "running")
        await self.manager.append_event(
            run_id, "run_started", {"run_id": run_id, "request": req}
        )

        claim = (req.get("claim") or "").strip()
        keyword = _derive_keyword(claim=claim, keyword=req.get("keyword"))
        audience_profile = req.get("audience_profile") or "both"
        report_template_id = req.get("report_template_id") or "deep-research-report"
        quality_mode = str(
            req.get("quality_mode") or getattr(settings, "INVESTIGATION_QUALITY_MODE", "strict")
        ).lower()
        if quality_mode not in {"strict", "balanced"}:
            quality_mode = "strict"
        min_valid_evidence_floor = max(
            10,
            _safe_int(
                getattr(settings, "INVESTIGATION_MIN_VALID_EVIDENCE_HARD_FLOOR", 100),
                100,
            ),
        )
        requested_target_valid_evidence = _safe_int(
            req.get("target_valid_evidence_min"),
            _safe_int(getattr(settings, "INVESTIGATION_TARGET_VALID_EVIDENCE_MIN", 300), 300),
        )
        target_valid_evidence_min = max(
            min_valid_evidence_floor,
            requested_target_valid_evidence,
        )
        live_evidence_target = max(
            0,
            _safe_int(
                req.get("live_evidence_target"),
                _safe_int(getattr(settings, "INVESTIGATION_LIVE_EVIDENCE_TARGET", 30), 30),
            ),
        )
        minimum_live_target = min(60, max(20, int(target_valid_evidence_min * 0.35)))
        live_evidence_target = max(live_evidence_target, minimum_live_target)
        source_profile = str(
            req.get("source_profile")
            or getattr(settings, "INVESTIGATION_SOURCE_PROFILE_DEFAULT", "stable_mixed_v1")
        ).strip().lower()
        if source_profile not in {"stable_mixed_v1", "full"}:
            source_profile = "stable_mixed_v1"
        source_strategy = str(req.get("source_strategy") or "auto").strip().lower()
        if source_strategy not in {"auto", "stable_mixed_v1", "full"}:
            source_strategy = "auto"
        if source_strategy in {"stable_mixed_v1", "full"}:
            source_profile = source_strategy
        strict_pipeline = str(
            req.get("strict_pipeline")
            or getattr(settings, "INVESTIGATION_STRICT_PIPELINE_DEFAULT", "staged_strict")
        ).strip().lower()
        if strict_pipeline not in {"staged_strict", "full_strict"}:
            strict_pipeline = "staged_strict"
        enable_cached_evidence = bool(
            req.get(
                "enable_cached_evidence",
                getattr(settings, "INVESTIGATION_ENABLE_CACHED_EVIDENCE", True),
            )
        )
        requested_phase1_target_valid_evidence = max(
            10,
            _safe_int(
                req.get("phase1_target_valid_evidence"),
                _safe_int(getattr(settings, "INVESTIGATION_PHASE1_TARGET_VALID_EVIDENCE", 50), 50),
            ),
        )
        recommended_phase1_target = min(
            target_valid_evidence_min,
            max(40, int(target_valid_evidence_min * 0.6)),
        )
        phase1_target_valid_evidence = min(
            target_valid_evidence_min,
            max(requested_phase1_target_valid_evidence, recommended_phase1_target),
        )
        phase1_deadline_sec = max(
            10,
            _safe_int(
                req.get("phase1_deadline_sec"),
                _safe_int(getattr(settings, "INVESTIGATION_PHASE1_DEADLINE_SEC", 90), 90),
            ),
        )
        phase1_live_rescue_timeout_sec = max(
            3,
            _safe_int(
                req.get("phase1_live_rescue_timeout_sec"),
                _safe_int(
                    getattr(settings, "INVESTIGATION_PHASE1_LIVE_RESCUE_TIMEOUT_SEC", 12),
                    12,
                ),
            ),
        )
        max_live_rescue_rounds = max(
            1,
            _safe_int(
                req.get("max_live_rescue_rounds"),
                _safe_int(getattr(settings, "INVESTIGATION_MAX_LIVE_RESCUE_ROUNDS", 3), 3),
            ),
        )
        force_live_before_cache = bool(
            req.get(
                "force_live_before_cache",
                getattr(settings, "INVESTIGATION_FORCE_LIVE_BEFORE_CACHE", True),
            )
        )
        low_latency_phase1_profile = (
            phase1_target_valid_evidence <= 50 and target_valid_evidence_min <= 50
        )
        max_concurrent_platforms_fast = max(
            1,
            _safe_int(
                req.get("max_concurrent_platforms_fast"),
                _safe_int(getattr(settings, "INVESTIGATION_MAX_CONCURRENT_PLATFORMS_FAST", 6), 6),
            ),
        )
        max_concurrent_platforms_fill = max(
            1,
            _safe_int(
                req.get("max_concurrent_platforms_fill"),
                _safe_int(getattr(settings, "INVESTIGATION_MAX_CONCURRENT_PLATFORMS_FILL", 2), 2),
            ),
        )
        enhanced_reasoning_timeout_sec = max(
            3,
            _safe_int(
                req.get("enhanced_reasoning_timeout_sec"),
                _safe_int(
                    getattr(settings, "INVESTIGATION_ENHANCED_REASONING_TIMEOUT_SEC", 25),
                    25,
                ),
            ),
        )
        if phase1_deadline_sec <= 90 and phase1_target_valid_evidence <= 50:
            enhanced_reasoning_timeout_sec = min(enhanced_reasoning_timeout_sec, 12)
        max_runtime_sec = max(
            30,
            _safe_int(req.get("max_runtime_sec"), _safe_int(getattr(settings, "INVESTIGATION_MAX_RUNTIME_SEC", 180), 180)),
        )
        run_deadline_ts = datetime.utcnow().timestamp() + max_runtime_sec
        early_stop_on_official = req.get("early_stop_on_official")
        if early_stop_on_official is None:
            early_stop_on_official = bool(
                getattr(settings, "INVESTIGATION_EARLY_STOP_OFFICIAL_ENABLED", True)
            )
        early_stop_min_official_items = max(
            1,
            _safe_int(
                req.get("early_stop_min_official_items"),
                _safe_int(
                    getattr(settings, "INVESTIGATION_EARLY_STOP_MIN_OFFICIAL_ITEMS", 2), 2
                ),
            ),
        )
        early_stop_min_official_platforms = max(
            1,
            _safe_int(
                req.get("early_stop_min_official_platforms"),
                _safe_int(
                    getattr(
                        settings, "INVESTIGATION_EARLY_STOP_MIN_OFFICIAL_PLATFORMS", 1
                    ),
                    1,
                ),
            ),
        )
        early_stop_relevance_floor = max(
            0.0,
            _safe_float(
                req.get("early_stop_relevance_floor"),
                _safe_float(
                    getattr(
                        settings, "INVESTIGATION_EARLY_STOP_RELEVANCE_FLOOR", 0.25
                    ),
                    0.25,
                ),
            ),
        )
        def _remaining_runtime_sec(reserve_sec: int = 0) -> int:
            return max(0, int(run_deadline_ts - datetime.utcnow().timestamp()) - max(0, reserve_sec))

        def _build_multi_agent_fallback(
            *,
            reason_code: str,
            attempted_platforms: List[str],
            message: str,
            coverage_ratio: float,
            total_items: int,
            status: str = "insufficient_evidence",
        ) -> Dict[str, Any]:
            return {
                "status": status,
                "overall_credibility": 0.35,
                "credibility_level": "UNCERTAIN",
                "consensus_points": [],
                "conflicts": [],
                "recommendation": message,
                "platform_results": {},
                "risk_flags": ["INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW"],
                "score_breakdown": {},
                "no_data_explainer": {
                    "reason_code": reason_code,
                    "attempted_platforms": attempted_platforms,
                    "platform_errors": {"multi_agent": [reason_code.lower()]},
                    "retrieval_scope": {
                        "keyword": keyword,
                        "target_valid_evidence_min": target_valid_evidence_min,
                        "live_evidence_target": live_evidence_target,
                    },
                    "coverage_ratio": round(coverage_ratio, 4),
                    "next_queries": [keyword, f"{keyword} 官方 声明"],
                },
                "evidence_summary": {
                    "total_platforms": len(attempted_platforms),
                    "platforms_with_data": len(
                        [p for p in attempted_platforms if len(search.get(p) or []) > 0]
                    ),
                    "total_items": int(total_items),
                    "specific_items": len(
                        [
                            row
                            for row in evidence_registry
                            if isinstance(row, dict)
                            and str(row.get("evidence_origin") or "external") == "external"
                        ]
                    ),
                },
                "input_source_breakdown": {
                    "live_count": len(
                        [c for c in search_evidence_cards if isinstance(c, dict) and not c.get("is_cached")]
                    ),
                    "cached_count": len(
                        [c for c in search_evidence_cards if isinstance(c, dict) and c.get("is_cached")]
                    ),
                },
                "generated_article": {
                    "title": f"{keyword} 核验简报（{reason_code}）",
                    "lead": "多Agent阶段未在预算内完成，已返回可解释降级结果。",
                    "body_markdown": (
                        f"### 状态\n{reason_code}\n\n"
                        f"### 说明\n{message}\n\n"
                        "### 建议\n- 缩小关键词范围\n- 限制平台范围\n- 提高运行预算后重试"
                    ),
                    "highlights": ["预算受限", "已降级输出", "建议补证"],
                    "insufficient_evidence": [reason_code],
                },
            }
        min_platforms_with_data = max(
            1,
            _safe_int(
                req.get("min_platforms_with_data"),
                _safe_int(getattr(settings, "INVESTIGATION_MIN_PLATFORMS_WITH_DATA", 8), 8),
            ),
        )
        phase1_min_platforms_with_data = min(5, max(1, min_platforms_with_data))
        free_source_only = bool(
            req.get("free_source_only", getattr(settings, "INVESTIGATION_FREE_SOURCE_ONLY", True))
        )

        crawlers = get_crawler_manager()
        mediacrawler_options: Dict[str, Any] = {
            "use_mediacrawler": req.get("use_mediacrawler"),
            "mediacrawler_platforms": req.get("mediacrawler_platforms"),
            "mediacrawler_timeout_sec": req.get("mediacrawler_timeout_sec"),
            "strict_search_only": bool(
                req.get(
                    "strict_search_only",
                    getattr(settings, "INVESTIGATION_STRICT_SEARCH_ONLY", True),
                )
            ),
        }
        default_platforms = [
            "weibo",
            "rss_pool",
            "xinhua",
            "peoples_daily",
            "china_gov",
            "news",
            "xiaohongshu",
            "zhihu",
            "bilibili",
            "douyin",
            "bbc",
            "guardian",
            "reuters",
            "ap_news",
            "sec",
            "samr",
            "csrc",
            "nhc",
            "cdc",
            "who",
            "un_news",
        ]
        requested_platforms = req.get("platforms") or default_platforms
        trusted_platforms = [
            str(x).strip()
            for x in str(
                getattr(
                    settings,
                    "INVESTIGATION_TRUSTED_PLATFORMS",
                    "rss_pool,weibo,zhihu,xinhua,peoples_daily,china_gov,samr,csrc,nhc",
                )
            ).split(",")
            if str(x).strip()
        ]
        only_trusted_platforms = bool(
            req.get(
                "only_trusted_platforms",
                getattr(settings, "INVESTIGATION_ONLY_TRUSTED_PLATFORMS", True),
            )
        )
        if only_trusted_platforms:
            requested_platforms = [p for p in requested_platforms if p in trusted_platforms]
            runtime_healthy = self._load_runtime_healthy_platforms()
            if runtime_healthy:
                requested_platforms = [p for p in requested_platforms if p in runtime_healthy]
            min_trusted_count = max(
                1, int(getattr(settings, "INVESTIGATION_TRUSTED_MIN_PLATFORM_COUNT", 4))
            )
            if len(requested_platforms) < min_trusted_count:
                for p in trusted_platforms:
                    if p not in requested_platforms:
                        requested_platforms.append(p)
                    if len(requested_platforms) >= min_trusted_count:
                        break
        official_floor_candidates = [
            "xinhua",
            "peoples_daily",
            "china_gov",
            "who",
            "un_news",
            "sec",
            "samr",
            "csrc",
            "nhc",
            "cdc",
        ]
        merged_requested: List[str] = []
        for p in list(requested_platforms) + ([] if only_trusted_platforms else official_floor_candidates):
            name = str(p or "").strip()
            if name and name not in merged_requested:
                merged_requested.append(name)
        requested_platforms = merged_requested
        background_platforms_selected: List[str] = []
        if bool(getattr(settings, "INVESTIGATION_LANGUAGE_ROUTING_ENABLED", True)) and self._is_zh_query(keyword):
            zh_background = self._zh_background_platforms()
            primary_requested = [p for p in requested_platforms if str(p).strip().lower() not in zh_background]
            background_platforms_selected = [
                p for p in requested_platforms if str(p).strip().lower() in zh_background
            ]
            if primary_requested:
                requested_platforms = primary_requested
            if background_platforms_selected:
                logger.info(
                    f"language routing (zh query): move {len(background_platforms_selected)} platforms to background pool"
                )
        source_plan: Dict[str, Any] = {
            "event_type": "generic_claim",
            "domain": "general_news",
            "domain_keywords": [],
            "plan_version": "manual_default",
            "selection_confidence": 0.35,
            "must_have_platforms": [],
            "candidate_platforms": [],
            "excluded_platforms": [],
            "selected_platforms": requested_platforms,
            "background_platforms": background_platforms_selected,
            "official_floor_platforms": [],
            "official_selected_platforms": [],
            "official_selected_count": 0,
            "selection_reasons": ["source_strategy=manual_or_default"],
            "risk_notes": [],
        }
        available_platforms = [
            p for p in requested_platforms if p in getattr(crawlers, "crawlers", {})
        ]
        if source_strategy == "auto":
            source_plan = plan_sources(
                claim=claim,
                keyword=keyword,
                available_platforms=available_platforms,
                platform_health_snapshot=(
                    crawlers.get_platform_health_snapshot()
                    if hasattr(crawlers, "get_platform_health_snapshot")
                    else {}
                ),
                platform_health_matrix=(
                    crawlers.get_platform_source_matrix()
                    if hasattr(crawlers, "get_platform_source_matrix")
                    else {}
                ),
            )
            selected = [p for p in (source_plan.get("selected_platforms") or []) if p in available_platforms]
            if selected:
                requested_platforms = selected
                available_platforms = selected
            if bool(getattr(settings, "INVESTIGATION_LANGUAGE_ROUTING_ENABLED", True)) and self._is_zh_query(keyword):
                zh_background = self._zh_background_platforms()
                primary_selected = [
                    p for p in requested_platforms if str(p).strip().lower() not in zh_background
                ]
                background_selected = [
                    p for p in requested_platforms if str(p).strip().lower() in zh_background
                ]
                if primary_selected:
                    requested_platforms = primary_selected
                    available_platforms = [p for p in available_platforms if p in primary_selected]
                    source_plan["selected_platforms"] = list(primary_selected)
                source_plan["background_platforms"] = list(background_selected)
            await self.manager.append_event(
                run_id,
                "source_plan_ready",
                {
                    "run_id": run_id,
                    "event_type": source_plan.get("event_type"),
                    "domain": source_plan.get("domain"),
                    "domain_keywords": source_plan.get("domain_keywords", []),
                    "selection_confidence": float(source_plan.get("selection_confidence") or 0.0),
                    "plan_version": source_plan.get("plan_version") or "auto_v2_precision",
                    "must_have_platforms": source_plan.get("must_have_platforms", []),
                    "candidate_platforms": source_plan.get("candidate_platforms", []),
                    "excluded_platforms": source_plan.get("excluded_platforms", []),
                    "selected_platforms": source_plan.get("selected_platforms", []),
                    "background_platforms": source_plan.get("background_platforms", []),
                    "official_floor_platforms": source_plan.get("official_floor_platforms", []),
                    "official_selected_platforms": source_plan.get("official_selected_platforms", []),
                    "official_selected_count": int(source_plan.get("official_selected_count") or 0),
                    "risk_notes": source_plan.get("risk_notes", []),
                },
            )
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "source_planning",
                    "status": "success",
                    "selected_count": len(source_plan.get("selected_platforms") or []),
                    "elapsed_ms": 0,
                },
            )
        mediacrawler_enabled_cfg = bool(getattr(settings, "MEDIACRAWLER_ENABLED", False))
        mediacrawler_ack_cfg = bool(getattr(settings, "MEDIACRAWLER_NONCOMMERCIAL_ACK", False))
        req_use_mediacrawler = mediacrawler_options.get("use_mediacrawler")
        mediacrawler_enabled_run = (
            bool(req_use_mediacrawler)
            if req_use_mediacrawler is not None
            else mediacrawler_enabled_cfg
        )
        if not mediacrawler_ack_cfg:
            mediacrawler_enabled_run = False
        mediacrawler_platforms = (
            list(mediacrawler_options.get("mediacrawler_platforms") or [])
            or list(
                str(
                    getattr(
                        settings,
                        "MEDIACRAWLER_PLATFORMS",
                        "xiaohongshu,douyin,weibo,zhihu",
                    )
                ).split(",")
            )
        )
        await self.manager.append_event(
            run_id,
            "mediacrawler_status",
            {
                "run_id": run_id,
                "enabled": bool(mediacrawler_enabled_run),
                "enabled_by_request": req_use_mediacrawler,
                "ack": mediacrawler_ack_cfg,
                "platforms": [str(x).strip() for x in mediacrawler_platforms if str(x).strip()],
                "timeout_sec": req.get("mediacrawler_timeout_sec")
                or int(getattr(settings, "MEDIACRAWLER_TASK_TIMEOUT_SEC", 120)),
            },
        )
        unavailable_platforms = [p for p in requested_platforms if p not in available_platforms]
        pools = self._split_platform_pools(
            crawlers=crawlers,
            source_profile=source_profile,
            available_platforms=available_platforms,
            must_have_platforms=(
                list(source_plan.get("must_have_platforms") or [])
                if isinstance(source_plan, dict)
                else []
            ),
        )
        stable_pool = list(pools.get("stable_pool") or [])
        experimental_pool = list(pools.get("experimental_pool") or [])
        tiered_search_enabled = bool(
            req.get("tiered_search")
            if req.get("tiered_search") is not None
            else getattr(settings, "INVESTIGATION_TIERED_SEARCH_ENABLED", False)
        )
        tiered_pools: Optional[Dict[str, Any]] = None
        if tiered_search_enabled:
            tiered_pools = self._build_tiered_pools(
                crawlers=crawlers,
                available_platforms=available_platforms,
                must_have_platforms=(
                    list(source_plan.get("must_have_platforms") or [])
                    if isinstance(source_plan, dict)
                    else []
                ),
            )
            tier1_pool = list(tiered_pools.get("tier1_pool") or [])
            tier2_pool = list(tiered_pools.get("tier2_pool") or [])
            tier3_pool = list(tiered_pools.get("tier3_pool") or [])
            if tier1_pool:
                stable_pool = tier1_pool
            experimental_pool = [p for p in (tier2_pool + tier3_pool) if p not in stable_pool]
            ordered = list(dict.fromkeys([*stable_pool, *experimental_pool]))
            available_platforms = ordered or available_platforms
            if isinstance(source_plan, dict):
                source_plan["tiered_pools"] = {
                    "tier1": tier1_pool,
                    "tier2": tier2_pool,
                    "tier3": tier3_pool,
                    "tier_map": tiered_pools.get("tier_map", {}),
                }
            await self.manager.append_event(
                run_id,
                "tiered_source_plan",
                {
                    "run_id": run_id,
                    "tier1_pool": tier1_pool,
                    "tier2_pool": tier2_pool,
                    "tier3_pool": tier3_pool,
                },
            )
        platform_health_snapshot: Dict[str, Any] = (
            crawlers.get_platform_health_snapshot()
            if hasattr(crawlers, "get_platform_health_snapshot")
            else {}
        )
        platform_health_matrix: Dict[str, Any] = (
            crawlers.get_platform_source_matrix()
            if hasattr(crawlers, "get_platform_source_matrix")
            else {}
        )
        allowed_domains = self._build_allowed_domains(
            crawlers=crawlers,
            platforms=available_platforms,
            free_source_only=free_source_only,
        )
        fallback_applied: List[Dict[str, Any]] = []
        data_quality_flags: List[str] = []
        early_stop_info: Dict[str, Any] = {}
        early_stop_triggered = False

        if unavailable_platforms:
            await self.manager.append_event(
                run_id,
                "warning",
                {
                    "code": "PLATFORM_UNAVAILABLE",
                    "message": "部分平台不可用，已自动剔除",
                    "unavailable_platforms": unavailable_platforms,
                },
            )
            data_quality_flags.append("PLATFORM_UNAVAILABLE")

        steps: List[Dict[str, Any]] = []
        if source_strategy == "auto":
            steps.append(
                {
                    "id": "source_planning",
                    "status": "success",
                    "started_at": run_started_at,
                    "finished_at": run_started_at,
                }
            )
        evidence_registry: List[Dict[str, Any]] = []
        search_evidence_cards: List[Dict[str, Any]] = []
        live_evidence_cards: List[Dict[str, Any]] = []
        cached_evidence_cards: List[Dict[str, Any]] = []
        result_status = "complete"
        search: Dict[str, List[Dict[str, Any]]] = {}
        search_hit_records: List[Dict[str, Any]] = []
        evidence_doc_records: List[Dict[str, Any]] = []
        raw_collected_count = 0
        invalid_items: List[Dict[str, Any]] = []
        deduplicated_count = 0
        platform_reason_stats: Dict[str, Dict[str, int]] = {}
        quality_summary: Dict[str, Any] = {}
        acquisition_report: Dict[str, Any] = {}
        platform_pool_stats: Dict[str, Any] = {
            "source_profile": source_profile,
            "source_strategy": source_strategy,
            "stable_pool": stable_pool,
            "experimental_pool": experimental_pool,
            "stable_platforms_with_data": 0,
            "experimental_platforms_with_data": 0,
        }
        mediacrawler_platforms_hit: set[str] = set()
        mediacrawler_failures: List[Dict[str, Any]] = []
        enhanced: Dict[str, Any] = {
            "intel": {"claim": claim, "keyword": keyword},
            "reasoning_chain": {
                "steps": [],
                "final_score": 0.45,
                "final_level": "UNCERTAIN",
                "risk_flags": ["INSUFFICIENT_EVIDENCE"],
                "total_confidence": 0.0,
                "processing_time_ms": 0,
            },
        }
        credibility: Dict[str, Any] = {
            "credibility_score": 0.0,
            "cross_platform_analysis": {},
            "anomalies": [],
        }
        multi_agent: Dict[str, Any] = _build_multi_agent_fallback(
            reason_code="NOT_STARTED",
            attempted_platforms=[],
            message="多Agent阶段未执行。",
            coverage_ratio=0.0,
            total_items=0,
        )
        template: Dict[str, Any] = {
            "template_id": report_template_id,
            "version": "fallback",
            "checksum": "fallback",
            "sections": [],
        }
        report_sections: List[Dict[str, Any]] = []
        source_trace: Dict[str, Any] = {
            "first_seen_at": None,
            "earliest_published_at": None,
            "timeline_count": 0,
            "timeline": [],
        }
        claim_analysis: Dict[str, Any] = {
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
            "factcheck": {"status": "NOT_RUN"},
        }
        opinion_monitoring: Dict[str, Any] = {
            "status": "NOT_RUN",
            "discovery_mode": "reuse_search_results",
            "synthetic_comment_mode": False,
            "keyword": keyword,
            "comment_target": int(
                _safe_int(
                    req.get("opinion_comment_target"),
                    _safe_int(getattr(settings, "INVESTIGATION_OPINION_COMMENT_TARGET", 120), 120),
                )
            ),
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
        agent_platforms: List[str] = []
        agent_limit_per_platform = 0
        agent_collection_rounds = 0

        analysis_started = datetime.utcnow()
        try:
            # Network precheck: fail fast when environment is globally unreachable.
            req_enable_network_precheck = req.get("enable_network_precheck")
            if req_enable_network_precheck is None:
                enable_network_precheck = bool(
                    getattr(settings, "INVESTIGATION_NETWORK_PRECHECK_ENABLED", True)
                )
            else:
                enable_network_precheck = bool(req_enable_network_precheck)
            precheck_timeout_sec = max(
                0.5,
                _safe_float(
                    req.get("network_precheck_timeout_sec"),
                    _safe_float(
                        getattr(settings, "INVESTIGATION_NETWORK_PRECHECK_TIMEOUT_SEC", 2.5),
                        2.5,
                    ),
                ),
            )
            precheck_fail_ratio_threshold = max(
                0.3,
                min(
                    1.0,
                    _safe_float(
                        req.get("network_precheck_fail_ratio_threshold"),
                        _safe_float(
                            getattr(
                                settings,
                                "INVESTIGATION_NETWORK_PRECHECK_FAIL_RATIO_THRESHOLD",
                                0.7,
                            ),
                            0.7,
                        ),
                    ),
                ),
            )
            precheck_min_hosts = max(
                1,
                _safe_int(
                    getattr(settings, "INVESTIGATION_NETWORK_PRECHECK_MIN_HOSTS", 3), 3
                ),
            )
            precheck_hosts = self._resolve_network_precheck_hosts(req)
            if enable_network_precheck:
                precheck_started_at = _utc_now()
                steps.append(
                    {"id": "network_precheck", "status": "running", "started_at": precheck_started_at}
                )
                await self.manager.append_event(
                    run_id,
                    "network_precheck_started",
                    {
                        "hosts": precheck_hosts,
                        "timeout_sec": precheck_timeout_sec,
                        "fail_ratio_threshold": precheck_fail_ratio_threshold,
                    },
                )
                precheck_result = await self._network_precheck(
                    hosts=precheck_hosts,
                    timeout_sec=precheck_timeout_sec,
                )
                steps[-1].update({"status": "success", "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "network_precheck_result",
                    {
                        **precheck_result,
                        "elapsed_ms": _elapsed_ms(precheck_started_at),
                    },
                )
                if (
                    precheck_result.get("checked", 0) >= precheck_min_hosts
                    and _safe_float(precheck_result.get("fail_ratio"), 0.0)
                    >= precheck_fail_ratio_threshold
                ):
                    steps[-1]["status"] = "partial"
                    data_quality_flags.extend(
                        ["NETWORK_PRECHECK_FAILED", "INSUFFICIENT_VALID_EVIDENCE"]
                    )
                    result_status = "insufficient_evidence"
                    nde = {
                        "reason_code": "NETWORK_UNREACHABLE",
                        "attempted_platforms": list(available_platforms),
                        "platform_errors": {
                            "network_precheck": [
                                row.get("error") or "unreachable"
                                for row in precheck_result.get("details", [])
                                if not row.get("reachable")
                            ]
                            or ["network_unreachable"]
                        },
                        "retrieval_scope": {
                            "keyword": keyword,
                            "quality_mode": quality_mode,
                            "target_valid_evidence_min": target_valid_evidence_min,
                            "live_evidence_target": live_evidence_target,
                        },
                        "coverage_ratio": 0.0,
                        "next_queries": [
                            keyword,
                            f"{keyword} site:news.cn",
                            f"{keyword} site:reuters.com",
                        ],
                    }
                    result = {
                        "run_id": run_id,
                        "status": result_status,
                        "accepted_at": req.get("accepted_at"),
                        "completed_at": _utc_now(),
                        "request": req,
                        "steps": steps,
                        "enhanced": enhanced,
                        "search": {"keyword": keyword, "data": {}},
                        "credibility": credibility,
                        "agent_outputs": multi_agent,
                        "evidence_registry": [],
                        "score_breakdown": {"evidence_count": 0, "valid_evidence_count": 0},
                        "dual_profile_result": self._build_dual_profile_result(
                            enhanced_score=0.0,
                            cross_score=0.0,
                            agent_score=0.0,
                            score_breakdown={},
                            insufficient=True,
                        ),
                        "report_template": {
                            "template_id": template.get("template_id"),
                            "version": template.get("version"),
                            "checksum": template.get("checksum"),
                        },
                        "report_sections": [],
                        "source_trace": source_trace,
                        "no_data_explainer": nde,
                        "external_sources": [],
                        "platform_health_snapshot": platform_health_snapshot,
                        "platform_health_matrix": platform_health_matrix,
                        "fallback_applied": fallback_applied,
                        "data_quality_flags": sorted(list(set(data_quality_flags))),
                        "acquisition_report": {
                            "source_profile": source_profile,
                            "source_strategy": source_strategy,
                            "strict_pipeline": strict_pipeline,
                            "target_valid_evidence_min": int(target_valid_evidence_min),
                            "live_evidence_target": int(live_evidence_target),
                            "phase1_target_valid_evidence": int(phase1_target_valid_evidence),
                            "max_live_rescue_rounds": int(max_live_rescue_rounds),
                            "force_live_before_cache": bool(force_live_before_cache),
                            "valid_evidence_count": 0,
                            "external_evidence_count": 0,
                            "derived_evidence_count": 0,
                            "synthetic_context_count": 0,
                            "external_primary_count": 0,
                            "external_background_count": 0,
                            "external_noise_count": 0,
                            "raw_collected_count": 0,
                            "deduplicated_count": 0,
                            "invalid_count": 0,
                            "live_evidence_count": 0,
                            "cached_evidence_count": 0,
                            "platforms_with_data": 0,
                            "platform_pool_stats": platform_pool_stats,
                            "source_plan": source_plan,
                            "platform_reason_stats": {
                                "by_platform": {"network_precheck": {"NETWORK_UNREACHABLE": 1}},
                                "by_reason": {"NETWORK_UNREACHABLE": 1},
                                "total": {"NETWORK_UNREACHABLE": 1},
                            },
                            "platform_health_matrix": platform_health_matrix,
                            "coverage_by_tier": {},
                            "opinion_comment_count": 0,
                            "opinion_unique_accounts_count": 0,
                            "opinion_suspicious_ratio": 0.0,
                            "opinion_risk_level": "unknown",
                            "opinion_target_reached": False,
                        },
                        "quality_summary": {
                            "keyword_match_ratio": 0.0,
                            "reachable_ratio": 0.0,
                            "specific_url_ratio": 0.0,
                            "domain_diversity": 0,
                            "invalid_evidence_ratio": 1.0,
                            "freshness_score": 0.0,
                        },
                        "agent_input_trace": {
                            "platforms": [],
                            "limit_per_platform": 0,
                            "collection_rounds": 0,
                            "sampled_evidence_ids": [],
                        },
                        "source_plan": source_plan,
                        "claim_analysis": claim_analysis,
                        "opinion_monitoring": opinion_monitoring,
                        "network_precheck": precheck_result,
                    }
                    result["step_summaries"] = self._build_step_summaries(result)
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "NETWORK_PRECHECK_FAILED",
                            "message": "网络预检失败，已快速返回可解释降级结果。",
                            "precheck": precheck_result,
                        },
                    )
                    await self.manager.append_event(
                        run_id,
                        "run_completed",
                        {
                            "run_id": run_id,
                            "status": result_status,
                            "evidence_count": 0,
                            "valid_evidence_count": 0,
                            "target_valid_evidence_min": target_valid_evidence_min,
                            "claim_count": 0,
                            "review_queue_count": 0,
                            "claim_run_verdict": "UNCERTAIN",
                        },
                    )
                    await self.manager.set_result(run_id, result=result, status=result_status)
                    return

            # Step 1: Enhanced reasoning
            step_started_at = _utc_now()
            steps.append({"id": "enhanced_reasoning", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "enhanced_reasoning", "status": "running", "elapsed_ms": 0},
            )
            try:
                intel, chain = await asyncio.wait_for(
                    analyze_intel_enhanced(
                        content=claim,
                        source_platform="investigation",
                        metadata={"keyword": keyword, "audience_profile": audience_profile},
                    ),
                    timeout=max(3, enhanced_reasoning_timeout_sec),
                )
                enhanced = {
                    "intel": intel,
                    "reasoning_chain": {
                        "steps": [s.model_dump() for s in chain.steps],
                        "final_score": chain.final_score,
                        "final_level": chain.final_level,
                        "risk_flags": chain.risk_flags,
                        "total_confidence": chain.total_confidence,
                        "processing_time_ms": chain.processing_time_ms,
                    },
                }
                for idx, step in enumerate(chain.steps):
                    evidence = step.evidence or []
                    for ev in evidence:
                        derived_at = _utc_now()
                        card = {
                            "id": f"ev_reasoning_{idx}_{len(evidence_registry)+1}",
                            "claim_ref": keyword,
                            "source_tier": 2,
                            "source_name": "reasoning_chain",
                            "evidence_origin": "derived_reasoning",
                            "url": "",
                            "snippet": str(ev),
                            "stance": "context",
                            "confidence": _safe_float(step.confidence, 0.0),
                            "collected_at": derived_at,
                            "published_at": None,
                            "first_seen_at": derived_at,
                            "retrieval_query": keyword,
                            "validation_status": "derived",
                            "retrieval_mode": "reasoning",
                            "is_cached": False,
                            "freshness_hours": 0.0,
                            "cache_run_id": None,
                        }
                        evidence_registry.append(card)
                        await self.manager.append_event(
                            run_id,
                            "evidence_found",
                            {"step_id": "enhanced_reasoning", "evidence_card": card},
                        )
                steps[-1].update({"status": "success", "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "enhanced_reasoning",
                        "status": "success",
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )
            except asyncio.TimeoutError:
                steps[-1].update({"status": "partial", "finished_at": _utc_now()})
                data_quality_flags.append("ENHANCED_REASONING_TIMEOUT")
                enhanced = {
                    "intel": {"claim": claim, "keyword": keyword},
                    "reasoning_chain": {
                        "steps": [],
                        "final_score": 0.45,
                        "final_level": "UNCERTAIN",
                        "risk_flags": ["ENHANCED_REASONING_TIMEOUT"],
                        "total_confidence": 0.0,
                        "processing_time_ms": 0,
                    },
                }
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "ENHANCED_REASONING_TIMEOUT",
                        "message": "增强推理超时，已降级并继续执行后续检索与多Agent流程。",
                        "timeout_sec": enhanced_reasoning_timeout_sec,
                    },
                )
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "enhanced_reasoning",
                        "status": "partial",
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )
            except Exception as exc:
                steps[-1].update({"status": "partial", "finished_at": _utc_now()})
                data_quality_flags.append("ENHANCED_REASONING_FAILED")
                enhanced = {
                    "intel": {"claim": claim, "keyword": keyword},
                    "reasoning_chain": {
                        "steps": [],
                        "final_score": 0.45,
                        "final_level": "UNCERTAIN",
                        "risk_flags": ["ENHANCED_REASONING_FAILED"],
                        "total_confidence": 0.0,
                        "processing_time_ms": 0,
                    },
                }
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "ENHANCED_REASONING_FAILED",
                        "message": "增强推理失败，已降级并继续执行后续检索与多Agent流程。",
                        "error": str(exc),
                    },
                )
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "enhanced_reasoning",
                        "status": "partial",
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )

            # Step 2: two-phase search + strict evidence validation
            step_started_at = _utc_now()
            steps.append({"id": "multiplatform_search", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "multiplatform_search", "status": "running", "elapsed_ms": 0},
            )
            fast_phase_seconds = min(max_runtime_sec, phase1_deadline_sec)
            if low_latency_phase1_profile:
                fast_phase_seconds = min(fast_phase_seconds, 65)
            max_rounds = max(
                1,
                _safe_int(getattr(settings, "INVESTIGATION_MAX_SEARCH_ROUNDS", 6), 6),
            )
            search_deadline_ts = run_deadline_ts
            fast_deadline_ts = min(
                search_deadline_ts, datetime.utcnow().timestamp() + fast_phase_seconds
            )
            base_limit = max(5, _safe_int(req.get("limit_per_platform"), 20))
            realtime_analysis_enabled = bool(
                req.get(
                    "realtime_platform_analysis",
                    getattr(settings, "INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_ENABLED", False),
                )
            )
            realtime_analysis_timeout_sec = max(
                3.0,
                _safe_float(
                    req.get("realtime_platform_analysis_timeout_sec"),
                    _safe_float(
                        getattr(
                            settings,
                            "INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_TIMEOUT_SEC",
                            12,
                        ),
                        12,
                    ),
                ),
            )
            realtime_analysis_concurrency = max(
                1,
                _safe_int(
                    req.get("realtime_platform_analysis_concurrency"),
                    _safe_int(
                        getattr(
                            settings,
                            "INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_CONCURRENCY",
                            4,
                        ),
                        4,
                    ),
                ),
            )
            realtime_analysis_top_k = max(
                1,
                _safe_int(
                    req.get("realtime_platform_analysis_topk"),
                    _safe_int(
                        getattr(
                            settings,
                            "INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_TOPK",
                            6,
                        ),
                        6,
                    ),
                ),
            )
            realtime_processor = get_multi_agent_processor() if realtime_analysis_enabled else None
            realtime_analysis_seen: set[str] = set()
            realtime_analysis_tasks: set[asyncio.Task] = set()
            realtime_analysis_sem = asyncio.Semaphore(realtime_analysis_concurrency)
            realtime_analysis_state = {
                "enabled": realtime_analysis_enabled,
                "processor": realtime_processor,
                "seen": realtime_analysis_seen,
                "tasks": realtime_analysis_tasks,
                "sem": realtime_analysis_sem,
                "timeout_sec": realtime_analysis_timeout_sec,
                "top_k": realtime_analysis_top_k,
            }

            staged_candidate_top_n = max(
                20,
                _safe_int(
                    getattr(settings, "INVESTIGATION_STAGED_STRICT_CANDIDATE_TOP_N", 200),
                    200,
                ),
            )
            staged_final_top_m = max(
                10,
                _safe_int(
                    getattr(settings, "INVESTIGATION_STAGED_STRICT_FINAL_TOP_M", 50), 50
                ),
            )
            phase1_operational_target_valid = max(
                10, min(target_valid_evidence_min, phase1_target_valid_evidence)
            )
            operational_target_valid = max(10, int(target_valid_evidence_min))
            staged_low_relevance_floor = max(
                max(3, int(live_evidence_target)),
                int(phase1_operational_target_valid),
            )
            staged_min_platform_coverage = max(
                2,
                min(int(min_platforms_with_data), max(2, len(available_platforms))),
            )

            # phase-1: stable pool first, then health sort
            sorted_platforms = list(stable_pool or available_platforms)
            sorted_platforms.sort(
                key=lambda p: float((platform_health_snapshot.get(p) or {}).get("health_score", 0.6)),
                reverse=True,
            )
            if source_profile == "stable_mixed_v1":
                # 稳定池优先模式：首轮直接覆盖全部稳定池，避免补采阶段预算不足导致覆盖断层。
                fast_platform_count = len(sorted_platforms)
            else:
                fast_platform_count = min(
                    len(sorted_platforms),
                    max(3, min(min_platforms_with_data, max_concurrent_platforms_fast)),
                )
            fast_platforms = sorted_platforms[:fast_platform_count] or sorted_platforms
            await self.manager.append_event(
                run_id,
                "source_pool_selected",
                {
                    "step_id": "multiplatform_search",
                    "phase": "fast",
                    "source_profile": source_profile,
                    "stable_pool": stable_pool,
                    "experimental_pool": experimental_pool,
                    "selected_platforms": fast_platforms,
                    "max_concurrency": max_concurrent_platforms_fast,
                },
            )

            phase1_remaining = _remaining_runtime_sec(reserve_sec=8)
            phase1_window_remaining = max(
                0, int(fast_deadline_ts - datetime.utcnow().timestamp())
            )
            if phase1_window_remaining > 0:
                phase1_remaining = min(phase1_remaining, phase1_window_remaining)
            if phase1_remaining <= 0:
                phase1 = {"search_data": {}, "reason_stats": {}}
                data_quality_flags.append("SEARCH_BUDGET_EXHAUSTED")
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "SEARCH_BUDGET_EXHAUSTED",
                        "message": "检索阶段预算不足，已进入降级结果拼装。",
                    },
                )
            else:
                try:
                    phase1 = await asyncio.wait_for(
                        self._search_round(
                            run_id=run_id,
                            crawlers=crawlers,
                            keyword=keyword,
                            platforms=fast_platforms,
                            limit_per_platform=max(20, base_limit),
                            max_concurrency=max_concurrent_platforms_fast,
                            mediacrawler_options=mediacrawler_options,
                            progress_started_at=step_started_at,
                            progress_target_valid_evidence_min=target_valid_evidence_min,
                            progress_emit_every=1,
                            realtime_analysis_state=realtime_analysis_state,
                        ),
                        timeout=max(1, phase1_remaining),
                    )
                except asyncio.TimeoutError:
                    phase1 = {"search_data": {}, "reason_stats": {}}
                    data_quality_flags.append("SEARCH_TIMEOUT")
                    for p in fast_platforms:
                        platform_reason_stats.setdefault(p, {})["CRAWLER_TIMEOUT"] = (
                            platform_reason_stats.setdefault(p, {}).get("CRAWLER_TIMEOUT", 0) + 1
                        )
                        await self.manager.append_event(
                            run_id,
                            "platform_status",
                            {
                                "platform": p,
                                "status": "timeout",
                                "reason_code": "CRAWLER_TIMEOUT",
                                "items_collected": 0,
                                "elapsed_ms": 0,
                                "impact_on_verdict": "high",
                            },
                        )
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "SEARCH_TIMEOUT",
                            "message": "检索阶段超时，已使用当前可用证据继续。",
                        },
                    )
            search.update(phase1["search_data"])
            for platform in list(phase1.get("mediacrawler_platforms_hit") or []):
                mediacrawler_platforms_hit.add(str(platform))
            mediacrawler_failures.extend(
                [
                    row
                    for row in list(phase1.get("mediacrawler_failures") or [])
                    if isinstance(row, dict)
                ]
            )
            for p, rows in phase1["reason_stats"].items():
                row = platform_reason_stats.setdefault(p, {})
                for reason, count in rows.items():
                    row[reason] = row.get(reason, 0) + int(count)

            platforms_with_data = sum(1 for items in search.values() if (items or []))
            raw_collected_count = sum(len(items or []) for items in search.values())
            coverage_ratio = float(platforms_with_data) / float(max(1, len(fast_platforms)))
            await self._emit_data_progress(
                run_id=run_id,
                valid_evidence_count=0,
                raw_collected_count=raw_collected_count,
                platforms_with_data=platforms_with_data,
                target_valid_evidence_min=target_valid_evidence_min,
                started_at=step_started_at,
                live_evidence_count=0,
                cached_evidence_count=0,
            )

            validated: Dict[str, Any] = {
                "valid_items": [],
                "invalid_items": [],
                "reason_counter": {},
                "platform_valid_counter": {},
                "deduplicated_count": 0,
            }
            # Early-stop: if authoritative sources already provide strong signal, skip further crawling.
            skip_fill_phase = False
            if early_stop_on_official and any((items or []) for items in search.values()):
                phase1_validated = self._build_validated_candidates(
                    keyword=keyword,
                    search_data=search,
                    allowed_domains=allowed_domains,
                    quality_mode="balanced",
                    reachability_map={},
                )
                official_focus = set(source_plan.get("official_selected_platforms") or [])
                if not official_focus:
                    official_focus = set(OFFICIAL_PLATFORMS) - {"news"}
                authoritative_rows = []
                for row in phase1_validated.get("valid_items") or []:
                    if not isinstance(row, dict):
                        continue
                    platform = str(row.get("platform") or "")
                    url = str(row.get("url") or "")
                    relevance_score = float(row.get("relevance_score") or 0.0)
                    if (
                        (platform in official_focus or _tier_for_url(url) == 1)
                        and bool(row.get("keyword_match"))
                        and relevance_score >= early_stop_relevance_floor
                    ):
                        authoritative_rows.append(row)
                authoritative_platforms = {
                    str(row.get("platform") or "") for row in authoritative_rows
                }
                if (
                    len(authoritative_rows) >= early_stop_min_official_items
                    and len(authoritative_platforms) >= early_stop_min_official_platforms
                ):
                    validated = phase1_validated
                    skip_fill_phase = True
                    early_stop_triggered = True
                    early_stop_info = {
                        "reason": "authoritative_sources_sufficient",
                        "official_platforms": sorted(list(authoritative_platforms)),
                        "official_item_count": len(authoritative_rows),
                        "platforms_with_data": platforms_with_data,
                        "min_official_items": early_stop_min_official_items,
                        "min_official_platforms": early_stop_min_official_platforms,
                        "relevance_floor": round(float(early_stop_relevance_floor), 3),
                    }
                    data_quality_flags.append("EARLY_STOP_OFFICIAL")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "EARLY_STOP_OFFICIAL",
                            "message": "权威信源已满足可信度要求，提前停止扩采。",
                            "details": early_stop_info,
                        },
                    )
                    await self._emit_data_progress(
                        run_id=run_id,
                        valid_evidence_count=len(validated.get("valid_items") or []),
                        raw_collected_count=raw_collected_count,
                        platforms_with_data=platforms_with_data,
                        target_valid_evidence_min=target_valid_evidence_min,
                        started_at=step_started_at,
                        live_evidence_count=len(validated.get("valid_items") or []),
                        cached_evidence_count=0,
                    )

            if not skip_fill_phase:
                fallback_threshold = float(
                    getattr(settings, "INVESTIGATION_FALLBACK_COVERAGE_THRESHOLD", 0.45)
                )
                fill_platforms = list(dict.fromkeys([*fast_platforms]))
                explicit_requested_platforms = bool(req.get("platforms"))
                if explicit_requested_platforms:
                    explicit_extra = [
                        p for p in requested_platforms if p not in fill_platforms
                    ]
                    if explicit_extra:
                        fill_platforms = list(
                            dict.fromkeys([*fill_platforms, *explicit_extra])
                        )
                        await self.manager.append_event(
                            run_id,
                            "platform_fallback_applied",
                            {
                                "step_id": "multiplatform_search",
                                "reason": "explicit_requested_platforms",
                                "replaced_platforms": [],
                                "added_platforms": explicit_extra,
                            },
                        )
                        await self.manager.append_event(
                            run_id,
                            "source_pool_selected",
                            {
                                "step_id": "multiplatform_search",
                                "phase": "fill",
                                "source_profile": source_profile,
                                "selected_platforms": fill_platforms,
                                "max_concurrency": max_concurrent_platforms_fill,
                            },
                        )
                if coverage_ratio < fallback_threshold:
                    supplement = [
                        p
                        for p in (stable_pool + experimental_pool)
                        if p not in fill_platforms
                    ]
                    if supplement:
                        reason = (
                            f"coverage_ratio={coverage_ratio:.2f} < {fallback_threshold:.2f}"
                        )
                        fallback_applied.append(
                            {
                                "step_id": "multiplatform_search",
                                "reason": reason,
                                "requested_platforms": list(fast_platforms),
                                "added_platforms": supplement,
                            }
                        )
                        await self.manager.append_event(
                            run_id,
                            "platform_fallback_applied",
                            {
                                "step_id": "multiplatform_search",
                                "reason": reason,
                                "replaced_platforms": [],
                                "added_platforms": supplement,
                            },
                        )
                        fill_platforms = list(
                            dict.fromkeys([*fill_platforms, *supplement])
                        )
                        data_quality_flags.append("FALLBACK_APPLIED")
                        await self.manager.append_event(
                            run_id,
                            "source_pool_selected",
                            {
                                "step_id": "multiplatform_search",
                                "phase": "fill",
                                "source_profile": source_profile,
                                "selected_platforms": fill_platforms,
                                "max_concurrency": max_concurrent_platforms_fill,
                            },
                        )

                # full profile can expand to all available platforms when target is high
                expand_to_all = bool(
                    getattr(
                        settings, "INVESTIGATION_EXPAND_TO_ALL_PLATFORMS_ON_GAP", True
                    )
                )
                if (
                    source_profile == "full"
                    and expand_to_all
                    and target_valid_evidence_min >= 200
                ):
                    extra_platforms = [
                        p
                        for p in getattr(crawlers, "crawlers", {}).keys()
                        if p not in fill_platforms
                    ]
                    if extra_platforms:
                        reason = (
                            f"high_target({target_valid_evidence_min}) expand platform pool "
                            f"{len(fill_platforms)}->{len(fill_platforms) + len(extra_platforms)}"
                        )
                        fallback_applied.append(
                            {
                                "step_id": "multiplatform_search",
                                "reason": reason,
                                "requested_platforms": list(requested_platforms),
                                "added_platforms": extra_platforms,
                            }
                        )
                        await self.manager.append_event(
                            run_id,
                            "platform_fallback_applied",
                            {
                                "step_id": "multiplatform_search",
                                "reason": reason,
                                "replaced_platforms": [],
                                "added_platforms": extra_platforms,
                            },
                        )
                        fill_platforms = list(
                            dict.fromkeys([*fill_platforms, *extra_platforms])
                        )
                        data_quality_flags.append("PLATFORM_POOL_EXPANDED")

                # phase-2: fill rounds until target or timeout
                round_idx = 0
                while (
                    datetime.utcnow().timestamp() < search_deadline_ts
                    and round_idx < max_rounds
                ):
                    round_idx += 1
                    # Hard-stop fill phase at phase1 deadline, then rely on cached evidence fallback.
                    if datetime.utcnow().timestamp() > fast_deadline_ts:
                        data_quality_flags.append("SEARCH_PHASE1_DEADLINE_REACHED")
                        await self.manager.append_event(
                            run_id,
                            "warning",
                            {
                                "code": "SEARCH_PHASE1_DEADLINE_REACHED",
                                "message": (
                                    "检索填充已达到 phase1_deadline，停止外部扩采并进入缓存补证。"
                                ),
                            },
                        )
                        break
                    if datetime.utcnow().timestamp() > fast_deadline_ts:
                        gap = max(
                            0,
                            target_valid_evidence_min
                            - len(validated.get("valid_items", [])),
                        )
                        per_platform_limit = min(
                            120,
                            max(base_limit, int(gap / max(1, len(fill_platforms))) + 12),
                        )
                    else:
                        per_platform_limit = max(20, base_limit)

                    # circuit breaker for timeout-heavy platforms
                    current_platforms: List[str] = []
                    for p in fill_platforms:
                        timeout_count = int(
                            platform_reason_stats.get(p, {}).get("CRAWLER_TIMEOUT", 0)
                        )
                        if timeout_count >= 2:
                            await self.manager.append_event(
                                run_id,
                                "platform_status",
                                {
                                    "platform": p,
                                    "status": "circuit_open",
                                    "reason_code": "CRAWLER_TIMEOUT",
                                    "items_collected": 0,
                                    "impact_on_verdict": "high",
                                },
                            )
                            await self.manager.append_event(
                                run_id,
                                "circuit_opened",
                                {
                                    "platform": p,
                                    "reason_code": "CRAWLER_TIMEOUT",
                                    "timeout_count": timeout_count,
                                    "step_id": "multiplatform_search",
                                },
                            )
                            continue
                        current_platforms.append(p)
                    if not current_platforms:
                        data_quality_flags.append("ALL_PLATFORM_CIRCUIT_OPEN")
                        break

                    round_remaining = _remaining_runtime_sec(reserve_sec=6)
                    phase1_window_remaining = max(
                        0, int(fast_deadline_ts - datetime.utcnow().timestamp())
                    )
                    if phase1_window_remaining > 0:
                        round_remaining = min(round_remaining, phase1_window_remaining)
                    if round_remaining <= 0:
                        data_quality_flags.append("SEARCH_BUDGET_EXHAUSTED")
                        await self.manager.append_event(
                            run_id,
                            "warning",
                            {
                                "code": "SEARCH_BUDGET_EXHAUSTED",
                                "message": "检索填充轮预算耗尽，结束检索并进入后续分析。",
                            },
                        )
                        break
                    try:
                        round_result = await asyncio.wait_for(
                            self._search_round(
                                run_id=run_id,
                                crawlers=crawlers,
                                keyword=keyword,
                                platforms=current_platforms,
                                limit_per_platform=per_platform_limit,
                                max_concurrency=max_concurrent_platforms_fill,
                                mediacrawler_options=mediacrawler_options,
                                progress_started_at=step_started_at,
                                progress_target_valid_evidence_min=target_valid_evidence_min,
                                progress_emit_every=1,
                                realtime_analysis_state=realtime_analysis_state,
                            ),
                            timeout=max(1, round_remaining),
                        )
                    except asyncio.TimeoutError:
                        data_quality_flags.append("SEARCH_TIMEOUT")
                        for p in current_platforms:
                            platform_reason_stats.setdefault(p, {})["CRAWLER_TIMEOUT"] = (
                                platform_reason_stats.setdefault(p, {}).get("CRAWLER_TIMEOUT", 0)
                                + 1
                            )
                            await self.manager.append_event(
                                run_id,
                                "platform_status",
                                {
                                    "platform": p,
                                    "status": "timeout",
                                    "reason_code": "CRAWLER_TIMEOUT",
                                    "items_collected": 0,
                                    "elapsed_ms": 0,
                                    "impact_on_verdict": "high",
                                },
                            )
                        await self.manager.append_event(
                            run_id,
                            "warning",
                            {
                                "code": "SEARCH_TIMEOUT",
                                "message": "检索填充轮超时，已停止继续扩采。",
                            },
                        )
                        break
                    for p, rows in round_result["reason_stats"].items():
                        stat_row = platform_reason_stats.setdefault(p, {})
                        for reason, count in rows.items():
                            stat_row[reason] = stat_row.get(reason, 0) + int(count)
                    for platform in list(
                        round_result.get("mediacrawler_platforms_hit") or []
                    ):
                        mediacrawler_platforms_hit.add(str(platform))
                    mediacrawler_failures.extend(
                        [
                            row
                            for row in list(
                                round_result.get("mediacrawler_failures") or []
                            )
                            if isinstance(row, dict)
                        ]
                    )

                    # merge with URL-level dedupe
                    for platform, items in (round_result["search_data"] or {}).items():
                        existing = search.get(platform) or []
                        seen = {
                            self._extract_item_url(x)
                            for x in existing
                            if isinstance(x, dict)
                        }
                        for item in (items or []):
                            if not isinstance(item, dict):
                                continue
                            u = self._extract_item_url(item)
                            if u and u in seen:
                                continue
                            if u:
                                seen.add(u)
                            existing.append(item)
                        search[platform] = existing

                    raw_collected_count = sum(len(items or []) for items in search.values())
                    candidate_rows: List[Dict[str, Any]] = []
                    if strict_pipeline == "staged_strict":
                        gather_validated = self._build_validated_candidates(
                            keyword=keyword,
                            search_data=search,
                            allowed_domains=allowed_domains,
                            quality_mode="balanced",
                            reachability_map={},
                        )
                        candidate_rows = list(gather_validated.get("valid_items") or [])[
                            : max(1, staged_candidate_top_n)
                        ]
                        await self.manager.append_event(
                            run_id,
                            "strict_stage_update",
                            {
                                "step_id": "multiplatform_search",
                                "stage": "gather",
                                "gather_count": len(
                                    gather_validated.get("valid_items") or []
                                ),
                                "candidate_limit": staged_candidate_top_n,
                            },
                        )
                        probe_unique = [
                            _normalize_url(str(row.get("url") or ""))
                            for row in candidate_rows
                            if _normalize_url(str(row.get("url") or ""))
                        ]
                    else:
                        probe_urls: List[str] = []
                        for items in search.values():
                            for item in (items or []):
                                if not isinstance(item, dict):
                                    continue
                                u = self._extract_item_url(item)
                                if u:
                                    probe_urls.append(u)
                        probe_unique = list(dict.fromkeys(probe_urls))

                    # strict mode: staged or full strict
                    probe_cap = min(
                        len(probe_unique),
                        max(target_valid_evidence_min * 2, 400)
                        if quality_mode == "strict"
                        else max(target_valid_evidence_min, 200),
                    )
                    probe_remaining = _remaining_runtime_sec(reserve_sec=5)
                    phase1_window_remaining = max(
                        0, int(fast_deadline_ts - datetime.utcnow().timestamp())
                    )
                    if phase1_window_remaining > 0:
                        probe_remaining = min(probe_remaining, phase1_window_remaining)
                    if probe_remaining <= 0:
                        reachability_map = {}
                        data_quality_flags.append("URL_PROBE_SKIPPED_BUDGET")
                    else:
                        probe_timeout_sec = float(
                            getattr(
                                settings, "INVESTIGATION_URL_PROBE_TIMEOUT_SEC", 4.0
                            )
                        )
                        try:
                            reachability_map = await asyncio.wait_for(
                                self._probe_urls(
                                    urls=probe_unique[:probe_cap],
                                    timeout_sec=min(
                                        probe_timeout_sec,
                                        max(1.0, probe_remaining / 2.0),
                                    ),
                                    concurrency=_safe_int(
                                        getattr(
                                            settings,
                                            "INVESTIGATION_URL_PROBE_CONCURRENCY",
                                            16,
                                        ),
                                        16,
                                    ),
                                ),
                                timeout=max(1, probe_remaining),
                            )
                        except asyncio.TimeoutError:
                            reachability_map = {}
                            data_quality_flags.append("URL_PROBE_TIMEOUT")
                            await self.manager.append_event(
                                run_id,
                                "warning",
                                {
                                    "code": "URL_PROBE_TIMEOUT",
                                    "message": "URL可达性探测超时，已使用结构化规则继续。",
                                },
                            )
                    if strict_pipeline == "staged_strict":
                        await self.manager.append_event(
                            run_id,
                            "strict_stage_update",
                            {
                                "step_id": "multiplatform_search",
                                "stage": "candidate_strict",
                                "candidate_count": len(candidate_rows),
                                "probed_urls": len(reachability_map),
                            },
                        )
                        validated = self._build_staged_validated_candidates(
                            keyword=keyword,
                            search_data=search,
                            allowed_domains=allowed_domains,
                            candidate_top_n=staged_candidate_top_n,
                            final_top_m=max(staged_final_top_m, operational_target_valid),
                            reachability_map=reachability_map,
                            min_low_relevance_accept=staged_low_relevance_floor,
                            min_platform_coverage=staged_min_platform_coverage,
                        )
                        await self.manager.append_event(
                            run_id,
                            "strict_stage_update",
                            {
                                "step_id": "multiplatform_search",
                                "stage": "final_strict",
                                "final_count": len(validated.get("valid_items") or []),
                            },
                        )
                    else:
                        validated = self._build_validated_candidates(
                            keyword=keyword,
                            search_data=search,
                            allowed_domains=allowed_domains,
                            quality_mode=quality_mode,
                            reachability_map=reachability_map,
                        )
                    platforms_with_data = sum(
                        1 for items in search.values() if (items or [])
                    )
                    await self._emit_data_progress(
                        run_id=run_id,
                        valid_evidence_count=len(validated["valid_items"]),
                        raw_collected_count=raw_collected_count,
                        platforms_with_data=platforms_with_data,
                        target_valid_evidence_min=target_valid_evidence_min,
                        started_at=step_started_at,
                        live_evidence_count=len(validated["valid_items"]),
                        cached_evidence_count=0,
                    )

                    # Stop fill rounds once evidence + platform coverage hit the phase-1 target.
                    if (
                        len(validated["valid_items"]) >= phase1_operational_target_valid
                        and platforms_with_data >= phase1_min_platforms_with_data
                    ):
                        break

            # 若填充轮因预算/超时提前中断，至少对现有 search 快照执行一次降级验证，
            # 避免出现 raw_collected_count>0 但 valid_evidence_count=0 的空结果。
            if raw_collected_count == 0:
                raw_collected_count = sum(len(items or []) for items in search.values())
            current_live_valid = len(
                [
                    row
                    for row in (validated.get("valid_items") or [])
                    if isinstance(row, dict) and not bool(row.get("is_cached"))
                ]
            )
            # Live rescue: when live evidence is missing/below target, run one or more short
            # stable-source rescue rounds before cache fill.
            if (not skip_fill_phase) and (
                raw_collected_count == 0 or current_live_valid < live_evidence_target
            ):
                rescue_platforms = [
                    p
                    for p in [
                        "xinhua",
                        "bbc",
                        "guardian",
                        "reuters",
                        "ap_news",
                        "sec",
                        "un_news",
                        "who",
                        "samr",
                        "csrc",
                    ]
                    if p in fill_platforms
                ]
                rescue_round_limit = (
                    max_live_rescue_rounds if force_live_before_cache else 1
                )
                if rescue_platforms and rescue_round_limit > 0:
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "LIVE_EVIDENCE_RESCUE",
                            "message": (
                                f"实时证据不足，触发稳定信源补采（最多{rescue_round_limit}轮）。"
                            ),
                            "current_live_valid": current_live_valid,
                            "live_evidence_target": live_evidence_target,
                        },
                    )
                    rescue_round = 0
                    while (
                        rescue_round < rescue_round_limit
                        and (raw_collected_count == 0 or current_live_valid < live_evidence_target)
                    ):
                        rescue_round += 1
                        rescue_remaining = min(
                            phase1_live_rescue_timeout_sec,
                            max(0, _remaining_runtime_sec(reserve_sec=12)),
                        )
                        if rescue_remaining <= 0:
                            data_quality_flags.append("LIVE_RESCUE_BUDGET_EXHAUSTED")
                            await self.manager.append_event(
                                run_id,
                                "warning",
                                {
                                    "code": "LIVE_RESCUE_BUDGET_EXHAUSTED",
                                    "message": "实时补采预算耗尽，进入降级流程。",
                                    "rescue_round": rescue_round,
                                },
                            )
                            break
                        await self.manager.append_event(
                            run_id,
                            "strict_stage_update",
                            {
                                "step_id": "multiplatform_search",
                                "stage": "live_rescue_round",
                                "rescue_round": rescue_round,
                                "max_rounds": rescue_round_limit,
                                "live_valid_before": current_live_valid,
                                "live_target": live_evidence_target,
                            },
                        )
                        try:
                            rescue_result = await asyncio.wait_for(
                                self._search_round(
                                    run_id=run_id,
                                    crawlers=crawlers,
                                    keyword=keyword,
                                    platforms=rescue_platforms,
                                    limit_per_platform=max(8, min(base_limit, 12)),
                                    max_concurrency=min(2, max_concurrent_platforms_fill),
                                    mediacrawler_options=mediacrawler_options,
                                ),
                                timeout=max(1, rescue_remaining),
                            )
                        except asyncio.TimeoutError:
                            rescue_result = {"search_data": {}, "reason_stats": {}}
                            await self.manager.append_event(
                                run_id,
                                "warning",
                                {
                                    "code": "LIVE_EVIDENCE_RESCUE_TIMEOUT",
                                    "message": "实时补采超时，继续下一轮或降级。",
                                    "rescue_round": rescue_round,
                                },
                            )
                        for p, rows in (rescue_result.get("reason_stats") or {}).items():
                            stat_row = platform_reason_stats.setdefault(p, {})
                            for reason, count in rows.items():
                                stat_row[reason] = stat_row.get(reason, 0) + int(count)
                        for platform in list(
                            rescue_result.get("mediacrawler_platforms_hit") or []
                        ):
                            mediacrawler_platforms_hit.add(str(platform))
                        mediacrawler_failures.extend(
                            [
                                row
                                for row in list(
                                    rescue_result.get("mediacrawler_failures") or []
                                )
                                if isinstance(row, dict)
                            ]
                        )
                        for platform, items in (rescue_result.get("search_data") or {}).items():
                            existing = search.get(platform) or []
                            seen = {
                                self._extract_item_url(x)
                                for x in existing
                                if isinstance(x, dict)
                            }
                            for item in (items or []):
                                if not isinstance(item, dict):
                                    continue
                                u = self._extract_item_url(item)
                                if u and u in seen:
                                    continue
                                if u:
                                    seen.add(u)
                                existing.append(item)
                            search[platform] = existing
                        raw_collected_count = sum(len(items or []) for items in search.values())
                        if raw_collected_count > 0:
                            if strict_pipeline == "staged_strict":
                                validated = self._build_staged_validated_candidates(
                                    keyword=keyword,
                                    search_data=search,
                                    allowed_domains=allowed_domains,
                                    candidate_top_n=staged_candidate_top_n,
                                    final_top_m=max(staged_final_top_m, operational_target_valid),
                                    reachability_map={},
                                    min_low_relevance_accept=staged_low_relevance_floor,
                                    min_platform_coverage=staged_min_platform_coverage,
                                )
                            else:
                                validated = self._build_validated_candidates(
                                    keyword=keyword,
                                    search_data=search,
                                    allowed_domains=allowed_domains,
                                    quality_mode="balanced",
                                    reachability_map={},
                                )
                        current_live_valid = len(
                            [
                                row
                                for row in (validated.get("valid_items") or [])
                                if isinstance(row, dict) and not bool(row.get("is_cached"))
                            ]
                        )
                        await self.manager.append_event(
                            run_id,
                            "strict_stage_update",
                            {
                                "step_id": "multiplatform_search",
                                "stage": "live_rescue_validation",
                                "rescue_round": rescue_round,
                                "final_count": len(validated.get("valid_items") or []),
                                "live_valid": current_live_valid,
                                "live_target": live_evidence_target,
                            },
                        )
                        platforms_with_data = sum(1 for items in search.values() if (items or []))
                        await self._emit_data_progress(
                            run_id=run_id,
                            valid_evidence_count=len(validated.get("valid_items") or []),
                            raw_collected_count=raw_collected_count,
                            platforms_with_data=platforms_with_data,
                            target_valid_evidence_min=target_valid_evidence_min,
                            started_at=step_started_at,
                            live_evidence_count=current_live_valid,
                            cached_evidence_count=0,
                        )
                        if not force_live_before_cache:
                            break
                    if current_live_valid < live_evidence_target:
                        data_quality_flags.append("LIVE_EVIDENCE_BELOW_TARGET")
                        if force_live_before_cache:
                            data_quality_flags.append("LIVE_RESCUE_ROUNDS_EXHAUSTED")
            if (not validated.get("valid_items")) and any((items or []) for items in search.values()):
                data_quality_flags.append("VALIDATION_DEGRADED_NO_PROBE")
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "VALIDATION_DEGRADED_NO_PROBE",
                        "message": "严格验证预算不足，已对当前检索结果执行降级验证以保留可追溯证据。",
                    },
                )
                if strict_pipeline == "staged_strict":
                    validated = self._build_staged_validated_candidates(
                        keyword=keyword,
                        search_data=search,
                        allowed_domains=allowed_domains,
                        candidate_top_n=staged_candidate_top_n,
                        final_top_m=max(staged_final_top_m, min(operational_target_valid, 20)),
                        reachability_map={},
                        min_low_relevance_accept=max(10, min(staged_low_relevance_floor, 20)),
                        min_platform_coverage=staged_min_platform_coverage,
                    )
                    await self.manager.append_event(
                        run_id,
                        "strict_stage_update",
                        {
                            "step_id": "multiplatform_search",
                            "stage": "degraded_validation",
                            "final_count": len(validated.get("valid_items") or []),
                        },
                    )
                else:
                    validated = self._build_validated_candidates(
                        keyword=keyword,
                        search_data=search,
                        allowed_domains=allowed_domains,
                        quality_mode="balanced",
                        reachability_map={},
                    )

            llm_semantic_enabled = bool(
                req.get(
                    "llm_semantic_rerank",
                    getattr(settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_ENABLED", True),
                )
            )
            if llm_semantic_enabled and list(validated.get("valid_items") or []):
                semantic_result = await self._apply_llm_semantic_gate(
                    claim=claim or keyword,
                    keyword=keyword,
                    rows=list(validated.get("valid_items") or []),
                    threshold=_safe_float(
                        getattr(
                            settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_THRESHOLD", 0.45
                        ),
                        0.45,
                    ),
                    max_items=_safe_int(
                        getattr(settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_MAX_ITEMS", 60),
                        60,
                    ),
                    concurrency=_safe_int(
                        getattr(settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_CONCURRENCY", 4),
                        4,
                    ),
                    timeout_sec=_safe_float(
                        getattr(settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_TIMEOUT_SEC", 12),
                        12,
                    ),
                    fallback_relevance=_safe_float(
                        getattr(
                            settings,
                            "INVESTIGATION_LLM_SEMANTIC_RERANK_FALLBACK_RELEVANCE",
                            0.6,
                        ),
                        0.6,
                    ),
                )
                validated["valid_items"] = semantic_result.get("rows") or []
                validated["semantic_stats"] = semantic_result.get("stats") or {}
                if int((semantic_result.get("stats") or {}).get("filtered") or 0) > 0:
                    data_quality_flags.append("LLM_SEMANTIC_FILTERED")
                await self.manager.append_event(
                    run_id,
                    "semantic_rerank",
                    {
                        "step_id": "multiplatform_search",
                        "stats": semantic_result.get("stats") or {},
                    },
                )

            # build cards with dynamic per-platform cap
            cap_per_platform = _safe_int(
                getattr(
                    settings,
                    "INVESTIGATION_EVIDENCE_CARD_MAX_PER_PLATFORM_STRICT"
                    if quality_mode == "strict"
                    else "INVESTIGATION_EVIDENCE_CARD_MAX_PER_PLATFORM_BALANCED",
                    60 if quality_mode == "strict" else 30,
                ),
                60 if quality_mode == "strict" else 30,
            )
            card_count_by_platform: Counter[str] = Counter()
            balanced_valid_rows = self._interleave_rows_by_platform(
                list(validated.get("valid_items") or [])
            )
            for row in balanced_valid_rows:
                platform = str(row.get("platform") or "unknown")
                if card_count_by_platform[platform] >= cap_per_platform:
                    continue
                card = self._to_evidence_card(
                    keyword=keyword,
                    row=row,
                    idx=len(evidence_registry) + 1,
                    source_plan=source_plan,
                )
                card_count_by_platform[platform] += 1
                evidence_registry.append(card)
                search_evidence_cards.append(card)
                live_evidence_cards.append(card)
                await self.manager.append_event(
                    run_id,
                    "evidence_found",
                    {"step_id": "multiplatform_search", "evidence_card": card},
                )
            if any(
                isinstance(card, dict) and card.get("validation_status") == "provisional"
                for card in live_evidence_cards
            ):
                data_quality_flags.append("PROVISIONAL_LIVE_EVIDENCE")

            live_before_cache = len(
                [
                    c
                    for c in search_evidence_cards
                    if isinstance(c, dict) and not bool(c.get("is_cached"))
                ]
            )
            # cache fallback for insufficient evidence
            if enable_cached_evidence and len(search_evidence_cards) < operational_target_valid:
                if force_live_before_cache and live_before_cache < live_evidence_target:
                    data_quality_flags.append("LIVE_TARGET_NOT_REACHED_BEFORE_CACHE")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "LIVE_TARGET_NOT_REACHED_BEFORE_CACHE",
                            "message": "实时证据仍不足，已在稳定池补采后进入缓存补证。",
                            "live_valid": live_before_cache,
                            "live_target": live_evidence_target,
                        },
                    )
                gap = max(0, operational_target_valid - len(search_evidence_cards))
                cache_max_age_hours = max(
                    1,
                    _safe_int(
                        getattr(settings, "INVESTIGATION_EVIDENCE_CACHE_MAX_AGE_HOURS", 72),
                        72,
                    ),
                )
                cached_raw = get_sqlite_db().get_cached_evidence(
                    keyword=keyword,
                    max_age_hours=cache_max_age_hours,
                    limit=max(gap * 3, 50),
                )
                cache_source = "evidence_cache"
                if not cached_raw:
                    cached_raw = get_sqlite_db().get_historical_evidence(
                        keyword=keyword,
                        max_age_hours=max(cache_max_age_hours, 720),
                        limit=max(gap * 3, 50),
                    )
                    if cached_raw:
                        cache_source = "historical_runs"
                elif len(cached_raw) < max(10, gap // 2):
                    broad_cached = get_sqlite_db().get_historical_evidence(
                        keyword=keyword,
                        max_age_hours=max(cache_max_age_hours, 720),
                        limit=max(gap * 5, 150),
                        min_token_overlap=0.0,
                    )
                    if broad_cached:
                        by_key: Dict[str, Dict[str, Any]] = {}
                        for row in list(cached_raw) + list(broad_cached):
                            if not isinstance(row, dict):
                                continue
                            k = str(row.get("url") or row.get("id") or "").strip()
                            if not k:
                                continue
                            by_key[k] = row
                        cached_raw = list(by_key.values())
                        cache_source = "historical_runs"
                if len(cached_raw) < gap:
                    no_url_cached = get_sqlite_db().get_historical_evidence(
                        keyword=keyword,
                        max_age_hours=max(cache_max_age_hours, 720),
                        limit=max(gap * 8, 200),
                        min_token_overlap=0.0,
                        include_no_url=True,
                    )
                    if no_url_cached:
                        by_key: Dict[str, Dict[str, Any]] = {}
                        for idx, row in enumerate(list(cached_raw) + list(no_url_cached)):
                            if not isinstance(row, dict):
                                continue
                            k = str(row.get("url") or row.get("id") or f"no_url_{idx}").strip()
                            if not k:
                                continue
                            by_key[k] = row
                        cached_raw = list(by_key.values())
                        cache_source = "historical_runs_derived"
                merged_cards = self._merge_cached_evidence(
                    keyword=keyword,
                    run_id=run_id,
                    existing_cards=search_evidence_cards,
                    cached_cards=cached_raw,
                    max_add=gap,
                    source_plan=source_plan,
                )
                if len(merged_cards) > len(search_evidence_cards):
                    newly_added = merged_cards[len(search_evidence_cards) :]
                    cached_evidence_cards.extend(newly_added)
                    for card in newly_added:
                        evidence_registry.append(card)
                        await self.manager.append_event(
                            run_id,
                            "evidence_found",
                            {"step_id": "multiplatform_search", "evidence_card": card},
                        )
                    avg_freshness = round(
                        sum(float(c.get("freshness_hours") or 0.0) for c in newly_added)
                        / max(1, len(newly_added)),
                        2,
                    )
                    await self.manager.append_event(
                        run_id,
                        "cache_evidence_loaded",
                        {
                            "step_id": "multiplatform_search",
                            "cached_loaded_count": len(newly_added),
                            "avg_freshness_hours": avg_freshness,
                            "cache_max_age_hours": cache_max_age_hours,
                            "cache_source": cache_source,
                        },
                    )
                    search_evidence_cards = merged_cards

            # 若严格验证 + 缓存补证后仍低于目标，补充“上下文证据”用于展示与回溯覆盖。
            # 这些卡片统一降级为 background/noise，不进入 primary 结论驱动。
            if len(search_evidence_cards) < operational_target_valid:
                context_gap = max(0, operational_target_valid - len(search_evidence_cards))
                seen_urls = {
                    _normalize_url(str(card.get("url") or ""))
                    for card in search_evidence_cards
                    if isinstance(card, dict) and str(card.get("url") or "").strip()
                }
                seen_content_hash = {
                    _stable_hash(str(card.get("snippet") or ""))
                    for card in search_evidence_cards
                    if isinstance(card, dict) and str(card.get("snippet") or "").strip()
                }
                context_added = 0
                for platform, items in (search or {}).items():
                    if context_added >= context_gap:
                        break
                    for item in (items or []):
                        if context_added >= context_gap:
                            break
                        if not isinstance(item, dict):
                            continue
                        url = self._extract_item_url(item)
                        if not url:
                            continue
                        norm_url = _normalize_url(url)
                        if norm_url and norm_url in seen_urls:
                            continue
                        text_blob = self._extract_item_text(item)
                        if not self._entity_gate_pass(keyword=keyword, text_blob=text_blob):
                            continue
                        content_hash = _stable_hash(text_blob)
                        if content_hash in seen_content_hash:
                            continue
                        metadata = (
                            item.get("metadata")
                            if isinstance(item.get("metadata"), dict)
                            else {}
                        )
                        relevance_score = _keyword_relevance_score(
                            keyword=keyword, text_blob=text_blob
                        )
                        row = {
                            "platform": platform,
                            "url": url,
                            "text_blob": text_blob,
                            "item": item,
                            "keyword_match": bool(metadata.get("keyword_match")),
                            "relevance_score": relevance_score,
                            "reachable": False,
                            "provisional": True,
                            "low_relevance_fallback": True,
                        }
                        card = self._to_evidence_card(
                            keyword=keyword,
                            row=row,
                            idx=len(evidence_registry) + 1,
                            source_plan=source_plan,
                        )
                        card["validation_status"] = "context_fallback"
                        card["retrieval_mode"] = str(
                            metadata.get("retrieval_mode") or "context_fallback"
                        )
                        if card.get("evidence_class") == "primary":
                            card["evidence_class"] = "background"
                            card["selection_reason"] = "context_fill_demoted_primary"
                        else:
                            card["selection_reason"] = "context_fill_to_target"
                        evidence_registry.append(card)
                        search_evidence_cards.append(card)
                        live_evidence_cards.append(card)
                        if norm_url:
                            seen_urls.add(norm_url)
                        if content_hash:
                            seen_content_hash.add(content_hash)
                        context_added += 1
                        await self.manager.append_event(
                            run_id,
                            "evidence_found",
                            {"step_id": "multiplatform_search", "evidence_card": card},
                        )
                if context_added > 0:
                    data_quality_flags.append("CONTEXT_FILL_APPLIED")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "CONTEXT_FILL_APPLIED",
                            "message": f"上下文补证已追加 {context_added} 条，保证证据池覆盖。",
                            "context_added": context_added,
                            "target_valid_evidence_min": int(operational_target_valid),
                        },
                    )

            raw_collected_count = sum(len(items or []) for items in search.values())
            invalid_items = list(validated.get("invalid_items", []))
            deduplicated_count = int(validated.get("deduplicated_count", 0) or 0)
            search_hit_records = self._apply_search_hit_promotions(
                hits=self._collect_search_hits(
                    keyword=keyword,
                    search_data=search,
                ),
                invalid_items=invalid_items,
                valid_rows=list(validated.get("valid_items") or []),
            )
            platforms_with_data = sum(1 for items in search.values() if (items or []))
            evidence_source_platforms = {
                str(card.get("source_name") or "").strip()
                for card in search_evidence_cards
                if isinstance(card, dict) and str(card.get("source_name") or "").strip()
            }
            evidence_source_platforms = {
                p for p in evidence_source_platforms if p not in {"reasoning_chain"}
            }
            effective_platforms_with_data = max(
                int(platforms_with_data), int(len(evidence_source_platforms))
            )
            quality_summary = self._build_quality_summary(
                valid_cards=search_evidence_cards,
                raw_collected_count=raw_collected_count,
                invalid_count=len(invalid_items),
            )
            live_count = len(
                [c for c in search_evidence_cards if isinstance(c, dict) and not c.get("is_cached")]
            )
            cached_count = len(
                [c for c in search_evidence_cards if isinstance(c, dict) and c.get("is_cached")]
            )
            await self._emit_data_progress(
                run_id=run_id,
                valid_evidence_count=len(search_evidence_cards),
                raw_collected_count=raw_collected_count,
                platforms_with_data=platforms_with_data,
                target_valid_evidence_min=target_valid_evidence_min,
                started_at=step_started_at,
                live_evidence_count=live_count,
                cached_evidence_count=cached_count,
            )
            try:
                if search_hit_records:
                    get_sqlite_db().save_search_hits_batch(
                        keyword=keyword,
                        run_id=run_id,
                        hits=search_hit_records,
                    )
            except Exception as hit_save_err:
                logger.warning(f"save search hits failed: {hit_save_err}")
            try:
                cache_candidates = live_evidence_cards
                if llm_semantic_enabled:
                    cache_candidates = [
                        c
                        for c in live_evidence_cards
                        if isinstance(c, dict) and c.get("llm_semantic_score") is not None
                    ]
                if cache_candidates:
                    get_sqlite_db().save_evidence_cache_batch(
                        keyword=keyword,
                        run_id=run_id,
                        cards=cache_candidates,
                    )
            except Exception as cache_save_err:
                logger.warning(f"save evidence cache failed: {cache_save_err}")
            coverage_ratio = round(
                effective_platforms_with_data / float(max(1, len(search))), 4
            )
            if len(search_evidence_cards) < target_valid_evidence_min:
                data_quality_flags.append("TARGET_EVIDENCE_NOT_REACHED")
            if quality_summary.get("invalid_evidence_ratio", 0.0) > 0.2:
                data_quality_flags.append("HIGH_INVALID_EVIDENCE_RATIO")
            search_step_status = "success"
            if any(
                flag in data_quality_flags
                for flag in ["SEARCH_TIMEOUT", "SEARCH_BUDGET_EXHAUSTED", "URL_PROBE_TIMEOUT"]
            ) or len(search_evidence_cards) == 0:
                search_step_status = "partial"
            phase1_deadline_reached = (
                "SEARCH_PHASE1_DEADLINE_REACHED" in data_quality_flags
            )
            steps[-1].update({"status": search_step_status, "finished_at": _utc_now()})
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "multiplatform_search",
                    "status": search_step_status,
                    "platform_count": len(search),
                    "platforms_with_data": effective_platforms_with_data,
                    "valid_evidence_count": len(search_evidence_cards),
                    "elapsed_ms": _elapsed_ms(step_started_at),
                    "coverage_ratio": coverage_ratio,
                },
            )

            # Step 3: aggregation + credibility
            step_started_at = _utc_now()
            steps.append({"id": "cross_platform_credibility", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "cross_platform_credibility", "status": "running", "elapsed_ms": 0},
            )
            credibility_step_status = "success"
            remaining_for_credibility = _remaining_runtime_sec(reserve_sec=4)
            if remaining_for_credibility <= 0:
                credibility_step_status = "partial"
                data_quality_flags.append("CREDIBILITY_SKIPPED_BUDGET")
                credibility = {
                    "credibility_score": 0.0,
                    "cross_platform_analysis": {},
                    "anomalies": [],
                    "status": "skipped_budget",
                }
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "CREDIBILITY_SKIPPED_BUDGET",
                        "message": "跨平台可信度分析预算不足，已跳过并继续。",
                    },
                )
            else:
                credibility_timeout_sec = max(
                    5,
                    min(
                        remaining_for_credibility,
                        _safe_int(getattr(settings, "INVESTIGATION_CREDIBILITY_TIMEOUT_SEC", 40), 40),
                    ),
                )
                if phase1_deadline_reached:
                    credibility_timeout_sec = min(credibility_timeout_sec, 12)
                if low_latency_phase1_profile:
                    credibility_timeout_sec = min(credibility_timeout_sec, 10)
                try:
                    credibility = await asyncio.wait_for(
                        get_fusion_service().analyze_cross_platform_credibility(
                            keyword=keyword,
                            platforms=list(search.keys()),
                            limit_per_platform=max(
                                20, min(80, _safe_int(req.get("limit_per_platform"), 20) * 2)
                            ),
                        ),
                        timeout=credibility_timeout_sec,
                    )
                except asyncio.TimeoutError:
                    credibility_step_status = "partial"
                    data_quality_flags.append("CREDIBILITY_TIMEOUT")
                    credibility = {
                        "credibility_score": 0.0,
                        "cross_platform_analysis": {},
                        "anomalies": [],
                        "status": "timeout",
                    }
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "CREDIBILITY_TIMEOUT",
                            "message": f"跨平台可信度分析超时（>{credibility_timeout_sec}s），已降级继续。",
                        },
                    )
            steps[-1].update({"status": credibility_step_status, "finished_at": _utc_now()})
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "cross_platform_credibility",
                    "status": credibility_step_status,
                    "credibility_score": credibility.get("credibility_score", 0),
                    "elapsed_ms": _elapsed_ms(step_started_at),
                },
            )

            # Step 4: multi-agent synthesis (budget controlled)
            step_started_at = _utc_now()
            steps.append({"id": "multi_agent", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "multi_agent", "status": "running", "elapsed_ms": 0},
            )
            configured_multi_agent_timeout_sec = int(
                getattr(settings, "INVESTIGATION_MULTI_AGENT_TIMEOUT_SEC", 180)
            )
            source_counter = Counter(
                str(card.get("source_name") or "unknown")
                for card in search_evidence_cards
                if isinstance(card, dict)
            )
            agent_platform_priority = sorted(
                list(source_counter.keys()),
                key=lambda p: int(source_counter.get(p, 0)),
                reverse=True,
            )
            agent_platforms = agent_platform_priority[:12]
            if not agent_platforms:
                agent_platforms = available_platforms[:8]
            agent_limit_per_platform = 0
            agent_collection_rounds = 1
            multi_agent_step_status = "success"
            remaining_for_multi_agent = _remaining_runtime_sec(reserve_sec=3)
            has_core_coverage = (
                len(search_evidence_cards) >= target_valid_evidence_min
            )
            if remaining_for_multi_agent <= 0 and not has_core_coverage:
                data_quality_flags.append("MULTI_AGENT_SKIPPED_BUDGET")
                multi_agent_step_status = "partial"
                multi_agent = _build_multi_agent_fallback(
                    reason_code="TIME_BUDGET_EXCEEDED",
                    attempted_platforms=agent_platforms,
                    message="多Agent阶段预算不足，已跳过并返回可解释降级结果。",
                    coverage_ratio=(effective_platforms_with_data / max(1, len(search))),
                    total_items=sum(len(search.get(p) or []) for p in agent_platforms),
                )
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "MULTI_AGENT_SKIPPED_BUDGET",
                        "message": "multi_agent 阶段预算不足，已返回可解释降级结果",
                    },
                )
            else:
                if remaining_for_multi_agent <= 0 and has_core_coverage:
                    data_quality_flags.append("MULTI_AGENT_BORROWED_BUDGET")
                    borrowed_timeout_sec = max(
                        8,
                        _safe_int(
                            getattr(settings, "INVESTIGATION_MULTI_AGENT_SOFT_TIMEOUT_SEC", 25),
                            25,
                        ),
                    )
                    multi_agent_timeout_sec = min(
                        configured_multi_agent_timeout_sec, borrowed_timeout_sec
                    )
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "MULTI_AGENT_BORROWED_BUDGET",
                            "message": (
                                "multi_agent 阶段触发软预算保护，将继续运行以保证Agent可用。"
                            ),
                        },
                    )
                else:
                    multi_agent_timeout_sec = max(
                        5, min(configured_multi_agent_timeout_sec, remaining_for_multi_agent)
                    )
                if phase1_deadline_reached:
                    multi_agent_timeout_sec = min(multi_agent_timeout_sec, 20)
                try:
                    multi_agent = await asyncio.wait_for(
                        get_multi_agent_processor().analyze_from_evidence_registry(
                            keyword=keyword,
                            evidence_registry=search_evidence_cards,
                            agent_topology="stable_3_agents",
                        ),
                        timeout=multi_agent_timeout_sec,
                    )
                except asyncio.TimeoutError:
                    data_quality_flags.append("MULTI_AGENT_TIMEOUT")
                    multi_agent_step_status = "partial"
                    fallback_status = (
                        "partial" if has_core_coverage else "insufficient_evidence"
                    )
                    multi_agent = _build_multi_agent_fallback(
                        reason_code="TIMEOUT",
                        attempted_platforms=agent_platforms,
                        message="多Agent步骤超时，已降级为部分结果，请缩小关键词范围后重试。",
                        coverage_ratio=(effective_platforms_with_data / max(1, len(search))),
                        total_items=sum(len(search.get(p) or []) for p in agent_platforms),
                        status=fallback_status,
                    )
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "MULTI_AGENT_TIMEOUT",
                            "message": f"multi_agent 超时（>{multi_agent_timeout_sec}s），已返回可解释降级结果",
                        },
                    )
            for platform, pdata in (multi_agent.get("platform_results") or {}).items():
                vote = {
                    "platform": platform,
                    "score": _safe_float(
                        (pdata.get("small_model_analysis") or {}).get("credibility_score", 0.0)
                    ),
                    "risk_flags": (pdata.get("small_model_analysis") or {}).get("risk_flags", []),
                }
                await self.manager.append_event(run_id, "agent_vote", vote)

            steps[-1].update({"status": multi_agent_step_status, "finished_at": _utc_now()})
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "multi_agent",
                    "status": multi_agent_step_status,
                    "overall_credibility": multi_agent.get("overall_credibility", 0.0),
                    "elapsed_ms": _elapsed_ms(step_started_at),
                },
            )

            # Step 5: external source checks (configurable)
            external_sources: List[Dict[str, Any]] = []

            # Step: Debate Reasoning (辩论式推理分析)
            debate_result: Dict[str, Any] = {}
            cot_display: Dict[str, Any] = {}
            remaining_for_debate = _remaining_runtime_sec(reserve_sec=2)
            if remaining_for_debate > 5:
                step_started_at = _utc_now()
                steps.append({"id": "debate_reasoning", "status": "running", "started_at": step_started_at})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {"step_id": "debate_reasoning", "status": "running", "elapsed_ms": 0},
                )
                debate_step_status = "success"
                try:
                    debate_engine = DebateReasoningEngine()
                    debate_timeout_sec = min(remaining_for_debate, 30)
                    debate_result = await asyncio.wait_for(
                        debate_engine.analyze_with_debate(
                            claim=claim or keyword,
                            evidence_pool=evidence_registry[:50],
                            keyword=keyword,
                        ),
                        timeout=debate_timeout_sec,
                    )
                    cot_display = generate_cot_display(debate_result)
                    logger.info(f"🎭 Debate reasoning completed: {debate_result.get('final_conclusion', {}).get('verdict', 'UNKNOWN')}")
                except asyncio.TimeoutError:
                    debate_step_status = "partial"
                    debate_result = {"error": "debate_timeout", "verdict": "UNCERTAIN"}
                    data_quality_flags.append("DEBATE_REASONING_TIMEOUT")
                except Exception as e:
                    debate_step_status = "partial"
                    debate_result = {"error": str(e), "verdict": "UNCERTAIN"}
                    logger.error(f"Debate reasoning failed: {e}")
                steps[-1].update({"status": debate_step_status, "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "debate_reasoning",
                        "status": debate_step_status,
                        "verdict": debate_result.get("final_conclusion", {}).get("verdict", "UNCERTAIN"),
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )
            else:
                data_quality_flags.append("DEBATE_REASONING_SKIPPED_BUDGET")

            external_feature_enabled = bool(
                getattr(settings, "INVESTIGATION_ENABLE_EXTERNAL_SOURCES", True)
            ) and bool(getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_ENABLED", True))
            external_mode = str(
                getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MODE", "adaptive")
            ).strip().lower()
            if external_mode in {"disabled", "off", "none"}:
                external_feature_enabled = False
            if external_feature_enabled:
                step_started_at = _utc_now()
                steps.append({"id": "external_sources", "status": "running", "started_at": step_started_at})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {"step_id": "external_sources", "status": "running", "elapsed_ms": 0},

                )
                external_step_status = "success"
                external_search_whitelist_only = bool(
                    getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_WHITELIST_ONLY", True)
                )
                external_allowed_domains = self._external_search_allowed_domains(
                    runtime_allowed_domains=allowed_domains
                )
                external_search_limit = max(
                    1,
                    _safe_int(
                        getattr(settings, "INVESTIGATION_EXTERNAL_SEARCH_MAX_RESULTS", 20),
                        20,
                    ),
                )
                external_sources: List[Dict[str, Any]] = []
                should_trigger_external, trigger_reason = self._should_trigger_external_search(
                    valid_evidence_count=len(search_evidence_cards),
                    platforms_with_data=effective_platforms_with_data,
                )
                remaining_for_external = _remaining_runtime_sec(reserve_sec=1)
                if remaining_for_external <= 0:
                    external_step_status = "partial"
                    data_quality_flags.append("EXTERNAL_SOURCES_SKIPPED_BUDGET")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "EXTERNAL_SOURCES_SKIPPED_BUDGET",
                            "message": "外部官方源校验预算不足，已跳过。",
                        },
                    )
                elif not should_trigger_external:
                    external_step_status = "partial"
                    data_quality_flags.append("EXTERNAL_SOURCES_SKIPPED_TRIGGER")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "EXTERNAL_SOURCES_SKIPPED_TRIGGER",
                            "message": (
                                "当前证据量与平台覆盖已达阈值，外部搜索步骤已跳过。"
                            ),
                            "trigger_reason": trigger_reason,
                            "valid_evidence_count": int(len(search_evidence_cards)),
                            "platforms_with_data": int(effective_platforms_with_data),
                        },
                    )
                else:
                    external_timeout_sec = max(
                        2,
                        min(
                            remaining_for_external,
                            _safe_int(getattr(settings, "INVESTIGATION_EXTERNAL_TIMEOUT_SEC", 20), 20),
                        ),
                    )
                    if low_latency_phase1_profile:
                        external_timeout_sec = min(external_timeout_sec, 3)
                    try:
                        external_sources = await asyncio.wait_for(
                            self._check_external_sources(
                                keyword,
                                allowed_domains=external_allowed_domains,
                                limit=external_search_limit,
                                whitelist_only=False,
                            ),
                            timeout=external_timeout_sec,
                        )
                    except asyncio.TimeoutError:
                        external_step_status = "partial"
                        data_quality_flags.append("EXTERNAL_SOURCES_TIMEOUT")
                        await self.manager.append_event(
                            run_id,
                            "warning",
                            {
                                "code": "EXTERNAL_SOURCES_TIMEOUT",
                                "message": f"外部官方源校验超时（>{external_timeout_sec}s），已降级继续。",
                            },
                        )
                promoted_count = 0
                background_count = 0
                external_keyword_threshold = float(
                    getattr(settings, "INVESTIGATION_KEYWORD_MATCH_THRESHOLD", 0.2)
                )
                external_min_relevance = float(
                    getattr(settings, "INVESTIGATION_EXTERNAL_EVIDENCE_MIN_RELEVANCE", 0.3)
                )
                external_keyword_threshold = max(
                    float(external_keyword_threshold),
                    float(external_min_relevance),
                )
                for ext in external_sources:
                    if not isinstance(ext, dict):
                        continue
                    url_value = _normalize_url(str(ext.get("url") or ""))
                    text_blob = "\n".join(
                        [
                            str(ext.get("title") or ""),
                            str(ext.get("summary") or ""),
                            str(ext.get("source_name") or ext.get("source") or ""),
                        ]
                    ).strip()
                    relevance_score = _safe_float(
                        ext.get("relevance_score"),
                        _keyword_relevance_score(keyword=keyword, text_blob=text_blob),
                    )
                    keyword_match = relevance_score >= external_keyword_threshold
                    entity_pass = self._entity_gate_pass(
                        keyword=keyword,
                        text_blob=text_blob,
                    )
                    reachable = bool(ext.get("reachable"))
                    domain_allowed = bool(ext.get("domain_allowed", True))
                    drop_reason = ""
                    if not entity_pass:
                        drop_reason = "ENTITY_GATE_MISS"
                    elif not keyword_match:
                        drop_reason = "LOW_RELEVANCE"
                    elif external_search_whitelist_only and not domain_allowed:
                        drop_reason = "DOMAIN_NOT_ALLOWED"
                    elif not reachable:
                        drop_reason = "UNREACHABLE"
                    used_as_evidence = drop_reason == ""
                    ext["relevance_score"] = float(relevance_score)
                    ext["keyword_match"] = bool(keyword_match)
                    ext["entity_pass"] = bool(entity_pass)
                    ext["domain_allowed"] = bool(domain_allowed)
                    ext["used_as_evidence"] = bool(used_as_evidence)
                    ext["drop_reason"] = drop_reason
                    ext["evidence_class"] = "primary" if used_as_evidence else "background"
                    if not used_as_evidence:
                        background_count += 1
                        continue
                    ext_collected_at = _utc_now()
                    source_name = str(
                        ext.get("source_name")
                        or ext.get("source")
                        or ext.get("source_domain")
                        or "external_search"
                    ).strip()
                    source_domain = str(ext.get("source_domain") or "").strip().lower()
                    source_tier_probe = (
                        f"https://{source_domain}/" if source_domain else url_value
                    )
                    source_tier = _tier_for_url(source_tier_probe) if source_tier_probe else 3
                    base_confidence = 0.85 if source_tier <= 2 else 0.7
                    published_dt = _parse_datetime_like(ext.get("published_at"))
                    published_at = _to_utc_iso(published_dt) if published_dt is not None else None
                    card = {
                        "id": f"ev_external_{len(evidence_registry)+1}",
                        "claim_ref": keyword,
                        "source_tier": source_tier,
                        "source_name": source_name,
                        "source_platform": "external_search",
                        "evidence_origin": "external",
                        "url": url_value,
                        "snippet": str(ext.get("summary") or ext.get("title") or "")[:500],
                        "stance": "support" if reachable else "unknown",
                        "confidence": base_confidence,
                        "collected_at": ext_collected_at,
                        "published_at": published_at,
                        "first_seen_at": published_at or ext_collected_at,
                        "retrieval_query": keyword,
                        "validation_status": "reachable" if reachable else "unreachable",
                        "retrieval_mode": "external_search",
                        "provider": str(ext.get("provider") or "external_search"),
                        "source_domain": source_domain,
                        "keyword_match": bool(keyword_match),
                        "entity_pass": bool(entity_pass),
                        "relevance_score": float(relevance_score),
                        "drop_reason": "",
                        "used_as_evidence": True,
                        "is_cached": False,
                        "freshness_hours": 0.0,
                        "cache_run_id": None,
                    }
                    card.update(
                        self._infer_evidence_class(
                            card=card,
                            source_plan=source_plan,
                            keyword=keyword,
                        )
                    )
                    evidence_registry.append(card)
                    search_evidence_cards.append(card)
                    live_evidence_cards.append(card)
                    promoted_count += 1
                    await self.manager.append_event(
                        run_id, "evidence_found", {"step_id": "external_sources", "evidence_card": card}
                    )
                if promoted_count <= 0 and should_trigger_external:
                    data_quality_flags.append("EXTERNAL_SOURCES_NO_EVIDENCE")
                if promoted_count > 0:
                    evidence_source_platforms = {
                        str(card.get("source_name") or "").strip()
                        for card in search_evidence_cards
                        if isinstance(card, dict)
                        and str(card.get("source_name") or "").strip()
                        and str(card.get("source_name") or "").strip() not in {"reasoning_chain"}
                    }
                    effective_platforms_with_data = max(
                        int(platforms_with_data),
                        int(len(evidence_source_platforms)),
                    )
                    live_count = len(
                        [
                            c
                            for c in search_evidence_cards
                            if isinstance(c, dict) and not c.get("is_cached")
                        ]
                    )
                    cached_count = len(
                        [
                            c
                            for c in search_evidence_cards
                            if isinstance(c, dict) and c.get("is_cached")
                        ]
                    )
                steps[-1].update({"status": external_step_status, "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "external_sources",
                        "status": external_step_status,
                        "source_count": len(external_sources),
                        "promoted_count": int(promoted_count),
                        "background_count": int(background_count),
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )

            # Step 6: claim-level analysis
            step_started_at = _utc_now()
            steps.append({"id": "claim_analysis", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "claim_analysis", "status": "running", "elapsed_ms": 0},
            )
            self._apply_evidence_stratification(
                evidence_cards=evidence_registry,
                source_plan=source_plan,
                keyword=keyword,
            )
            self._attach_traceable_fields(
                evidence_cards=evidence_registry,
                crawlers=crawlers,
            )
            claim_step_status = "success"
            if not bool(getattr(settings, "INVESTIGATION_ENABLE_CLAIM_ANALYSIS", True)):
                claim_step_status = "partial"
                claim_analysis = {
                    "claims": [],
                    "review_queue": [],
                    "claim_reasoning": [],
                    "matrix_summary": claim_analysis.get("matrix_summary") or {},
                    "run_verdict": "UNCERTAIN",
                    "summary": {},
                    "factcheck": {"status": "CLAIM_ANALYSIS_DISABLED"},
                }
            else:
                try:
                    claim_input_evidence = [
                        row
                        for row in evidence_registry
                        if isinstance(row, dict)
                        and str(row.get("evidence_origin") or "external") == "external"
                    ]
                    claim_bundle = await analyze_claims(
                        primary_claim=claim,
                        keyword=keyword,
                        evidence_registry=claim_input_evidence,
                        source_plan=source_plan,
                    )
                    appended_evidence = list(claim_bundle.pop("evidence_append", []) or [])
                    claim_links = dict(claim_bundle.pop("claim_links", {}) or {})
                    claim_analysis = dict(claim_bundle)

                    if appended_evidence:
                        existing_ids = {
                            str(row.get("id") or "")
                            for row in evidence_registry
                            if isinstance(row, dict) and row.get("id")
                        }
                        for row in appended_evidence:
                            if not isinstance(row, dict):
                                continue
                            row.setdefault("evidence_origin", "external")
                            row_id = str(row.get("id") or "")
                            if not row_id or row_id in existing_ids:
                                continue
                            existing_ids.add(row_id)
                            evidence_registry.append(row)
                            search_evidence_cards.append(row)
                            await self.manager.append_event(
                                run_id,
                                "evidence_found",
                                {"step_id": "claim_analysis", "evidence_card": row},
                            )
                    self._apply_evidence_stratification(
                        evidence_cards=evidence_registry,
                        source_plan=source_plan,
                        keyword=keyword,
                    )
                    self._attach_traceable_fields(
                        evidence_cards=evidence_registry,
                        crawlers=crawlers,
                    )

                    for claim_row in claim_analysis.get("claims") or []:
                        claim_id = str(claim_row.get("claim_id") or "")
                        linked_rows = list(
                            claim_row.get("linked_evidence") or claim_links.get(claim_id) or []
                        )
                        await self.manager.append_event(
                            run_id,
                            "claim_extracted",
                            {
                                "run_id": run_id,
                                "claim_id": claim_id,
                                "text": claim_row.get("text", ""),
                                "type": claim_row.get("type", "generic_claim"),
                            },
                        )
                        stance_summary = claim_row.get("stance_summary") or {}
                        await self.manager.append_event(
                            run_id,
                            "claim_evidence_linked",
                            {
                                "run_id": run_id,
                                "claim_id": claim_id,
                                "evidence_count": len(linked_rows),
                                "support_count": int(stance_summary.get("support", 0)),
                                "refute_count": int(stance_summary.get("refute", 0)),
                            },
                        )
                        await self.manager.append_event(
                            run_id,
                            "claim_verdict_ready",
                            {
                                "run_id": run_id,
                                "claim_id": claim_id,
                                "status": "ready",
                                "verdict": claim_row.get("verdict", "UNCERTAIN"),
                                "gate_passed": bool(claim_row.get("gate_passed")),
                                "score": float(claim_row.get("score") or 0.0),
                                "gate_reasons": claim_row.get("gate_reasons") or [],
                            },
                        )
                    for reasoning_row in claim_analysis.get("claim_reasoning") or []:
                        await self.manager.append_event(
                            run_id,
                            "claim_reasoning_ready",
                            {
                                "run_id": run_id,
                                "claim_id": reasoning_row.get("claim_id"),
                                "fallback": bool(reasoning_row.get("fallback")),
                                "citation_count": len(reasoning_row.get("citations") or []),
                            },
                        )
                    await self.manager.append_event(
                        run_id,
                        "review_queue_updated",
                        {
                            "run_id": run_id,
                            "queue_count": len(claim_analysis.get("review_queue") or []),
                            "items": (claim_analysis.get("review_queue") or [])[:20],
                        },
                    )
                except Exception as exc:
                    claim_step_status = "partial"
                    claim_analysis = {
                        "claims": [],
                        "review_queue": [],
                        "claim_reasoning": [],
                        "matrix_summary": claim_analysis.get("matrix_summary") or {},
                        "run_verdict": "UNCERTAIN",
                        "summary": {},
                        "factcheck": {"status": "CLAIM_ANALYSIS_FAILED", "error": str(exc)},
                    }
                    data_quality_flags.append("CLAIM_ANALYSIS_FAILED")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "CLAIM_ANALYSIS_FAILED",
                            "message": "主张级分析失败，已降级返回原有结果。",
                            "error": str(exc),
                        },
                    )
            steps[-1].update({"status": claim_step_status, "finished_at": _utc_now()})
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "claim_analysis",
                    "status": claim_step_status,
                    "claim_count": len(claim_analysis.get("claims") or []),
                    "review_queue_count": len(claim_analysis.get("review_queue") or []),
                    "elapsed_ms": _elapsed_ms(step_started_at),
                },
            )

            iteration_summary: List[Dict[str, Any]] = []
            iteration_enabled = bool(
                req.get(
                    "iteration_enabled",
                    getattr(settings, "INVESTIGATION_ITERATION_ENABLED", False),
                )
            )
            iteration_rounds = max(
                0,
                _safe_int(
                    req.get("iteration_rounds"),
                    _safe_int(getattr(settings, "INVESTIGATION_ITERATION_MAX_ROUNDS", 2), 2),
                ),
            )
            iteration_max_queries = max(
                1,
                _safe_int(
                    req.get("iteration_max_queries"),
                    _safe_int(getattr(settings, "INVESTIGATION_ITERATION_MAX_QUERIES", 3), 3),
                ),
            )
            iteration_limit_per_platform = max(
                5,
                _safe_int(
                    getattr(settings, "INVESTIGATION_ITERATION_LIMIT_PER_PLATFORM", 20),
                    20,
                ),
            )
            iteration_needed = (
                len(search_evidence_cards) < target_valid_evidence_min
                or len(claim_analysis.get("review_queue") or []) > 0
            )
            if (
                iteration_enabled
                and iteration_rounds > 0
                and iteration_needed
                and _remaining_runtime_sec(8) > 0
            ):
                iteration_started_at = _utc_now()
                steps.append(
                    {"id": "reflection_iteration", "status": "running", "started_at": iteration_started_at}
                )
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {"step_id": "reflection_iteration", "status": "running", "elapsed_ms": 0},
                )
                iteration_status = "success"
                iteration_used_queries: set[str] = set()
                iteration_added_total = 0
                existing_urls = {
                    _normalize_url(str(card.get("url") or ""))
                    for card in evidence_registry
                    if isinstance(card, dict) and str(card.get("url") or "").strip()
                }
                for round_idx in range(iteration_rounds):
                    if _remaining_runtime_sec(6) <= 0:
                        iteration_status = "partial"
                        data_quality_flags.append("ITERATION_BUDGET_EXHAUSTED")
                        break
                    plan = self._build_iteration_plan(
                        keyword=keyword,
                        claim=claim,
                        claim_analysis=claim_analysis,
                        data_quality_flags=data_quality_flags,
                        source_plan=source_plan,
                        available_platforms=available_platforms,
                        max_queries=iteration_max_queries,
                    )
                    plan_queries = [
                        q
                        for q in (plan.get("queries") or [])
                        if isinstance(q, str) and q not in iteration_used_queries
                    ]
                    if not plan_queries:
                        break
                    plan_queries = plan_queries[:iteration_max_queries]
                    iteration_used_queries.update(plan_queries)
                    target_platforms = list(plan.get("platforms") or [])
                    if not target_platforms:
                        target_platforms = list(available_platforms or [])
                    await self.manager.append_event(
                        run_id,
                        "iteration_plan",
                        {
                            "round": round_idx + 1,
                            "queries": plan_queries,
                            "platforms": target_platforms,
                            "reason_codes": plan.get("reason_codes") or [],
                        },
                    )
                    round_added = 0
                    round_raw = 0
                    round_platforms_with_data: set[str] = set()
                    for query in plan_queries:
                        if _remaining_runtime_sec(4) <= 0:
                            iteration_status = "partial"
                            data_quality_flags.append("ITERATION_BUDGET_EXHAUSTED")
                            break
                        round_result = await self._search_round(
                            run_id=run_id,
                            crawlers=crawlers,
                            keyword=query,
                            platforms=target_platforms,
                            limit_per_platform=iteration_limit_per_platform,
                            max_concurrency=max_concurrent_platforms_fill,
                            mediacrawler_options=mediacrawler_options,
                        )
                        round_search_data = round_result.get("search_data") or {}
                        for platform, items in (round_search_data or {}).items():
                            existing = search.get(platform) or []
                            seen = {
                                self._extract_item_url(x)
                                for x in existing
                                if isinstance(x, dict)
                            }
                            for item in (items or []):
                                if not isinstance(item, dict):
                                    continue
                                u = self._extract_item_url(item)
                                if u and u in seen:
                                    continue
                                if u:
                                    seen.add(u)
                                existing.append(item)
                            search[platform] = existing
                            if items:
                                round_platforms_with_data.add(platform)
                        round_raw += sum(len(items or []) for items in round_search_data.values())
                        for platform, reason_rows in (round_result.get("reason_stats") or {}).items():
                            platform_reason_stats.setdefault(platform, {})
                            for reason, count in (reason_rows or {}).items():
                                platform_reason_stats[platform][reason] = (
                                    platform_reason_stats[platform].get(reason, 0)
                                    + int(count)
                                )
                        for platform in list(
                            round_result.get("mediacrawler_platforms_hit") or []
                        ):
                            mediacrawler_platforms_hit.add(str(platform))
                        mediacrawler_failures.extend(
                            [
                                row
                                for row in list(
                                    round_result.get("mediacrawler_failures") or []
                                )
                                if isinstance(row, dict)
                            ]
                        )

                        if strict_pipeline == "staged_strict":
                            validated_round = self._build_staged_validated_candidates(
                                keyword=query,
                                search_data=round_search_data,
                                allowed_domains=allowed_domains,
                                candidate_top_n=staged_candidate_top_n,
                                final_top_m=max(staged_final_top_m, 20),
                                reachability_map={},
                                min_low_relevance_accept=staged_low_relevance_floor,
                                min_platform_coverage=staged_min_platform_coverage,
                            )
                        else:
                            validated_round = self._build_validated_candidates(
                                keyword=query,
                                search_data=round_search_data,
                                allowed_domains=allowed_domains,
                                quality_mode="balanced",
                                reachability_map={},
                            )
                        if llm_semantic_enabled and list(validated_round.get("valid_items") or []):
                            semantic_result = await self._apply_llm_semantic_gate(
                                claim=claim or keyword,
                                keyword=query,
                                rows=list(validated_round.get("valid_items") or []),
                                threshold=_safe_float(
                                    getattr(
                                        settings,
                                        "INVESTIGATION_LLM_SEMANTIC_RERANK_THRESHOLD",
                                        0.45,
                                    ),
                                    0.45,
                                ),
                                max_items=_safe_int(
                                    getattr(
                                        settings,
                                        "INVESTIGATION_LLM_SEMANTIC_RERANK_MAX_ITEMS",
                                        60,
                                    ),
                                    60,
                                ),
                                concurrency=_safe_int(
                                    getattr(
                                        settings,
                                        "INVESTIGATION_LLM_SEMANTIC_RERANK_CONCURRENCY",
                                        4,
                                    ),
                                    4,
                                ),
                                timeout_sec=_safe_float(
                                    getattr(
                                        settings,
                                        "INVESTIGATION_LLM_SEMANTIC_RERANK_TIMEOUT_SEC",
                                        12,
                                    ),
                                    12,
                                ),
                                fallback_relevance=_safe_float(
                                    getattr(
                                        settings,
                                        "INVESTIGATION_LLM_SEMANTIC_RERANK_FALLBACK_RELEVANCE",
                                        0.6,
                                    ),
                                    0.6,
                                ),
                            )
                            validated_round["valid_items"] = semantic_result.get("rows") or []
                            validated_round["semantic_stats"] = (
                                semantic_result.get("stats") or {}
                            )
                            if int((semantic_result.get("stats") or {}).get("filtered") or 0) > 0:
                                data_quality_flags.append("LLM_SEMANTIC_FILTERED")
                            await self.manager.append_event(
                                run_id,
                                "semantic_rerank",
                                {
                                    "step_id": "reflection_iteration",
                                    "query": query,
                                    "stats": semantic_result.get("stats") or {},
                                },
                            )
                        for row in validated_round.get("valid_items") or []:
                            if not isinstance(row, dict):
                                continue
                            url = _normalize_url(str(row.get("url") or ""))
                            if url and url in existing_urls:
                                continue
                            card = self._to_evidence_card(
                                keyword=query,
                                row=row,
                                idx=len(evidence_registry) + 1,
                                source_plan=source_plan,
                            )
                            if url:
                                existing_urls.add(url)
                            evidence_registry.append(card)
                            search_evidence_cards.append(card)
                            live_evidence_cards.append(card)
                            round_added += 1
                            await self.manager.append_event(
                                run_id,
                                "evidence_found",
                                {"step_id": "reflection_iteration", "evidence_card": card},
                            )
                    iteration_summary.append(
                        {
                            "round": round_idx + 1,
                            "queries": plan_queries,
                            "platforms": target_platforms,
                            "raw_collected": round_raw,
                            "platforms_with_data": sorted(list(round_platforms_with_data)),
                            "new_evidence": round_added,
                        }
                    )
                    iteration_added_total += round_added
                    if round_added > 0:
                        data_quality_flags.append("ITERATION_APPLIED")
                        try:
                            claim_input_evidence = [
                                row
                                for row in evidence_registry
                                if isinstance(row, dict)
                                and str(row.get("evidence_origin") or "external") == "external"
                            ]
                            claim_bundle = await analyze_claims(
                                primary_claim=claim,
                                keyword=keyword,
                                evidence_registry=claim_input_evidence,
                                source_plan=source_plan,
                            )
                            appended_evidence = list(
                                claim_bundle.pop("evidence_append", []) or []
                            )
                            claim_analysis = dict(claim_bundle)
                            if appended_evidence:
                                existing_ids = {
                                    str(row.get("id") or "")
                                    for row in evidence_registry
                                    if isinstance(row, dict) and row.get("id")
                                }
                                for row in appended_evidence:
                                    if not isinstance(row, dict):
                                        continue
                                    row.setdefault("evidence_origin", "external")
                                    row_id = str(row.get("id") or "")
                                    if not row_id or row_id in existing_ids:
                                        continue
                                    existing_ids.add(row_id)
                                    evidence_registry.append(row)
                                    search_evidence_cards.append(row)
                                    await self.manager.append_event(
                                        run_id,
                                        "evidence_found",
                                        {"step_id": "reflection_iteration", "evidence_card": row},
                                    )
                            self._apply_evidence_stratification(
                                evidence_cards=evidence_registry,
                                source_plan=source_plan,
                                keyword=keyword,
                            )
                            self._attach_traceable_fields(
                                evidence_cards=evidence_registry,
                                crawlers=crawlers,
                            )
                            await self.manager.append_event(
                                run_id,
                                "iteration_claim_analysis_ready",
                                {
                                    "run_id": run_id,
                                    "claim_count": len(claim_analysis.get("claims") or []),
                                    "review_queue_count": len(
                                        claim_analysis.get("review_queue") or []
                                    ),
                                    "run_verdict": claim_analysis.get("run_verdict", "UNCERTAIN"),
                                },
                            )
                        except Exception as exc:
                            iteration_status = "partial"
                            data_quality_flags.append("ITERATION_CLAIM_ANALYSIS_FAILED")
                            await self.manager.append_event(
                                run_id,
                                "warning",
                                {
                                    "code": "ITERATION_CLAIM_ANALYSIS_FAILED",
                                    "message": "迭代后主张分析失败，已保留原有结论。",
                                    "error": str(exc),
                                },
                            )
                    if round_added <= 0:
                        data_quality_flags.append("ITERATION_NO_GAIN")
                        break
                    if (
                        len(search_evidence_cards) >= target_valid_evidence_min
                        and len(claim_analysis.get("review_queue") or []) == 0
                    ):
                        break
                steps[-1].update({"status": iteration_status, "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "reflection_iteration",
                        "status": iteration_status,
                        "elapsed_ms": _elapsed_ms(iteration_started_at),
                        "rounds": len(iteration_summary),
                    },
                )
                if iteration_added_total > 0:
                    self._attach_traceable_fields(
                        evidence_cards=evidence_registry,
                        crawlers=crawlers,
                    )

                if len(search_evidence_cards) >= target_valid_evidence_min:
                    data_quality_flags = [
                        flag for flag in data_quality_flags if flag != "TARGET_EVIDENCE_NOT_REACHED"
                    ]
                raw_collected_count = sum(len(items or []) for items in search.values())
                platforms_with_data = sum(1 for items in search.values() if (items or []))
                evidence_source_platforms = {
                    str(card.get("source_name") or "").strip()
                    for card in search_evidence_cards
                    if isinstance(card, dict) and str(card.get("source_name") or "").strip()
                }
                evidence_source_platforms = {
                    p for p in evidence_source_platforms if p not in {"reasoning_chain"}
                }
                effective_platforms_with_data = max(
                    int(platforms_with_data), int(len(evidence_source_platforms))
                )
                live_count = len(
                    [
                        c
                        for c in search_evidence_cards
                        if isinstance(c, dict) and not c.get("is_cached")
                    ]
                )
                cached_count = len(
                    [
                        c
                        for c in search_evidence_cards
                        if isinstance(c, dict) and c.get("is_cached")
                    ]
                )
                quality_summary = self._build_quality_summary(
                    valid_cards=search_evidence_cards,
                    raw_collected_count=raw_collected_count,
                    invalid_count=len(invalid_items),
                )

            # Step 7: opinion monitoring (comments + bot risk)
            step_started_at = _utc_now()
            steps.append({"id": "opinion_monitoring", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "opinion_monitoring", "status": "running", "elapsed_ms": 0},
            )
            opinion_step_status = "success"
            opinion_budget_left = _remaining_runtime_sec(6)
            opinion_enabled = bool(
                req.get(
                    "enable_opinion_monitoring",
                    getattr(settings, "INVESTIGATION_ENABLE_OPINION_MONITORING", True),
                )
            )
            opinion_gap_force_review = bool(
                getattr(settings, "INVESTIGATION_OPINION_GAP_FORCE_REVIEW", False)
            )
            comment_target = max(
                20,
                _safe_int(
                    req.get("opinion_comment_target"),
                    _safe_int(getattr(settings, "INVESTIGATION_OPINION_COMMENT_TARGET", 120), 120),
                ),
            )
            comment_limit_per_post = max(
                5,
                _safe_int(
                    req.get("opinion_comment_limit_per_post"),
                    _safe_int(
                        getattr(settings, "INVESTIGATION_OPINION_COMMENT_LIMIT_PER_POST", 40),
                        40,
                    ),
                ),
            )
            max_posts_per_platform = max(
                1,
                _safe_int(
                    req.get("opinion_max_posts_per_platform"),
                    _safe_int(
                        getattr(settings, "INVESTIGATION_OPINION_MAX_POSTS_PER_PLATFORM", 2),
                        2,
                    ),
                ),
            )
            max_opinion_platforms = max(
                1,
                _safe_int(
                    req.get("opinion_max_platforms"),
                    _safe_int(getattr(settings, "INVESTIGATION_OPINION_MAX_PLATFORMS", 6), 6),
                ),
            )
            allow_synthetic_comments = bool(
                req.get(
                    "allow_synthetic_comments",
                    getattr(settings, "INVESTIGATION_OPINION_ALLOW_SYNTHETIC_COMMENTS", False),
                )
            )
            if opinion_budget_left <= 0:
                opinion_step_status = "partial"
                opinion_monitoring = {
                    **opinion_monitoring,
                    "status": "OPINION_MONITORING_SKIPPED_BUDGET",
                    "comment_target": int(comment_target),
                    "summary_text": "评论监测因运行时预算耗尽已跳过，不阻断主流程。",
                    "risk_flags": ["OPINION_MONITORING_SKIPPED_BUDGET"],
                }
                data_quality_flags.append("OPINION_MONITORING_SKIPPED_BUDGET")
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "OPINION_MONITORING_SKIPPED_BUDGET",
                        "message": "评论监测因预算耗尽被跳过。",
                    },
                )
            elif not opinion_enabled:
                opinion_step_status = "partial"
                opinion_monitoring = {
                    **opinion_monitoring,
                    "status": "OPINION_MONITORING_DISABLED",
                    "comment_target": int(comment_target),
                    "summary_text": "评论监测已关闭（enable_opinion_monitoring=false）。",
                    "risk_flags": ["OPINION_MONITORING_DISABLED"],
                }
            else:
                try:
                    opinion_monitoring = await analyze_opinion_monitoring(
                        keyword=keyword,
                        search_data=search,
                        source_plan=source_plan,
                        crawler_manager=crawlers,
                        mediacrawler_options=mediacrawler_options,
                        comment_target=comment_target,
                        comment_limit_per_post=comment_limit_per_post,
                        max_posts_per_platform=max_posts_per_platform,
                        max_platforms=max_opinion_platforms,
                        allow_synthetic_comments=allow_synthetic_comments,
                    )
                    opinion_sidecar_failures = [
                        row
                        for row in list(opinion_monitoring.get("sidecar_failures") or [])
                        if isinstance(row, dict)
                    ]
                    if opinion_sidecar_failures:
                        existing_mc_failure_keys = {
                            (
                                str(row.get("platform") or ""),
                                str(row.get("reason") or ""),
                                str(row.get("stage") or "search"),
                                str(row.get("post_id") or ""),
                            )
                            for row in list(mediacrawler_failures or [])
                            if isinstance(row, dict)
                        }
                        for failure in opinion_sidecar_failures:
                            normalized = {
                                "platform": str(failure.get("platform") or "unknown"),
                                "reason": str(
                                    failure.get("reason")
                                    or "MEDIACRAWLER_COMMENT_FAILED"
                                ),
                                "post_id": str(failure.get("post_id") or ""),
                                "stage": "comments",
                            }
                            key = (
                                normalized["platform"],
                                normalized["reason"],
                                normalized["stage"],
                                normalized["post_id"],
                            )
                            if key not in existing_mc_failure_keys:
                                mediacrawler_failures.append(normalized)
                                existing_mc_failure_keys.add(key)
                            await self.manager.append_event(
                                run_id,
                                "mediacrawler_degraded",
                                {
                                    "run_id": run_id,
                                    "platform": normalized["platform"],
                                    "reason": normalized["reason"],
                                    "stage": "comments",
                                    "post_id": normalized["post_id"],
                                    "impact_scope": {
                                        "lost_comments": int(comment_limit_per_post),
                                        "comment_target": int(comment_target),
                                        "real_comments_collected": int(
                                            opinion_monitoring.get("real_comment_count")
                                            or 0
                                        ),
                                    },
                                },
                            )
                    if not bool(opinion_monitoring.get("comment_target_reached")):
                        data_quality_flags.append("OPINION_COMMENT_COVERAGE_GAP")
                        if opinion_gap_force_review:
                            claim_analysis.setdefault("review_queue", [])
                            review_key = (
                                "global",
                                "INSUFFICIENT_COMMENT_COVERAGE",
                                "REVIEW_REQUIRED",
                            )
                            review_seen = {
                                (
                                    str(item.get("claim_id") or ""),
                                    *(str(x) for x in list(item.get("reasons") or [])),
                                )
                                for item in list(claim_analysis.get("review_queue") or [])
                                if isinstance(item, dict)
                            }
                            if review_key not in review_seen:
                                claim_analysis["review_queue"].append(
                                    {
                                        "claim_id": "global",
                                        "priority": "high",
                                        "reasons": [
                                            "INSUFFICIENT_COMMENT_COVERAGE",
                                            "REVIEW_REQUIRED",
                                        ],
                                    }
                                )
                    risk_level = str(opinion_monitoring.get("risk_level") or "low").lower()
                    if risk_level in {"medium", "high"}:
                        data_quality_flags.append("BOT_SWARM_RISK_SIGNAL")
                        claim_analysis.setdefault("review_queue", [])
                        review_key = (
                            "global",
                            "BOT_SWARM_SIGNAL",
                            "REVIEW_REQUIRED",
                        )
                        review_seen = {
                            (
                                str(item.get("claim_id") or ""),
                                *(str(x) for x in list(item.get("reasons") or [])),
                            )
                            for item in list(claim_analysis.get("review_queue") or [])
                            if isinstance(item, dict)
                        }
                        if review_key not in review_seen:
                            claim_analysis["review_queue"].append(
                                {
                                    "claim_id": "global",
                                    "priority": "high" if risk_level == "high" else "medium",
                                    "reasons": ["BOT_SWARM_SIGNAL", "REVIEW_REQUIRED"],
                                }
                            )
                    await self.manager.append_event(
                        run_id,
                        "opinion_monitoring_ready",
                        {
                            "run_id": run_id,
                            "status": opinion_monitoring.get("status"),
                            "total_comments": int(opinion_monitoring.get("total_comments") or 0),
                            "real_comment_count": int(opinion_monitoring.get("real_comment_count") or 0),
                            "synthetic_comment_count": int(opinion_monitoring.get("synthetic_comment_count") or 0),
                            "sidecar_comment_count": int(opinion_monitoring.get("sidecar_comment_count") or 0),
                            "real_comment_ratio": float(opinion_monitoring.get("real_comment_ratio") or 0.0),
                            "real_comment_target_reached": bool(
                                opinion_monitoring.get("real_comment_target_reached")
                            ),
                            "comment_target": int(opinion_monitoring.get("comment_target") or comment_target),
                            "comment_target_reached": bool(opinion_monitoring.get("comment_target_reached")),
                            "unique_accounts_count": int(opinion_monitoring.get("unique_accounts_count") or 0),
                            "suspicious_accounts_count": int(opinion_monitoring.get("suspicious_accounts_count") or 0),
                            "suspicious_ratio": float(opinion_monitoring.get("suspicious_ratio") or 0.0),
                            "risk_level": opinion_monitoring.get("risk_level", "low"),
                            "risk_flags": list(opinion_monitoring.get("risk_flags") or []),
                            "failed_platforms": list(opinion_monitoring.get("failed_platforms") or []),
                            "sidecar_failures": list(
                                opinion_monitoring.get("sidecar_failures") or []
                            ),
                        },
                    )
                except Exception as exc:
                    opinion_step_status = "partial"
                    opinion_monitoring = {
                        **opinion_monitoring,
                        "status": "OPINION_MONITORING_FAILED",
                        "summary_text": "评论监测执行失败，已降级不阻断主流程。",
                        "risk_flags": ["OPINION_MONITORING_FAILED"],
                        "error": str(exc),
                    }
                    data_quality_flags.append("OPINION_MONITORING_FAILED")
                    await self.manager.append_event(
                        run_id,
                        "warning",
                        {
                            "code": "OPINION_MONITORING_FAILED",
                            "message": "评论与水军风险监测失败，已降级继续。",
                            "error": str(exc),
                        },
                    )
            steps[-1].update({"status": opinion_step_status, "finished_at": _utc_now()})
            await self.manager.append_event(
                run_id,
                "step_update",
                {
                    "step_id": "opinion_monitoring",
                    "status": opinion_step_status,
                    "total_comments": int(opinion_monitoring.get("total_comments") or 0),
                    "suspicious_ratio": float(opinion_monitoring.get("suspicious_ratio") or 0.0),
                    "risk_level": opinion_monitoring.get("risk_level", "unknown"),
                    "elapsed_ms": _elapsed_ms(step_started_at),
                },
            )

            # Step 8: template render
            step_started_at = _utc_now()
            steps.append({"id": "report_template_render", "status": "running", "started_at": step_started_at})
            await self.manager.append_event(
                run_id,
                "step_update",
                {"step_id": "report_template_render", "status": "running", "elapsed_ms": 0},
            )
            if _remaining_runtime_sec(2) <= 0:
                source_trace = self._build_source_trace(
                    evidence_cards=evidence_registry,
                    limit=max(
                        10,
                        _safe_int(
                            getattr(settings, "INVESTIGATION_SOURCE_TRACE_LIMIT", 40),
                            40,
                        ),
                    ),
                )
                report_sections = []
                steps[-1].update({"status": "partial", "finished_at": _utc_now()})
                data_quality_flags.append("REPORT_RENDER_SKIPPED_BUDGET")
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "REPORT_RENDER_SKIPPED_BUDGET",
                        "message": "报告模板渲染因预算耗尽被跳过，返回结构化结果。",
                    },
                )
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "report_template_render",
                        "status": "partial",
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )
            else:
                source_trace = self._build_source_trace(
                    evidence_cards=evidence_registry,
                    limit=max(
                        10,
                        _safe_int(
                            getattr(settings, "INVESTIGATION_SOURCE_TRACE_LIMIT", 40),
                            40,
                        ),
                    ),
                )
                template = get_report_template_service().get_cached_or_load(report_template_id)
                report_sections = self._build_report_sections(
                    template=template,
                    keyword=keyword,
                    enhanced=enhanced,
                    credibility=credibility,
                    multi_agent=multi_agent,
                    evidence_registry=evidence_registry,
                    steps=steps,
                    source_trace=source_trace,
                    opinion_monitoring=opinion_monitoring,
                )
                steps[-1].update({"status": "success", "finished_at": _utc_now()})
                await self.manager.append_event(
                    run_id,
                    "step_update",
                    {
                        "step_id": "report_template_render",
                        "status": "success",
                        "elapsed_ms": _elapsed_ms(step_started_at),
                    },
                )

            # dual profile scores
            score_breakdown = dict(multi_agent.get("score_breakdown") or {})
            dual_profile = self._build_dual_profile_result(
                enhanced_score=_safe_float(enhanced["reasoning_chain"].get("final_score"), 0.0),
                cross_score=_safe_float(credibility.get("credibility_score", 0.0), 0.0),
                agent_score=_safe_float(multi_agent.get("overall_credibility", 0.0), 0.0),
                score_breakdown=score_breakdown,
                insufficient=(multi_agent.get("status") == "insufficient_evidence"),
            )

            external_cards_for_status = [
                c
                for c in evidence_registry
                if isinstance(c, dict)
                and str(c.get("evidence_origin") or "external") == "external"
            ]
            live_evidence_count_for_status = len(
                [c for c in external_cards_for_status if not c.get("is_cached")]
            )
            external_valid_count_for_status = len(external_cards_for_status)
            result_status = self._determine_result_status(
                multi_agent_status=str(multi_agent.get("status") or ""),
                valid_evidence_count=external_valid_count_for_status,
                target_valid_evidence_min=target_valid_evidence_min,
                live_evidence_count=live_evidence_count_for_status,
                live_evidence_target=live_evidence_target,
                platforms_with_data=effective_platforms_with_data,
                min_platforms_with_data=min_platforms_with_data,
                steps=steps,
            )
            claim_run_verdict = str(claim_analysis.get("run_verdict") or "UNCERTAIN")
            review_queue_count = len(claim_analysis.get("review_queue") or [])
            external_primary_for_status = len(
                [
                    c
                    for c in external_cards_for_status
                    if isinstance(c, dict)
                    and str(c.get("evidence_class") or "background") == "primary"
                ]
            )
            matrix_summary = claim_analysis.get("matrix_summary") or {}
            tier12_count = int(matrix_summary.get("tier1_count") or 0) + int(
                matrix_summary.get("tier2_count") or 0
            )
            strong_claim_signal = (
                claim_run_verdict in {"SUPPORTED", "REFUTED"}
                and external_primary_for_status >= 8
                and tier12_count >= 2
            )
            must_have_platforms = [str(x) for x in list(source_plan.get("must_have_platforms") or []) if str(x)]
            must_have_with_data = [p for p in must_have_platforms if len(search.get(p) or []) > 0]
            must_have_fail_count = max(0, len(must_have_platforms) - len(must_have_with_data))
            strict_must_have_gating = bool(
                getattr(settings, "INVESTIGATION_STRICT_MUST_HAVE_GATING", False)
            )
            if (
                must_have_platforms
                and must_have_fail_count >= max(1, (len(must_have_platforms) + 1) // 2)
            ):
                data_quality_flags.append("SOURCE_PLAN_MUST_HAVE_GAP")
                if result_status == "complete":
                    result_status = "partial"
                if strict_must_have_gating or not strong_claim_signal:
                    if claim_run_verdict not in {"UNCERTAIN", "REVIEW_REQUIRED"}:
                        claim_analysis["run_verdict"] = "UNCERTAIN"
                        claim_run_verdict = "UNCERTAIN"
                    claim_analysis.setdefault("review_queue", [])
                    claim_analysis["review_queue"].append(
                        {
                            "claim_id": "global",
                            "priority": "high",
                            "reasons": ["MUST_HAVE_SOURCE_FAILURE", "REVIEW_REQUIRED"],
                        }
                    )
                    review_queue_count = len(claim_analysis.get("review_queue") or [])
                else:
                    data_quality_flags.append("MUST_HAVE_GAP_SOFTENED_BY_STRONG_SIGNAL")
                    claim_analysis.setdefault("review_queue", [])
                    claim_analysis["review_queue"].append(
                        {
                            "claim_id": "global",
                            "priority": "medium",
                            "reasons": ["MUST_HAVE_SOURCE_FAILURE"],
                        }
                    )
                    review_queue_count = len(claim_analysis.get("review_queue") or [])
            if strong_claim_signal and result_status == "insufficient_evidence":
                result_status = "partial"
                data_quality_flags.append("CLAIM_SIGNAL_OVERRIDE_INSUFFICIENT")
            if claim_run_verdict == "REVIEW_REQUIRED":
                data_quality_flags.append("CLAIM_GATE_REVIEW_REQUIRED")
                result_status = "insufficient_evidence"
            elif claim_run_verdict == "UNCERTAIN" and result_status == "complete":
                data_quality_flags.append("CLAIM_GATE_UNCERTAIN")
                result_status = "partial"
            if review_queue_count > 0:
                data_quality_flags.append("CLAIM_REVIEW_QUEUE_NON_EMPTY")
            if isinstance(multi_agent, dict) and not multi_agent.get("input_source_breakdown"):
                multi_agent["input_source_breakdown"] = {
                    "live_count": len(
                        [c for c in search_evidence_cards if isinstance(c, dict) and not c.get("is_cached")]
                    ),
                    "cached_count": len(
                        [c for c in search_evidence_cards if isinstance(c, dict) and c.get("is_cached")]
                    ),
                }

            # acquisition report
            by_reason = Counter()
            for _, reason_rows in (platform_reason_stats or {}).items():
                for reason, count in (reason_rows or {}).items():
                    by_reason[str(reason)] += int(count)
            coverage_by_tier = Counter(
                card.get("source_tier", 3)
                for card in search_evidence_cards
                if isinstance(card, dict)
            )
            origin_counter = Counter(
                str(card.get("evidence_origin") or "external")
                for card in evidence_registry
                if isinstance(card, dict)
            )
            external_cards = [
                card
                for card in evidence_registry
                if isinstance(card, dict)
                and str(card.get("evidence_origin") or "external") == "external"
            ]
            partitioned_external = self._partition_external_evidence_cards(evidence_registry)
            evidence_pool_cards = list(partitioned_external.get("evidence_pool") or [])
            context_pool_cards = list(partitioned_external.get("context_pool") or [])
            noise_pool_cards = list(partitioned_external.get("noise_pool") or [])
            evidence_class_counter = Counter(
                str(card.get("evidence_class") or "background")
                for card in external_cards
                if isinstance(card, dict)
            )
            hot_fallback_count = sum(
                1
                for card in external_cards
                if isinstance(card, dict)
                and str(card.get("retrieval_mode") or "")
                in {"hot_fallback", "rss_emergency_fallback", "web_search_fallback"}
            )
            mediacrawler_live_count = sum(
                1
                for card in external_cards
                if isinstance(card, dict)
                and not bool(card.get("is_cached"))
                and str(card.get("provider") or "").lower() == "mediacrawler"
            )
            deduped_mediacrawler_failures: List[Dict[str, Any]] = []
            seen_mc_failure_keys: set[tuple[str, str, str, str]] = set()
            for row in list(mediacrawler_failures or []):
                if not isinstance(row, dict):
                    continue
                key = (
                    str(row.get("platform") or ""),
                    str(row.get("reason") or ""),
                    str(row.get("stage") or "search"),
                    str(row.get("post_id") or ""),
                )
                if key in seen_mc_failure_keys:
                    continue
                seen_mc_failure_keys.add(key)
                normalized = dict(row)
                normalized.setdefault("stage", "search")
                deduped_mediacrawler_failures.append(normalized)
            native_live_count = sum(
                1
                for card in external_cards
                if isinstance(card, dict)
                and not bool(card.get("is_cached"))
                and str(card.get("provider") or "native").lower() != "mediacrawler"
            )
            stable_platforms_with_data = sum(
                1 for p in stable_pool if len(search.get(p) or []) > 0
            )
            experimental_platforms_with_data = sum(
                1 for p in experimental_pool if len(search.get(p) or []) > 0
            )
            platform_pool_stats.update(
                {
                    "stable_platforms_with_data": int(stable_platforms_with_data),
                    "experimental_platforms_with_data": int(experimental_platforms_with_data),
                }
            )
            acquisition_report = {
                "source_profile": source_profile,
                "source_strategy": source_strategy,
                "strict_pipeline": strict_pipeline,
                "requested_target_valid_evidence_min": int(requested_target_valid_evidence),
                "hard_floor_target_valid_evidence_min": int(min_valid_evidence_floor),
                "target_valid_evidence_min": int(target_valid_evidence_min),
                "live_evidence_target": int(live_evidence_target),
                "phase1_target_valid_evidence": int(phase1_target_valid_evidence),
                "phase1_operational_target_valid_evidence": int(phase1_operational_target_valid),
                "max_live_rescue_rounds": int(max_live_rescue_rounds),
                "force_live_before_cache": bool(force_live_before_cache),
                "early_stop_triggered": bool(early_stop_triggered),
                "early_stop": early_stop_info,
                "valid_evidence_count": len(external_cards),
                "external_evidence_count": len(external_cards),
                "derived_evidence_count": int(origin_counter.get("derived_reasoning", 0)),
                "synthetic_context_count": int(origin_counter.get("synthetic_context", 0)),
                "raw_collected_count": int(raw_collected_count),
                "deduplicated_count": int(deduplicated_count),
                "invalid_count": len(invalid_items),
                "live_evidence_count": int(live_count),
                "cached_evidence_count": int(cached_count),
                "platforms_with_data_live_only": int(sum(1 for items in search.values() if (items or []))),
                "platforms_with_data": int(effective_platforms_with_data),
                "platform_pool_stats": platform_pool_stats,
                "source_plan": {
                    "event_type": source_plan.get("event_type"),
                    "domain": source_plan.get("domain"),
                    "domain_keywords": list(source_plan.get("domain_keywords") or []),
                    "selection_confidence": float(source_plan.get("selection_confidence") or 0.0),
                    "plan_version": source_plan.get("plan_version") or "auto_v2_precision",
                    "must_have_platforms": list(source_plan.get("must_have_platforms") or []),
                    "selected_platforms": list(source_plan.get("selected_platforms") or []),
                    "excluded_platforms": list(source_plan.get("excluded_platforms") or []),
                    "risk_notes": list(source_plan.get("risk_notes") or []),
                },
                "platform_reason_stats": {
                    "by_platform": platform_reason_stats,
                    "by_reason": dict(by_reason),
                    "total": dict(by_reason),
                },
                "validation_diagnostics": {
                    "gather_count": int(validated.get("gather_count") or 0),
                    "candidate_count": int(validated.get("candidate_count") or 0),
                    "final_count": int(len(validated.get("valid_items") or [])),
                    "reason_counter": dict(validated.get("reason_counter") or {}),
                    "platform_valid_counter": dict(
                        validated.get("platform_valid_counter") or {}
                    ),
                },
                "first_seen_at": source_trace.get("first_seen_at"),
                "earliest_published_at": source_trace.get("earliest_published_at"),
                "latest_related_content_at": source_trace.get("latest_event_at"),
                "timeline_count": int(source_trace.get("timeline_count") or 0),
                "platform_health_matrix": (
                    crawlers.get_platform_source_matrix()
                    if hasattr(crawlers, "get_platform_source_matrix")
                    else platform_health_matrix
                ),
                "coverage_by_tier": {str(k): int(v) for k, v in coverage_by_tier.items()},
                "primary_count": int(evidence_class_counter.get("primary", 0)),
                "background_count": int(evidence_class_counter.get("background", 0)),
                "noise_count": int(evidence_class_counter.get("noise", 0)),
                "evidence_pool_count": int(len(evidence_pool_cards)),
                "context_pool_count": int(len(context_pool_cards)),
                "noise_pool_count": int(len(noise_pool_cards)),
                "external_primary_count": int(evidence_class_counter.get("primary", 0)),
                "external_background_count": int(evidence_class_counter.get("background", 0)),
                "external_noise_count": int(evidence_class_counter.get("noise", 0)),
                "hot_fallback_count": int(hot_fallback_count),
                "mediacrawler_live_count": int(mediacrawler_live_count),
                "native_live_count": int(native_live_count),
                "mediacrawler_platforms_hit": sorted(list(mediacrawler_platforms_hit)),
                "mediacrawler_failures": deduped_mediacrawler_failures[:30],
                "claim_count": int(len(claim_analysis.get("claims") or [])),
                "gate_fail_count": int(
                    len(
                        [
                            row
                            for row in (claim_analysis.get("claims") or [])
                            if isinstance(row, dict) and not bool(row.get("gate_passed"))
                        ]
                    )
                ),
                "review_queue_count": int(len(claim_analysis.get("review_queue") or [])),
                "must_have_platform_count": int(len(must_have_platforms)),
                "must_have_platform_with_data_count": int(len(must_have_with_data)),
                "must_have_platform_fail_count": int(must_have_fail_count),
                "must_have_hit_ratio": round(
                    float(len(must_have_with_data)) / float(max(1, len(must_have_platforms))),
                    4,
                )
                if must_have_platforms
                else 0.0,
                "factcheck_status": str((claim_analysis.get("factcheck") or {}).get("status") or "UNKNOWN"),
                "factcheck_success_rate": round(
                    float((claim_analysis.get("factcheck") or {}).get("successful_claims") or 0)
                    / max(
                        1,
                        float((claim_analysis.get("factcheck") or {}).get("requested_claims") or 0),
                    ),
                    4,
                ),
                "opinion_comment_count": int(opinion_monitoring.get("total_comments") or 0),
                "opinion_unique_accounts_count": int(opinion_monitoring.get("unique_accounts_count") or 0),
                "opinion_suspicious_accounts_count": int(
                    opinion_monitoring.get("suspicious_accounts_count") or 0
                ),
                "opinion_suspicious_ratio": round(
                    float(opinion_monitoring.get("suspicious_ratio") or 0.0), 4
                ),
                "opinion_risk_level": str(opinion_monitoring.get("risk_level") or "unknown"),
                "opinion_target_reached": bool(opinion_monitoring.get("comment_target_reached")),
                "opinion_sidecar_comment_count": int(opinion_monitoring.get("sidecar_comment_count") or 0),
                "opinion_real_comment_count": int(opinion_monitoring.get("real_comment_count") or 0),
                "opinion_synthetic_comment_count": int(
                    opinion_monitoring.get("synthetic_comment_count") or 0
                ),
                "opinion_real_comment_ratio": round(
                    float(opinion_monitoring.get("real_comment_ratio") or 0.0),
                    4,
                ),
                "opinion_real_comment_target_reached": bool(
                    opinion_monitoring.get("real_comment_target_reached")
                ),
            }
            freshness_score = 1.0
            if cached_count > 0:
                avg_freshness = sum(
                    float(c.get("freshness_hours") or 0.0)
                    for c in search_evidence_cards
                    if isinstance(c, dict)
                ) / max(1, len(search_evidence_cards))
                freshness_score = max(
                    0.0,
                    1.0
                    - min(
                        1.0,
                        avg_freshness
                        / max(
                            1.0,
                            float(
                                _safe_int(
                                    getattr(settings, "INVESTIGATION_EVIDENCE_CACHE_MAX_AGE_HOURS", 72),
                                    72,
                                )
                            ),
                        ),
                    ),
                )
            quality_summary = {
                **quality_summary,
                "specific_url_ratio": quality_summary.get("specific_url_ratio", 0.0),
                "freshness_score": round(float(freshness_score), 4),
            }
            evidence_doc_records = self._build_evidence_docs(evidence_registry)
            try:
                if evidence_doc_records:
                    get_sqlite_db().save_evidence_docs_batch(
                        keyword=keyword,
                        run_id=run_id,
                        docs=evidence_doc_records,
                    )
            except Exception as doc_save_err:
                logger.warning(f"save evidence docs failed: {doc_save_err}")
            hit_total = len(search_hit_records)
            hit_promoted = len(
                [
                    row
                    for row in search_hit_records
                    if isinstance(row, dict) and bool(row.get("is_promoted"))
                ]
            )
            hit_dropped = max(0, hit_total - hit_promoted)
            acquisition_report["search_hit_total"] = int(hit_total)
            acquisition_report["search_hit_promoted"] = int(hit_promoted)
            acquisition_report["search_hit_dropped"] = int(hit_dropped)
            acquisition_report["evidence_doc_count"] = int(len(evidence_doc_records))

            if int(acquisition_report.get("external_evidence_count") or len(search_evidence_cards)) < target_valid_evidence_min:
                data_quality_flags.append("INSUFFICIENT_VALID_EVIDENCE")
            if effective_platforms_with_data < min_platforms_with_data:
                data_quality_flags.append("LOW_PLATFORM_COVERAGE")

            result = {
                "run_id": run_id,
                "status": result_status,
                "accepted_at": req.get("accepted_at"),
                "completed_at": _utc_now(),
                "request": req,
                "steps": steps,
                "iteration_summary": iteration_summary,
                "enhanced": enhanced,
                "search": {"keyword": keyword, "data": search},
                "search_hits": search_hit_records[:1200],
                "credibility": credibility,
                "agent_outputs": multi_agent,
                "debate_analysis": debate_result,
                "cot_thinking_chain": cot_display,
                "evidence_registry": evidence_registry,
                "evidence_docs": evidence_doc_records[:1200],
                "evidence_pool": evidence_pool_cards[:200],
                "context_pool": context_pool_cards[:200],
                "noise_pool": noise_pool_cards[:200],
                "score_breakdown": {
                    **score_breakdown,
                    "evidence_count": len(evidence_registry),
                    "valid_evidence_count": int(
                        acquisition_report.get("external_evidence_count")
                        or len(search_evidence_cards)
                    ),
                },
                "dual_profile_result": dual_profile,
                "report_template": {
                    "template_id": template.get("template_id"),
                    "version": template.get("version"),
                    "checksum": template.get("checksum"),
                },
                "report_sections": report_sections,
                "source_trace": source_trace,
                "earliest_related_content_at": (
                    source_trace.get("earliest_published_at")
                    or source_trace.get("first_seen_at")
                ),
                "latest_related_content_at": source_trace.get("latest_event_at"),
                "no_data_explainer": multi_agent.get("no_data_explainer"),
                "external_sources": external_sources,
                "platform_health_snapshot": (
                    crawlers.get_platform_health_snapshot()
                    if hasattr(crawlers, "get_platform_health_snapshot")
                    else platform_health_snapshot
                ),
                "platform_health_matrix": (
                    crawlers.get_platform_source_matrix()
                    if hasattr(crawlers, "get_platform_source_matrix")
                    else platform_health_matrix
                ),
                "fallback_applied": fallback_applied,
                "data_quality_flags": sorted(list(set(data_quality_flags))),
                "acquisition_report": acquisition_report,
                "quality_summary": quality_summary,
                "agent_input_trace": {
                    "platforms": agent_platforms,
                    "limit_per_platform": agent_limit_per_platform,
                    "collection_rounds": agent_collection_rounds,
                    "sampled_evidence_ids": [x.get("id") for x in evidence_registry[:80]],
                },
                "source_plan": source_plan,
                "claim_analysis": claim_analysis,
                "opinion_monitoring": opinion_monitoring,
            }
            nde = result.get("no_data_explainer")
            total_reason_stats = acquisition_report.get("platform_reason_stats", {}).get("by_reason") or {}
            network_fail_total = sum(
                int(total_reason_stats.get(code, 0))
                for code in [
                    "CRAWLER_TIMEOUT",
                    "TLS_TIMEOUT",
                    "UNREACHABLE",
                    "NETWORK_ERROR",
                    "FALLBACK_EMPTY",
                    "DNS_ERROR",
                    "PROXY_UNREACHABLE",
                ]
            )
            all_fail_total = sum(int(v) for v in total_reason_stats.values()) or 0
            external_valid_count = int(
                acquisition_report.get("external_evidence_count")
                or len(search_evidence_cards)
            )
            has_min_coverage = (
                external_valid_count >= target_valid_evidence_min
                and effective_platforms_with_data >= min_platforms_with_data
            )
            if has_min_coverage:
                inferred_reason_code = "AGENT_DEGRADED"
            else:
                inferred_reason_code = (
                    "NETWORK_UNREACHABLE"
                    if all_fail_total > 0 and network_fail_total / float(all_fail_total) >= 0.6
                    else "INSUFFICIENT_EVIDENCE"
                )
            hard_fail_on_zero_evidence = bool(
                getattr(settings, "INVESTIGATION_HARD_FAIL_ON_ZERO_EVIDENCE", True)
            )
            hard_fail_network_ratio_threshold = _safe_float(
                getattr(settings, "INVESTIGATION_HARD_FAIL_NETWORK_RATIO_THRESHOLD", 0.7),
                0.7,
            )
            network_fail_ratio = (
                network_fail_total / float(all_fail_total)
                if all_fail_total > 0
                else 0.0
            )
            if (
                hard_fail_on_zero_evidence
                and external_valid_count <= 0
                and effective_platforms_with_data <= 0
            ):
                hard_fail_reason = (
                    "NETWORK_UNREACHABLE"
                    if network_fail_ratio >= hard_fail_network_ratio_threshold
                    else "INSUFFICIENT_EVIDENCE"
                )
                await self.manager.append_event(
                    run_id,
                    "warning",
                    {
                        "code": "HARD_FAIL_ZERO_EVIDENCE",
                        "reason_code": hard_fail_reason,
                        "network_fail_ratio": round(network_fail_ratio, 4),
                        "network_fail_total": int(network_fail_total),
                        "all_fail_total": int(all_fail_total),
                    },
                )
                raise RuntimeError(
                    f"HARD_FAIL_ZERO_EVIDENCE({hard_fail_reason})"
                )
            if result_status in {"partial", "insufficient_evidence"} and not isinstance(nde, dict):
                nde = {
                    "reason_code": inferred_reason_code,
                    "attempted_platforms": list(search.keys()),
                    "platform_errors": (
                        acquisition_report.get("platform_reason_stats", {}).get("by_platform")
                        or {"unknown": {"crawler_empty": 1}}
                    ),
                    "retrieval_scope": {
                        "keyword": keyword,
                        "quality_mode": quality_mode,
                        "target_valid_evidence_min": target_valid_evidence_min,
                        "live_evidence_target": live_evidence_target,
                    },
                    "coverage_ratio": round(
                        effective_platforms_with_data / float(max(1, len(search))),
                        4,
                    ),
                    "next_queries": [
                        keyword,
                        f"{keyword} 官方 通告",
                        f"{keyword} site:news.cn",
                        f"{keyword} site:reuters.com",
                    ],
                }
                result["no_data_explainer"] = nde
            if isinstance(nde, dict) and not nde.get("platform_errors"):
                nde["platform_errors"] = {"unknown": ["crawler_empty"]}
            if isinstance(nde, dict) and not nde.get("reason_code"):
                nde["reason_code"] = inferred_reason_code
            if (
                isinstance(nde, dict)
                and inferred_reason_code == "NETWORK_UNREACHABLE"
                and nde.get("reason_code") in {"INSUFFICIENT_EVIDENCE", "TIMEOUT", "TIME_BUDGET_EXCEEDED"}
                and not has_min_coverage
            ):
                nde["reason_code"] = "NETWORK_UNREACHABLE"

            result["debug_summary"] = self._build_debug_summary(
                result_status=result_status,
                data_quality_flags=data_quality_flags,
                acquisition_report=acquisition_report,
                claim_analysis=claim_analysis,
                no_data_explainer=nde,
                source_plan=source_plan,
            )

            result["step_summaries"] = self._build_step_summaries(result)

            await self.manager.append_event(
                run_id,
                "run_completed",
                {
                    "run_id": run_id,
                    "status": result_status,
                    "evidence_count": len(evidence_registry),
                    "valid_evidence_count": int(
                        acquisition_report.get("external_evidence_count")
                        or len(search_evidence_cards)
                    ),
                    "external_evidence_count": int(
                        acquisition_report.get("external_evidence_count") or 0
                    ),
                    "derived_evidence_count": int(
                        acquisition_report.get("derived_evidence_count") or 0
                    ),
                    "target_valid_evidence_min": target_valid_evidence_min,
                    "claim_count": len(claim_analysis.get("claims") or []),
                    "review_queue_count": len(claim_analysis.get("review_queue") or []),
                    "claim_run_verdict": claim_analysis.get("run_verdict", "UNCERTAIN"),
                    "opinion_comment_count": int(opinion_monitoring.get("total_comments") or 0),
                    "opinion_risk_level": str(opinion_monitoring.get("risk_level") or "unknown"),
                    "search_hit_total": int(acquisition_report.get("search_hit_total") or 0),
                    "search_hit_promoted": int(
                        acquisition_report.get("search_hit_promoted") or 0
                    ),
                    "search_hit_dropped": int(
                        acquisition_report.get("search_hit_dropped") or 0
                    ),
                },
            )
            await self.manager.set_result(run_id, result=result, status=result_status)
            try:
                valid_for_metrics = int(
                    acquisition_report.get("external_evidence_count")
                    or len(search_evidence_cards)
                )
                investigation_valid_evidence_count.observe(valid_for_metrics)
                investigation_live_evidence_count.observe(int(live_count))
                investigation_cached_evidence_count.observe(int(cached_count))
                investigation_target_reached_total.labels(
                    reached="true"
                    if valid_for_metrics >= target_valid_evidence_min
                    else "false"
                ).inc()
            except Exception:
                pass
            analysis_requests_total.labels(
                analysis_type="investigation_run", status="success"
            ).inc()
        except Exception as exc:
            analysis_requests_total.labels(
                analysis_type="investigation_run", status="error"
            ).inc()
            logger.error(f"investigation run failed: {exc}", exc_info=True)
            await self.manager.append_event(
                run_id,
                "run_failed",
                {"run_id": run_id, "error": str(exc)},
            )
            await self.manager.set_status(run_id, "failed", error=str(exc))
        finally:
            duration = max(0.0, (datetime.utcnow() - analysis_started).total_seconds())
            analysis_duration_seconds.labels(analysis_type="investigation_run").observe(
                duration
            )
            try:
                investigation_duration_seconds.observe(duration)
            except Exception:
                pass

    def _build_dual_profile_result(
        self,
        enhanced_score: float,
        cross_score: float,
        agent_score: float,
        score_breakdown: Dict[str, Any],
        insufficient: bool,
    ) -> Dict[str, Any]:
        return build_dual_profile_result(
            enhanced_score=enhanced_score,
            cross_score=cross_score,
            agent_score=agent_score,
            score_breakdown=score_breakdown,
            insufficient=insufficient,
        )

    def _determine_result_status(
        self,
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
        return determine_result_status(
            multi_agent_status=multi_agent_status,
            valid_evidence_count=valid_evidence_count,
            target_valid_evidence_min=target_valid_evidence_min,
            live_evidence_count=live_evidence_count,
            live_evidence_target=live_evidence_target,
            platforms_with_data=platforms_with_data,
            min_platforms_with_data=min_platforms_with_data,
            steps=steps,
        )

    async def _check_external_sources(
        self,
        keyword: str,
        *,
        allowed_domains: Optional[List[str]] = None,
        limit: Optional[int] = None,
        whitelist_only: bool = False,
    ) -> List[Dict[str, Any]]:
        return await check_external_sources(
            keyword=keyword,
            allowed_domains=allowed_domains,
            limit=limit,
            whitelist_only=whitelist_only,
        )

    def _build_report_sections(
        self,
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
        return build_report_sections(
            template=template,
            keyword=keyword,
            enhanced=enhanced,
            credibility=credibility,
            multi_agent=multi_agent,
            evidence_registry=evidence_registry,
            steps=steps,
            source_trace=source_trace,
            opinion_monitoring=opinion_monitoring,
        )


_investigation_manager: InvestigationRunManager | None = None
_investigation_orchestrator: InvestigationOrchestrator | None = None


def get_investigation_manager() -> InvestigationRunManager:
    global _investigation_manager
    if _investigation_manager is None:
        _investigation_manager = InvestigationRunManager()
    return _investigation_manager


def get_investigation_orchestrator() -> InvestigationOrchestrator:
    global _investigation_orchestrator
    if _investigation_orchestrator is None:
        _investigation_orchestrator = InvestigationOrchestrator(
            manager=get_investigation_manager()
        )
    return _investigation_orchestrator
