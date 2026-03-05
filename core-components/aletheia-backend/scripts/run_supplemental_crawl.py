"""
运行资讯补量爬虫（主链路 + 补充链路），并输出 JSON/Markdown 报告。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from services.supplement_crawler import SupplementCrawlerService


def _parse_platforms(raw: str) -> List[str]:
    return [x.strip() for x in str(raw or "").split(",") if x.strip()]


def _to_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 资讯补量抓取报告")
    lines.append("")
    lines.append(f"- keyword: `{report.get('keyword')}`")
    lines.append(
        f"- promoted/target: `{report.get('promoted_items')}/{report.get('target_evidence')}`"
    )
    lines.append(f"- total_items: `{report.get('total_items')}`")
    lines.append(f"- rounds_executed: `{report.get('rounds_executed')}`")
    lines.append(f"- coverage_reached: `{report.get('coverage_reached')}`")
    lines.append("")
    lines.append("## 平台尝试明细")
    lines.append("")
    lines.append("| round | platform | status | reason_code | items | promoted | elapsed_ms | modes |")
    lines.append("|---:|---|---|---|---:|---:|---:|---|")
    for row in list(report.get("platform_attempts") or []):
        lines.append(
            "| {round} | {platform} | {status} | {reason_code} | {items_collected} | "
            "{promoted_items} | {elapsed_ms} | {modes} |".format(
                round=int(row.get("round") or 0),
                platform=str(row.get("platform") or ""),
                status=str(row.get("status") or ""),
                reason_code=str(row.get("reason_code") or ""),
                items_collected=int(row.get("items_collected") or 0),
                promoted_items=int(row.get("promoted_items") or 0),
                elapsed_ms=int(row.get("elapsed_ms") or 0),
                modes=",".join(list(row.get("retrieval_modes") or [])),
            )
        )
    return "\n".join(lines).strip() + "\n"


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    service = SupplementCrawlerService()
    return await service.run(
        keyword=args.keyword,
        target_evidence=args.target_evidence,
        rounds=args.rounds,
        limit_per_platform=args.limit_per_platform,
        primary_platforms=_parse_platforms(args.primary_platforms),
        supplement_platforms=_parse_platforms(args.supplement_platforms),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run supplemental crawler")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--target-evidence", type=int, default=12, help="目标证据条数")
    parser.add_argument("--rounds", type=int, default=3, help="最大轮次")
    parser.add_argument("--limit-per-platform", type=int, default=20, help="每平台抓取上限")
    parser.add_argument(
        "--primary-platforms",
        default="",
        help="主链路平台列表（逗号分隔），为空则走默认",
    )
    parser.add_argument(
        "--supplement-platforms",
        default="",
        help="补充链路平台列表（逗号分隔），为空则走默认",
    )
    parser.add_argument(
        "--output-prefix",
        default="docs/supplement-crawl-report",
        help="输出文件前缀（默认 docs/supplement-crawl-report）",
    )
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.parent / f"{prefix.name}-{ts}.json"
    md_path = prefix.parent / f"{prefix.name}-{ts}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(_to_markdown(report), encoding="utf-8")

    print(f"json: {json_path}")
    print(f"md:   {md_path}")
    print(
        "summary: promoted={promoted} total={total} rounds={rounds} reached={reached}".format(
            promoted=int(report.get("promoted_items") or 0),
            total=int(report.get("total_items") or 0),
            rounds=int(report.get("rounds_executed") or 0),
            reached=bool(report.get("coverage_reached")),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
