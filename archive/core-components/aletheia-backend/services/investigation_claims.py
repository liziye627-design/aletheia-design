"""
主张级分析编排：
1) 主张抽取
2) 证据链接（含信源分级）
3) 强门槛判定
4) Fact Check 外部证据融合（可选）
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from core.config import settings
from services.evidence_linking import link_evidence_to_claims
from services.external.factcheck_client import GoogleFactCheckClient
from services.multi_agent_siliconflow import get_multi_agent_processor
from services.verdict_gate import StrongVerdictGate
from utils.logging import logger


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", str(text or "").lower())


def _logic_match_ratio(tokens: List[str], evidence_text: str) -> float:
    if not tokens:
        return 0.0
    hay = str(evidence_text or "").lower()
    if not hay:
        return 0.0
    matched = sum(1 for t in tokens if t and t in hay)
    return float(matched) / float(max(1, len(tokens)))


def _extract_evidence_text(row: Dict[str, Any]) -> str:
    snippet = str(row.get("snippet") or "")
    title = str(row.get("title") or row.get("headline") or "")
    return " ".join([title, snippet]).strip()


def _infer_claim_type(text: str) -> str:
    low = str(text or "").lower()
    if any(k in low for k in ["发布", "上线", "推出", "release", "launch", "announc"]):
        return "product_release"
    if any(k in low for k in ["感染", "疫情", "死亡", "病例", "virus", "disease"]):
        return "public_health"
    if any(k in low for k in ["融资", "收购", "ipo", "财报", "earnings", "acquisition"]):
        return "business_event"
    if any(k in low for k in ["政策", "监管", "条例", "law", "regulat", "sanction"]):
        return "policy_regulation"
    return "generic_claim"


def extract_claims(primary_claim: str, *, keyword: str = "", max_claims: int = 8) -> List[Dict[str, Any]]:
    source = _normalize(primary_claim)
    if not source:
        source = _normalize(keyword)
    if not source:
        return []

    rough_parts = re.split(r"[。！？!?;\n]+", source)
    candidates: List[str] = []
    for row in rough_parts:
        item = _normalize(row)
        if not item:
            continue
        # 过长段落按逗号再次拆分，避免单 claim 过宽
        if len(item) > 220 and ("，" in item or "," in item):
            for sub in re.split(r"[，,]+", item):
                sub_item = _normalize(sub)
                if len(sub_item) >= 8:
                    candidates.append(sub_item)
        else:
            candidates.append(item)

    if not candidates:
        candidates = [source]

    dedup: List[str] = []
    seen: set[str] = set()
    for item in candidates:
        sig = _normalize(item).lower()
        if len(sig) < 8 or sig in seen:
            continue
        seen.add(sig)
        dedup.append(item)
        if len(dedup) >= max_claims:
            break

    if not dedup:
        dedup = [source[:300]]

    claims: List[Dict[str, Any]] = []
    for idx, text in enumerate(dedup, start=1):
        claims.append(
            {
                "claim_id": f"clm_{idx:03d}",
                "text": text,
                "type": _infer_claim_type(text),
                "tokens": _tokenize(text),
            }
        )
    return claims


def _to_factcheck_evidence(claim_id: str, claim_text: str, fc_item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    title = str(fc_item.get("title") or "")
    rating = str(fc_item.get("rating") or "")
    snippet = " | ".join(x for x in [title, rating] if x).strip() or claim_text
    url = str(fc_item.get("url") or "")
    publisher = str(fc_item.get("publisher_name") or "factcheck")
    claim_date = fc_item.get("claim_date")
    collected_at = fc_item.get("fetched_at")
    stance = str(fc_item.get("stance") or "unclear")
    confidence = 0.78 if stance in {"support", "refute"} else 0.55
    return {
        "id": f"ev_factcheck_{claim_id}_{idx}",
        "claim_ref": claim_id,
        "source_tier": 2 if "factcheck" in publisher.lower() else 1,
        "source_name": publisher,
        "url": url,
        "snippet": snippet,
        "stance": stance,
        "confidence": confidence,
        "collected_at": collected_at,
        "published_at": claim_date,
        "first_seen_at": claim_date,
        "retrieval_query": claim_text,
        "validation_status": "reachable" if url else "derived",
        "retrieval_mode": "google_factcheck",
        "is_cached": False,
        "freshness_hours": 0.0,
        "cache_run_id": None,
        "evidence_class": "primary",
        "selection_reason": "factcheck_external_verification",
        "domain_match_score": 0.82,
        "metadata": {"origin": "google_factcheck"},
    }


async def _fetch_factcheck_evidence(
    claims: List[Dict[str, Any]],
    *,
    max_claims: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    client = GoogleFactCheckClient()
    external_rows: List[Dict[str, Any]] = []
    stats = {
        "requested_claims": 0,
        "successful_claims": 0,
        "fact_items": 0,
        "status": "NOT_RUN",
    }
    if not bool(getattr(settings, "FACTCHECK_ENABLE", True)):
        stats["status"] = "FACTCHECK_DISABLED"
        return external_rows, stats

    for claim in claims[: max(0, max_claims)]:
        claim_text = str(claim.get("text") or "")
        claim_id = str(claim.get("claim_id") or "")
        if not claim_text:
            continue
        stats["requested_claims"] += 1
        response = await client.search_claim(claim_text, page_size=5)
        items = list(response.get("items") or [])
        if response.get("available"):
            stats["successful_claims"] += 1
            stats["status"] = "OK"
        else:
            stats["status"] = str(response.get("reason") or "FACTCHECK_UNAVAILABLE")
        for idx, row in enumerate(items, start=1):
            enriched = dict(row)
            enriched["fetched_at"] = response.get("fetched_at")
            external_rows.append(_to_factcheck_evidence(claim_id, claim_text, enriched, idx))
        stats["fact_items"] += len(items)

    if stats["status"] == "NOT_RUN":
        stats["status"] = "FACTCHECK_UNAVAILABLE"
    return external_rows, stats


async def analyze_claims(
    *,
    primary_claim: str,
    keyword: str,
    evidence_registry: List[Dict[str, Any]],
    source_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    claims = extract_claims(
        primary_claim,
        keyword=keyword,
        max_claims=int(getattr(settings, "INVESTIGATION_CLAIM_MAX_CLAIMS", 8)),
    )
    if not claims:
        return {
            "claims": [],
            "review_queue": [],
            "matrix_summary": {"tier1_count": 0, "tier2_count": 0, "tier3_count": 0, "tier4_count": 0},
            "run_verdict": "UNCERTAIN",
            "factcheck": {"status": "FACTCHECK_UNAVAILABLE"},
            "claim_links": {},
            "evidence_append": [],
        }

    factcheck_rows: List[Dict[str, Any]] = []
    factcheck_stats: Dict[str, Any] = {"status": "FACTCHECK_DISABLED"}
    try:
        if bool(getattr(settings, "FACTCHECK_ENABLE", True)):
            factcheck_rows, factcheck_stats = await _fetch_factcheck_evidence(
                claims,
                max_claims=int(getattr(settings, "INVESTIGATION_FACTCHECK_MAX_CLAIMS", 3)),
            )
    except Exception as exc:
        logger.warning(f"claim factcheck failed: {exc}")
        factcheck_stats = {"status": "FACTCHECK_UNAVAILABLE", "error": str(exc)}
        factcheck_rows = []

    merged_evidence = list(evidence_registry or [])
    merged_evidence.extend(factcheck_rows)
    excluded_platforms = set(str(x) for x in (source_plan or {}).get("excluded_platforms", []))

    def _is_primary(row: Dict[str, Any]) -> bool:
        evidence_class = str(row.get("evidence_class") or "").strip().lower()
        if evidence_class:
            return evidence_class == "primary"
        tier = int(row.get("source_tier") or 4)
        relevance = float(row.get("relevance_score") or 0.0)
        validation = str(row.get("validation_status") or "").lower()
        source_name = str(row.get("source_name") or "")
        if source_name in excluded_platforms and relevance < 0.45:
            return False
        if validation in {"invalid", "unreachable", "discarded"}:
            return False
        return (tier <= 2 and relevance >= 0.2) or relevance >= 0.45

    primary_evidence = [row for row in merged_evidence if isinstance(row, dict) and _is_primary(row)]
    evidence_for_linking = primary_evidence if primary_evidence else merged_evidence
    claim_links, matrix_summary = link_evidence_to_claims(
        claims,
        evidence_for_linking,
        max_per_claim=int(getattr(settings, "INVESTIGATION_CLAIM_LINK_MAX_PER_CLAIM", 24)),
        min_relevance=float(getattr(settings, "INVESTIGATION_CLAIM_MIN_RELEVANCE", 0.08)),
    )
    gate = StrongVerdictGate()
    verdict_bundle = gate.evaluate_all(claims=claims, claim_links=claim_links)
    output_claims = list(verdict_bundle.get("claims") or [])

    # 把链接明细压缩到 claim 中，前端按 claim_id 查询即可。
    for row in output_claims:
        claim_id = str(row.get("claim_id") or "")
        linked = claim_links.get(claim_id) or []
        row["linked_evidence"] = linked

    review_queue = list(verdict_bundle.get("review_queue") or [])
    if not primary_evidence:
        review_queue.append(
            {
                "claim_id": "global",
                "priority": "high",
                "reasons": ["INSUFFICIENT_PRIMARY_EVIDENCE", "DOMAIN_SOURCE_MISMATCH"],
            }
        )
    if any(len(str(c.get("text") or "")) <= 10 for c in claims):
        review_queue.append(
            {
                "claim_id": "global",
                "priority": "medium",
                "reasons": ["ENTITY_AMBIGUITY"],
            }
        )

    # Optional logic consistency check (simple token overlap guard)
    if bool(getattr(settings, "INVESTIGATION_LOGIC_CHECK_ENABLED", False)):
        min_ratio = float(
            getattr(settings, "INVESTIGATION_LOGIC_CHECK_MIN_MATCH_RATIO", 0.2)
        )
        mismatched_claims: List[str] = []
        for row in output_claims:
            claim_text = str(row.get("text") or "")
            tokens = _tokenize(claim_text)
            linked_rows = list(row.get("linked_evidence") or [])
            if not linked_rows:
                continue
            ratios = [
                _logic_match_ratio(tokens, _extract_evidence_text(ev))
                for ev in linked_rows
                if isinstance(ev, dict)
            ]
            best_ratio = max(ratios) if ratios else 0.0
            row["logic_check"] = {
                "match_ratio": round(float(best_ratio), 4),
                "status": "ok" if best_ratio >= min_ratio else "mismatch",
                "threshold": round(float(min_ratio), 4),
            }
            if best_ratio < min_ratio:
                mismatched_claims.append(str(row.get("claim_id") or ""))

        if mismatched_claims:
            for claim_id in mismatched_claims:
                review_queue.append(
                    {
                        "claim_id": claim_id,
                        "priority": "high",
                        "reasons": ["LOGIC_MISMATCH"],
                    }
                )

    claim_reasoning: List[Dict[str, Any]] = []
    require_reasoning = bool(
        getattr(settings, "INVESTIGATION_CLAIM_REASONING_REQUIRE_LLM", False)
    )
    try:
        enable_reasoning = bool(getattr(settings, "INVESTIGATION_CLAIM_REASONING_ENABLE_LLM", True))
        max_reasoning_claims = max(
            1,
            int(getattr(settings, "INVESTIGATION_CLAIM_REASONING_MAX_CLAIMS", 4) or 4),
        )
        timeout_sec = max(
            3,
            int(getattr(settings, "INVESTIGATION_CLAIM_REASONING_TIMEOUT_SEC", 8) or 8),
        )
        max_attempts = max(
            1,
            int(getattr(settings, "INVESTIGATION_CLAIM_REASONING_RETRIES", 1) or 1),
        )
        backoff_sec = max(
            0.0,
            float(getattr(settings, "INVESTIGATION_CLAIM_REASONING_RETRY_BACKOFF_SEC", 1.5) or 0.0),
        )
        if enable_reasoning and output_claims:
            processor = get_multi_agent_processor()
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    claim_reasoning = await asyncio.wait_for(
                        processor.build_claim_reasoning_with_citations(
                            keyword=keyword,
                            claims=output_claims[:max_reasoning_claims],
                        ),
                        timeout=timeout_sec,
                    )
                    if claim_reasoning:
                        break
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        f"claim reasoning attempt {attempt}/{max_attempts} failed: {exc!r}"
                    )
                if attempt < max_attempts and backoff_sec > 0:
                    await asyncio.sleep(backoff_sec * attempt)
            if not claim_reasoning and last_exc:
                raise last_exc
        elif require_reasoning and output_claims:
            logger.warning("claim reasoning skipped: LLM disabled but required")
    except Exception as exc:
        logger.warning(
            f"claim reasoning build failed{' (llm required)' if require_reasoning else ''}: {exc!r}"
        )
        claim_reasoning = []

    if require_reasoning and claim_reasoning:
        filtered = [row for row in claim_reasoning if not bool(row.get("fallback"))]
        if len(filtered) != len(claim_reasoning):
            logger.warning("claim reasoning filtered fallback rows because LLM is required")
        claim_reasoning = filtered

    if require_reasoning and output_claims and not claim_reasoning:
        review_queue.append(
            {
                "claim_id": "global",
                "priority": "high",
                "reasons": ["LLM_REASONING_MISSING", "LLM_REQUIRED"],
            }
        )

    if not claim_reasoning and not require_reasoning:
        for claim_row in output_claims:
            linked = list(claim_row.get("linked_evidence") or [])[:6]
            citations = [
                {
                    "evidence_id": str(ev.get("evidence_id") or ""),
                    "url": str(ev.get("url") or ""),
                    "source_name": str(ev.get("source_name") or "unknown"),
                    "source_tier": int(ev.get("source_tier") or 4),
                    "stance": str(ev.get("stance") or "unclear"),
                    "snippet_quote": str(ev.get("snippet") or "")[:180],
                }
                for ev in linked
                if isinstance(ev, dict)
            ]
            claim_reasoning.append(
                {
                    "claim_id": claim_row.get("claim_id"),
                    "conclusion_text": f"结论：{claim_row.get('verdict', 'UNCERTAIN')}（score={float(claim_row.get('score') or 0.0):.2f}）。",
                    "risk_text": (
                        f"风险：{','.join(claim_row.get('gate_reasons') or []) or '无显著风险码'}。"
                    ),
                    "reasoning_steps": [
                        f"S={int((claim_row.get('stance_summary') or {}).get('support', 0))}",
                        f"R={int((claim_row.get('stance_summary') or {}).get('refute', 0))}",
                        f"U={int((claim_row.get('stance_summary') or {}).get('unclear', 0))}",
                    ],
                    "citations": citations,
                    "fallback": True,
                }
            )

    # 对齐 claim 数量：若 LLM 仅返回部分主张，补齐缺失行
    claim_reasoning_by_id = {
        str(row.get("claim_id") or ""): row
        for row in claim_reasoning
        if isinstance(row, dict)
    }
    if require_reasoning:
        missing_ids = [
            str(row.get("claim_id") or "")
            for row in output_claims
            if str(row.get("claim_id") or "") not in claim_reasoning_by_id
        ]
        if missing_ids:
            review_queue.append(
                {
                    "claim_id": "global",
                    "priority": "high",
                    "reasons": ["LLM_REASONING_PARTIAL", "LLM_REQUIRED"],
                    "missing_claim_ids": missing_ids[:20],
                }
            )
    if not require_reasoning:
        for claim_row in output_claims:
            claim_id = str(claim_row.get("claim_id") or "")
            if claim_id and claim_id not in claim_reasoning_by_id:
                linked = list(claim_row.get("linked_evidence") or [])[:6]
                citations = [
                    {
                        "evidence_id": str(ev.get("evidence_id") or ""),
                        "url": str(ev.get("url") or ""),
                        "source_name": str(ev.get("source_name") or "unknown"),
                        "source_tier": int(ev.get("source_tier") or 4),
                        "stance": str(ev.get("stance") or "unclear"),
                        "snippet_quote": str(ev.get("snippet") or "")[:180],
                    }
                    for ev in linked
                    if isinstance(ev, dict)
                ]
                row = {
                    "claim_id": claim_id,
                    "conclusion_text": f"结论：{claim_row.get('verdict', 'UNCERTAIN')}（score={float(claim_row.get('score') or 0.0):.2f}）。",
                    "risk_text": f"风险：{','.join(claim_row.get('gate_reasons') or []) or '无显著风险码'}。",
                    "reasoning_steps": [
                        f"S={int((claim_row.get('stance_summary') or {}).get('support', 0))}",
                        f"R={int((claim_row.get('stance_summary') or {}).get('refute', 0))}",
                        f"U={int((claim_row.get('stance_summary') or {}).get('unclear', 0))}",
                    ],
                    "citations": citations,
                    "fallback": True,
                }
                claim_reasoning.append(row)
                claim_reasoning_by_id[claim_id] = row

    # 质量守卫：每条 claim 至少有 1 条可追溯链接；否则入复核队列
    review_seen = {
        (str(item.get("claim_id") or ""), tuple(sorted([str(x) for x in item.get("reasons") or []])))
        for item in review_queue
        if isinstance(item, dict)
    }
    for claim_row in output_claims:
        claim_id = str(claim_row.get("claim_id") or "")
        reason_row = claim_reasoning_by_id.get(claim_id)
        if not isinstance(reason_row, dict):
            continue
        citations_raw = [c for c in list(reason_row.get("citations") or []) if isinstance(c, dict)]
        traceable = [c for c in citations_raw if str(c.get("url") or "").startswith("http")]
        if not traceable:
            for ev in list(claim_row.get("linked_evidence") or []):
                if not isinstance(ev, dict):
                    continue
                url = str(ev.get("url") or "")
                if not url.startswith("http"):
                    continue
                traceable.append(
                    {
                        "evidence_id": str(ev.get("evidence_id") or ""),
                        "url": url,
                        "source_name": str(ev.get("source_name") or "unknown"),
                        "source_tier": int(ev.get("source_tier") or 4),
                        "stance": str(ev.get("stance") or "unclear"),
                        "snippet_quote": str(ev.get("snippet") or "")[:180],
                    }
                )
                break
        reason_row["citations"] = traceable[:6]
        if not reason_row["citations"]:
            key = (claim_id, ("INSUFFICIENT_CITED_EVIDENCE", "REVIEW_REQUIRED"))
            if key not in review_seen:
                review_queue.append(
                    {
                        "claim_id": claim_id or "global",
                        "priority": "high",
                        "reasons": ["INSUFFICIENT_CITED_EVIDENCE", "REVIEW_REQUIRED"],
                    }
                )
                review_seen.add(key)
            reason_row["fallback"] = True
            risk_text = str(reason_row.get("risk_text") or "")
            if "INSUFFICIENT_CITED_EVIDENCE" not in risk_text:
                reason_row["risk_text"] = (risk_text + " ").strip() + "风险：缺少可追溯引用链接。"

    verdict_counter = Counter(str(row.get("verdict") or "UNCERTAIN") for row in output_claims)
    run_verdict = verdict_bundle.get("run_verdict") or "UNCERTAIN"
    if any("LOGIC_MISMATCH" in (row.get("reasons") or []) for row in review_queue):
        run_verdict = "REVIEW_REQUIRED"
    return {
        "claims": output_claims,
        "review_queue": review_queue,
        "claim_reasoning": claim_reasoning,
        "matrix_summary": matrix_summary,
        "run_verdict": run_verdict,
        "summary": dict(verdict_counter),
        "factcheck": factcheck_stats,
        "claim_links": claim_links,
        "evidence_append": factcheck_rows,
    }
