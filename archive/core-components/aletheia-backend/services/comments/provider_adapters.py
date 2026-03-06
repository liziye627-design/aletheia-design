"""Provider-specific comment adapters for major domestic sites."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AdapterResult:
    provider: str
    endpoint: str
    thread_id: Optional[str] = None
    extra_params: Optional[Dict[str, Any]] = None


def _first_match(patterns, text: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _match_sina(url: str, html: str) -> Optional[AdapterResult]:
    if "sina.com.cn" not in url and "sina" not in html.lower():
        return None
    newsid = _first_match([r"newsid\s*[:=]\s*['\"](\w+)"], html)
    channel = _first_match([r"channel\s*[:=]\s*['\"](\w+)"], html) or "gn"
    if not newsid:
        return None
    endpoint = "https://comment5.news.sina.com.cn/page/info"
    return AdapterResult(
        provider="sina",
        endpoint=endpoint,
        thread_id=newsid,
        extra_params={
            "format": "json",
            "channel": channel,
            "newsid": newsid,
        },
    )


def _match_tencent(url: str, html: str) -> Optional[AdapterResult]:
    if "qq.com" not in url and "coral.qq.com" not in html:
        return None
    article_id = _first_match(
        [r"comment_id\s*[:=]\s*['\"](\w+)" , r"cmt_id\s*[:=]\s*['\"](\w+)", r"article_id\s*[:=]\s*['\"](\w+)"] ,
        html,
    )
    if not article_id:
        return None
    endpoint = f"https://coral.qq.com/article/{article_id}/comment/v2"
    return AdapterResult(provider="tencent_coral", endpoint=endpoint, thread_id=article_id)


def _match_netease(url: str, html: str) -> Optional[AdapterResult]:
    if "163.com" not in url and "netease" not in html.lower():
        return None
    doc_id = _first_match([r"docId\s*[:=]\s*['\"](\w+)"], html)
    product_key = _first_match([r"productKey\s*[:=]\s*['\"](\w+)"], html)
    if not doc_id or not product_key:
        return None
    endpoint = (
        f"https://comment.api.163.com/api/v1/products/{product_key}"
        f"/threads/{doc_id}/comments/newList"
    )
    return AdapterResult(
        provider="netease",
        endpoint=endpoint,
        thread_id=doc_id,
        extra_params={"pageNo": 1, "pageSize": 20},
    )


def _match_changyan(url: str, html: str) -> Optional[AdapterResult]:
    if "changyan" not in html.lower():
        return None
    client_id = _first_match([r"client_id\s*[:=]\s*['\"](\w+)"], html)
    if not client_id:
        return None
    endpoint = "https://changyan.sohu.com/api/2/topic/comments"
    return AdapterResult(
        provider="changyan",
        endpoint=endpoint,
        thread_id=None,
        extra_params={"client_id": client_id, "topic_url": url},
    )


def resolve_adapter(url: str, html: str) -> Optional[AdapterResult]:
    for matcher in (_match_sina, _match_tencent, _match_netease, _match_changyan):
        result = matcher(url, html)
        if result:
            return result
    return None
