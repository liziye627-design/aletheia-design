"""
MediaCrawler 数据标准化（帖子/评论）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from services.investigation_helpers import (
    _extract_published_at,
    _parse_datetime_like,
    _safe_float,
    _safe_int,
    _stable_hash,
    _to_utc_iso,
)

_TEXT_SPLIT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", flags=re.UNICODE)


def _norm_text(text: Any) -> str:
    return str(text or "").strip()


def _tokens(text: str) -> List[str]:
    return [x for x in _TEXT_SPLIT_RE.split(str(text or "").lower()) if len(x) >= 2]


def _keyword_match(keyword: str, blob: str) -> Dict[str, Any]:
    kw = str(keyword or "").strip().lower()
    tx = str(blob or "").lower()
    if not kw:
        return {"hit": False, "score": 0.0, "match_type": "none"}
    if kw in tx:
        return {"hit": True, "score": 1.0, "match_type": "exact"}
    kw_tokens = set(_tokens(kw))
    tx_tokens = set(_tokens(tx))
    if not kw_tokens or not tx_tokens:
        return {"hit": False, "score": 0.0, "match_type": "none"}
    overlap = float(len(kw_tokens & tx_tokens)) / float(max(1, len(kw_tokens)))
    return {
        "hit": overlap >= 0.2,
        "score": round(overlap, 4),
        "match_type": "token_overlap" if overlap > 0 else "none",
    }


def _pick_first(raw: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _pick_post_id(raw: Dict[str, Any]) -> str:
    for key in [
        "post_id",
        "note_id",
        "aweme_id",
        "mblogid",
        "mid",
        "answer_id",
        "question_id",
        "item_id",
        "id",
    ]:
        value = _pick_first(raw, [key])
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _pick_url(raw: Dict[str, Any], platform: str, post_id: str) -> str:
    direct = _pick_first(
        raw,
        [
            "original_url",
            "source_url",
            "url",
            "note_url",
            "post_url",
            "jump_url",
            "share_url",
            "link",
            "href",
        ],
    )
    text = str(direct or "").strip()
    if text:
        return text
    if not post_id:
        return ""
    platform_l = str(platform or "").strip().lower()
    if platform_l == "xiaohongshu":
        return f"https://www.xiaohongshu.com/explore/{post_id}"
    if platform_l == "douyin":
        return f"https://www.douyin.com/video/{post_id}"
    if platform_l == "weibo":
        return f"https://weibo.com/{post_id}"
    if platform_l == "zhihu":
        return f"https://www.zhihu.com/question/{post_id}"
    return ""


def _pick_content(raw: Dict[str, Any]) -> str:
    value = _pick_first(
        raw,
        [
            "content_text",
            "content",
            "desc",
            "description",
            "text",
            "title",
            "snippet",
            "note_content",
            "summary",
        ],
    )
    return _norm_text(value)


def _pick_author_name(raw: Dict[str, Any]) -> str:
    value = _pick_first(raw, ["author_name", "nickname", "user_name", "screen_name", "author"])
    return _norm_text(value)


def _pick_author_id(raw: Dict[str, Any]) -> str:
    value = _pick_first(raw, ["author_id", "user_id", "uid"])
    return _norm_text(value)


def normalize_mediacrawler_posts(
    *,
    platform: str,
    rows: List[Dict[str, Any]],
    keyword: str,
    sidecar_task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        post_id = _pick_post_id(raw)
        url = _pick_url(raw, platform=platform, post_id=post_id)
        content_text = _pick_content(raw)
        title = _norm_text(_pick_first(raw, ["title", "note_title", "headline"]))
        blob = " ".join([title, content_text, _pick_author_name(raw)])
        match = _keyword_match(keyword, blob)
        created_at = _extract_published_at(raw)
        if created_at is None:
            dt = _parse_datetime_like(_pick_first(raw, ["created_at", "timestamp", "publish_time", "time"]))
            if dt is not None:
                created_at = _to_utc_iso(dt)
        likes = _safe_int(_pick_first(raw, ["likes", "like_count", "liked_count", "digg_count"]), 0)
        comments = _safe_int(_pick_first(raw, ["comments", "comment_count"]), 0)
        shares = _safe_int(_pick_first(raw, ["shares", "share_count", "repost_count"]), 0)
        metadata = {
            "provider": "mediacrawler",
            "retrieval_mode": "mediacrawler_api",
            "sidecar_task_id": str(sidecar_task_id or ""),
            "post_id": post_id,
            "note_id": _norm_text(_pick_first(raw, ["note_id"])),
            "aweme_id": _norm_text(_pick_first(raw, ["aweme_id"])),
            "mblogid": _norm_text(_pick_first(raw, ["mblogid", "mid"])),
            "answer_id": _norm_text(_pick_first(raw, ["answer_id"])),
            "question_id": _norm_text(_pick_first(raw, ["question_id"])),
            "item_id": _norm_text(_pick_first(raw, ["item_id"])),
            "author_id": _pick_author_id(raw),
            "author_name": _pick_author_name(raw),
            "timestamp": created_at,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "keyword_match": bool(match["hit"]),
            "keyword_match_score": float(match["score"]),
            "keyword_match_type": str(match["match_type"]),
        }
        out.append(
            {
                "id": str(_pick_first(raw, ["id"]) or f"mc_{platform}_{post_id or _stable_hash(blob[:160])[:16]}"),
                "source_platform": str(platform or ""),
                "original_url": url,
                "url": url,
                "title": title,
                "content_text": content_text,
                "content_type": str(_pick_first(raw, ["content_type", "type"]) or "TEXT"),
                "created_at": created_at,
                "metadata": metadata,
            }
        )
    return out


def _extract_comment_candidates(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not isinstance(row, dict):
        return candidates
    nested_keys = ["comments", "comment_list", "sub_comments", "replies", "reply_list"]
    for key in nested_keys:
        value = row.get(key)
        if isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    candidates.append(child)
    if candidates:
        return candidates
    # 如果 row 本身就是评论项
    looks_like_comment = bool(
        _pick_first(row, ["comment_id", "cid", "text", "content", "content_text", "reply_content"])
    )
    if looks_like_comment:
        return [row]
    return []


def normalize_mediacrawler_comments(
    *,
    platform: str,
    rows: List[Dict[str, Any]],
    post_id: str,
    sidecar_task_id: Optional[str] = None,
    limit: int = 120,
) -> List[Dict[str, Any]]:
    comments: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for comment in _extract_comment_candidates(row):
            text = _norm_text(
                _pick_first(
                    comment,
                    [
                        "content_text",
                        "content",
                        "text",
                        "reply_content",
                        "desc",
                    ],
                )
            )
            if not text:
                continue
            comment_id = _norm_text(_pick_first(comment, ["comment_id", "cid", "id"]))
            author_id = _norm_text(_pick_first(comment, ["author_id", "user_id", "uid"]))
            author_name = _norm_text(
                _pick_first(comment, ["author_name", "nickname", "screen_name", "user_name"])
            )
            published = _extract_published_at(comment) or _extract_published_at(row)
            likes = _safe_int(_pick_first(comment, ["likes", "like_count", "digg_count"]), 0)
            comments.append(
                {
                    "id": str(comment_id or f"mc_comment_{_stable_hash(text[:180])[:20]}"),
                    "source_platform": str(platform or ""),
                    "content_text": text,
                    "original_url": _pick_url(row, platform=platform, post_id=str(post_id or "")),
                    "metadata": {
                        "provider": "mediacrawler",
                        "retrieval_mode": "mediacrawler_api",
                        "sidecar_task_id": str(sidecar_task_id or ""),
                        "post_id": str(post_id or ""),
                        "comment_id": comment_id,
                        "author_id": author_id,
                        "author_name": author_name,
                        "likes": likes,
                        "comments": 0,
                        "shares": 0,
                        "timestamp": published,
                    },
                }
            )
            if len(comments) >= max(1, int(limit)):
                return comments
    return comments

