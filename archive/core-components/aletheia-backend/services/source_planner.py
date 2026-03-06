"""
Investigation source planner.
根据主张语义自动选择更相关的数据源，避免固定平台池导致噪声放大。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    low = _normalize(text)
    return any(k in low for k in keywords)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _infer_event_type_and_domain(claim: str, keyword: str) -> Dict[str, Any]:
    text = f"{claim or ''} {keyword or ''}".strip()
    locale = "cn" if _contains_cjk(text) else "global"
    rules: List[Tuple[str, str, List[str]]] = [
        (
            "sports_person",
            "sports_person_status",
            [
                "退役",
                "复出",
                "夺冠",
                "禁赛",
                "athlete",
                "olympic",
                "football",
                "nba",
                "world athletics",
                "track and field",
            ],
        ),
        (
            "public_health",
            "public_health_alert",
            [
                "疫情",
                "病例",
                "感染",
                "死亡",
                "病毒",
                "公共卫生",
                "卫生",
                "global health",
                "pandemic",
                "who",
                "cdc",
                "outbreak",
                "disease",
                "health emergency",
            ],
        ),
        (
            "regulatory_finance",
            "regulatory_action",
            [
                "监管",
                "证监",
                "罚款",
                "财报",
                "ipo",
                "sec",
                "acquisition",
                "earnings",
                "policy",
                "sanction",
                "并购",
                "处罚",
            ],
        ),
        (
            "geopolitics",
            "geopolitical_event",
            [
                "战争",
                "停火",
                "边境",
                "冲突",
                "un",
                "security council",
                "外交",
                "制裁",
            ],
        ),
    ]
    low = _normalize(text)
    for domain, event_type, keywords in rules:
        matched = [k for k in keywords if k in low]
        if matched:
            return {
                "event_type": event_type,
                "domain": domain,
                "domain_keywords": matched[:8],
                "locale": locale,
            }
    return {
        "event_type": "generic_claim",
        "domain": "general_news",
        "domain_keywords": [],
        "locale": locale,
    }


DOMAIN_RULES: Dict[str, Dict[str, List[str]]] = {
    "sports_person": {
        "must": ["xinhua", "news", "weibo"],
        "candidate": [
            "samr",
            "csrc",
            "nhc",
            "mps",
            "mem",
            "the_paper",
            "caixin",
            "zhihu",
            "xiaohongshu",
            "douyin",
            "bilibili",
            "reuters",
            "bbc",
            "guardian",
            "ap_news",
        ],
        "exclude": ["who", "un_news", "sec", "cdc", "samr", "csrc", "fca_uk"],
    },
    "public_health": {
        "must": ["who", "cdc", "nhc", "un_news", "xinhua"],
        "candidate": ["bbc", "guardian", "ap_news", "news", "reuters"],
        "exclude": ["sec", "csrc", "samr", "fca_uk", "weibo", "douyin", "xiaohongshu"],
    },
    "regulatory_finance": {
        "must": ["sec", "csrc", "samr", "xinhua", "caixin"],
        "candidate": ["fca_uk", "reuters", "bbc", "guardian", "ap_news", "news", "the_paper"],
        "exclude": ["who", "un_news", "cdc"],
    },
    "geopolitics": {
        "must": ["un_news", "reuters", "ap_news", "bbc", "xinhua"],
        "candidate": ["guardian", "who", "news", "the_paper", "weibo"],
        "exclude": ["sec", "csrc", "samr"],
    },
    "general_news": {
        "must": ["xinhua", "reuters", "bbc", "un_news", "peoples_daily"],
        "candidate": [
            "guardian",
            "ap_news",
            "news",
            "rss_pool",
            "weibo",
            "zhihu",
            "xiaohongshu",
            "douyin",
        ],
        "exclude": [],
    },
}

OFFICIAL_PLATFORMS = {
    "xinhua",
    "peoples_daily",
    "news",
    "who",
    "cdc",
    "nhc",
    "un_news",
    "sec",
    "csrc",
    "samr",
    "fca_uk",
    "mem",
    "mps",
    "supreme_court",
    "supreme_procuratorate",
}

DOMAIN_OFFICIAL_FLOOR: Dict[str, List[str]] = {
    "sports_person": ["xinhua", "news", "peoples_daily"],
    "public_health": ["who", "nhc", "cdc", "un_news", "xinhua", "peoples_daily"],
    "regulatory_finance": ["sec", "csrc", "samr", "xinhua", "peoples_daily"],
    "geopolitics": ["un_news", "xinhua", "who", "news", "peoples_daily"],
    "general_news": ["xinhua", "un_news", "news", "peoples_daily"],
}

MIN_HEALTH_SCORE = 0.35


def _health_of(platform: str, health_snapshot: Dict[str, Any]) -> float:
    row = health_snapshot.get(platform) if isinstance(health_snapshot, dict) else None
    if not isinstance(row, dict):
        return 0.6
    try:
        return float(row.get("health_score") or 0.6)
    except Exception:
        return 0.6


DOMAIN_PLATFORM_AFFINITY: Dict[str, Dict[str, float]] = {
    "sports_person": {
        "xinhua": 0.94,
        "news": 0.9,
        "weibo": 0.9,
        "the_paper": 0.88,
        "caixin": 0.86,
        "csrc": 0.74,
        "samr": 0.72,
        "nhc": 0.68,
        "mps": 0.62,
        "mem": 0.62,
        "reuters": 0.8,
        "bbc": 0.76,
        "guardian": 0.74,
        "ap_news": 0.74,
        "zhihu": 0.58,
        "xiaohongshu": 0.54,
        "douyin": 0.52,
        "bilibili": 0.5,
    },
    "public_health": {
        "who": 1.0,
        "cdc": 0.96,
        "nhc": 0.95,
        "xinhua": 0.84,
        "news": 0.82,
        "reuters": 0.88,
        "bbc": 0.85,
        "guardian": 0.82,
        "ap_news": 0.82,
        "un_news": 0.8,
    },
    "regulatory_finance": {
        "sec": 1.0,
        "csrc": 0.96,
        "samr": 0.94,
        "fca_uk": 0.92,
        "caixin": 0.9,
        "reuters": 0.88,
        "bbc": 0.8,
        "guardian": 0.78,
        "xinhua": 0.82,
        "peoples_daily": 0.75,
    },
    "geopolitics": {
        "reuters": 0.92,
        "ap_news": 0.9,
        "bbc": 0.88,
        "guardian": 0.86,
        "un_news": 0.9,
        "xinhua": 0.84,
        "news": 0.8,
        "who": 0.75,
    },
    "general_news": {
        "reuters": 0.9,
        "bbc": 0.88,
        "xinhua": 0.86,
        "peoples_daily": 0.85,
        "guardian": 0.84,
        "ap_news": 0.82,
        "un_news": 0.79,
        "news": 0.78,
        "rss_pool": 0.6,
        "weibo": 0.76,
        "zhihu": 0.72,
        "xiaohongshu": 0.7,
        "douyin": 0.68,
    },
}


def _domain_affinity(platform: str, domain: str) -> float:
    table = DOMAIN_PLATFORM_AFFINITY.get(domain, {})
    return float(table.get(platform, 0.5))


def plan_sources(
    *,
    claim: str,
    keyword: str,
    available_platforms: List[str],
    platform_health_snapshot: Dict[str, Any] | None = None,
    platform_health_matrix: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del platform_health_matrix  # reserved for future weighting

    inferred = _infer_event_type_and_domain(claim=claim, keyword=keyword)
    domain = str(inferred["domain"])
    event_type = str(inferred["event_type"])
    domain_keywords = list(inferred.get("domain_keywords") or [])
    locale = str(inferred.get("locale") or "global")
    rules = DOMAIN_RULES.get(domain, DOMAIN_RULES["general_news"])

    available = list(dict.fromkeys([str(x) for x in (available_platforms or []) if x]))
    available_set = set(available)
    health_snapshot = platform_health_snapshot or {}

    must_raw = [p for p in rules["must"] if p in available_set]
    candidate_raw = [p for p in rules["candidate"] if p in available_set and p not in must_raw]
    excluded = [p for p in rules["exclude"] if p in available_set]

    must_sorted = sorted(
        must_raw,
        key=lambda p: (_health_of(p, health_snapshot), _domain_affinity(p, domain)),
        reverse=True,
    )
    candidate_sorted = sorted(
        candidate_raw,
        key=lambda p: (
            _health_of(p, health_snapshot) * 0.65 + _domain_affinity(p, domain) * 0.35,
            1 if p in excluded else 0,
        ),
        reverse=True,
    )

    healthy_must = [p for p in must_sorted if _health_of(p, health_snapshot) >= MIN_HEALTH_SCORE]
    unhealthy_must = [p for p in must_sorted if _health_of(p, health_snapshot) < MIN_HEALTH_SCORE]
    healthy_candidate = [
        p
        for p in candidate_sorted
        if _health_of(p, health_snapshot) >= MIN_HEALTH_SCORE and p not in excluded
    ]
    selected: List[str] = []
    for p in healthy_must + healthy_candidate:
        if p in excluded:
            continue
        if p not in selected:
            selected.append(p)

    # 保底：官方信源优先进入 selected，避免舆论源独占
    official_floor = [
        p
        for p in (DOMAIN_OFFICIAL_FLOOR.get(domain) or DOMAIN_OFFICIAL_FLOOR["general_news"])
        if p in available_set and p not in excluded
    ]
    selected_with_official: List[str] = []
    for p in official_floor + selected:
        if p not in selected_with_official:
            selected_with_official.append(p)
    if selected_with_official:
        selected = selected_with_official

    if not selected:
        selected = sorted(
            [p for p in available if p not in excluded],
            key=lambda p: _health_of(p, health_snapshot),
            reverse=True,
        )[:8]

    # 限制轮次复杂度，收敛平台池避免噪声放大
    selected = selected[:8]

    official_selected = [p for p in selected if p in OFFICIAL_PLATFORMS]
    official_floor_required = min(2, len(official_floor))
    forced_official = [p for p in official_floor if p in selected]
    if len(official_selected) < official_floor_required and official_floor:
        for p in official_floor:
            if p in selected:
                continue
            # 替换尾部非官方平台，优先保证官方源在执行池内
            replaced = False
            for idx in range(len(selected) - 1, -1, -1):
                cur = selected[idx]
                if cur not in OFFICIAL_PLATFORMS:
                    selected[idx] = p
                    replaced = True
                    break
            if not replaced and p not in selected and len(selected) < 8:
                selected.append(p)
            official_selected = [x for x in selected if x in OFFICIAL_PLATFORMS]
            if len(official_selected) >= official_floor_required:
                break

    missing_must = [p for p in rules["must"] if p not in available_set]
    risk_notes: List[str] = []
    if missing_must:
        risk_notes.append(f"MISSING_MUST_HAVE:{','.join(missing_must[:6])}")
    if unhealthy_must:
        risk_notes.append(f"UNHEALTHY_MUST_HAVE:{','.join(unhealthy_must[:6])}")
    if official_floor and len(official_selected) < official_floor_required:
        risk_notes.append(
            f"OFFICIAL_FLOOR_NOT_MET:{len(official_selected)}/{official_floor_required}"
        )
    low_health_official = [
        p for p in official_selected if _health_of(p, health_snapshot) < MIN_HEALTH_SCORE
    ]
    if low_health_official:
        risk_notes.append(f"LOW_HEALTH_OFFICIAL_SELECTED:{','.join(low_health_official[:6])}")

    selection_reasons = [
        f"event_type={event_type}",
        f"domain={domain}",
        f"locale={locale}",
        f"domain_keywords={','.join(domain_keywords) if domain_keywords else 'none'}",
        f"must_have_count={len(healthy_must)}",
        f"candidate_count={len(healthy_candidate)}",
        f"official_floor_available={len(official_floor)}",
        f"official_selected={len(official_selected)}",
        f"min_health={MIN_HEALTH_SCORE}",
        f"excluded_count={len(excluded)}",
    ]
    selected_health = [_health_of(p, health_snapshot) for p in selected]
    mean_health = sum(selected_health) / max(1, len(selected_health))
    must_coverage = len(healthy_must) / max(1, len(rules.get("must") or []))
    confidence = 0.35 + (0.4 * must_coverage) + (0.25 * mean_health)
    if missing_must:
        confidence -= 0.12
    if unhealthy_must:
        confidence -= 0.08
    selection_confidence = round(max(0.0, min(1.0, confidence)), 4)

    return {
        "event_type": event_type,
        "domain": domain,
        "domain_keywords": domain_keywords,
        "plan_version": "auto_v2_precision",
        "selection_confidence": selection_confidence,
        "must_have_platforms": healthy_must,
        "candidate_platforms": candidate_sorted,
        "excluded_platforms": excluded,
        "selected_platforms": selected,
        "official_floor_platforms": official_floor,
        "official_selected_platforms": official_selected,
        "official_selected_count": len(official_selected),
        "selection_reasons": selection_reasons,
        "risk_notes": risk_notes,
    }
