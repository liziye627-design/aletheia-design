#!/usr/bin/env python3
"""
Build trusted platform whitelist from source-health report.

Usage:
  PYTHONPATH=. ./venv/bin/python scripts/build_trusted_platforms_from_health.py \
      --in docs/source-health-report-strict.json \
      --out config/trusted_platforms.auto.json \
      --min-success 0.34 \
      --require-items
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _pick_platforms(
    payload: Dict[str, Any],
    min_success: float,
    require_items: bool,
    seed: List[str],
) -> List[str]:
    probe = payload.get("probe") if isinstance(payload.get("probe"), dict) else {}
    rows: List[str] = []
    seed_set = set(seed or [])
    for platform, row in probe.items():
        if not isinstance(row, dict):
            continue
        if seed_set and str(platform) not in seed_set:
            continue
        rounds = max(1, int(row.get("rounds") or 1))
        success = int(row.get("evidence_success_rounds") or row.get("success_rounds") or 0)
        items = int(row.get("evidence_items") or row.get("items_collected") or 0)
        rate = float(success) / float(rounds)
        if rate < min_success:
            continue
        if require_items and items <= 0:
            continue
        rows.append(str(platform))
    return sorted(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build trusted platforms from health report")
    parser.add_argument("--in", dest="input_path", required=True)
    parser.add_argument("--out", dest="output_path", required=True)
    parser.add_argument("--min-success", type=float, default=0.34)
    parser.add_argument("--require-items", action="store_true")
    parser.add_argument(
        "--seed",
        default=(
            "rss_pool,weibo,zhihu,xinhua,peoples_daily,china_gov,samr,csrc,nhc,"
            "who,un_news,reuters,bbc,guardian,ap_news,the_paper,caixin,sec"
        ),
    )
    args = parser.parse_args()

    src = Path(args.input_path)
    payload = json.loads(src.read_text(encoding="utf-8"))
    seed = [x.strip() for x in str(args.seed).split(",") if x.strip()]
    platforms = _pick_platforms(
        payload=payload,
        min_success=max(0.0, min(1.0, float(args.min_success))),
        require_items=bool(args.require_items),
        seed=seed,
    )
    out_payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "input_report": str(src),
        "min_success": float(args.min_success),
        "require_items": bool(args.require_items),
        "seed": seed,
        "trusted_platforms": platforms,
        "env_value": ",".join(platforms),
    }
    out = Path(args.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")
    print(f"env: INVESTIGATION_TRUSTED_PLATFORMS={out_payload['env_value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
