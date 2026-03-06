"""RSS auto-expansion: discover candidate feeds, validate, score, and emit sources YAML."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import feedparser
import httpx

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from dateutil import parser as date_parser
except Exception:  # pragma: no cover
    date_parser = None


logger = logging.getLogger("rss_autoexpand")


_DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "enabled": False,
    "seeds": {
        "directory_pages": [],
        "opml_urls": [],
        "site_homepages": [],
    },
    "discovery": {
        "rel_alternate": True,
        "guess_paths": ["/rss", "/feed", "/rss.xml", "/atom.xml", "/index.xml", "/feed.xml"],
        "max_candidates_per_page": 50,
    },
    "validation": {
        "min_entries": 5,
        "require_title_link": True,
        "recent_days": 7,
    },
    "scoring": {
        "min_quality_score": 70,
        "weights": {
            "parse_success": 25,
            "freshness": 20,
            "duplication_penalty": 15,
            "source_authority": 20,
            "risk_friendly": 20,
        },
        "authority_domains": [],
    },
    "output": {
        "path": "config/sources.auto.yaml",
        "mode_default": "rss_only",
        "comment_policy_default": "try_public",
    },
}


@dataclass
class FeedValidation:
    ok: bool
    url: str
    entry_count: int
    unique_links: int
    latest_published_at: Optional[datetime]
    error: Optional[str] = None
    score: float = 0.0


@dataclass
class CandidateFeed:
    url: str
    source_page: Optional[str] = None
    title: Optional[str] = None


def _normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme:
        return raw
    netloc = parsed.hostname or ""
    return parsed._replace(netloc=netloc.lower()).geturl()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "rss"


def _hash_id(value: str, size: int = 8) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()[:size]


def _parse_datetime(text: str) -> Optional[datetime]:
    if not text:
        return None
    if date_parser is None:
        return None
    try:
        dt = date_parser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _read_config(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path) or yaml is None:
        return dict(_DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            return dict(_DEFAULT_CONFIG)
        merged = dict(_DEFAULT_CONFIG)
        merged.update(data)
        for key, value in _DEFAULT_CONFIG.items():
            if isinstance(value, dict):
                merged[key] = {**value, **(data.get(key) or {})}
        return merged
    except Exception as exc:
        logger.warning("rss_autoexpand: failed to load %s: %s", path, exc)
        return dict(_DEFAULT_CONFIG)


async def _fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 3,
    timeout: float = 10.0,
) -> Tuple[Optional[str], Optional[int]]:
    for attempt in range(retries):
        try:
            resp = await client.get(url, timeout=timeout, follow_redirects=True)
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError("bad status", request=resp.request, response=resp)
            return resp.text, resp.status_code
        except Exception as exc:
            if attempt >= retries - 1:
                logger.warning("rss_autoexpand: fetch failed %s: %s", url, type(exc).__name__)
                return None, None
            await asyncio.sleep(0.5 * (2 ** attempt))
    return None, None


def _extract_links_from_html(html: str, base_url: str) -> List[str]:
    if not html:
        return []
    links: List[str] = []
    if BeautifulSoup is None:
        return links
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["link", "a"]):
        href = tag.get("href") or ""
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        links.append(abs_url)
    return links


def _extract_rel_alternate(html: str, base_url: str) -> List[str]:
    if not html or BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: List[str] = []
    for tag in soup.find_all("link"):
        rel = " ".join(tag.get("rel") or []).lower()
        if "alternate" not in rel:
            continue
        type_attr = (tag.get("type") or "").lower()
        if "rss" not in type_attr and "atom" not in type_attr and "xml" not in type_attr:
            continue
        href = tag.get("href") or ""
        if not href:
            continue
        out.append(urljoin(base_url, href))
    return out


def _extract_opml_urls(xml_text: str, base_url: str) -> List[str]:
    if not xml_text:
        return []
    urls = re.findall(r"xmlUrl=\"([^\"]+)\"", xml_text)
    return [urljoin(base_url, url) for url in urls]


def _guess_feed_urls(base_url: str, guess_paths: Sequence[str]) -> List[str]:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return [urljoin(root, path) for path in guess_paths]


async def discover_candidate_feeds(
    client: httpx.AsyncClient,
    seed_url: str,
    *,
    config: Dict[str, Any],
) -> List[CandidateFeed]:
    html, _ = await _fetch_text(client, seed_url)
    if not html:
        return []
    candidates: List[str] = []
    discovery_cfg = config.get("discovery") or {}
    if discovery_cfg.get("rel_alternate", True):
        candidates.extend(_extract_rel_alternate(html, seed_url))
    candidates.extend(_extract_links_from_html(html, seed_url))
    candidates.extend(_guess_feed_urls(seed_url, discovery_cfg.get("guess_paths") or []))
    # OPML support
    if "<opml" in html.lower():
        candidates.extend(_extract_opml_urls(html, seed_url))

    normalized: List[str] = []
    for url in candidates:
        url = _normalize_url(url)
        if not url:
            continue
        if url not in normalized:
            normalized.append(url)

    max_candidates = int(discovery_cfg.get("max_candidates_per_page") or 50)
    out: List[CandidateFeed] = []
    for url in normalized[:max_candidates]:
        out.append(CandidateFeed(url=url, source_page=seed_url))
    return out


def _compute_score(
    validation: FeedValidation,
    *,
    config: Dict[str, Any],
) -> float:
    weights = (config.get("scoring") or {}).get("weights") or {}
    score = 0.0
    if validation.ok:
        score += float(weights.get("parse_success") or 0)
        if validation.latest_published_at is not None:
            recent_days = int((config.get("validation") or {}).get("recent_days") or 7)
            threshold = datetime.now(timezone.utc) - timedelta(days=recent_days)
            if validation.latest_published_at >= threshold:
                score += float(weights.get("freshness") or 0)
        if validation.entry_count > 0:
            dup_ratio = 1.0 - (validation.unique_links / max(1, validation.entry_count))
            score -= float(weights.get("duplication_penalty") or 0) * dup_ratio
        score += float(weights.get("risk_friendly") or 0)
        authority_domains = (config.get("scoring") or {}).get("authority_domains") or []
        parsed = urlparse(validation.url)
        if parsed.hostname and parsed.hostname in authority_domains:
            score += float(weights.get("source_authority") or 0)
    return max(0.0, score)


async def validate_feed(
    client: httpx.AsyncClient,
    url: str,
    config: Dict[str, Any],
) -> FeedValidation:
    validation_cfg = config.get("validation") or {}
    min_entries = int(validation_cfg.get("min_entries") or 5)
    require_title_link = bool(validation_cfg.get("require_title_link", True))

    text, _ = await _fetch_text(client, url)
    if not text:
        return FeedValidation(
            ok=False,
            url=url,
            entry_count=0,
            unique_links=0,
            latest_published_at=None,
            error="fetch_failed",
        )

    feed = feedparser.parse(text)
    entries = list(getattr(feed, "entries", []) or [])
    if getattr(feed, "bozo", False) and not entries:
        return FeedValidation(
            ok=False,
            url=url,
            entry_count=0,
            unique_links=0,
            latest_published_at=None,
            error="parse_failed",
        )
    if len(entries) < min_entries:
        return FeedValidation(
            ok=False,
            url=url,
            entry_count=len(entries),
            unique_links=0,
            latest_published_at=None,
            error="too_few_entries",
        )

    links: List[str] = []
    latest: Optional[datetime] = None
    for entry in entries:
        title = str(entry.get("title", "") or "").strip()
        link = str(entry.get("link", "") or "").strip()
        if require_title_link and (not title or not link):
            continue
        if link:
            links.append(link)
        published = _parse_datetime(str(entry.get("published", "") or entry.get("updated", "") or ""))
        if published and (latest is None or published > latest):
            latest = published

    unique_links = len(set(links))
    ok = unique_links >= min_entries
    validation = FeedValidation(
        ok=ok,
        url=url,
        entry_count=len(entries),
        unique_links=unique_links,
        latest_published_at=latest,
        error=None if ok else "missing_title_or_link",
    )
    validation.score = _compute_score(validation, config=config)
    return validation


def build_sources_yaml(
    validations: List[FeedValidation],
    *,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    output_cfg = config.get("output") or {}
    mode_default = str(output_cfg.get("mode_default") or "rss_only")
    comment_policy = str(output_cfg.get("comment_policy_default") or "try_public")

    sources: List[Dict[str, Any]] = []
    for validation in validations:
        if not validation.ok:
            continue
        parsed = urlparse(validation.url)
        domain = parsed.hostname or "rss"
        source_id = f"auto_{_slugify(domain)}_{_hash_id(validation.url)}"
        sources.append(
            {
                "source_id": source_id,
                "name": domain,
                "category": "未分类",
                "url": validation.url,
                "priority": 6,
                "mode": mode_default,
                "comment_policy": comment_policy,
                "quality_score": round(validation.score, 2),
                "enabled": True,
            }
        )

    return {
        "version": 1,
        "defaults": {"type": "rss"},
        "groups": [
            {
                "group_id": "auto_discovered",
                "name": "自动扩源",
                "sources": sources,
            }
        ],
    }


async def run_autoexpand(
    config_path: str,
    *,
    existing_urls: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    config = _read_config(config_path)
    if not config.get("enabled", False):
        return {"status": "disabled", "written": False}

    timeout = httpx.Timeout(10.0, connect=5.0)
    candidates: List[CandidateFeed] = []
    existing = { _normalize_url(url) for url in (existing_urls or []) if _normalize_url(url)}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        seeds = config.get("seeds") or {}
        seed_pages = [
            *(seeds.get("directory_pages") or []),
            *(seeds.get("site_homepages") or []),
        ]
        seed_urls: List[str] = []
        for row in seed_pages:
            if isinstance(row, dict):
                url = str(row.get("url") or "").strip()
            else:
                url = str(row or "").strip()
            if url:
                seed_urls.append(url)
        seed_urls.extend(seeds.get("opml_urls") or [])

        for seed_url in seed_urls:
            seed_url = str(seed_url or "").strip()
            if not seed_url:
                continue
            discovered = await discover_candidate_feeds(client, seed_url, config=config)
            candidates.extend(discovered)

        # Validate feeds
        validations: List[FeedValidation] = []
        for candidate in candidates:
            if _normalize_url(candidate.url) in existing:
                continue
            validation = await validate_feed(client, candidate.url, config)
            if validation.ok:
                validations.append(validation)

    min_score = float((config.get("scoring") or {}).get("min_quality_score") or 70)
    filtered = [v for v in validations if v.score >= min_score]

    output_data = build_sources_yaml(filtered, config=config)
    output_path = str((config.get("output") or {}).get("path") or "config/sources.auto.yaml")
    if yaml is None:
        return {"status": "missing_yaml", "written": False}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(output_data, fh, allow_unicode=True, sort_keys=False)
    return {
        "status": "ok",
        "written": True,
        "output_path": output_path,
        "count": len(filtered),
    }
