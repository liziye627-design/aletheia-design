"""
资讯补量抓取服务：
按主链路 -> 补充链路分轮抓取，输出可解释的平台诊断与证据汇总。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from core.config import settings
from services.investigation_helpers import _keyword_relevance_score, _normalize_url
from services.layer1_perception.crawler_manager import get_crawler_manager


def _is_cjk_query(text: str) -> bool:
    raw = str(text or "")
    return any("\u4e00" <= ch <= "\u9fff" for ch in raw)


def _parse_platforms(raw: str) -> List[str]:
    values = [x.strip() for x in str(raw or "").split(",")]
    out: List[str] = []
    seen: set[str] = set()
    for row in values:
        if not row:
            continue
        if row in seen:
            continue
        seen.add(row)
        out.append(row)
    return out


class SupplementCrawlerService:
    def __init__(self, crawler_manager: Any = None) -> None:
        self.crawlers = crawler_manager or get_crawler_manager()
        self.keyword_threshold = float(
            getattr(settings, "CRAWLER_KEYWORD_MATCH_THRESHOLD", 0.2)
        )

    def _default_primary_platforms(self, keyword: str) -> List[str]:
        if _is_cjk_query(keyword):
            raw = str(
                getattr(
                    settings,
                    "INVESTIGATION_TRUSTED_ZH_PLATFORMS",
                    "rss_pool,weibo,zhihu,xinhua,peoples_daily,china_gov,samr,csrc,nhc",
                )
            )
            return _parse_platforms(raw)
        raw = str(
            getattr(
                settings,
                "INVESTIGATION_TRUSTED_PLATFORM_WHITELIST",
                "bbc,reuters,ap_news,guardian,xinhua,who,un_news",
            )
        )
        return _parse_platforms(raw)

    def _default_supplement_platforms(self, keyword: str) -> List[str]:
        if _is_cjk_query(keyword):
            raw = str(
                getattr(
                    settings,
                    "INVESTIGATION_ZH_QUERY_BACKGROUND_PLATFORMS",
                    "news,bbc,reuters,guardian,ap_news,who,un_news",
                )
            )
            return _parse_platforms(raw)
        return ["news"]

    def _item_dedupe_key(self, item: Dict[str, Any]) -> str:
        if not isinstance(item, dict):
            return ""
        url = _normalize_url(str(item.get("url") or item.get("source_url") or ""))
        if url:
            return f"url:{url}"
        text = str(item.get("content_text") or item.get("title") or "").strip().lower()
        if text:
            return f"text:{text[:220]}"
        return ""

    def _is_promotable(self, keyword: str, item: Dict[str, Any]) -> bool:
        if not isinstance(item, dict):
            return False
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        mode = str(metadata.get("retrieval_mode") or "").strip().lower()
        if mode in {"hot_fallback"}:
            return False
        if bool(metadata.get("keyword_match")):
            return True
        score = 0.0
        try:
            score = float(metadata.get("keyword_match_score") or 0.0)
        except Exception:
            score = 0.0
        if score <= 0.0:
            blob = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("content_text") or ""),
                    str(item.get("snippet") or ""),
                ]
            )
            score = float(_keyword_relevance_score(keyword=keyword, text_blob=blob))
        return score >= self.keyword_threshold

    async def run(
        self,
        *,
        keyword: str,
        target_evidence: int = 12,
        rounds: int = 3,
        limit_per_platform: int = 20,
        primary_platforms: Optional[List[str]] = None,
        supplement_platforms: Optional[List[str]] = None,
        mediacrawler_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = str(keyword or "").strip()
        if not query:
            raise ValueError("keyword is required")

        crawlers_map = getattr(self.crawlers, "crawlers", {}) or {}
        primary = list(primary_platforms or self._default_primary_platforms(query))
        supplement = list(supplement_platforms or self._default_supplement_platforms(query))
        primary = [p for p in primary if p in crawlers_map]
        supplement = [p for p in supplement if p in crawlers_map and p not in primary]

        promoted_seen: Set[str] = set()
        all_seen: Set[str] = set()
        promoted_items: List[Dict[str, Any]] = []
        all_items: List[Dict[str, Any]] = []
        attempts: List[Dict[str, Any]] = []

        rounds_executed = 0
        used_platforms: Set[str] = set()

        for round_idx in range(1, max(1, int(rounds)) + 1):
            if round_idx == 1:
                active = list(primary)
            else:
                active = [p for p in supplement if p not in used_platforms]
            if not active:
                continue
            rounds_executed += 1
            used_platforms.update(active)

            verbose = await self.crawlers.search_across_platforms_verbose(
                keyword=query,
                platforms=active,
                limit_per_platform=max(1, int(limit_per_platform)),
                mediacrawler_options=mediacrawler_options,
            )
            for platform in active:
                row = dict(verbose.get(platform) or {})
                items = list(row.get("items") or [])
                promoted_count = 0
                for item in items:
                    key = self._item_dedupe_key(item)
                    if key and key not in all_seen:
                        all_seen.add(key)
                        all_items.append(item)
                    if not self._is_promotable(query, item):
                        continue
                    if key and key in promoted_seen:
                        continue
                    if key:
                        promoted_seen.add(key)
                    promoted_items.append(item)
                    promoted_count += 1

                retrieval_modes = sorted(
                    list(
                        {
                            str((it.get("metadata") or {}).get("retrieval_mode") or "")
                            .strip()
                            .lower()
                            for it in items
                            if isinstance(it, dict)
                            and isinstance(it.get("metadata"), dict)
                        }
                    )
                )
                attempts.append(
                    {
                        "round": round_idx,
                        "platform": platform,
                        "status": str(row.get("status") or "unknown"),
                        "reason_code": str(row.get("reason_code") or "UNKNOWN"),
                        "items_collected": int(row.get("items_collected") or len(items)),
                        "promoted_items": int(promoted_count),
                        "elapsed_ms": int(row.get("elapsed_ms") or 0),
                        "retrieval_modes": retrieval_modes,
                    }
                )

            if len(promoted_items) >= int(target_evidence):
                break

        matrix = {}
        if hasattr(self.crawlers, "get_platform_source_matrix"):
            matrix = dict(self.crawlers.get_platform_source_matrix() or {})
        account_pool_snapshot = {
            platform: dict((matrix.get(platform) or {}).get("account_pool") or {})
            for platform in used_platforms
        }

        return {
            "keyword": query,
            "target_evidence": int(target_evidence),
            "rounds_planned": int(rounds),
            "rounds_executed": int(rounds_executed),
            "primary_platforms": primary,
            "supplement_platforms": supplement,
            "platform_attempts": attempts,
            "total_items": int(len(all_items)),
            "promoted_items": int(len(promoted_items)),
            "coverage_reached": bool(len(promoted_items) >= int(target_evidence)),
            "promoted_preview": promoted_items[:100],
            "platform_matrix": {
                p: matrix.get(p)
                for p in sorted(set([*primary, *supplement]))
                if p in matrix
            },
            "account_pool_snapshot": account_pool_snapshot,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
