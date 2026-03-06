"""
Investigation 引擎通用辅助函数与常量。
"""

from __future__ import annotations

import email.utils
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env


TERMINAL_STATUSES = {"complete", "failed", "partial", "insufficient_evidence"}
_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ InvestigationEngine disable httpx trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


FALLBACK_STABLE_PLATFORMS = ["bbc", "guardian", "reuters", "ap_news", "xinhua"]
STABLE_MIXED_PROFILE = [
    "bbc",
    "guardian",
    "reuters",
    "ap_news",
    "xinhua",
    "who",
    "un_news",
    "sec",
    "samr",
    "csrc",
]
OFFICIAL_DOMAINS = {
    "openai.com",
    "help.openai.com",
    "news.cn",
    "gov.cn",
    "people.com.cn",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "theguardian.com",
    "thepaper.cn",
    "caixin.com",
    "samr.gov.cn",
    "csrc.gov.cn",
    "nhc.gov.cn",
    "mem.gov.cn",
    "mps.gov.cn",
    "who.int",
    "cdc.gov",
    "un.org",
    "sec.gov",
    "fca.org.uk",
}


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _to_utc_iso(value: datetime) -> str:
    dt = value
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()


def _parse_datetime_like(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            if ts <= 0:
                return None
            return datetime.utcfromtimestamp(ts)
        except Exception:
            return None
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        pass
    fmts = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    try:
        return email.utils.parsedate_to_datetime(raw)
    except Exception:
        return None


def _extract_published_at(item: Dict[str, Any]) -> Optional[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    candidates = [
        item.get("published_at"),
        item.get("publish_time"),
        item.get("published"),
        item.get("timestamp"),
        item.get("created_at"),
        item.get("time"),
        item.get("date"),
        metadata.get("published_at"),
        metadata.get("publish_time"),
        metadata.get("published"),
        metadata.get("timestamp"),
        metadata.get("created_at"),
        metadata.get("source_time"),
        metadata.get("time"),
    ]
    for val in candidates:
        dt = _parse_datetime_like(val)
        if dt is not None:
            return _to_utc_iso(dt)
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _derive_keyword(claim: str, keyword: Optional[str]) -> str:
    if keyword and keyword.strip():
        return keyword.strip()
    text = " ".join((claim or "").split())
    if len(text) <= 24:
        return text
    return text[:24]


def _is_official_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == d or host.endswith(f".{d}") for d in OFFICIAL_DOMAINS)


def _tier_for_url(url: str) -> int:
    if _is_official_url(url):
        return 1
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    tier2_domains = {
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "theguardian.com",
        "caixin.com",
        "thepaper.cn",
        "news.cn",
        "xinhuanet.com",
    }
    if any(host == d or host.endswith(f".{d}") for d in tier2_domains):
        return 2
    return 3


def _build_level(score: float) -> str:
    """根据分数判断可信度等级 - 降低阈值使权威媒体报道更容易达到高等级"""
    if score >= 0.80:  # 从 0.85 降低到 0.80
        return "VERIFIED"
    if score >= 0.60:  # 从 0.65 降低到 0.60
        return "LIKELY_TRUE"
    if score >= 0.40:  # 从 0.45 降低到 0.40
        return "UNCERTAIN"
    if score >= 0.20:  # 从 0.25 降低到 0.20
        return "LIKELY_FALSE"
    return "FALSE"


def _elapsed_ms(started_at: str) -> int:
    try:
        start = datetime.fromisoformat(started_at)
        return max(0, int((datetime.utcnow() - start).total_seconds() * 1000))
    except Exception:
        return 0


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return ""
        host = (parsed.hostname or "").lower().strip()
        path = (parsed.path or "").rstrip("/")
        query = parsed.query or ""
        if not host:
            return ""
        normalized = f"{parsed.scheme}://{host}{path}"
        if query:
            normalized = f"{normalized}?{query}"
        return normalized
    except Exception:
        return ""


def _tokenize(text: str) -> List[str]:
    raw = str(text or "").lower().strip()
    if not raw:
        return []

    chunks = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", raw)
    out: List[str] = []
    cjk_hints = (
        "退役",
        "复出",
        "夺冠",
        "去世",
        "辟谣",
        "回应",
        "宣布",
        "否认",
        "确认",
        "爆料",
        "传闻",
        "处罚",
    )

    def _is_cjk(token: str) -> bool:
        return bool(token) and bool(re.fullmatch(r"[\u4e00-\u9fff]+", token))

    def _append(val: str) -> None:
        value = str(val or "").strip()
        if len(value) >= 2 and value not in out:
            out.append(value)

    for chunk in chunks:
        if len(chunk) < 2:
            continue
        _append(chunk)
        if not _is_cjk(chunk):
            continue

        trimmed = re.sub(r"[了啊呀嘛吧呢吗哈]+$", "", chunk).strip()
        if len(trimmed) >= 2:
            _append(trimmed)

        for hint in cjk_hints:
            pos = chunk.find(hint)
            if pos > 0:
                prefix = chunk[:pos].strip()
                if len(prefix) >= 2:
                    _append(prefix)
                    _append(f"{prefix}{hint}")

        # CJK 连续词做 2/3-gram，提升“整句 vs 短语”匹配稳定性。
        if len(chunk) >= 4:
            max_grams = 24
            used = 0
            for n in (2, 3):
                if len(chunk) < n:
                    continue
                for idx in range(0, len(chunk) - n + 1):
                    _append(chunk[idx : idx + n])
                    used += 1
                    if used >= max_grams:
                        break
                if used >= max_grams:
                    break
    return out


def _keyword_relevance_score(keyword: str, text_blob: str) -> float:
    kw_tokens = set(_tokenize(keyword))
    tx_tokens = set(_tokenize(text_blob))
    token_score = 0.0
    if kw_tokens and tx_tokens:
        inter = kw_tokens.intersection(tx_tokens)
        token_score = float(len(inter)) / float(max(1, len(kw_tokens)))

    # CJK 兜底：若关键词是中文短语，允许按短语重叠计算相关度，降低“整句不等于短句”误伤。
    kw_cjk = re.findall(r"[\u4e00-\u9fff]{2,}", str(keyword or ""))
    txt_cjk = re.findall(r"[\u4e00-\u9fff]{2,}", str(text_blob or ""))
    cjk_score = 0.0
    if kw_cjk and txt_cjk:
        main_kw = max(kw_cjk, key=len)
        if main_kw and main_kw in str(text_blob or ""):
            cjk_score = 1.0
        elif len(main_kw) >= 2:
            kw_grams = {main_kw[i : i + 2] for i in range(0, len(main_kw) - 1)}
            txt_grams = set()
            for row in txt_cjk:
                if len(row) < 2:
                    continue
                txt_grams.update({row[i : i + 2] for i in range(0, len(row) - 1)})
            if kw_grams and txt_grams:
                cjk_score = float(len(kw_grams & txt_grams)) / float(max(1, len(kw_grams)))
    return round(max(token_score, cjk_score), 4)


def _looks_like_specific_content_url(url: str) -> bool:
    try:
        parsed = urlparse(str(url or ""))
        path = (parsed.path or "").strip("/")
        query = (parsed.query or "").lower()
        if parsed.scheme not in {"http", "https"}:
            return False
        if not (parsed.hostname or ""):
            return False
        if not path:
            return False
        if any(k in query for k in ["q=", "query=", "search=", "keyword=", "wd="]):
            return False
        bad_parts = {"search", "topic", "topics", "tag", "tags", "home", "index"}
        parts = [p.lower() for p in path.split("/") if p.strip()]
        if any(p in bad_parts for p in parts):
            return False
        return True
    except Exception:
        return False


def _stable_hash(text: str) -> str:
    return hashlib.sha1(str(text or "").encode("utf-8", errors="ignore")).hexdigest()


def _httpx_trust_env_candidates() -> List[bool]:
    out: List[bool] = []
    for val in (_HTTPX_TRUST_ENV, not _HTTPX_TRUST_ENV):
        if val not in out:
            out.append(val)
    return out

# 官方媒体账号映射（社交媒体上的官方账号）
OFFICIAL_MEDIA_ACCOUNTS = {
    # 新华社官方账号
    "新华社": {"tier": 1, "platforms": ["weibo", "twitter", "wechat"]},
    "新华视点": {"tier": 1, "platforms": ["weibo"]},
    "新华网": {"tier": 1, "platforms": ["weibo", "twitter"]},
    "Xinhua News Agency": {"tier": 1, "platforms": ["twitter"]},
    # 央视官方账号
    "央视新闻": {"tier": 1, "platforms": ["weibo"]},
    "CCTV": {"tier": 1, "platforms": ["twitter"]},
    # 人民日报
    "人民日报": {"tier": 1, "platforms": ["weibo"]},
    # 体育官方
    "中国田径协会": {"tier": 1, "platforms": ["weibo", "website"]},
    "世界田联": {"tier": 1, "platforms": ["twitter", "website"]},
    "World Athletics": {"tier": 1, "platforms": ["twitter"]},
    # 奥委会
    "中国奥委会": {"tier": 1, "platforms": ["weibo", "website"]},
    "Olympics": {"tier": 1, "platforms": ["twitter"]},
}

# Tier1 来源名称

# Tier1 来源名称 - 中央官方与权威新闻门户
TIER1_SOURCE_NAMES = {
    # ===== 中央官方新闻门户 =====
    "xinhua", "新华社", "新华网", "新华视点", "xinhuashe",
    "people", "人民日报", "人民网", "peoples_daily", "people_com_cn",
    "cctv", "央视", "央视新闻", "cctv_news",
    "chinanews", "中新社", "中国新闻网",
    "china_org_cn", "中国网",
    "cri", "国际在线",
    "cnr", "央广网",
    # ===== 国际官方机构 =====
    "who", "世界卫生组织",
    "cdc", "疾病预防控制中心",
    "nhc", "国家卫健委",
    "olympics", "奥林匹克", "国际奥委会",
    "worldathletics", "世界田联", "国际田联",
    "athletics_org_cn", "中国田协", "中国田径协会",
}

# Tier2 来源名称 - 商业门户与深度评论
TIER2_SOURCE_NAMES = {
    # ===== 商业门户与综合新闻 =====
    "qq", "腾讯新闻", "tencent_news",
    "sina", "新浪新闻", "sina_news",
    "163", "netease", "网易新闻",
    "sohu", "搜狐新闻",
    "ifeng", "凤凰资讯",
    # ===== 深度与评论类资讯平台 =====
    "guancha", "观察者网",
    "thepaper", "澎湃新闻", "澎湃",
    "caixin", "财新", "财新网",
    # ===== 国际主流媒体 =====
    "reuters", "路透社",
    "ap_news", "ap", "美联社",
    "bbc", "英国广播公司",
    "guardian", "卫报",
}


def _tier_for_source_name(source_name: str, platform: str = "") -> int:
    """根据来源名称判断层级"""
    name = str(source_name or "").lower().strip()
    plat = str(platform or "").lower().strip()
    
    # 检查 Tier1 来源名称
    for t1 in TIER1_SOURCE_NAMES:
        if t1.lower() in name:
            return 1
    
    # 检查官方媒体账号映射
    for official_name, info in OFFICIAL_MEDIA_ACCOUNTS.items():
        if official_name in source_name or source_name in official_name:
            if plat in info.get("platforms", []) or not plat:
                return info.get("tier", 2)
    
    # 检查 Tier2 来源名称
    for t2 in TIER2_SOURCE_NAMES:
        if t2.lower() in name:
            return 2
    
    return 3


def _tier_for_evidence(url: str, source_name: str = "", platform: str = "") -> int:
    """
    综合判断证据层级 - 同时考虑 URL 和来源名称
    
    当证据来自官方媒体的社交媒体账号时（如新华社微博），
    应该根据来源名称而非 URL 来判断层级。
    """
    # 优先根据来源名称判断
    if source_name:
        name_tier = _tier_for_source_name(source_name, platform)
        if name_tier <= 2:
            return name_tier
    
    # 回退到 URL 判断
    return _tier_for_url(url)
