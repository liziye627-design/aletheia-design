"""
强门槛结论判定器 - 改进版

修复问题：
1. xinhua 等 Tier1 证据应正确识别
2. 实现 fail-closed 三段式输出
3. 改进证据层级判定逻辑
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple, Set


INSUFFICIENT_GATE_REASONS = {
    "NO_LINKED_EVIDENCE",
    "INSUFFICIENT_HIGH_TIER_EVIDENCE",
    "INSUFFICIENT_PRIMARY_EVIDENCE",
    "LOW_HIGH_TIER_PLATFORM_COVERAGE",
}

# Tier1 平台定义 - 官方/监管/权威公共机构
TIER1_PLATFORMS: Set[str] = {
    # 更多体育官方
    "china_athletics", "athletics_org_cn", "sport_gov_cn", "olympic_cn",
    "worldathletics", "olympics", "fifa", "uefa", "nba", "cba",
    # 更多中国官方机构
    "ndrc", "mofcom", "mof", "most", "moe", "mohrss", "mnr", "mee",
    "stats", "customs", "pbc", "cbirc", "csrc", "safe",
    # 更多国际官方
    "imf", "oecd", "wto", "fao", "unesco", "unicef", "unhcr",
    "ecb", "boe", "boj", "fed",
    # ===== 中央官方与权威新闻门户 =====
    "xinhua", "xinhuanet", "news_cn", "xinhuashe",  # 新华网
    "people", "peoples_daily", "people_com_cn",  # 人民网
    "cctv", "cctv_news", "cctv_com",  # 央视网
    "chinanews", "chinanews_com_cn",  # 中国新闻网
    "china_org_cn", "china_com_cn",  # 中国网
    "cri", "cri_cn", "crionline",  # 国际在线
    "cnr", "cnr_cn", "cnr_news",  # 央广网
}


# Tier2 平台定义 - 主流媒体与可信社交平台
TIER2_PLATFORMS: Set[str] = {
    "weibo", "zhihu", "xiaohongshu", "douyin", "bilibili",
    "kuaishou", "douban", "reddit",
    "twitter", "github", "stackoverflow",
    # ===== 商业门户与综合新闻 =====
    "qq", "qq_news", "tencent_news",  # 腾讯新闻
    "sina", "sina_news", "sina_com_cn",  # 新浪新闻
    "163", "netease", "netease_news", "news_163",  # 网易新闻
    "sohu", "sohu_news",  # 搜狐新闻
    "ifeng", "ifeng_news",  # 凤凰资讯
    # ===== 深度与评论类资讯平台 =====
    "guancha", "guancha_cn",  # 观察者网
    "thepaper", "thepaper_cn", "pengpai",  # 澎湃新闻
    "caixin", "caixin_com",  # 财新网
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _get_platform_tier(platform: str) -> int:
    """获取平台层级（保守判定，避免误把普通媒体升为 Tier1）"""
    p = str(platform or "").lower().strip()
    # 去除可能的域名后缀
    p_clean = p.replace(".", "_").replace("-", "_")
    
    # 精确匹配 Tier1
    if p in TIER1_PLATFORMS or p_clean in TIER1_PLATFORMS:
        return 1
    
    # 社交媒体关键词（默认保持为 Tier3，避免误入“高阶证据”）
    social_markers = ["weibo", "zhihu", "douyin", "xiaohongshu", "bilibili"]
    if any(m in p for m in social_markers):
        return 3

    # 精确匹配 Tier2
    if p in TIER2_PLATFORMS or p_clean in TIER2_PLATFORMS:
        return 2
    
    return 3


def _is_official_source(platform: str) -> bool:
    """判断是否为官方信源"""
    return _get_platform_tier(platform) == 1


def _weight(row: Dict[str, Any]) -> float:
    """计算证据权重 - 改进版：Tier1 官方媒体权重更高"""
    source_tier = _get_platform_tier(row.get("source_name") or row.get("platform") or "")

    # 检查是否为顶级官方媒体
    platform = str(row.get("source_name") or row.get("platform") or "").lower()
    tier1_official_bonus = 1.0
    if source_tier == 1:
        tier1_officials = {"xinhua", "peoples_daily", "cctv", "who", "cdc", "un_news", "sec", "csrc", "新华社", "人民日报", "央视"}
        if any(official in platform for official in tier1_officials):
            tier1_official_bonus = 1.5  # 顶级官方媒体额外加成

    # Tier1 权重提升至 1.5，加上官方加成可达 2.25
    tier_weight = {1: 1.5 * tier1_official_bonus, 2: 0.7, 3: 0.4}.get(source_tier, 0.4)

    return (
        tier_weight
        * _safe_float(row.get("source_score"), 0.35)
        * max(0.05, _safe_float(row.get("quality_score"), 0.35))
        * max(0.2, _safe_float(row.get("confidence"), 0.55))
    )


def _next_queries(claim_text: str, reasons: List[str]) -> List[str]:
    """生成下一步查询建议"""
    base = [claim_text, f"{claim_text} 官方 通告"]
    
    if "ENTITY_AMBIGUITY" in reasons:
        base.append(f"{claim_text} 全称 官方公告")
    if "INSUFFICIENT_HIGH_TIER_EVIDENCE" in reasons:
        base.append(f"{claim_text} site:news.cn")
        base.append(f"{claim_text} site:xinhuanet.com")
    if "CONFLICTING_HIGH_TIER_EVIDENCE" in reasons:
        base.append(f"{claim_text} 官方 辟谣")
    
    seen: Set[str] = set()
    out: List[str] = []
    for q in base:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:6]


class StrongVerdictGate:
    """主张级强门槛判定 - 改进版"""

    def evaluate_claim(
        self,
        *,
        claim: Dict[str, Any],
        linked_evidence: Iterable[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
        rows = [row for row in (linked_evidence or []) if isinstance(row, dict)]
        claim_id = str(claim.get("claim_id") or "")
        claim_text = str(claim.get("text") or "")

        stance_summary = Counter(str(row.get("stance") or "unclear") for row in rows)
        
        # 改进：使用 _get_platform_tier 函数判断层级
        high_tier_rows = []
        for row in rows:
            platform = row.get("source_name") or row.get("platform") or ""
            tier = _get_platform_tier(platform)
            # 同时检查原有的 source_tier 字段
            orig_tier = int(row.get("source_tier") or 4)
            effective_tier = min(tier, orig_tier)
            
            if effective_tier <= 2:
                validation_status = str(row.get("validation_status") or "").lower()
                if validation_status not in {"unreachable", "invalid", "discarded"}:
                    row["_effective_tier"] = effective_tier
                    high_tier_rows.append(row)
        
        tier1_rows = [r for r in high_tier_rows if r.get("_effective_tier") == 1]
        tier2_rows = [r for r in high_tier_rows if r.get("_effective_tier") == 2]
        
        high_tier_platforms = {
            str(row.get("source_name") or row.get("platform") or "unknown")
            for row in high_tier_rows
        }
        
        high_support = [row for row in high_tier_rows if str(row.get("stance")) == "support"]
        high_refute = [row for row in high_tier_rows if str(row.get("stance")) == "refute"]
        
        has_evidence_class = any("evidence_class" in row for row in rows)
        primary_like_rows = [row for row in rows if str(row.get("evidence_class") or "").lower() == "primary"]

        support_weight = sum(_weight(row) for row in rows if str(row.get("stance")) == "support")
        refute_weight = sum(_weight(row) for row in rows if str(row.get("stance")) == "refute")
        mixed_weight = sum(_weight(row) for row in rows if str(row.get("stance")) in {"mixed", "context"})
        
        support_platforms = {
            str(row.get("source_name") or row.get("platform") or "unknown")
            for row in rows
            if str(row.get("stance")) == "support"
        }

        gate_passed = True
        gate_reasons: List[str] = []

        # 门槛检查 - 改进版
        if not rows:
            gate_passed = False
            gate_reasons.append("NO_LINKED_EVIDENCE")
        
        # 改进：Tier1 >= 1 或 Tier2 >= 2 即可通过高阶证据门槛
        if len(tier1_rows) < 1 and len(tier2_rows) < 2:
            gate_passed = False
            gate_reasons.append("INSUFFICIENT_HIGH_TIER_EVIDENCE")
            # 添加详细信息
            gate_reasons.append(f"TIER1_COUNT:{len(tier1_rows)}")
            gate_reasons.append(f"TIER2_COUNT:{len(tier2_rows)}")
        
        if has_evidence_class and rows and not primary_like_rows:
            gate_passed = False
            gate_reasons.append("INSUFFICIENT_PRIMARY_EVIDENCE")
        
        # 高层证据应至少覆盖 2 个平台
        if len(high_tier_platforms) < 2:
            gate_passed = False
            gate_reasons.append("LOW_HIGH_TIER_PLATFORM_COVERAGE")
        
        if high_support and high_refute:
            gate_passed = False
            gate_reasons.append("CONFLICTING_HIGH_TIER_EVIDENCE")

        support_count = int(stance_summary.get("support", 0))
        refute_count = int(stance_summary.get("refute", 0))
        tier1_support = [r for r in tier1_rows if str(r.get("stance")) == "support"]

        # 有限高阶证据下的强支持覆盖（仅允许覆盖“证据不足类”软门槛）
        limited_high_tier_strong_support = (
            (not gate_passed)
            and support_count >= 5
            and refute_count == 0
            and len(rows) >= 5
            and (len(support_platforms) >= 2 or len(tier1_support) >= 1)
        )
        if limited_high_tier_strong_support:
            soft_only_reasons = {
                "INSUFFICIENT_HIGH_TIER_EVIDENCE",
                "LOW_HIGH_TIER_PLATFORM_COVERAGE",
                "DOMAIN_SOURCE_MISMATCH",
            }
            effective_reasons = {r for r in gate_reasons if not str(r).startswith("TIER")}
            if effective_reasons and effective_reasons.issubset(soft_only_reasons):
                gate_passed = True
                gate_reasons = sorted(
                    list(set(gate_reasons + ["LIMITED_HIGH_TIER_STRONG_SUPPORT"]))
                )

        # 判定结论
        if gate_passed:
            delta = support_weight - refute_weight
            if delta >= 0.2:  # 降低阈值
                verdict = "SUPPORTED"
            elif delta <= -0.2:
                verdict = "REFUTED"
            else:
                verdict = "UNCERTAIN"
                gate_reasons.append("INSUFFICIENT_SIGNAL_SEPARATION")
        else:
            if "CONFLICTING_HIGH_TIER_EVIDENCE" in gate_reasons:
                verdict = "UNCERTAIN"
            elif any(reason in INSUFFICIENT_GATE_REASONS for reason in gate_reasons):
                verdict = "REVIEW_REQUIRED"
            else:
                verdict = "UNCERTAIN"

        # 计算置信分数
        denom = max(1e-6, support_weight + refute_weight + mixed_weight)
        if verdict == "SUPPORTED":
            score = support_weight / denom
        elif verdict == "REFUTED":
            score = refute_weight / denom
        else:
            score = max(support_weight, refute_weight) / denom

        # 根据证据质量调整分数 - Tier1 官方媒体加分
        tier1_support_count = len(tier1_support)
        if tier1_support_count > 0:
            # 每个 Tier1 官方源加分 0.12，多个叠加最高加 0.40
            bonus = min(0.40, 0.12 * tier1_support_count)
            score = min(1.0, score + bonus)

        # 不确定/需复核结论严格限幅，避免“高分但不确定”
        if verdict in {"UNCERTAIN", "REVIEW_REQUIRED"}:
            score = min(score, 0.59)

        score = round(max(0.0, min(1.0, score)), 4)

        conflicts: List[str] = []
        if high_support and high_refute:
            support_src = " / ".join(
                sorted({str(row.get("source_name") or "source") for row in high_support})[:3]
            )
            refute_src = " / ".join(
                sorted({str(row.get("source_name") or "source") for row in high_refute})[:3]
            )
            conflicts.append(f"High-tier support vs refute: {support_src} <> {refute_src}")

        claim_result = {
            "claim_id": claim_id,
            "text": claim_text,
            "type": str(claim.get("type") or "generic_claim"),
            "stance_summary": {
                "support": int(stance_summary.get("support", 0)),
                "refute": int(stance_summary.get("refute", 0)),
                "mixed": int(stance_summary.get("mixed", 0)),
                "unclear": int(stance_summary.get("unclear", 0))
                + int(stance_summary.get("context", 0)),
            },
            "verdict": verdict,
            "score": score,
            "gate_passed": gate_passed,
            "gate_reasons": sorted(list(set(gate_reasons))),
            "evidence_ids": [str(row.get("evidence_id") or "") for row in rows if row.get("evidence_id")],
            "conflicts": conflicts,
            "next_queries": _next_queries(claim_text, gate_reasons),
            # 新增：证据层级统计
            "tier_stats": {
                "tier1_count": len(tier1_rows),
                "tier2_count": len(tier2_rows),
                "tier1_platforms": list({r.get("source_name") or r.get("platform") for r in tier1_rows}),
                "tier2_platforms": list({r.get("source_name") or r.get("platform") for r in tier2_rows}),
            }
        }

        review_item = None
        if verdict == "UNCERTAIN":
            priority = "high" if "CONFLICTING_HIGH_TIER_EVIDENCE" in gate_reasons else "medium"
            review_item = {
                "claim_id": claim_id,
                "priority": priority,
                "reasons": sorted(list(set(gate_reasons or ["INSUFFICIENT_SIGNAL_SEPARATION"]))),
            }
        elif verdict == "REVIEW_REQUIRED":
            priority = "high" if "INSUFFICIENT_HIGH_TIER_EVIDENCE" in gate_reasons else "medium"
            review_item = {
                "claim_id": claim_id,
                "priority": priority,
                "reasons": sorted(list(set(gate_reasons or ["REVIEW_REQUIRED"]))),
            }
        return claim_result, review_item

    def evaluate_all(
        self, *, claims: Iterable[Dict[str, Any]], claim_links: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        outputs: List[Dict[str, Any]] = []
        review_queue: List[Dict[str, Any]] = []

        for claim in claims or []:
            claim_id = str(claim.get("claim_id") or "")
            linked = claim_links.get(claim_id) or []
            result, review_item = self.evaluate_claim(claim=claim, linked_evidence=linked)
            outputs.append(result)
            if review_item:
                review_queue.append(review_item)

        verdict_counter = Counter(str(row.get("verdict") or "UNCERTAIN") for row in outputs)
        if verdict_counter.get("REVIEW_REQUIRED", 0) > 0:
            run_verdict = "REVIEW_REQUIRED"
        elif verdict_counter.get("UNCERTAIN", 0) > 0:
            run_verdict = "UNCERTAIN"
        elif verdict_counter.get("REFUTED", 0) > verdict_counter.get("SUPPORTED", 0):
            run_verdict = "REFUTED"
        elif verdict_counter.get("SUPPORTED", 0) > 0:
            run_verdict = "SUPPORTED"
        else:
            run_verdict = "UNCERTAIN"

        return {
            "claims": outputs,
            "review_queue": review_queue,
            "run_verdict": run_verdict,
            "summary": dict(verdict_counter),
        }
