"""
Evidence Credibility Scoring System.
证据可信度评分系统

Implements a multi-factor credibility scoring model:
evidence_score = 0.35*source_tier_score
                + 0.20*recency_score
                + 0.20*corroboration_score
                + 0.15*extraction_confidence
                + 0.10*provenance_score
                - 0.30*penalty_flags

Author: Aletheia Team
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Set
from enum import Enum
import structlog

logger = structlog.get_logger()


class SourceTier(str, Enum):
    """Source credibility tiers"""
    S = "S"  # 权威媒体/官方机构 (trust_score: 0.95)
    A = "A"  # 主流门户/商业媒体 (trust_score: 0.75)
    B = "B"  # 大型内容平台 (trust_score: 0.55)
    C = "C"  # 高噪声社媒 (trust_score: 0.35)


# Tier trust scores
TIER_TRUST_SCORES = {
    SourceTier.S: 0.95,
    SourceTier.A: 0.75,
    SourceTier.B: 0.55,
    SourceTier.C: 0.35,
}

# Scoring weights
SCORING_WEIGHTS = {
    "source_tier": 0.35,
    "recency": 0.20,
    "corroboration": 0.20,
    "extraction_confidence": 0.15,
    "provenance": 0.10,
    "penalty": 0.30,  # Subtracted
}


@dataclass
class PenaltyFlags:
    """Penalty flags for evidence scoring"""
    is_deleted: bool = False
    is_updated: bool = False
    has_correction: bool = False
    content_missing: bool = False
    fetch_failed: bool = False
    suspicious_redirect: bool = False
    low_extraction_confidence: bool = False
    flagged_as_misinformation: bool = False

    def to_list(self) -> List[str]:
        """Convert to list of flag names"""
        flags = []
        if self.is_deleted:
            flags.append("is_deleted")
        if self.is_updated:
            flags.append("is_updated")
        if self.has_correction:
            flags.append("has_correction")
        if self.content_missing:
            flags.append("content_missing")
        if self.fetch_failed:
            flags.append("fetch_failed")
        if self.suspicious_redirect:
            flags.append("suspicious_redirect")
        if self.low_extraction_confidence:
            flags.append("low_extraction_confidence")
        if self.flagged_as_misinformation:
            flags.append("flagged_as_misinformation")
        return flags

    def calculate_penalty(self) -> float:
        """Calculate total penalty score"""
        penalty = 0.0
        if self.is_deleted:
            penalty += 0.5
        if self.has_correction:
            penalty += 0.3
        if self.content_missing:
            penalty += 0.4
        if self.fetch_failed:
            penalty += 0.3
        if self.suspicious_redirect:
            penalty += 0.2
        if self.low_extraction_confidence:
            penalty += 0.1
        if self.flagged_as_misinformation:
            penalty += 0.8  # Highest penalty
        return min(penalty, 1.0)


@dataclass
class ScoringContext:
    """Context for evidence scoring"""
    # Source information
    source_tier: SourceTier = SourceTier.C
    source_domain: str = ""
    platform: str = ""

    # Temporal information
    publish_time: Optional[datetime] = None
    crawl_time: datetime = field(default_factory=datetime.utcnow)
    event_time: Optional[datetime] = None  # Time of event being fact-checked

    # Extraction information
    extraction_method: str = "fallback"
    extraction_confidence: float = 0.0

    # Corroboration
    corroborating_sources: Set[str] = field(default_factory=set)
    unique_domains_count: int = 1

    # Provenance
    is_original_source: bool = False
    is_aggregation: bool = False
    canonical_matches_original: bool = True

    # Penalty flags
    penalties: PenaltyFlags = field(default_factory=PenaltyFlags)


@dataclass
class ScoringResult:
    """Result of evidence scoring"""
    evidence_score: float
    source_tier_score: float
    recency_score: float
    corroboration_score: float
    extraction_score: float
    provenance_score: float
    penalty_score: float

    components: Dict[str, float] = field(default_factory=dict)
    penalty_flags: List[str] = field(default_factory=list)

    credibility_level: str = "LOW"  # VERY_HIGH, HIGH, MEDIUM, LOW, VERY_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_score": self.evidence_score,
            "source_tier_score": self.source_tier_score,
            "recency_score": self.recency_score,
            "corroboration_score": self.corroboration_score,
            "extraction_score": self.extraction_score,
            "provenance_score": self.provenance_score,
            "penalty_score": self.penalty_score,
            "components": self.components,
            "penalty_flags": self.penalty_flags,
            "credibility_level": self.credibility_level,
        }


class EvidenceScorer:
    """
    Evidence credibility scorer.
    证据可信度评分器
    """

    # Recency thresholds (in hours)
    RECENCY_THRESHOLDS = {
        "breaking": 6,      # < 6 hours: full score
        "recent": 24,       # < 24 hours: high score
        "current": 72,      # < 72 hours: medium score
        "dated": 168,       # < 1 week: low score
        "old": 720,         # < 30 days: very low score
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        tier_scores: Optional[Dict[SourceTier, float]] = None,
    ):
        self.weights = weights or SCORING_WEIGHTS.copy()
        self.tier_scores = tier_scores or TIER_TRUST_SCORES.copy()

    def score(self, context: ScoringContext) -> ScoringResult:
        """
        Calculate evidence credibility score.
        计算证据可信度评分

        Args:
            context: Scoring context with all relevant information

        Returns:
            ScoringResult with detailed score breakdown
        """
        # Calculate component scores
        source_tier_score = self._score_source_tier(context)
        recency_score = self._score_recency(context)
        corroboration_score = self._score_corroboration(context)
        extraction_score = self._score_extraction(context)
        provenance_score = self._score_provenance(context)
        penalty_score = context.penalties.calculate_penalty()

        # Calculate weighted sum
        base_score = (
            self.weights["source_tier"] * source_tier_score
            + self.weights["recency"] * recency_score
            + self.weights["corroboration"] * corroboration_score
            + self.weights["extraction_confidence"] * extraction_score
            + self.weights["provenance"] * provenance_score
        )

        # Apply penalty
        final_score = max(0.0, base_score - self.weights["penalty"] * penalty_score)
        final_score = min(1.0, final_score)  # Cap at 1.0

        # Determine credibility level
        credibility_level = self._get_credibility_level(final_score)

        return ScoringResult(
            evidence_score=round(final_score, 4),
            source_tier_score=round(source_tier_score, 4),
            recency_score=round(recency_score, 4),
            corroboration_score=round(corroboration_score, 4),
            extraction_score=round(extraction_score, 4),
            provenance_score=round(provenance_score, 4),
            penalty_score=round(penalty_score, 4),
            components={
                "source_tier_weighted": round(self.weights["source_tier"] * source_tier_score, 4),
                "recency_weighted": round(self.weights["recency"] * recency_score, 4),
                "corroboration_weighted": round(self.weights["corroboration"] * corroboration_score, 4),
                "extraction_weighted": round(self.weights["extraction_confidence"] * extraction_score, 4),
                "provenance_weighted": round(self.weights["provenance"] * provenance_score, 4),
                "penalty_weighted": round(self.weights["penalty"] * penalty_score, 4),
            },
            penalty_flags=context.penalties.to_list(),
            credibility_level=credibility_level,
        )

    def _score_source_tier(self, context: ScoringContext) -> float:
        """Score based on source tier"""
        return self.tier_scores.get(context.source_tier, 0.35)

    def _score_recency(self, context: ScoringContext) -> float:
        """
        Score based on temporal relevance.
        基于时效性评分
        """
        # Use event time if available, otherwise use crawl time
        reference_time = context.event_time or context.crawl_time

        if not context.publish_time:
            # No publish time, assume moderate recency
            return 0.5

        age_hours = (reference_time - context.publish_time).total_seconds() / 3600

        # Handle future dates (likely errors)
        if age_hours < 0:
            return 0.7

        if age_hours < self.RECENCY_THRESHOLDS["breaking"]:
            return 1.0
        elif age_hours < self.RECENCY_THRESHOLDS["recent"]:
            return 0.85
        elif age_hours < self.RECENCY_THRESHOLDS["current"]:
            return 0.70
        elif age_hours < self.RECENCY_THRESHOLDS["dated"]:
            return 0.50
        elif age_hours < self.RECENCY_THRESHOLDS["old"]:
            return 0.30
        else:
            return 0.15

    def _score_corroboration(self, context: ScoringContext) -> float:
        """
        Score based on independent source corroboration.
        基于独立来源证实评分
        """
        # Higher score for more unique domains corroborating
        domain_count = context.unique_domains_count

        if domain_count >= 5:
            return 1.0
        elif domain_count >= 4:
            return 0.85
        elif domain_count >= 3:
            return 0.70
        elif domain_count >= 2:
            return 0.55
        else:
            return 0.35

    def _score_extraction(self, context: ScoringContext) -> float:
        """
        Score based on extraction method and confidence.
        基于抽取方法与置信度评分
        """
        method_scores = {
            "template_rules": 0.95,
            "jsonld": 0.80,
            "opengraph": 0.70,
            "trafilatura": 0.65,
            "readability": 0.60,
            "fallback": 0.50,
        }

        base_score = method_scores.get(context.extraction_method, 0.50)

        # Adjust by extraction confidence
        confidence_factor = context.extraction_confidence

        return base_score * confidence_factor if confidence_factor > 0 else base_score * 0.5

    def _score_provenance(self, context: ScoringContext) -> float:
        """
        Score based on content provenance.
        基于内容来源评分
        """
        score = 0.5  # Default

        # Original source is preferred
        if context.is_original_source:
            score = 0.95
        elif context.canonical_matches_original:
            score = 0.80
        elif context.is_aggregation:
            score = 0.40

        return score

    def _get_credibility_level(self, score: float) -> str:
        """Determine credibility level from score"""
        if score >= 0.90:
            return "VERY_HIGH"
        elif score >= 0.70:
            return "HIGH"
        elif score >= 0.50:
            return "MEDIUM"
        elif score >= 0.30:
            return "LOW"
        else:
            return "VERY_LOW"


class SourceTierResolver:
    """
    Resolve source tier from domain/platform.
    从域名/平台解析来源层级
    """

    # Domain tier mappings
    TIER_S_DOMAINS = {
        # 官方媒体
        "news.cn", "xinhuanet.com",  # 新华社
        "people.com.cn",  # 人民网
        "cctv.com", "cntv.cn",  # 央视
        "gov.cn",  # 国务院
        "china.com.cn",  # 中国网
        "chinanews.com.cn",  # 中新网
        # 官方机构
        "nhc.gov.cn",  # 卫健委
        "stats.gov.cn",  # 统计局
        "samr.gov.cn",  # 市监总局
        "csrc.gov.cn",  # 证监会
        "mps.gov.cn",  # 公安部
        # 国际组织
        "who.int", "un.org", "wto.org",
    }

    TIER_A_DOMAINS = {
        # 主流门户
        "thepaper.cn",  # 澎湃
        "caixin.com",  # 财新
        "jiemian.com",  # 界面
        "yicai.com",  # 第一财经
        "china daily.com.cn",
        # 国际媒体
        "reuters.com", "bbc.com", "bbc.co.uk",
        "apnews.com", "theguardian.com",
    }

    TIER_B_DOMAINS = {
        # 商业门户
        "sohu.com", "sina.com.cn", "163.com", "ifeng.com",
        "qq.com", "toutiao.com",
        # 财经科技
        "36kr.com", "tmtpost.com", "ithome.com",
    }

    TIER_C_DOMAINS = {
        # 社媒平台
        "weibo.com", "weibo.cn",
        "zhihu.com",
        "bilibili.com",
        "douyin.com",
        "xiaohongshu.com",
        "kuaishou.com",
        "douban.com",
        # 国际社媒
        "twitter.com", "x.com",
        "facebook.com",
        "youtube.com",
        "reddit.com",
    }

    def resolve(self, domain: str) -> SourceTier:
        """
        Resolve source tier from domain.
        从域名解析来源层级

        Args:
            domain: Domain name (e.g., "news.cn")

        Returns:
            SourceTier enum value
        """
        domain_lower = domain.lower()

        # Check each tier
        for tier_domain in self.TIER_S_DOMAINS:
            if domain_lower.endswith(tier_domain) or domain_lower == tier_domain:
                return SourceTier.S

        for tier_domain in self.TIER_A_DOMAINS:
            if domain_lower.endswith(tier_domain) or domain_lower == tier_domain:
                return SourceTier.A

        for tier_domain in self.TIER_B_DOMAINS:
            if domain_lower.endswith(tier_domain) or domain_lower == tier_domain:
                return SourceTier.B

        for tier_domain in self.TIER_C_DOMAINS:
            if domain_lower.endswith(tier_domain) or domain_lower == tier_domain:
                return SourceTier.C

        # Default to C for unknown domains
        return SourceTier.C


# Convenience functions
def score_evidence(
    source_tier: str,
    publish_time: Optional[datetime] = None,
    extraction_confidence: float = 0.0,
    unique_domains: int = 1,
    is_deleted: bool = False,
    has_correction: bool = False,
) -> ScoringResult:
    """
    Convenience function to score evidence.
    便捷的证据评分函数
    """
    tier = SourceTier(source_tier) if isinstance(source_tier, str) else source_tier

    context = ScoringContext(
        source_tier=tier,
        publish_time=publish_time,
        extraction_confidence=extraction_confidence,
        unique_domains_count=unique_domains,
        penalties=PenaltyFlags(
            is_deleted=is_deleted,
            has_correction=has_correction,
        ),
    )

    scorer = EvidenceScorer()
    return scorer.score(context)


def resolve_tier(domain: str) -> str:
    """Convenience function to resolve source tier"""
    resolver = SourceTierResolver()
    return resolver.resolve(domain).value