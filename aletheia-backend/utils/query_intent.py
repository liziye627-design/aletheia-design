"""
Lightweight keyword normalization and relevance scoring utilities.

Goal: make Chinese claim-style queries (e.g. "苏炳添退役了吗") searchable
across RSS/local-index pipelines without requiring LLM.
"""

from __future__ import annotations

import re
from typing import List


_CJK_EVENT_HINTS = (
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


def _is_cjk_token(token: str) -> bool:
    return bool(token) and bool(re.fullmatch(r"[\u4e00-\u9fff]+", token))


def _append_unique(rows: List[str], value: str, *, min_len: int = 2) -> None:
    val = str(value or "").strip().lower()
    if len(val) < min_len:
        return
    if val not in rows:
        rows.append(val)


def _expand_cjk_token(token: str) -> List[str]:
    base = str(token or "").strip().lower()
    if len(base) < 2 or (not _is_cjk_token(base)):
        return []

    out: List[str] = []
    _append_unique(out, base)
    trimmed = re.sub(r"[了啊呀嘛吧呢吗哈么]+$", "", base).strip()
    _append_unique(out, trimmed)

    for hint in _CJK_EVENT_HINTS:
        pos = base.find(hint)
        if pos > 0:
            prefix = base[:pos].strip()
            _append_unique(out, prefix)
            _append_unique(out, f"{prefix}{hint}")

    if len(base) >= 4:
        max_grams = 24
        used = 0
        for n in (2, 3):
            if len(base) < n:
                continue
            for idx in range(0, len(base) - n + 1):
                _append_unique(out, base[idx : idx + n])
                used += 1
                if used >= max_grams:
                    break
            if used >= max_grams:
                break
    return out


def extract_keyword_terms(keyword: str, *, max_terms: int = 16) -> List[str]:
    raw = str(keyword or "").strip().lower()
    if not raw:
        return []

    out: List[str] = []
    _append_unique(out, raw)

    normalized = re.sub(r"[？?]+$", "", raw).strip()
    _append_unique(out, normalized)
    trimmed = re.sub(r"[了啊呀嘛吧呢吗么]+$", "", normalized).strip()
    _append_unique(out, trimmed)

    chunks = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", raw)
    for chunk in chunks:
        token = str(chunk or "").strip().lower()
        if len(token) < 2:
            continue
        _append_unique(out, token)
        if _is_cjk_token(token):
            for ext in _expand_cjk_token(token):
                _append_unique(out, ext)

    # For compact CJK sentence-like queries, extract phrase prefix around event hints.
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{3,}", raw)
    for chunk in cjk_chunks[:2]:
        for hint in _CJK_EVENT_HINTS:
            pos = chunk.find(hint)
            if pos > 0:
                prefix = chunk[:pos].strip()
                _append_unique(out, prefix)
                _append_unique(out, f"{prefix}{hint}")

    if max_terms > 0:
        return out[: max(1, int(max_terms))]
    return out


def score_keyword_relevance(keyword: str, text: str) -> float:
    blob = str(text or "").lower()
    if not blob:
        return 0.0
    terms = extract_keyword_terms(keyword, max_terms=24)
    if not terms:
        return 0.0

    full = str(keyword or "").strip().lower()
    if full and full in blob:
        return 1.0

    # Scoring should prioritize stronger/longer terms and avoid being diluted
    # by many short CJK n-grams.
    unique_terms = list(dict.fromkeys(terms))
    unique_terms.sort(key=lambda x: len(str(x or "")), reverse=True)
    scoring_terms = unique_terms[:8]
    hit = sum(1 for t in scoring_terms if t in blob)
    token_score = float(hit) / float(max(1, len(scoring_terms)))

    kw_cjk = [t for t in terms if _is_cjk_token(t) and len(t) >= 2]
    txt_cjk = re.findall(r"[\u4e00-\u9fff]{2,}", blob)
    cjk_score = 0.0
    if kw_cjk and txt_cjk:
        main_kw = max(kw_cjk, key=len)
        if main_kw in blob:
            cjk_score = 1.0
        elif len(main_kw) >= 2:
            kw_grams = {main_kw[i : i + 2] for i in range(0, len(main_kw) - 1)}
            txt_grams = set()
            for row in txt_cjk:
                txt_grams.update({row[i : i + 2] for i in range(0, len(row) - 1)})
            if kw_grams and txt_grams:
                cjk_score = float(len(kw_grams & txt_grams)) / float(max(1, len(kw_grams)))
    return round(max(token_score, cjk_score), 4)
