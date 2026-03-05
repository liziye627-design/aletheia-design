"""Run RSS auto-expansion and write discovered sources file."""

from __future__ import annotations

import argparse
import asyncio

from services.rss_autoexpand import run_autoexpand
from services.rss_sources_config import get_rss_sources_registry
from core.config import settings


async def _run(config_path: str) -> None:
    registry = get_rss_sources_registry()
    existing = registry.get_rss_urls() if registry else []
    result = await run_autoexpand(config_path, existing_urls=existing)
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        default=str(getattr(settings, "RSS_AUTOEXPAND_CONFIG_PATH", "config/autoexpand.yaml")),
    )
    args = parser.parse_args()
    asyncio.run(_run(args.config))


if __name__ == "__main__":
    main()
