import json
from pathlib import Path

from services.source_tier_config import SourceTierConfig


def _write_config(tmp_path: Path) -> str:
    cfg = {
        "version": 1,
        "updated_at": "2026-03-03T00:00:00Z",
        "tiers": {
            "1": {"name": "Tier1", "trust_score": 0.95, "rules": ["official"]},
            "2": {"name": "Tier2", "trust_score": 0.75, "rules": ["mainstream"]},
            "3": {"name": "Tier3", "trust_score": 0.35, "rules": ["ugc"]},
        },
        "entries": [
            {"pattern": "news.cn", "match": "suffix", "tier": 1},
            {"pattern": "example.com", "match": "exact", "tier": 2, "rules": ["custom"]},
        ],
    }
    path = tmp_path / "source_tier_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


def test_resolve_suffix_match(tmp_path: Path):
    path = _write_config(tmp_path)
    resolver = SourceTierConfig(config_path=path, refresh_sec=0.0)
    result = resolver.resolve("https://www.news.cn/test")
    assert result.tier == 1
    assert result.match_type == "suffix"
    assert result.matched_pattern == "news.cn"


def test_resolve_exact_match(tmp_path: Path):
    path = _write_config(tmp_path)
    resolver = SourceTierConfig(config_path=path, refresh_sec=0.0)
    result = resolver.resolve("example.com")
    assert result.tier == 2
    assert "custom" in result.rules


def test_fallback_to_tier3(tmp_path: Path):
    path = _write_config(tmp_path)
    resolver = SourceTierConfig(config_path=path, refresh_sec=0.0)
    result = resolver.resolve("unknown-domain.xyz")
    assert result.tier == 3
    assert result.match_type == "fallback"
