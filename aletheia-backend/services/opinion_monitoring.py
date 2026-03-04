"""
舆情评论监测：
1) 从已抓取证据中抽取可评论化 post_id
2) 跨平台抓取评论
3) BotDetector 账号可疑度打分
4) 输出风险分层与可追溯样本
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.config import settings
from services.agent_framework.bot_detector import (
    AccountProfile,
    BotDetector,
    ContentItem,
)
from services.investigation_helpers import (
    _keyword_relevance_score,
    _parse_datetime_like,
    _safe_float,
    _safe_int,
    _stable_hash,
)
from utils.logging import logger

SOCIAL_COMMENT_PLATFORMS = {
    "weibo",
    "twitter",
    "reddit",
    "zhihu",
    "xiaohongshu",
    "douyin",
    "bilibili",
    "kuaishou",
    "douban",
}

_BOT_DETECTOR: Optional[BotDetector] = None


def _get_bot_detector() -> BotDetector:
    global _BOT_DETECTOR
    if _BOT_DETECTOR is None:
        _BOT_DETECTOR = BotDetector()
    return _BOT_DETECTOR


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _looks_generated_hash_id(value: str) -> bool:
    raw = str(value or "").strip().lower()
    return bool(re.fullmatch(r"[a-f0-9]{32}", raw))


def _extract_post_id_from_url(platform: str, url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    patterns = {
        "twitter": [r"/status/(\d+)"],
        "weibo": [r"/([A-Za-z0-9]{8,})$"],
        "reddit": [r"/comments/([A-Za-z0-9_]+)/?"],
        "zhihu": [r"/answer/(\d+)", r"/p/(\d+)"],
        "xiaohongshu": [r"/explore/([A-Za-z0-9]+)"],
        "douyin": [r"/video/(\d+)"],
        "bilibili": [r"/video/(BV[0-9A-Za-z]+)", r"/video/av(\d+)"],
    }
    for pattern in patterns.get(platform, []):
        match = re.search(pattern, raw)
        if match:
            return str(match.group(1))
    return ""


def _extract_post_id(platform: str, item: Dict[str, Any]) -> str:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    direct_keys = [
        "post_id",
        "tweet_id",
        "aweme_id",
        "note_id",
        "mblogid",
        "mid",
        "zhihu_id",
        "answer_id",
        "question_id",
        "item_id",
        "aid",
        "bvid",
    ]
    meta_keys = [
        "post_id",
        "tweet_id",
        "aweme_id",
        "note_id",
        "mblogid",
        "mid",
        "zhihu_id",
        "answer_id",
        "question_id",
        "item_id",
        "aid",
        "bvid",
    ]

    for key in direct_keys:
        value = str(item.get(key) or "").strip()
        if value and not _looks_generated_hash_id(value):
            return value
    for key in meta_keys:
        value = str(meta.get(key) or "").strip()
        if value and not _looks_generated_hash_id(value):
            return value

    for key in ["url", "original_url", "source_url"]:
        post_id = _extract_post_id_from_url(platform, str(item.get(key) or meta.get(key) or ""))
        if post_id:
            return post_id
    return ""


def _score_post_candidate(keyword: str, item: Dict[str, Any]) -> float:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    text_blob = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("content_text") or item.get("content") or item.get("snippet") or ""),
            str(meta.get("author_name") or ""),
        ]
    )
    relevance = max(
        _safe_float(item.get("relevance_score"), 0.0),
        _safe_float(meta.get("keyword_match_score"), 0.0),
        _keyword_relevance_score(keyword, text_blob),
    )
    likes = _safe_int(meta.get("likes"), 0)
    comments = _safe_int(meta.get("comments"), 0)
    shares = _safe_int(meta.get("shares"), 0)
    engagement = likes + comments + shares
    keyword_bonus = 0.12 if bool(item.get("keyword_match") or meta.get("keyword_match")) else 0.0
    provider_bonus = 0.16 if str(meta.get("provider") or item.get("provider") or "").lower() == "mediacrawler" else 0.0
    fallback_penalty = (
        0.08
        if str(item.get("retrieval_mode") or meta.get("retrieval_mode") or "").lower()
        in {"hot_fallback", "rss_emergency_fallback", "web_search_fallback"}
        else 0.0
    )
    score = (
        relevance * 0.65
        + min(1.0, engagement / 5000.0) * 0.35
        + keyword_bonus
        + provider_bonus
        - fallback_penalty
    )
    return round(max(0.0, min(1.0, score)), 4)


def _build_comment_post_targets(
    *,
    keyword: str,
    search_data: Dict[str, List[Dict[str, Any]]],
    source_plan: Optional[Dict[str, Any]],
    max_posts_per_platform: int,
    max_platforms: int,
) -> Dict[str, str]:
    selected_platforms = [
        str(p)
        for p in list((source_plan or {}).get("selected_platforms") or [])
        if str(p) in SOCIAL_COMMENT_PLATFORMS
    ]
    candidate_platforms = selected_platforms or [
        str(p)
        for p in list(search_data.keys())
        if str(p) in SOCIAL_COMMENT_PLATFORMS
    ]
    candidate_platforms = candidate_platforms[: max(1, int(max_platforms))]

    targets: Dict[str, str] = {}
    for platform in candidate_platforms:
        rows = list(search_data.get(platform) or [])
        if not rows:
            continue
        ranked = sorted(
            rows,
            key=lambda row: _score_post_candidate(keyword, row if isinstance(row, dict) else {}),
            reverse=True,
        )
        chosen = ""
        for item in ranked[: max(1, int(max_posts_per_platform))]:
            if not isinstance(item, dict):
                continue
            post_id = _extract_post_id(platform, item)
            if post_id:
                chosen = post_id
                break
        if chosen:
            targets[platform] = chosen
    return targets


def _account_register_time_from_comment(comment: Dict[str, Any]) -> Optional[datetime]:
    meta = comment.get("metadata") if isinstance(comment.get("metadata"), dict) else {}
    age_days = _safe_float(meta.get("account_age_days"), -1.0)
    if age_days >= 0:
        try:
            return datetime.utcnow() - timedelta(days=float(age_days))
        except Exception:
            return None
    return None


def _comment_time(comment: Dict[str, Any]) -> Optional[datetime]:
    meta = comment.get("metadata") if isinstance(comment.get("metadata"), dict) else {}
    for key in ["timestamp", "created_at", "published_at"]:
        dt = _parse_datetime_like(meta.get(key) or comment.get(key))
        if dt is not None:
            return dt
    return None


def _build_user_profile(platform: str, user_id: str, rows: List[Dict[str, Any]]) -> AccountProfile:
    first = rows[0] if rows else {}
    meta = first.get("metadata") if isinstance(first.get("metadata"), dict) else {}
    follower_count = _safe_int(
        meta.get("author_follower_count") or meta.get("followers") or first.get("followers"),
        0,
    )
    following_count = _safe_int(meta.get("author_following_count"), 0)
    verified = bool(meta.get("verified") or first.get("verified"))
    profile = AccountProfile(
        user_id=user_id,
        nickname=str(meta.get("author_name") or first.get("author_name") or "unknown"),
        platform=platform,
        register_time=_account_register_time_from_comment(first),
        follower_count=follower_count,
        following_count=following_count,
        post_count=max(1, len(rows)),
        is_verified=verified,
        verify_type="verified" if verified else "",
        metadata={
            "platform": platform,
            "sample_comment_count": len(rows),
        },
    )
    return profile


def _build_user_contents(user_id: str, rows: List[Dict[str, Any]]) -> List[ContentItem]:
    contents: List[ContentItem] = []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        text = _normalize_text(
            row.get("content_text") or row.get("content") or row.get("text") or row.get("snippet") or ""
        )
        if not text:
            continue
        content_id = str(row.get("id") or meta.get("comment_id") or _stable_hash(text[:180]))
        contents.append(
            ContentItem(
                content_id=content_id,
                user_id=user_id,
                text=text,
                publish_time=_comment_time(row),
                likes=_safe_int(meta.get("likes"), 0),
                comments=_safe_int(meta.get("comments"), 0),
                shares=_safe_int(meta.get("shares"), 0),
                has_image=bool(row.get("image_urls")),
                has_video=bool(row.get("video_url")),
            )
        )
    return contents


def _run_bot_detection(comments_by_platform: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    detector = _get_bot_detector()
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for platform, rows in comments_by_platform.items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            user_id = str(meta.get("author_id") or row.get("author_id") or "").strip()
            if not user_id:
                text = _normalize_text(
                    row.get("content_text") or row.get("content") or row.get("text") or row.get("snippet") or ""
                )
                if not text:
                    continue
                user_id = f"{platform}_anon_{_stable_hash(text[:120])[:12]}"
            grouped[platform][user_id].append(row)

    account_rows: List[Dict[str, Any]] = []
    for platform, users in grouped.items():
        for user_id, rows in users.items():
            try:
                profile = _build_user_profile(platform, user_id, rows)
                contents = _build_user_contents(user_id, rows)
                detection = detector.detect(profile, contents)
                account_rows.append(
                    {
                        "platform": platform,
                        "user_id": user_id,
                        "nickname": profile.nickname,
                        "comment_count": len(rows),
                        "risk_score": float(detection.risk_score),
                        "risk_level": str(detection.risk_level),
                        "is_suspicious": bool(detection.is_suspicious),
                        "detected_features": list(detection.detected_features or []),
                        "sample_comments": [
                            _normalize_text(
                                r.get("content_text")
                                or r.get("content")
                                or r.get("text")
                                or r.get("snippet")
                                or ""
                            )[:160]
                            for r in rows[:3]
                        ],
                    }
                )
            except Exception as exc:
                logger.debug(f"bot detection skipped for {platform}/{user_id}: {exc}")
    account_rows.sort(key=lambda row: float(row.get("risk_score") or 0.0), reverse=True)
    return account_rows


def _template_repeat_ratio(comments_by_platform: Dict[str, List[Dict[str, Any]]]) -> float:
    texts: List[str] = []
    for rows in comments_by_platform.values():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            text = _normalize_text(
                row.get("content_text") or row.get("content") or row.get("text") or row.get("snippet") or ""
            ).lower()
            if not text:
                continue
            texts.append(text)
    if not texts:
        return 0.0
    counter = Counter(texts)
    top = max(counter.values())
    return round(float(top) / float(len(texts)), 4)


def _sample_comments(comments_by_platform: Dict[str, List[Dict[str, Any]]], *, limit: int = 12) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for platform, comments in comments_by_platform.items():
        for comment in comments[: max(1, int(limit))]:
            if not isinstance(comment, dict):
                continue
            meta = comment.get("metadata") if isinstance(comment.get("metadata"), dict) else {}
            text = _normalize_text(
                comment.get("content_text")
                or comment.get("content")
                or comment.get("text")
                or comment.get("snippet")
                or ""
            )
            if not text:
                continue
            rows.append(
                {
                    "platform": platform,
                    "url": str(comment.get("original_url") or comment.get("url") or ""),
                    "text": text[:220],
                    "snippet": text[:220],
                    "author_name": str(meta.get("author_name") or comment.get("author_name") or "unknown"),
                    "author_id": str(meta.get("author_id") or comment.get("author_id") or ""),
                    "likes": _safe_int(meta.get("likes"), 0),
                    "published_at": (
                        _comment_time(comment).isoformat()
                        if _comment_time(comment) is not None
                        else None
                    ),
                }
            )
            if len(rows) >= max(1, int(limit)):
                return rows
    return rows


def _build_pseudo_comments_from_posts(
    search_data: Dict[str, List[Dict[str, Any]]],
    *,
    limit_total: int,
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    remaining = max(1, int(limit_total))
    for platform, rows in (search_data or {}).items():
        if remaining <= 0:
            break
        for row in rows or []:
            if remaining <= 0:
                break
            if not isinstance(row, dict):
                continue
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            text_candidates = [
                _normalize_text(row.get("content_text") or row.get("content") or row.get("text") or ""),
                _normalize_text(row.get("snippet") or ""),
                _normalize_text(row.get("title") or ""),
            ]
            text_candidates = [t for t in text_candidates if len(t) >= 8]
            dedup: List[str] = []
            for text in text_candidates:
                if text not in dedup:
                    dedup.append(text)
            if len(dedup) == 1 and remaining > 1:
                base = dedup[0]
                fragments = [
                    _normalize_text(x)
                    for x in re.split(r"[。！？.!?;；,，]", base)
                    if _normalize_text(x)
                ]
                for frag in fragments:
                    if frag != base and len(frag) >= 8 and frag not in dedup:
                        dedup.append(frag[:220])
                        break
                if len(dedup) == 1 and len(base) >= 48:
                    half = len(base) // 2
                    tail = _normalize_text(base[half : half + 220])
                    if len(tail) >= 8 and tail not in dedup:
                        dedup.append(tail)
            if not dedup:
                continue
            for idx, text in enumerate(dedup[:2]):
                if remaining <= 0:
                    break
                pseudo = {
                    "url": str(row.get("url") or row.get("original_url") or row.get("source_url") or ""),
                    "content_text": text[:260],
                    "metadata": {
                        "author_id": str(
                            meta.get("author_id")
                            or row.get("author_id")
                            or _stable_hash(f"{text[:120]}#{idx}")[:12]
                        ),
                        "author_name": str(meta.get("author_name") or row.get("author_name") or platform),
                        "likes": _safe_int(meta.get("likes"), 0),
                        "comments": _safe_int(meta.get("comments"), 0),
                        "shares": _safe_int(meta.get("shares"), 0),
                        "account_age_days": _safe_float(meta.get("account_age_days"), -1.0),
                        "timestamp": meta.get("timestamp") or row.get("created_at"),
                        "synthetic_comment": True,
                    },
                }
                out[str(platform)].append(pseudo)
                remaining -= 1
    return dict(out)


async def analyze_opinion_monitoring(
    *,
    keyword: str,
    search_data: Dict[str, List[Dict[str, Any]]],
    source_plan: Optional[Dict[str, Any]],
    crawler_manager: Any,
    mediacrawler_options: Optional[Dict[str, Any]] = None,
    comment_target: int,
    comment_limit_per_post: int,
    max_posts_per_platform: int,
    max_platforms: int,
    allow_synthetic_comments: bool = False,
) -> Dict[str, Any]:
    fallback_search_data: Dict[str, List[Dict[str, Any]]] = dict(search_data or {})
    extra_sidecar_failures: List[Dict[str, Any]] = []
    no_comment_post_candidates = False
    post_targets = _build_comment_post_targets(
        keyword=keyword,
        search_data=search_data,
        source_plan=source_plan,
        max_posts_per_platform=max_posts_per_platform,
        max_platforms=max_platforms,
    )
    discovery_mode = "reuse_search_results"
    if not post_targets and hasattr(crawler_manager, "search_across_platforms"):
        social_platforms = [
            str(p)
            for p in list(getattr(crawler_manager, "crawlers", {}).keys())
            if str(p) in SOCIAL_COMMENT_PLATFORMS
        ][: max(1, int(max_platforms))]
        if social_platforms:
            try:
                social_search: Dict[str, List[Dict[str, Any]]] = {}
                if hasattr(crawler_manager, "search_across_platforms_verbose"):
                    social_verbose = await crawler_manager.search_across_platforms_verbose(
                        keyword=keyword,
                        platforms=social_platforms,
                        limit_per_platform=max(6, int(max_posts_per_platform) * 3),
                        mediacrawler_options=mediacrawler_options,
                    )
                    for p, row in (social_verbose or {}).items():
                        items = row.get("items") if isinstance(row, dict) else []
                        social_search[str(p)] = (
                            list(items) if isinstance(items, list) else []
                        )
                        sidecar = dict((row or {}).get("mediacrawler") or {})
                        if bool(sidecar.get("degraded")):
                            sidecar_reason = str(
                                sidecar.get("error")
                                or sidecar.get("reason")
                                or "MEDIACRAWLER_DEGRADED"
                            )
                            extra_sidecar_failures.append(
                                {
                                    "platform": str(p),
                                    "post_id": "",
                                    "reason": sidecar_reason,
                                }
                            )
                else:
                    social_search = await crawler_manager.search_across_platforms(
                        keyword=keyword,
                        platforms=social_platforms,
                        limit_per_platform=max(6, int(max_posts_per_platform) * 3),
                        mediacrawler_options=mediacrawler_options,
                    )
                post_targets = _build_comment_post_targets(
                    keyword=keyword,
                    search_data=social_search if isinstance(social_search, dict) else {},
                    source_plan={"selected_platforms": social_platforms},
                    max_posts_per_platform=max_posts_per_platform,
                    max_platforms=max_platforms,
                )
                if isinstance(social_search, dict):
                    fallback_search_data.update(
                        {
                            str(p): list(rows or [])
                            for p, rows in social_search.items()
                            if isinstance(rows, list)
                        }
                    )
                if post_targets:
                    discovery_mode = "quick_social_search"
            except Exception as exc:
                logger.warning(f"opinion quick social search failed: {exc}")
    comments_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    if post_targets:
        comments_by_platform = await crawler_manager.fetch_comments_multi_platform(
            post_ids=post_targets,
            limit_per_platform=max(1, int(comment_limit_per_post)),
            mediacrawler_options=mediacrawler_options,
        )
        if not isinstance(comments_by_platform, dict):
            comments_by_platform = {}
    else:
        no_comment_post_candidates = True

    sidecar_diag = {}
    if hasattr(crawler_manager, "get_last_comment_sidecar_diag"):
        try:
            sidecar_diag = dict(crawler_manager.get_last_comment_sidecar_diag() or {})
        except Exception:
            sidecar_diag = {}
    sidecar_failures: List[Dict[str, Any]] = [
        row for row in list(sidecar_diag.get("failures") or []) if isinstance(row, dict)
    ]
    sidecar_failures.extend(
        [row for row in extra_sidecar_failures if isinstance(row, dict)]
    )

    failed_platforms: List[Dict[str, Any]] = []
    platform_comment_stats: Dict[str, Any] = {}
    total_comments = 0
    synthetic_comment_mode = False
    sidecar_comment_count = 0
    for platform, post_id in post_targets.items():
        rows = list(comments_by_platform.get(platform) or [])
        count = len(rows)
        total_comments += count
        for row in rows:
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if str(meta.get("provider") or "").lower() == "mediacrawler":
                sidecar_comment_count += 1
        if count <= 0:
            failed_platforms.append(
                {
                    "platform": platform,
                    "post_id": post_id,
                    "reason": "EMPTY_COMMENTS",
                }
            )
        platform_comment_stats[platform] = {
            "post_id": post_id,
            "comment_count": count,
        }
    if sidecar_failures:
        existed = {(str(x.get("platform") or ""), str(x.get("reason") or "")) for x in failed_platforms}
        for row in sidecar_failures:
            key = (str(row.get("platform") or ""), str(row.get("reason") or ""))
            if key in existed:
                continue
            existed.add(key)
            failed_platforms.append(
                {
                    "platform": str(row.get("platform") or "unknown"),
                    "post_id": str(row.get("post_id") or ""),
                    "reason": str(row.get("reason") or "MEDIACRAWLER_COMMENT_FAILED"),
                }
            )
    sidecar_comment_count = max(sidecar_comment_count, int(sidecar_diag.get("hit_count") or 0))

    real_comment_count = int(total_comments)
    synthetic_comment_count = 0

    if no_comment_post_candidates and total_comments <= 0 and not bool(allow_synthetic_comments):
        return {
            "status": "no_comment_post_candidates",
            "keyword": keyword,
            "comment_target": int(comment_target),
            "comment_limit_per_post": int(comment_limit_per_post),
            "max_posts_per_platform": int(max_posts_per_platform),
            "candidate_platforms": [],
            "post_targets": {},
            "platform_comment_stats": {},
            "failed_platforms": [{"platform": "global", "post_id": "", "reason": "NO_REAL_COMMENT_ID"}],
            "total_comments": 0,
            "real_comment_count": 0,
            "synthetic_comment_count": 0,
            "sidecar_comment_count": 0,
            "sidecar_failures": sidecar_failures,
            "real_comment_ratio": 0.0,
            "real_comment_target_reached": False,
            "unique_accounts_count": 0,
            "suspicious_accounts_count": 0,
            "suspicious_ratio": 0.0,
            "template_repeat_ratio": 0.0,
            "risk_level": "medium",
            "risk_flags": [
                "NO_COMMENT_POST_CANDIDATES",
                "INSUFFICIENT_COMMENT_COVERAGE",
                "SYNTHETIC_COMMENTS_DISABLED",
            ],
            "comment_target_reached": False,
            "summary_text": "评论监测未找到可抓取评论的帖子 ID，且 synthetic 回退已关闭。",
            "top_suspicious_accounts": [],
            "sample_comments": [],
            "discovery_mode": discovery_mode,
            "synthetic_comment_mode": False,
        }

    if total_comments < int(comment_target) and bool(allow_synthetic_comments):
        need = max(1, int(comment_target) - int(total_comments))
        pseudo_comments = _build_pseudo_comments_from_posts(
            fallback_search_data,
            limit_total=max(need, 60),
        )
        pseudo_total = sum(len(rows or []) for rows in pseudo_comments.values())
        if pseudo_total > 0:
            merged_comments: Dict[str, List[Dict[str, Any]]] = {
                str(p): list(rows or [])
                for p, rows in (comments_by_platform or {}).items()
                if isinstance(rows, list)
            }
            for platform, rows in pseudo_comments.items():
                merged_comments.setdefault(str(platform), [])
                merged_comments[str(platform)].extend(list(rows or []))
            comments_by_platform = merged_comments
            synthetic_comment_count = int(pseudo_total)
            total_comments = int(total_comments) + int(pseudo_total)
            synthetic_comment_mode = True
            discovery_mode = (
                f"{discovery_mode}_fallback_posts"
                if "fallback_posts" not in discovery_mode
                else discovery_mode
            )
            if no_comment_post_candidates:
                failed_platforms = []
            for platform, rows in pseudo_comments.items():
                stat = platform_comment_stats.setdefault(
                    str(platform),
                    {
                        "post_id": str(post_targets.get(platform) or ""),
                        "comment_count": 0,
                    },
                )
                stat["comment_count"] = int(stat.get("comment_count") or 0) + len(rows or [])
                stat["synthetic_comment_mode"] = True
                stat["synthetic_comment_count"] = int(stat.get("synthetic_comment_count") or 0) + len(rows or [])
        elif no_comment_post_candidates:
            real_comment_ratio = 0.0
            return {
                "status": "no_comment_post_candidates",
                "keyword": keyword,
                "comment_target": int(comment_target),
                "comment_limit_per_post": int(comment_limit_per_post),
                "max_posts_per_platform": int(max_posts_per_platform),
                "candidate_platforms": [],
                "post_targets": {},
                "platform_comment_stats": {},
                "failed_platforms": [],
                "total_comments": 0,
                "unique_accounts_count": 0,
                "suspicious_accounts_count": 0,
                "suspicious_ratio": 0.0,
                "template_repeat_ratio": 0.0,
                "risk_level": "medium",
                "risk_flags": ["NO_COMMENT_POST_CANDIDATES", "INSUFFICIENT_COMMENT_COVERAGE"],
                "comment_target_reached": False,
                "real_comment_ratio": real_comment_ratio,
                "real_comment_target_reached": False,
                "summary_text": "评论监测未找到可抓取评论的帖子 ID，且无可用回退样本。",
                "top_suspicious_accounts": [],
                "sample_comments": [],
                "discovery_mode": discovery_mode,
                "synthetic_comment_mode": False,
                "real_comment_count": 0,
                "synthetic_comment_count": 0,
                "sidecar_comment_count": 0,
                "sidecar_failures": sidecar_failures,
            }
    elif total_comments < int(comment_target):
        if no_comment_post_candidates:
            failed_platforms.append(
                {
                    "platform": "global",
                    "post_id": "",
                    "reason": "NO_REAL_COMMENT_ID",
                }
            )

    account_rows = _run_bot_detection(comments_by_platform)
    unique_accounts_count = len(account_rows)
    suspicious_accounts = [row for row in account_rows if bool(row.get("is_suspicious"))]
    suspicious_accounts_count = len(suspicious_accounts)
    suspicious_ratio = round(
        float(suspicious_accounts_count) / float(max(1, unique_accounts_count)),
        4,
    )
    repeat_ratio = _template_repeat_ratio(comments_by_platform)
    comment_target_reached = total_comments >= int(comment_target)
    real_comment_ratio = round(
        float(real_comment_count) / float(max(1, total_comments)),
        4,
    )
    real_comment_target_reached = real_comment_count >= int(comment_target)

    risk_flags: List[str] = []
    if not comment_target_reached:
        risk_flags.append("INSUFFICIENT_COMMENT_COVERAGE")
    if failed_platforms:
        risk_flags.append("COMMENT_FETCH_PARTIAL_FAILURE")
    if sidecar_failures:
        risk_flags.append("MEDIACRAWLER_COMMENT_DEGRADED")
    if no_comment_post_candidates:
        risk_flags.append("NO_COMMENT_POST_CANDIDATES")
    if synthetic_comment_mode:
        risk_flags.append("COMMENT_SOURCE_FALLBACK_POSTS")
    if (not allow_synthetic_comments) and real_comment_count < int(comment_target):
        risk_flags.append("REAL_COMMENT_SHORTFALL")
    if not allow_synthetic_comments:
        risk_flags.append("SYNTHETIC_COMMENTS_DISABLED")
    medium_threshold = _safe_float(
        getattr(settings, "INVESTIGATION_OPINION_SUSPICIOUS_RATIO_MEDIUM", 0.25),
        0.25,
    )
    high_threshold = _safe_float(
        getattr(settings, "INVESTIGATION_OPINION_SUSPICIOUS_RATIO_HIGH", 0.45),
        0.45,
    )
    risk_level = "low"
    if suspicious_ratio >= high_threshold or repeat_ratio >= 0.35:
        risk_level = "high"
        risk_flags.append("BOT_SWARM_RISK_HIGH")
    elif suspicious_ratio >= medium_threshold or repeat_ratio >= 0.2:
        risk_level = "medium"
        risk_flags.append("BOT_SWARM_RISK_MEDIUM")
    if not risk_flags:
        risk_flags.append("COMMENT_MONITORING_OK")

    summary_text = (
        f"评论监测：候选平台 {len(post_targets)}，抓取评论 {total_comments} 条，"
        f"唯一账号 {unique_accounts_count} 个，可疑账号 {suspicious_accounts_count} 个"
        f"（{round(suspicious_ratio * 100, 1)}%），风险等级 {risk_level.upper()}。"
    )
    if synthetic_comment_mode:
        summary_text += (
            f" 其中真实评论 {real_comment_count} 条，回退样本 {synthetic_comment_count} 条。"
        )
    elif not allow_synthetic_comments and total_comments < int(comment_target):
        summary_text += " synthetic 回退已关闭，保留真实评论缺口供复核。"
    if sidecar_comment_count > 0:
        summary_text += f" MediaCrawler补抓评论 {sidecar_comment_count} 条。"
    if sidecar_failures:
        summary_text += f" Sidecar降级 {len(sidecar_failures)} 个平台。"

    return {
        "status": "ok" if comment_target_reached else "partial",
        "discovery_mode": discovery_mode,
        "keyword": keyword,
        "comment_target": int(comment_target),
        "comment_limit_per_post": int(comment_limit_per_post),
        "max_posts_per_platform": int(max_posts_per_platform),
        "candidate_platforms": list(post_targets.keys()),
        "post_targets": post_targets,
        "platform_comment_stats": platform_comment_stats,
        "failed_platforms": failed_platforms,
        "total_comments": int(total_comments),
        "real_comment_count": int(real_comment_count),
        "synthetic_comment_count": int(synthetic_comment_count),
        "sidecar_comment_count": int(sidecar_comment_count),
        "sidecar_failures": sidecar_failures,
        "unique_accounts_count": int(unique_accounts_count),
        "suspicious_accounts_count": int(suspicious_accounts_count),
        "suspicious_ratio": float(suspicious_ratio),
        "template_repeat_ratio": float(repeat_ratio),
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "comment_target_reached": bool(comment_target_reached),
        "real_comment_ratio": float(real_comment_ratio),
        "real_comment_target_reached": bool(real_comment_target_reached),
        "synthetic_comment_mode": bool(synthetic_comment_mode),
        "summary_text": summary_text,
        "top_suspicious_accounts": suspicious_accounts[:10],
        "sample_comments": _sample_comments(comments_by_platform, limit=15),
    }
