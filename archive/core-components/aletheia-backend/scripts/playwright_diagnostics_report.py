#!/usr/bin/env python3
"""
Playwright platform diagnostics report.

Usage:
  python scripts/playwright_diagnostics_report.py --keyword gpt --headless
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.layer1_perception.agents.bilibili_agent import BilibiliAgent
from services.layer1_perception.agents.concurrent_manager import ConcurrentAgentManager
from services.layer1_perception.agents.douyin_agent import DouyinAgent
from services.layer1_perception.agents.xiaohongshu_agent import XiaohongshuAgent
from services.layer1_perception.agents.zhihu_agent import ZhihuAgent


SUPPORTED = {
    "bilibili": BilibiliAgent,
    "douyin": DouyinAgent,
    "xiaohongshu": XiaohongshuAgent,
    "zhihu": ZhihuAgent,
}


def _resolve_storage_state(platform: str, storage_state: Optional[str]) -> Optional[str]:
    if storage_state:
        return storage_state
    env_key = f"PLAYWRIGHT_STORAGE_STATE_{platform.upper()}"
    if os.getenv(env_key):
        return os.getenv(env_key)
    return os.getenv("PLAYWRIGHT_STORAGE_STATE")


async def run_probe(
    *,
    keyword: str,
    platforms: List[str],
    limit_per_platform: int,
    headless: bool,
    max_concurrent_agents: int,
    storage_state: Optional[str],
) -> Dict[str, Any]:
    manager = ConcurrentAgentManager(
        max_concurrent_agents=max(1, int(max_concurrent_agents)),
        enable_retry=True,
        max_retries=1,
    )
    selected = [p for p in platforms if p in SUPPORTED]
    storage_state_map: Dict[str, str] = {}
    try:
        for platform in selected:
            state = _resolve_storage_state(platform, storage_state)
            if state:
                storage_state_map[platform] = state
            await manager.register_platform(
                platform,
                SUPPORTED[platform],
                pool_size=max(1, int(max_concurrent_agents)),
                headless=headless,
                storage_state_path=state,
            )
        result = await manager.concurrent_search(
            platforms=selected,
            keyword=keyword,
            limit_per_platform=max(1, int(limit_per_platform)),
        )
        diagnostics = manager.last_platform_diagnostics
        reason_stats = Counter(
            str((diag or {}).get("reason_code") or "UNKNOWN")
            for diag in diagnostics.values()
        )
        total_items = sum(len(items or []) for items in result.values())
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "keyword": keyword,
            "platforms": selected,
            "total_items": total_items,
            "reason_stats": dict(reason_stats),
            "results": result,
            "diagnostics": diagnostics,
            "storage_state_map": storage_state_map,
        }
    finally:
        await manager.close_all()


def _to_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Playwright Agent Diagnostics Report",
        "",
        f"- Generated At: {payload.get('generated_at')}",
        f"- Keyword: `{payload.get('keyword')}`",
        f"- Platforms: {', '.join(payload.get('platforms') or [])}",
        f"- Total Items: {payload.get('total_items')}",
        "",
        "## Reason Stats",
    ]
    for reason, count in sorted((payload.get("reason_stats") or {}).items()):
        lines.append(f"- {reason}: {count}")
    lines.extend(
        [
            "",
            "## Platform Diagnostics",
            "",
            "| Platform | Reason Code | Suggested Action | Reason |",
            "|---|---|---|---|",
        ]
    )
    diagnostics = payload.get("diagnostics") or {}
    for platform in sorted(diagnostics.keys()):
        row = diagnostics.get(platform) or {}
        lines.append(
            "| {platform} | {reason_code} | {suggested_action} | {reason} |".format(
                platform=platform,
                reason_code=str(row.get("reason_code") or "UNKNOWN"),
                suggested_action=str(row.get("suggested_action") or "-"),
                reason=str(row.get("reason") or "-"),
            )
        )
    lines.append("")
    return "\n".join(lines)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate playwright diagnostics report.")
    parser.add_argument("--keyword", default="gpt")
    parser.add_argument("--platforms", nargs="*", default=["bilibili", "zhihu", "douyin", "xiaohongshu"])
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-concurrent-agents", type=int, default=1)
    parser.add_argument("--storage-state", default=None)
    parser.add_argument("--json-out", default="../playwright-diagnostics-report.json")
    parser.add_argument("--md-out", default="../playwright-diagnostics-report.md")
    args = parser.parse_args()

    payload = await run_probe(
        keyword=str(args.keyword).strip(),
        platforms=list(args.platforms or []),
        limit_per_platform=max(1, int(args.limit)),
        headless=bool(args.headless),
        max_concurrent_agents=max(1, int(args.max_concurrent_agents)),
        storage_state=args.storage_state,
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
