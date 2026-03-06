#!/usr/bin/env python3
"""
Generate health report for Chinese core evidence chain only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from scripts.source_health_report import run_probe, _to_markdown


DEFAULT_PLATFORMS = [
    "rss_pool",
    "weibo",
    "zhihu",
    "xinhua",
    "peoples_daily",
    "china_gov",
    "samr",
    "csrc",
    "nhc",
]


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate ZH-core source health report.")
    parser.add_argument("--keyword", default="苏炳添 退役")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated core platforms",
    )
    parser.add_argument("--json-out", default="docs/source-health-report-zh-core.json")
    parser.add_argument("--md-out", default="docs/source-health-report-zh-core.md")
    args = parser.parse_args()

    platforms = [p.strip() for p in str(args.platforms or "").split(",") if p.strip()]
    payload = await run_probe(
        keyword=str(args.keyword).strip(),
        rounds=max(1, int(args.rounds)),
        limit_per_platform=max(1, int(args.limit)),
        platforms=platforms or DEFAULT_PLATFORMS,
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
