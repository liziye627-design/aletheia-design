#!/usr/bin/env python3
"""
Build a production-ready RSS source list from searchability audit report.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _flatten_sources(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for group in list(data.get("groups") or []):
        if not isinstance(group, dict):
            continue
        gid = str(group.get("group_id") or "")
        gname = str(group.get("name") or gid)
        for src in list(group.get("sources") or []):
            if not isinstance(src, dict):
                continue
            row = dict(src)
            row["_group_id"] = gid
            row["_group_name"] = gname
            out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build searchable RSS source config")
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--audit", default="docs/rss_searchability_report.json")
    parser.add_argument("--out", default="config/sources.searchable.yaml")
    parser.add_argument("--min-hits", type=int, default=1)
    parser.add_argument("--max-priority", type=int, default=7)
    args = parser.parse_args()

    src_data = _load_yaml(Path(args.sources))
    audit_data = _load_yaml(Path(args.audit))
    src_rows = _flatten_sources(src_data)
    audit_rows = list(audit_data.get("results") or [])

    kept_ids: set[str] = set()
    for row in audit_rows:
        if not isinstance(row, dict):
            continue
        if not row.get("ok"):
            continue
        sid = str(row.get("source_id") or "")
        if not sid:
            continue
        hit_total = 0
        qh = row.get("query_hits") or {}
        if isinstance(qh, dict):
            for v in qh.values():
                if isinstance(v, dict):
                    hit_total += int(v.get("hits") or 0)
        searchable = bool(row.get("searchable")) or hit_total >= args.min_hits
        if searchable:
            kept_ids.add(sid)

    group_map: Dict[str, Dict[str, Any]] = {}
    for src in src_rows:
        sid = str(src.get("source_id") or "")
        if sid not in kept_ids:
            continue
        prio = int(src.get("priority") or 5)
        if prio > int(args.max_priority):
            continue
        gid = str(src.get("_group_id") or "searchable")
        gname = str(src.get("_group_name") or gid)
        grp = group_map.setdefault(gid, {"group_id": gid, "name": gname, "sources": []})
        clean = {k: v for k, v in src.items() if not str(k).startswith("_")}
        grp["sources"].append(clean)

    out = {
        "version": 1,
        "defaults": src_data.get("defaults") or {},
        "groups": list(group_map.values()),
        "meta": {
            "generated_from_audit": args.audit,
            "source_count": sum(len(g.get("sources") or []) for g in group_map.values()),
        },
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"generated: {out_path} sources={out['meta']['source_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
