#!/usr/bin/env python3
"""
Playwright rendered-page extraction template.

Two-stage strategy:
1) Render stage: navigate + wait + scroll + settle network/DOM.
2) Extract stage: visible text + HTML + schema fields + API JSON responses.

Usage:
  python scripts/playwright_rendered_extract_template.py \
    --url "https://example.com" \
    --critical-selector "main" \
    --schema '{"title":{"selector":"h1","mode":"text"}}' \
    --json-out ../playwright-rendered-extract.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow running this script directly from aletheia-backend/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.layer1_perception.agents.browser_agent import BrowserAgent


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
        return {"value": value}
    except Exception:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture fully-rendered page info, then extract fields and API JSON."
    )
    parser.add_argument("--url", required=True, help="Target URL")
    parser.add_argument(
        "--critical-selector",
        default="",
        help="Selector that must appear before extraction, e.g. '.result-item'",
    )
    parser.add_argument(
        "--schema",
        default="{}",
        help=(
            "JSON schema for field extraction. "
            "Example: "
            '\'{"title":{"selector":"h1","mode":"text"},'
            '"links":{"selector":"a","mode":"attr","attr":"href","many":true}}\''
        ),
    )
    parser.add_argument(
        "--api-url-keyword",
        default="",
        help="Only keep JSON responses whose URL contains this keyword",
    )
    parser.add_argument("--max-api-items", type=int, default=30)
    parser.add_argument("--visible-text-limit", type=int, default=18000)
    parser.add_argument("--html-limit", type=int, default=250000)
    parser.add_argument("--storage-state-path", default=None)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    schema = _safe_json_loads(args.schema) or {}
    if not isinstance(schema, dict):
        raise ValueError("--schema must be a JSON object")

    async with BrowserAgent(
        headless=bool(args.headless),
        storage_state_path=args.storage_state_path,
    ) as agent:
        payload = await agent.capture_rendered_page(
            url=args.url,
            critical_selector=args.critical_selector or None,
            schema=schema,
            api_url_keyword=args.api_url_keyword,
            max_api_items=max(1, int(args.max_api_items)),
            visible_text_limit=max(1000, int(args.visible_text_limit)),
            html_limit=max(10000, int(args.html_limit)),
        )

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[OK] wrote {args.json_out}")
    else:
        print(text)


if __name__ == "__main__":
    asyncio.run(main())
