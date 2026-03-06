"""
主张-证据链接与信源分级。
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from loguru import logger

from services.investigation_helpers import _tier_for_url


_QUESTION_TAIL = re.compile(r"(?:[吗么嘛呢吧啊呀了]+\??)+$")
_CJK_HINTS = (
    "退役",
    "复出",
    "夺冠",
    "去世",
    "辟谣",
    "回应",
    "宣布",
    "否认",
    "确认",
    "爆料",
    "传闻",
    "处罚",
)


def _normalize_semantic_text(text: str) -> str:
    low = str(text or "").strip().lower()
    if not low:
        return ""
    low = low.replace("？", "?")
    low = re.sub(r"[，。、“”‘’【】（）\(\)\[\]<>《》!！,.;:：]", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    # 常见中文问句尾裁剪，降低 “退役了吗/是否退役” 对匹配的干扰。
    low = _QUESTION_TAIL.sub("", low).strip()
    return low


def _expand_cjk_token(token: str) -> List[str]:
    base = str(token or "").strip()
    if len(base) < 2 or not re.fullmatch(r"[\u4e00-\u9fff]+", base):
        return []
    out: List[str] = [base]
    trimmed = _QUESTION_TAIL.sub("", base).strip()
    if len(trimmed) >= 2 and trimmed not in out:
        out.append(trimmed)
    for hint in _CJK_HINTS:
        pos = base.find(hint)
        if pos > 0:
            prefix = base[:pos].strip()
            if len(prefix) >= 2 and prefix not in out:
                out.append(prefix)
            phrase = f"{prefix}{hint}".strip()
            if len(phrase) >= 3 and phrase not in out:
                out.append(phrase)
    return out


def _tokenize(text: str) -> List[str]:
    norm = _normalize_semantic_text(text)
    chunks = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", norm)
    out: List[str] = []
    for chunk in chunks:
        if len(chunk) < 2:
            continue
        if chunk not in out:
            out.append(chunk)
        for ext in _expand_cjk_token(chunk):
            if ext not in out:
                out.append(ext)
    return out


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    normalized = re.sub(r"\s+", "", _normalize_semantic_text(text))
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return float(inter / max(1, union))


def _entity_overlap_score(claim_text: str, evidence_text: str) -> float:
    claim_entities = {t for t in _tokenize(claim_text) if len(t) >= 3}
    evidence_entities = {t for t in _tokenize(evidence_text) if len(t) >= 3}
    if not claim_entities or not evidence_entities:
        return 0.0
    inter = claim_entities.intersection(evidence_entities)
    return float(len(inter) / max(1, len(claim_entities)))


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def infer_source_tier(item: Dict[str, Any]) -> int:
    tier = item.get("source_tier")
    if isinstance(tier, int) and 1 <= tier <= 4:
        return tier
    if isinstance(tier, str) and tier.isdigit():
        value = int(tier)
        if 1 <= value <= 4:
            return value
    url = str(item.get("url") or "")
    inferred = int(_tier_for_url(url))
    return inferred if inferred in {1, 2, 3} else 4


def infer_source_type(item: Dict[str, Any], source_tier: int) -> str:
    source_name = str(item.get("source_name") or "").lower()
    host = _domain_from_url(str(item.get("url") or ""))
    if source_tier == 1:
        return "official"
    if source_tier == 2:
        return "authority_media"
    if any(x in source_name for x in ("weibo", "reddit", "xiaohongshu", "douyin", "bilibili")):
        return "social"
    if any(x in host for x in ("gov.", ".gov", "who.int", "un.org", "sec.gov")):
        return "official"
    return "community"


def infer_source_score(source_tier: int) -> float:
    if source_tier == 1:
        return 1.0
    if source_tier == 2:
        return 0.82
    if source_tier == 3:
        return 0.48
    return 0.25


def _build_text_blob(item: Dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    values = [
        item.get("snippet"),
        item.get("title"),
        item.get("headline"),
        item.get("content"),
        item.get("content_text"),
        item.get("text"),
        item.get("summary"),
        metadata.get("author_name"),
        metadata.get("author"),
    ]
    return "\n".join(str(v or "") for v in values)


def compute_relevance(claim_text: str, evidence_item: Dict[str, Any]) -> float:
    claim_tokens = set(_tokenize(claim_text))
    evidence_tokens = set(_tokenize(_build_text_blob(evidence_item)))
    if not claim_tokens or not evidence_tokens:
        return 0.0
    overlap = claim_tokens.intersection(evidence_tokens)
    token_score = len(overlap) / max(1, len(claim_tokens))
    char_score = _jaccard(_char_ngrams(claim_text, 2), _char_ngrams(_build_text_blob(evidence_item), 2))
    score = max(float(token_score), float(char_score) * 0.82)
    return round(float(max(0.0, min(1.0, score))), 4)


def _semantic_rerank_score(
    claim_text: str,
    evidence_item: Dict[str, Any],
    *,
    stage1_score: float,
    source_score: float,
) -> float:
    evidence_blob = _build_text_blob(evidence_item)
    char_sim = _jaccard(_char_ngrams(claim_text, 2), _char_ngrams(evidence_blob, 2))
    entity_overlap = _entity_overlap_score(claim_text, evidence_blob)
    low_claim = _normalize_semantic_text(claim_text)
    low_blob = _normalize_semantic_text(evidence_blob)
    phrase_bonus = 0.15 if low_claim and low_claim in low_blob else 0.0
    if not phrase_bonus:
        claim_variants = [t for t in _tokenize(low_claim) if len(t) >= 3][:4]
        if any(variant in low_blob for variant in claim_variants):
            phrase_bonus = 0.09
    title_blob = str(evidence_item.get("title") or evidence_item.get("headline") or "").lower()
    title_bonus = 0.08 if low_claim and low_claim[: min(16, len(low_claim))] in title_blob else 0.0

    rerank = (
        0.45 * max(0.0, min(1.0, stage1_score))
        + 0.25 * max(0.0, min(1.0, char_sim))
        + 0.2 * max(0.0, min(1.0, entity_overlap))
        + 0.1 * max(0.0, min(1.0, source_score))
        + phrase_bonus
        + title_bonus
    )
    return round(max(0.0, min(1.0, rerank)), 4)


def classify_stance(claim_text: str, evidence_item: Dict[str, Any]) -> str:
    text_blob = _build_text_blob(evidence_item).lower()
    low_claim = _normalize_semantic_text(claim_text)
    if not text_blob:
        return "unclear"

    support_terms = [
        "confirmed",
        "official",
        "announced",
        "announce",
        "证实",
        "发布",
        "通报",
        "公告",
        "官宣",
        "宣布",
        "确认",
        "正式退役",
        "宣布退役",
        "退役声明",
        "结束职业生涯",
        "告别赛场",
        "confirmed",
        "according to",
    ]
    refute_terms = [
        "false",
        "fake",
        "hoax",
        "debunk",
        "incorrect",
        "not true",
        "不实",
        "辟谣",
        "谣言",
        "未发生",
        "并未",
        "否认",
        "并未退役",
        "未退役",
        "没有退役",
        "退役传闻",
        "与事实不符",
    ]
    has_support = any(token in text_blob for token in support_terms)
    has_refute = any(token in text_blob for token in refute_terms)

    # 事件词定向补强：例如 “退役了吗” 需要识别 “宣布退役/正式退役” 这类表述。
    if "退役" in low_claim:
        if any(
            token in text_blob
            for token in (
                "宣布退役",
                "正式退役",
                "退役声明",
                "结束职业生涯",
                "告别职业赛场",
            )
        ):
            has_support = True
        if any(token in text_blob for token in ("并未退役", "没有退役", "否认退役", "退役传闻")):
            has_refute = True
    if has_support and has_refute:
        return "mixed"
    if has_refute:
        return "refute"
    if has_support:
        return "support"

    # 轻量兜底：若 claim 词命中较高，且证据可达，则按 context。
    relevance = compute_relevance(low_claim, evidence_item)
    if relevance >= 0.45 and str(evidence_item.get("validation_status") or "").lower() in {
        "reachable",
        "valid",
        "derived",
    }:
        return "context"
    return "unclear"


def _confidence_multiplier(validation_status: str) -> float:
    low = str(validation_status or "").lower()
    if low in {"reachable", "valid", "derived"}:
        return 1.0
    if low in {"provisional_reachable", "provisional", "unknown"}:
        return 0.75
    if low in {"unreachable", "invalid", "discarded"}:
        return 0.35
    return 0.7


def link_evidence_to_claims(
    claims: Iterable[Dict[str, Any]],
    evidence_registry: List[Dict[str, Any]],
    *,
    max_per_claim: int = 24,
    min_relevance: float = 0.2,
    use_llm_rerank: bool = False,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Link evidence to claims with optional LLM-based reranking.

    Args:
        claims: Iterable of claim dictionaries
        evidence_registry: List of evidence item dictionaries
        max_per_claim: Maximum evidence items per claim
        min_relevance: Minimum relevance threshold for evidence
        use_llm_rerank: Whether to use LLM-based reranking (requires async context)

    Returns:
        Tuple of (claim_links dict, matrix_summary dict)
    """
    # For sync usage, delegate to async version with default reranking
    if use_llm_rerank:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in async context - use the rule-based method
            logger.warning(
                "link_evidence_to_claims called with use_llm_rerank=True in async context. "
                "Use link_evidence_to_claims_async for LLM reranking."
            )
        else:
            # Sync context - run async version
            return asyncio.run(
                link_evidence_to_claims_async(
                    claims,
                    evidence_registry,
                    max_per_claim=max_per_claim,
                    min_relevance=min_relevance,
                    use_llm_rerank=True,
                )
            )

    # Rule-based linking (original implementation)
    return _link_evidence_to_claims_sync(claims, evidence_registry, max_per_claim, min_relevance)


