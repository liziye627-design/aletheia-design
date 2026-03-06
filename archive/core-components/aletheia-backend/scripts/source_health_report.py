#!/usr/bin/env python3
"""
Source health diagnostics for investigation crawlers.

Usage:
  python scripts/source_health_report.py --keyword gpt --rounds 3 --limit 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from services.layer1_perception.crawler_manager import get_crawler_manager


def _percentile(samples: List[int], pct: float) -> int:
    if not samples:
        return 0
    rows = sorted(samples)
    idx = min(len(rows) - 1, int(len(rows) * pct))
    return int(rows[idx])


def _keyword_tokens(text: str) -> List[str]:
    rows = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", str(text or "").lower())
    out: List[str] = []
    for row in rows:
        token = str(row or "").strip()
        if len(token) < 2:
            continue
        if token not in out:
            out.append(token)
    return out


def _entity_tokens(text: str) -> List[str]:
    raw = str(text or "").strip().lower()
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


def _entity_hit(keyword: str, item: Dict[str, Any]) -> bool:
    entities = _entity_tokens(keyword)
    if not entities:
        return False
    blob = "\n".join(
        [
            str(item.get("title") or ""),
            str(item.get("content") or ""),
            str(item.get("summary") or ""),
            str(item.get("snippet") or ""),
            str(item.get("content_text") or ""),
            str(item.get("url") or ""),
        ]
    ).lower()
    return any(ent in blob for ent in entities)


def _issue_category_and_hint(reason_code: str) -> tuple[str, str]:
    code = str(reason_code or "").upper()
    if code == "NO_EVIDENCE_MATCH":
        return (
            "relevance_scope",
            "平台返回了数据但未命中“关键词+实体”，优先启用本地索引检索或调整来源范围",
        )
    if code in {"MISSING_TOKEN", "PLATFORM_401", "PLATFORM_402", "PLATFORM_403"}:
        return ("credentials", "配置或刷新平台凭证（token/cookies），并验证权限")
    if code in {"DNS_ERROR", "TLS_TIMEOUT", "UNREACHABLE", "PROXY_UNREACHABLE"}:
        return ("network", "执行 network_preflight，修复 DNS/代理链路后重试")
    if code in {"CRAWLER_TIMEOUT", "FALLBACK_EMPTY"}:
        return ("timeout_or_source", "提高该平台预算/超时，或切换为本地索引优先")
    if code in {"HOT_FALLBACK", "WEB_FALLBACK", "RSS_EMERGENCY_FALLBACK"}:
        return ("degraded", "当前为降级结果，建议补充本地索引与主检索源")
    if code in {"OK", ""}:
        return ("healthy", "无需修复")
    return ("unknown", "检查平台实现日志与 reason_stats 进一步定位")


async def run_probe(
    keyword: str,
    rounds: int,
    limit_per_platform: int,
    platforms: List[str] | None = None,
) -> Dict[str, Any]:
    crawlers = get_crawler_manager()
    all_platforms = sorted(list(getattr(crawlers, "crawlers", {}).keys()))
    if platforms:
        selected = [p for p in platforms if p in all_platforms]
        platforms = sorted(list(dict.fromkeys(selected)))
    else:
        platforms = all_platforms
    source_matrix = (
        crawlers.get_platform_source_matrix()
        if hasattr(crawlers, "get_platform_source_matrix")
        else {}
    )

    round_rows: List[Dict[str, Dict[str, Any]]] = []
    for _ in range(max(1, rounds)):
        verbose = await crawlers.search_across_platforms_verbose(
            keyword=keyword,
            platforms=platforms,
            limit_per_platform=limit_per_platform,
        )
        round_rows.append(verbose)

    probe: Dict[str, Dict[str, Any]] = {}
    global_reason = Counter()
    platforms_with_data = 0
    total_items = 0
    for platform in platforms:
        reason_stats = Counter()
        elapsed = []
        total_platform_items = 0
        success_rounds = 0
        evidence_success_rounds = 0
        total_keyword_hit_items = 0
        total_entity_hit_items = 0
        total_evidence_items = 0
        latest_status = "unknown"
        for row in round_rows:
            data = (row or {}).get(platform) or {}
            reason = str(data.get("reason_code") or "UNKNOWN")
            latest_status = str(data.get("status") or latest_status)
            elapsed.append(int(data.get("elapsed_ms") or 0))
            items = int(data.get("items_collected") or 0)
            total_platform_items += items
            reason_stats[reason] += 1
            if items > 0:
                success_rounds += 1
            row_items = list(data.get("items") or [])
            row_kw_hits = 0
            row_entity_hits = 0
            row_evidence_hits = 0
            for item in row_items:
                if not isinstance(item, dict):
                    continue
                meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                kw_hit = bool(meta.get("keyword_match"))
                ent_hit = _entity_hit(keyword=keyword, item=item)
                if kw_hit:
                    row_kw_hits += 1
                if ent_hit:
                    row_entity_hits += 1
                if kw_hit and ent_hit:
                    row_evidence_hits += 1
            total_keyword_hit_items += row_kw_hits
            total_entity_hit_items += row_entity_hits
            total_evidence_items += row_evidence_hits
            if row_evidence_hits > 0:
                evidence_success_rounds += 1
        top_reason = reason_stats.most_common(1)[0][0] if reason_stats else "UNKNOWN"
        if total_platform_items > 0 and total_evidence_items <= 0:
            top_reason = "NO_EVIDENCE_MATCH"
        evidence_success_rate = float(evidence_success_rounds) / float(max(1, rounds))
        final_status = "ok" if evidence_success_rounds > 0 else (
            "degraded" if total_platform_items > 0 else latest_status
        )
        if total_evidence_items > 0:
            platforms_with_data += 1
        total_items += total_evidence_items
        global_reason[top_reason] += 1
        issue_category, action_hint = _issue_category_and_hint(top_reason)
        probe[platform] = {
            "status": final_status,
            "reason_code": top_reason,
            "issue_category": issue_category,
            "action_hint": action_hint,
            "reason_stats": dict(reason_stats),
            "success_rounds": int(success_rounds),
            "evidence_success_rounds": int(evidence_success_rounds),
            "evidence_success_rate": round(float(evidence_success_rate), 4),
            "rounds": int(rounds),
            "items_collected": int(total_platform_items),
            "keyword_hit_items": int(total_keyword_hit_items),
            "entity_hit_items": int(total_entity_hit_items),
            "evidence_items": int(total_evidence_items),
            "elapsed_ms_p50": _percentile(elapsed, 0.50),
            "elapsed_ms_p95": _percentile(elapsed, 0.95),
            "source": source_matrix.get(platform, {}),
        }

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "keyword": keyword,
        "rounds": rounds,
        "limit_per_platform": limit_per_platform,
        "platform_count": len(platforms),
        "platforms_with_data": platforms_with_data,
        "total_items": total_items,
        "reason_stats": dict(global_reason),
        "probe": probe,
    }


def _to_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Source Health Report",
        "",
        f"- Generated At: {payload.get('generated_at')}",
        f"- Keyword: `{payload.get('keyword')}`",
        f"- Rounds: {payload.get('rounds')}",
        f"- Platforms With Data: {payload.get('platforms_with_data')}/{payload.get('platform_count')}",
        f"- Total Evidence Items: {payload.get('total_items')}",
        "",
        "## Reason Stats",
    ]
    for reason, count in sorted((payload.get("reason_stats") or {}).items()):
        lines.append(f"- {reason}: {count}")
    lines.append("")
    lines.append("## Platform Matrix")
    lines.append("")
    lines.append("| Platform | Pool | Status | Reason | Category | EvdRate | Evidence | KeywordHit | EntityHit | Items | P50 | P95 | Primary URL | Hint |")
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
    probe = payload.get("probe") or {}
    for platform in sorted(probe.keys()):
        row = probe.get(platform) or {}
        source = row.get("source") or {}
        lines.append(
            "| {platform} | {pool} | {status} | {reason} | {category} | {evdrate:.2f} | {evidence} | {kwhit} | {enthit} | {items} | {p50} | {p95} | {url} | {hint} |".format(
                platform=platform,
                pool=str(source.get("profile_pool") or "-"),
                status=str(row.get("status") or "-"),
                reason=str(row.get("reason_code") or "-"),
                category=str(row.get("issue_category") or "-"),
                evdrate=float(row.get("evidence_success_rate") or 0.0),
                evidence=int(row.get("evidence_items") or 0),
                kwhit=int(row.get("keyword_hit_items") or 0),
                enthit=int(row.get("entity_hit_items") or 0),
                items=int(row.get("items_collected") or 0),
                p50=int(row.get("elapsed_ms_p50") or 0),
                p95=int(row.get("elapsed_ms_p95") or 0),
                url=str(source.get("primary_url") or "-"),
                hint=str(row.get("action_hint") or "-"),
            )
        )
    lines.append("")
    return "\n".join(lines)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate crawler source health report.")
    parser.add_argument("--keyword", default="gpt")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--platforms",
        default="",
        help="Comma-separated platform names. Empty = all.",
    )
    parser.add_argument("--json-out", default="../source-health-report.json")
    parser.add_argument("--md-out", default="../source-health-report.md")
    args = parser.parse_args()
    selected_platforms = [
        p.strip()
        for p in str(args.platforms or "").split(",")
        if p.strip()
    ]

    payload = await run_probe(
        keyword=str(args.keyword).strip(),
        rounds=max(1, int(args.rounds)),
        limit_per_platform=max(1, int(args.limit)),
        platforms=selected_platforms or None,
    )
    json_out = Path(args.json_out)
    md_out = Path(args.md_out)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_to_markdown(payload), encoding="utf-8")
    print(f"saved: {json_out}")
    print(f"saved: {md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
