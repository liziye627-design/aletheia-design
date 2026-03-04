#!/usr/bin/env python3
"""
Audit RSS sources for keyword-search usability.

This script does NOT assume native search support from source sites.
It checks whether recent feed items contain query anchors.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import feedparser
import httpx
import yaml


def _tokens(text: str) -> List[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", str(text or "").lower())
        if t
    ]


def _score(query: str, text: str) -> float:
    q = str(query or "").strip().lower()
    blob = str(text or "").lower()
    if not q or not blob:
        return 0.0
    if q in blob:
        return 1.0
    qt = set(_tokens(q))
    bt = set(_tokens(blob))
    if not qt or not bt:
        return 0.0
    return len(qt & bt) / max(1, len(qt))


def _flatten_sources(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for group in list(data.get("groups") or []):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "")
        group_name = str(group.get("name") or group_id or "group")
        for src in list(group.get("sources") or []):
            if not isinstance(src, dict):
                continue
            row = dict(src)
            row["_group_id"] = group_id
            row["_group_name"] = group_name
            out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RSS source searchability")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        default=[],
        help="Query to test (repeatable)",
    )
    parser.add_argument("--max-sources", type=int, default=0)
    parser.add_argument("--max-entries", type=int, default=30)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument(
        "--out-json",
        default="docs/rss_searchability_report.json",
    )
    parser.add_argument(
        "--out-md",
        default="docs/rss_searchability_report.md",
    )
    args = parser.parse_args()

    queries = [q.strip() for q in args.queries if q and q.strip()]
    if not queries:
        queries = ["苏炳添 退役", "OpenAI", "全国两会"]

    src_path = Path(args.sources)
    if not src_path.exists():
        raise SystemExit(f"sources file not found: {src_path}")
    data = yaml.safe_load(src_path.read_text(encoding="utf-8")) or {}
    sources = [
        s
        for s in _flatten_sources(data)
        if bool(s.get("enabled", True))
        and str(s.get("type") or "rss").strip().lower() in {"rss", "atom"}
        and str(s.get("url") or "").strip()
    ]
    if args.max_sources > 0:
        sources = sources[: max(1, args.max_sources)]

    results: List[Dict[str, Any]] = []
    timeout = httpx.Timeout(args.timeout, connect=min(3.0, args.timeout))
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for src in sources:
            url = str(src.get("url") or "").strip()
            row: Dict[str, Any] = {
                "source_id": str(src.get("source_id") or ""),
                "name": str(src.get("name") or ""),
                "url": url,
                "group": str(src.get("_group_name") or ""),
                "category": str(src.get("category") or ""),
                "ok": False,
                "error": "",
                "entries": 0,
                "query_hits": {},
                "searchable": False,
            }
            try:
                r = client.get(url)
                if int(r.status_code) >= 400:
                    row["error"] = f"HTTP_{int(r.status_code)}"
                    results.append(row)
                    continue
                feed = feedparser.parse(r.text or "")
                entries = list(getattr(feed, "entries", []) or [])[: max(1, args.max_entries)]
                row["ok"] = True
                row["entries"] = len(entries)
                searchable = False
                for q in queries:
                    hits = 0
                    best = 0.0
                    for e in entries:
                        blob = "\n".join(
                            [
                                str(e.get("title") or ""),
                                str(e.get("summary") or ""),
                                str(e.get("description") or ""),
                            ]
                        )
                        s = _score(q, blob)
                        if s >= args.threshold:
                            hits += 1
                        if s > best:
                            best = s
                    row["query_hits"][q] = {"hits": hits, "best_score": round(best, 4)}
                    if hits > 0:
                        searchable = True
                row["searchable"] = searchable
                results.append(row)
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                results.append(row)

    searchable_rows = [r for r in results if r.get("searchable")]
    failed_rows = [r for r in results if not r.get("ok")]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "threshold": args.threshold,
        "sources_total": len(results),
        "sources_ok": len([r for r in results if r.get("ok")]),
        "sources_failed": len(failed_rows),
        "sources_searchable": len(searchable_rows),
    }
    out = {"summary": summary, "results": results}

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md = Path(args.out_md)
    lines = [
        "# RSS Searchability Report",
        "",
        f"- Generated: `{summary['generated_at']}`",
        f"- Queries: `{', '.join(queries)}`",
        f"- Threshold: `{args.threshold}`",
        f"- Total: `{summary['sources_total']}`",
        f"- OK: `{summary['sources_ok']}`",
        f"- Failed: `{summary['sources_failed']}`",
        f"- Searchable: `{summary['sources_searchable']}`",
        "",
        "## Keep (searchable)",
        "",
    ]
    for r in searchable_rows:
        lines.append(
            f"- `{r['source_id']}` | {r['name']} | entries={r['entries']} | {r['url']}"
        )
    lines.extend(["", "## Drop/Review", ""])
    for r in results:
        if r.get("searchable"):
            continue
        reason = r.get("error") or "NO_QUERY_HIT"
        lines.append(
            f"- `{r['source_id']}` | {r['name']} | reason={reason} | {r['url']}"
        )
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