async def link_evidence_to_claims_async(
    claims: Iterable[Dict[str, Any]],
    evidence_registry: List[Dict[str, Any]],
    *,
    max_per_claim: int = 24,
    min_relevance: float = 0.2,
    use_llm_rerank: bool = True,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Async version of link_evidence_to_claims with LLM-based reranking support.

    Args:
        claims: Iterable of claim dictionaries
        evidence_registry: List of evidence item dictionaries
        max_per_claim: Maximum evidence items per claim
        min_relevance: Minimum relevance threshold for evidence
        use_llm_rerank: Whether to use LLM-based reranking

    Returns:
        Tuple of (claim_links dict, matrix_summary dict)
    """
    from core.config import settings

    # Check if LLM reranking is enabled
    llm_rerank_enabled = use_llm_rerank and getattr(
        settings, "INVESTIGATION_LLM_SEMANTIC_RERANK_ENABLED", False
    )

    if not llm_rerank_enabled:
        return _link_evidence_to_claims_sync(claims, evidence_registry, max_per_claim, min_relevance)

    # Use LLM reranking
    try:
        from services.reranker import get_evidence_reranker

        reranker = get_evidence_reranker()
        return await _link_evidence_to_claims_with_llm_rerank(
            claims, evidence_registry, reranker, max_per_claim, min_relevance
        )
    except Exception as e:
        logger.error(f"LLM reranking failed, falling back to rule-based: {e}")
        return _link_evidence_to_claims_sync(claims, evidence_registry, max_per_claim, min_relevance)


def _link_evidence_to_claims_sync(
    claims: Iterable[Dict[str, Any]],
    evidence_registry: List[Dict[str, Any]],
    max_per_claim: int,
    min_relevance: float,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    claim_links: Dict[str, List[Dict[str, Any]]] = {}
    all_selected: List[Dict[str, Any]] = []

    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        claim_text = str(claim.get("text") or "")
        ranked: List[Dict[str, Any]] = []
        for item in evidence_registry or []:
            if not isinstance(item, dict):
                continue
            # Stage 1: 轻量召回（词项相关）
            relevance = compute_relevance(claim_text, item)
            tier = infer_source_tier(item)
            stage1_threshold = float(min_relevance)
            if tier <= 2:
                stage1_threshold = max(0.08, stage1_threshold * 0.75)
            if relevance < stage1_threshold:
                # 对已被上游判定为主证据的高层级信源做小幅召回兜底，
                # 避免中英混合或短文本导致的 token overlap 假阴性。
                evidence_class = str(item.get("evidence_class") or "").lower()
                validation_status = str(item.get("validation_status") or "").lower()
                confidence = float(item.get("confidence") or 0.0)
                if not (
                    evidence_class == "primary"
                    and tier <= 2
                    and validation_status in {"reachable", "valid", "provisional", "provisional_reachable"}
                    and confidence >= 0.6
                ):
                    continue
                relevance = stage1_threshold

            source_score = infer_source_score(tier)
            # Stage 2: 语义近似重排（无重依赖，代理 cross-encoder）
            stage2_score = _semantic_rerank_score(
                claim_text,
                item,
                stage1_score=relevance,
                source_score=source_score,
            )
            stance = classify_stance(claim_text, item)
            validation_status = str(item.get("validation_status") or "unknown")
            conf = float(item.get("confidence") or 0.0)
            quality_score = round(
                source_score
                * max(0.1, min(1.0, stage2_score + 0.15))
                * _confidence_multiplier(validation_status)
                * max(0.2, min(1.0, conf if conf > 0 else 0.55)),
                4,
            )
            row = {
                "evidence_id": str(item.get("id") or ""),
                "source_name": str(item.get("source_name") or "unknown"),
                "platform": str(item.get("source_platform") or item.get("source_name") or "unknown"),
                "url": str(item.get("url") or ""),
                "snippet": str(item.get("snippet") or ""),
                "published_at": item.get("published_at"),
                "collected_at": item.get("collected_at"),
                "source_tier": tier,
                "source_type": infer_source_type(item, tier),
                "source_score": source_score,
                "stance": stance,
                "validation_status": validation_status,
                "confidence": conf,
                "relevance": relevance,
                "stage1_score": relevance,
                "stage2_score": stage2_score,
                "quality_score": quality_score,
            }
            ranked.append(row)

        ranked.sort(
            key=lambda row: (
                -float(row.get("stage2_score") or 0.0),
                int(row.get("source_tier") or 4),
                -float(row.get("quality_score") or 0.0),
                -float(row.get("relevance") or 0.0),
            )
        )
        selected = ranked[: max(1, max_per_claim)]
        claim_links[claim_id] = selected
        all_selected.extend(selected)

    tier_counter = Counter(int(row.get("source_tier") or 4) for row in all_selected)
    source_counter = Counter(str(row.get("source_name") or "unknown") for row in all_selected)
    stance_counter = Counter(str(row.get("stance") or "unclear") for row in all_selected)

    matrix_summary = {
        "tier1_count": int(tier_counter.get(1, 0)),
        "tier2_count": int(tier_counter.get(2, 0)),
        "tier3_count": int(tier_counter.get(3, 0)),
        "tier4_count": int(tier_counter.get(4, 0)),
        "source_count": len(source_counter),
        "stance_breakdown": dict(stance_counter),
    }
    return claim_links, matrix_summary


async def _link_evidence_to_claims_with_llm_rerank(
    claims: Iterable[Dict[str, Any]],
    evidence_registry: List[Dict[str, Any]],
    reranker,
    max_per_claim: int,
    min_relevance: float,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Link evidence to claims using LLM-based reranking.

    This function uses the EvidenceReranker to compute semantic relevance scores
    using the Qwen3-Reranker-8B model, providing more accurate evidence ranking.
    """
    claim_links: Dict[str, List[Dict[str, Any]]] = {}
    all_selected: List[Dict[str, Any]] = []

    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        claim_text = str(claim.get("text") or "")

        # Stage 1: Filter by relevance threshold
        candidates: List[Dict[str, Any]] = []
        for item in evidence_registry or []:
            if not isinstance(item, dict):
                continue

            relevance = compute_relevance(claim_text, item)
            tier = infer_source_tier(item)
            stage1_threshold = float(min_relevance)

            if tier <= 2:
                stage1_threshold = max(0.08, stage1_threshold * 0.75)

            if relevance < stage1_threshold:
                evidence_class = str(item.get("evidence_class") or "").lower()
                validation_status = str(item.get("validation_status") or "").lower()
                confidence = float(item.get("confidence") or 0.0)
                if not (
                    evidence_class == "primary"
                    and tier <= 2
                    and validation_status in {"reachable", "valid", "provisional", "provisional_reachable"}
                    and confidence >= 0.6
                ):
                    continue
                relevance = stage1_threshold

            candidates.append({
                "item": item,
                "relevance": relevance,
                "tier": tier,
                "source_score": infer_source_score(tier),
            })

        if not candidates:
            claim_links[claim_id] = []
            continue

        # Stage 2: LLM Reranking
        evidence_items = [c["item"] for c in candidates]
        reranked_items = await reranker.rerank_evidence(
            claim_text=claim_text,
            evidence_items=evidence_items,
            top_n=max_per_claim,
        )

        # Build final results with combined scores
        ranked: List[Dict[str, Any]] = []
        for reranked in reranked_items:
            # Find the candidate for this item
            original_item = None
            candidate_info = None
            for c in candidates:
                if c["item"].get("id") == reranked.get("id") or c["item"].get("url") == reranked.get("url"):
                    original_item = c["item"]
                    candidate_info = c
                    break

            if not original_item or not candidate_info:
                continue

            tier = candidate_info["tier"]
            relevance = candidate_info["relevance"]
            source_score = candidate_info["source_score"]
            rerank_score = reranked.get("rerank_score", 0.5)

            # Use LLM rerank score as the primary stage2 score
            stage2_score = rerank_score

            stance = classify_stance(claim_text, original_item)
            validation_status = str(original_item.get("validation_status") or "unknown")
            conf = float(original_item.get("confidence") or 0.0)

            quality_score = round(
                source_score
                * max(0.1, min(1.0, stage2_score + 0.15))
                * _confidence_multiplier(validation_status)
                * max(0.2, min(1.0, conf if conf > 0 else 0.55)),
                4,
            )

            row = {
                "evidence_id": str(original_item.get("id") or ""),
                "source_name": str(original_item.get("source_name") or "unknown"),
                "platform": str(original_item.get("source_platform") or original_item.get("source_name") or "unknown"),
                "url": str(original_item.get("url") or ""),
                "snippet": str(original_item.get("snippet") or ""),
                "published_at": original_item.get("published_at"),
                "collected_at": original_item.get("collected_at"),
                "source_tier": tier,
                "source_type": infer_source_type(original_item, tier),
                "source_score": source_score,
                "stance": stance,
                "validation_status": validation_status,
                "confidence": conf,
                "relevance": relevance,
                "stage1_score": relevance,
                "stage2_score": stage2_score,
                "rerank_score": rerank_score,
                "quality_score": quality_score,
            }
            ranked.append(row)

        # Sort by LLM rerank score
        ranked.sort(
            key=lambda row: (
                -float(row.get("rerank_score") or 0.0),
                int(row.get("source_tier") or 4),
                -float(row.get("quality_score") or 0.0),
            )
        )

        selected = ranked[: max(1, max_per_claim)]
        claim_links[claim_id] = selected
        all_selected.extend(selected)

    tier_counter = Counter(int(row.get("source_tier") or 4) for row in all_selected)
    source_counter = Counter(str(row.get("source_name") or "unknown") for row in all_selected)
    stance_counter = Counter(str(row.get("stance") or "unclear") for row in all_selected)

    matrix_summary = {
        "tier1_count": int(tier_counter.get(1, 0)),
        "tier2_count": int(tier_counter.get(2, 0)),
        "tier3_count": int(tier_counter.get(3, 0)),
        "tier4_count": int(tier_counter.get(4, 0)),
        "source_count": len(source_counter),
        "stance_breakdown": dict(stance_counter),
        "rerank_method": "llm",
    }
    return claim_links, matrix_summary
