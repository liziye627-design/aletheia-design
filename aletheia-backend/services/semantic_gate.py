"""
语义闸门模块 - 防止噪声证据进入证据池

根据复盘报告的问题，实现两阶段召回策略：
- 第一阶段：追求覆盖，保留"候选集"身份
- 第二阶段：实体绑定/主题匹配/时间窗匹配/语言匹配，通过后才进入"证据池"
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime


@dataclass
class GateResult:
    """闸门判定结果"""
    passed: bool
    stage: str  # "candidate" | "evidence_pool" | "rejected"
    reasons: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    entity_match: bool = False
    topic_match: bool = False


class SemanticGate:
    """语义闸门 - 过滤噪声证据"""
    
    # 候选集身份标记
    CANDIDATE_MARKERS = {
        "hot_fallback",
        "rss_emergency_fallback",
        "web_search_fallback",
        "all_fallback_results",
    }
    
    # 相关性阈值
    RELEVANCE_THRESHOLD_HIGH = 0.6
    RELEVANCE_THRESHOLD_MEDIUM = 0.35
    RELEVANCE_THRESHOLD_LOW = 0.15
    KEYWORD_MATCH_MIN = 0.2
    
    # 时间窗口（天）
    TIME_WINDOW_DAYS = 365
    
    def __init__(
        self,
        claim_text: str,
        keyword: str,
        entity_names: Optional[List[str]] = None,
        event_date_hint: Optional[str] = None,
        locale: str = "cn",
    ):
        self.claim_text = claim_text.lower().strip()
        self.keyword = keyword.lower().strip()
        self.entities = [e.lower().strip() for e in (entity_names or []) if e]
        self.event_date_hint = event_date_hint
        self.locale = locale
        self._extract_entities_from_claim()
        self.time_keywords = self._extract_time_keywords()
        
    def _extract_entities_from_claim(self) -> None:
        """从主张中提取实体名称"""
        # 人名模式（中文姓名：2-4个汉字）
        cjk_name_pattern = r'[\u4e00-\u9fff]{2,4}'
        matches = re.findall(cjk_name_pattern, self.claim_text)
        for m in matches:
            if m not in self.entities and len(m) >= 2:
                self.entities.append(m.lower())
        
        # 英文名模式
        en_name_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'
        matches = re.findall(en_name_pattern, self.claim_text, re.IGNORECASE)
        for m in matches:
            if m.lower() not in self.entities:
                self.entities.append(m.lower())
    
    def _extract_time_keywords(self) -> List[str]:
        """提取时间相关关键词"""
        time_patterns = [
            r'\d{4}年\d{1,2}月\d{1,2}日',
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'\d{1,2}月\d{1,2}日',
        ]
        keywords = []
        for pattern in time_patterns:
            matches = re.findall(pattern, self.claim_text)
            keywords.extend(matches)
        return keywords
    
    def _compute_relevance_score(self, card: Dict[str, Any]) -> Tuple[float, List[str]]:
        """计算证据卡片与主张的相关性分数"""
        score = 0.0
        factors = []
        
        title = str(card.get("title") or "").lower()
        content = str(card.get("content") or card.get("snippet") or "").lower()
        combined = f"{title} {content}"
        
        # 1. 关键词匹配（权重 0.3）
        if self.keyword:
            keyword_count = combined.count(self.keyword)
            if keyword_count > 0:
                score += min(0.3, 0.1 * keyword_count)
                factors.append(f"keyword_match:{keyword_count}")
        
        # 2. 实体匹配（权重 0.35）
        matched_entities = [e for e in self.entities if e in combined]
        if matched_entities:
            score += min(0.35, 0.15 * len(matched_entities))
            factors.append(f"entity_match:{len(matched_entities)}")
        
        # 3. 时间窗口匹配（权重 0.15）
        published_at = card.get("published_at") or card.get("publish_time")
        if published_at:
            try:
                if isinstance(published_at, str):
                    pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                else:
                    pub_date = published_at
                now = datetime.now(pub_date.tzinfo) if pub_date.tzinfo else datetime.now()
                delta_days = abs((now - pub_date).days)
                if delta_days <= self.TIME_WINDOW_DAYS:
                    score += 0.15 * (1 - delta_days / self.TIME_WINDOW_DAYS)
                    factors.append(f"recent:{delta_days}d")
            except Exception:
                pass
        
        # 4. 语言匹配（权重 0.1）
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', combined))
        if self.locale == "cn" and has_cjk:
            score += 0.1
            factors.append("lang_cn")
        elif self.locale != "cn" and not has_cjk:
            score += 0.05
            factors.append("lang_en")
        
        # 5. 来源权威性加成（权重 0.1）
        source_tier = int(card.get("source_tier") or 3)
        tier_bonus = {1: 0.1, 2: 0.05, 3: 0.0}
        score += tier_bonus.get(source_tier, 0.0)
        if source_tier <= 2:
            factors.append(f"tier{source_tier}")
        
        return min(1.0, score), factors
    
    def _is_candidate_only(self, card: Dict[str, Any]) -> bool:
        """判断证据是否仅处于候选集身份"""
        retrieval_mode = str(card.get("retrieval_mode") or "").lower()
        reason_code = str(card.get("reason_code") or "").lower()
        return (
            retrieval_mode in self.CANDIDATE_MARKERS or
            reason_code in self.CANDIDATE_MARKERS or
            "fallback" in retrieval_mode or
            "fallback" in reason_code
        )
    
    def evaluate(self, card: Dict[str, Any]) -> GateResult:
        """评估证据卡片是否可以通过语义闸门"""
        reasons = []
        relevance_score, relevance_factors = self._compute_relevance_score(card)
        is_candidate = self._is_candidate_only(card)
        
        title = str(card.get("title") or "").lower()
        content = str(card.get("content") or card.get("snippet") or "").lower()
        combined = f"{title} {content}"
        
        entity_match = any(e in combined for e in self.entities) if self.entities else True
        topic_match = self.keyword in combined if self.keyword else True
        
        # 判定逻辑
        passed = False
        stage = "rejected"
        
        if is_candidate:
            # 候选集必须通过更严格的闸门
            if entity_match and topic_match and relevance_score >= self.RELEVANCE_THRESHOLD_MEDIUM:
                passed = True
                stage = "evidence_pool"
                reasons.append("candidate_passed_semantic_gate")
            elif entity_match or topic_match:
                passed = True
                stage = "candidate"
                reasons.append("candidate_partial_match")
            else:
                reasons.append("candidate_no_match")
                if relevance_score < self.KEYWORD_MATCH_MIN:
                    reasons.append("low_relevance_noise")
        else:
            # 非候选集证据
            if relevance_score >= self.RELEVANCE_THRESHOLD_HIGH:
                passed = True
                stage = "evidence_pool"
            elif relevance_score >= self.RELEVANCE_THRESHOLD_MEDIUM:
                passed = True
                stage = "candidate"
                reasons.append("medium_relevance")
            else:
                reasons.append("relevance_below_threshold")
        
        reasons.extend(relevance_factors)
        
        return GateResult(
            passed=passed,
            stage=stage,
            reasons=reasons,
            relevance_score=relevance_score,
            entity_match=entity_match,
            topic_match=topic_match,
        )
    
    def batch_evaluate(
        self,
        cards: List[Dict[str, Any]],
        max_evidence: int = 40,
    ) -> Dict[str, Any]:
        """批量评估证据卡片"""
        evidence_pool = []
        candidate_pool = []
        rejected = []
        
        for card in cards:
            result = self.evaluate(card)
            card["_gate_result"] = {
                "passed": result.passed,
                "stage": result.stage,
                "reasons": result.reasons,
                "relevance_score": result.relevance_score,
            }
            
            if result.stage == "evidence_pool":
                evidence_pool.append(card)
            elif result.stage == "candidate":
                candidate_pool.append(card)
            else:
                rejected.append(card)
        
        # 按相关性分数排序
        evidence_pool.sort(key=lambda x: x.get("_gate_result", {}).get("relevance_score", 0), reverse=True)
        candidate_pool.sort(key=lambda x: x.get("_gate_result", {}).get("relevance_score", 0), reverse=True)
        
        # 限制证据池大小
        final_evidence = evidence_pool[:max_evidence]
        
        return {
            "evidence_pool": final_evidence,
            "candidate_pool": candidate_pool,
            "rejected": rejected,
            "stats": {
                "total_input": len(cards),
                "evidence_pool_count": len(final_evidence),
                "candidate_pool_count": len(candidate_pool),
                "rejected_count": len(rejected),
                "noise_filtered_ratio": len(rejected) / max(1, len(cards)),
            }
        }


class EvidenceDeduplicator:
    """证据去重器"""
    
    @staticmethod
    def _compute_text_hash(text: str) -> str:
        normalized = re.sub(r'\s+', ' ', str(text or "").lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    @staticmethod
    def _compute_similarity(text1: str, text2: str) -> float:
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
    
    @classmethod
    def deduplicate(cls, cards: List[Dict[str, Any]], similarity_threshold: float = 0.8) -> List[Dict[str, Any]]:
        if not cards:
            return []
        
        seen_urls: Set[str] = set()
        seen_hashes: Set[str] = set()
        seen_titles: Set[str] = set()
        result = []
        
        for card in cards:
            url = str(card.get("url") or card.get("canonical_url") or "").strip()
            if url and url in seen_urls:
                continue
            
            title = str(card.get("title") or "").strip()
            title_hash = cls._compute_text_hash(title)
            if title_hash in seen_hashes:
                continue
            
            content = str(card.get("content") or card.get("snippet") or "")
            content_hash = cls._compute_text_hash(content[:500])
            if content_hash in seen_hashes:
                continue
            
            is_similar = any(
                cls._compute_similarity(title, seen) >= similarity_threshold
                for seen in seen_titles
            )
            if is_similar:
                continue
            
            result.append(card)
            if url:
                seen_urls.add(url)
            if title:
                seen_titles.add(title)
                seen_hashes.add(title_hash)
            if content:
                seen_hashes.add(content_hash)
        
        return result
