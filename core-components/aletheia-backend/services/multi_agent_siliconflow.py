"""
多 Agent + SiliconFlow 小模型处理系统
整合现有爬虫系统与 SiliconFlow API
"""

import asyncio
import re
from collections import Counter
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import quote
from urllib.parse import urlparse

import httpx

from core.config import settings
from services.llm.siliconflow_client import get_siliconflow_client

try:
    from services.layer1_perception.crawler_manager import get_crawler_manager
except Exception:
    get_crawler_manager = None
from utils.logging import logger
from services.debate_reasoning import DebateReasoningEngine, generate_cot_display
from utils.network_env import evaluate_trust_env


_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ MultiAgent disable httpx trust_env due unreachable local proxy: {','.join(_BROKEN_LOCAL_PROXY)}"
    )


class MultiAgentSiliconFlowProcessor:
    """
    多 Agent + SiliconFlow 处理器

    流程:
    1. 各平台 Agent 爬取数据
    2. SiliconFlow 小模型分析每个平台数据
    3. SiliconFlow 大模型合成最终结果
    """

    def __init__(self):
        self.llm = get_siliconflow_client()
        self.crawler_manager = get_crawler_manager() if get_crawler_manager else None
        self.http_timeout = 30.0
        self.max_enrich_items = 3
        self.small_model_top_k = max(
            3, int(getattr(settings, "INVESTIGATION_AGENT_TOPK_PER_PLATFORM", 12) or 12)
        )
        self.small_model_max_content_chars = max(
            1200, int(getattr(settings, "INVESTIGATION_AGENT_MAX_CONTENT_CHARS", 2400) or 2400)
        )
        allow_web_search_fallback = getattr(
            settings, "LLM_ALLOW_WEB_SEARCH_FALLBACK", None
        )
        if allow_web_search_fallback is None:
            allow_web_search_fallback = getattr(
                settings, "SILICONFLOW_ALLOW_WEB_SEARCH_FALLBACK", False
            )
        self.allow_web_search_fallback = bool(allow_web_search_fallback)
        self.max_url_validation_items = 12
        self.allowed_domains = {
            "x.com",
            "twitter.com",
            "weibo.com",
            "m.weibo.cn",
            "xiaohongshu.com",
            "zhihu.com",
            "zhuanlan.zhihu.com",
            "bilibili.com",
            "douyin.com",
            "sina.com.cn",
            "qq.com",
            "163.com",
            "toutiao.com",
            "ifeng.com",
            "xinhuanet.com",
            "gov.cn",
            "news.cn",
            "people.com.cn",
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "theguardian.com",
            "caixin.com",
            "thepaper.cn",
            "who.int",
            "cdc.gov",
            "un.org",
            "sec.gov",
            "fca.org.uk",
        }

    async def search_and_analyze(
        self,
        keyword: str,
        platforms: Optional[List[str]] = None,
        limit_per_platform: int = 10,
        collection_rounds: int = 3,
        round_interval_sec: float = 1.0,
    ) -> Dict[str, Any]:
        """
        搜索并分析 - 完整流程

        Args:
            keyword: 搜索关键词
            platforms: 平台列表 (None = 全部)
            limit_per_platform: 每个平台获取数量

        Returns:
            {
                "keyword": "关键词",
                "platform_results": {
                    "platform_name": {
                        "raw_data": [...],
                        "small_model_analysis": {...},
                        "agent_metadata": {...}
                    }
                },
                "synthesis": {...},  # 大模型合成结果
                "overall_credibility": 0.65,
                "risk_flags": [...],
                "processing_time_ms": 12345
            }
        """
        start_time = datetime.utcnow()
        logger.info(f"🚀 启动多Agent+SiliconFlow分析: '{keyword}'")
        platform_errors: Dict[str, List[str]] = {}
        invalid_evidence: Dict[str, List[Dict[str, Any]]] = {}

        # 步骤1: 并行爬取各平台数据
        logger.info("📡 步骤1: 并行爬取各平台数据...")
        raw_results = await self._crawl_platforms(
            keyword=keyword,
            platforms=platforms,
            limit_per_platform=limit_per_platform,
            collection_rounds=collection_rounds,
            round_interval_sec=round_interval_sec,
            platform_errors=platform_errors,
            invalid_evidence=invalid_evidence,
        )

        # 步骤2: SiliconFlow 小模型并行分析每个平台
        logger.info("🧠 步骤2: SiliconFlow小模型并行分析...")
        platform_analyses = await self._analyze_with_small_models(
            raw_results=raw_results,
            platform_errors=platform_errors,
            invalid_evidence=invalid_evidence,
        )

        # 步骤3: SiliconFlow 大模型合成最终结果
        logger.info("🎯 步骤3: SiliconFlow大模型合成...")
        synthesis = await self._synthesize_with_large_model(
            keyword=keyword, platform_analyses=platform_analyses
        )
        synthesis_before_degrade = dict(synthesis) if isinstance(synthesis, dict) else {}

        evidence_summary = self._build_evidence_summary(
            platform_analyses=platform_analyses, keyword=keyword
        )
        if platform_errors:
            evidence_summary["platform_errors"] = platform_errors
        score_breakdown = self._build_score_breakdown(
            platform_analyses=platform_analyses,
            synthesis=synthesis,
            evidence_summary=evidence_summary,
        )
        keyword_match_ratio = float(evidence_summary.get("keyword_match_ratio", 0.0) or 0.0)
        hot_fallback_ratio = (
            float(evidence_summary.get("hot_fallback_items", 0) or 0)
            / max(1, int(evidence_summary.get("total_items", 0) or 0))
        )
        relevance_threshold = float(
            getattr(settings, "INVESTIGATION_KEYWORD_MATCH_THRESHOLD", 0.2)
        )
        if (
            keyword_match_ratio < relevance_threshold
            and hot_fallback_ratio >= 0.5
            and synthesis.get("credibility_level") in {"FABRICATED", "LIKELY_FALSE", "LIKELY_TRUE", "VERIFIED"}
        ):
            synthesis["overall_credibility"] = min(
                0.45, float(synthesis.get("overall_credibility", 0.45) or 0.45)
            )
            synthesis["credibility_level"] = "UNCERTAIN"
            synthesis["recommendation"] = (
                "证据相关性偏低且热点回退占比较高，已自动降级为不确定结论，建议补充更精准检索。"
            )
            flags = synthesis.get("risk_flags") or []
            if "INSUFFICIENT_RELEVANCE" not in flags:
                flags.append("INSUFFICIENT_RELEVANCE")
            synthesis["risk_flags"] = flags

        status = "complete"
        no_data_explainer: Optional[Dict[str, Any]] = None
        if self._should_return_no_data(evidence_summary, platform_analyses):
            synthesis = self._build_no_data_synthesis(
                keyword=keyword,
                platform_analyses=platform_analyses,
                evidence_summary=evidence_summary,
            )
            # 保留一次模型合成诊断，不再让 NO_DATA 变成“完全无AI处理”
            model_diag = synthesis_before_degrade.get(
                "cross_platform_verification", ""
            ) or synthesis_before_degrade.get("recommendation", "")
            if model_diag:
                synthesis["ai_diagnostic"] = str(model_diag)[:800]
            article = self._build_no_data_article(keyword, evidence_summary)
            if model_diag:
                article["body_markdown"] += (
                    "\n\n### AI 诊断补充\n"
                    f"{str(model_diag)[:1200]}"
                )
            no_data_explainer = self._build_no_data_explainer(
                keyword=keyword,
                evidence_summary=evidence_summary,
                platform_errors=platform_errors,
            )
            status = "insufficient_evidence"
        else:
            article = await self.llm.generate_verification_article(
                keyword=keyword,
                synthesis=synthesis,
                platform_results=[
                    {
                        "platform": p,
                        "small_model_analysis": d.get("small_model_analysis", {}),
                        "raw_data": d.get("raw_data", []),
                    }
                    for p, d in platform_analyses.items()
                ],
            )
            if isinstance(article, str):
                article = {
                    "title": f"{keyword} 核验报告",
                    "lead": "系统已生成摘要。",
                    "body_markdown": article,
                    "highlights": [],
                    "insufficient_evidence": [],
                }

        # 计算处理时间
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        risk_flags = set(self._collect_risk_flags(platform_analyses))
        risk_flags.update(synthesis.get("risk_flags", []))

        # 计算时效性
        freshness = self._calculate_freshness(platform_analyses, article)

        # 评估是否需要人工复核
        human_review = self._evaluate_human_review(synthesis, article, freshness)

        # 如果时效性过时，降低可信度
        if freshness.get("degraded") and freshness.get("status") == "STALE":
            synthesis["overall_credibility"] = min(
                0.55, float(synthesis.get("overall_credibility", 0.5))
            )
            if synthesis.get("credibility_level") in {"VERIFIED", "LIKELY_TRUE"}:
                synthesis["credibility_level"] = "UNCERTAIN"
            risk_flags.add("STALE_EVIDENCE")

        # 将 freshness 和 human_review 注入 article
        if isinstance(article, dict):
            if "freshness" not in article:
                article["freshness"] = freshness
            if "human_review" not in article:
                article["human_review"] = human_review

        # 构建最终结果
        result = {
            "keyword": keyword,
            "platform_results": platform_analyses,
            "synthesis": synthesis,
            "overall_credibility": synthesis.get("overall_credibility", 0.5),
            "credibility_level": synthesis.get("credibility_level", "UNCERTAIN"),
            "status": status,
            "risk_flags": list(risk_flags),
            "consensus_points": synthesis.get("consensus_points", []),
            "conflicts": synthesis.get("conflicts", []),
            "recommendation": synthesis.get("recommendation", "需要人工复核"),
            "evidence_summary": evidence_summary,
            "platform_errors": platform_errors,
            "no_data_explainer": no_data_explainer,
            "score_breakdown": score_breakdown,
            "generated_article": article,
            "processing_time_ms": int(processing_time),
            "timestamp": datetime.utcnow().isoformat(),
            "debate_analysis": debate_analysis,
            "cot_thinking_chain": cot_thinking_chain,
            "collection_rounds": collection_rounds,
            "freshness": freshness,
            "human_review": human_review,
        }

        logger.info(
            f"✅ 分析完成: 可信度={result['overall_credibility']:.2%}, 用时={processing_time:.1f}ms"
        )

        return result

    async def analyze_from_evidence_registry(
        self,
        keyword: str,
        evidence_registry: List[Dict[str, Any]],
        agent_topology: str = "stable_3_agents",
    ) -> Dict[str, Any]:
        """
        证据仓驱动分析（不二次爬取）。

        3-Agent 拓扑:
        1) FactExtractor: 提取事实点/主张点
        2) CrossVerifier: 来源与立场一致性校验
        3) Synthesis: 综合输出结论与建议
        """
        start_time = datetime.utcnow()
        cards = [c for c in (evidence_registry or []) if isinstance(c, dict)]
        live_cards = [
            c for c in cards if not c.get("is_cached") and c.get("retrieval_mode") != "cached_evidence"
        ]
        cached_cards = [c for c in cards if c.get("is_cached") or c.get("retrieval_mode") == "cached_evidence"]
        llm_digest: Dict[str, Any] = {
            "summary": "摘要未启用",
            "key_points": [],
            "conflicts": [],
            "gaps": [],
            "recommended_queries": [keyword],
            "confidence_hint": 0.0,
        }
        if bool(getattr(settings, "INVESTIGATION_AGENT_ENABLE_LLM_DIGEST", True)):
            digest_timeout_sec = max(
                3,
                int(getattr(settings, "INVESTIGATION_AGENT_LLM_DIGEST_TIMEOUT_SEC", 10) or 10),
            )
            try:
                llm_digest = await asyncio.wait_for(
                    self.llm.summarize_evidence_digest(
                        keyword=keyword,
                        evidence_cards=cards,
                        max_cards=int(
                            getattr(settings, "INVESTIGATION_AGENT_LLM_DIGEST_MAX_CARDS", 24)
                            or 24
                        ),
                    ),
                    timeout=digest_timeout_sec,
                )
            except asyncio.TimeoutError:
                llm_digest = {
                    "summary": "低成本模型摘要超时，已降级为规则摘要。",
                    "key_points": [],
                    "conflicts": [],
                    "gaps": ["LLM_DIGEST_TIMEOUT"],
                    "recommended_queries": [keyword, f"{keyword} 官方 通告"],
                    "confidence_hint": 0.0,
                    "fallback": True,
                }
            except Exception as exc:
                llm_digest = {
                    "summary": f"低成本模型摘要失败，已降级。原因: {str(exc)[:120]}",
                    "key_points": [],
                    "conflicts": [],
                    "gaps": ["LLM_DIGEST_FAILED"],
                    "recommended_queries": [keyword, f"{keyword} 官方 通告"],
                    "confidence_hint": 0.0,
                    "fallback": True,
                }

        by_platform: Dict[str, List[Dict[str, Any]]] = {}
        for card in cards:
            platform = str(card.get("source_name") or "unknown")
            by_platform.setdefault(platform, []).append(card)

        platform_results: Dict[str, Dict[str, Any]] = {}
        for platform, rows in by_platform.items():
            avg_score = (
                sum(float(x.get("confidence") or 0.0) for x in rows) / max(1, len(rows))
            )
            source_tier_mix = Counter(int(x.get("source_tier") or 3) for x in rows)
            platform_results[platform] = {
                "raw_data": rows[:50],
                "small_model_analysis": {
                    "credibility_score": round(float(avg_score), 4),
                    "summary": f"{platform} 提供 {len(rows)} 条证据",
                    "key_claims": [
                        str(x.get("snippet") or "")[:120]
                        for x in rows[:5]
                        if str(x.get("snippet") or "").strip()
                    ],
                    "risk_flags": [],
                    "sources_mentioned": [platform],
                    "sentiment": "neutral",
                },
                "agent_metadata": {
                    "evidence_count": len(rows),
                    "source_tier_mix": {str(k): int(v) for k, v in source_tier_mix.items()},
                },
            }

        # Agent-1: FactExtractor
        extracted_facts: List[Dict[str, Any]] = []
        for idx, card in enumerate(cards[:200], start=1):
            snippet = str(card.get("snippet") or "").strip()
            if not snippet:
                continue
            extracted_facts.append(
                {
                    "id": f"fact_{idx}",
                    "text": snippet[:300],
                    "source_name": str(card.get("source_name") or "unknown"),
                    "source_tier": int(card.get("source_tier") or 3),
                    "url": str(card.get("url") or ""),
                    "confidence": float(card.get("confidence") or 0.0),
                }
            )

        # Agent-2: CrossVerifier
        tier1_2_count = sum(
            1 for c in cards if int(c.get("source_tier") or 3) <= 2
        )
        reachable_like = sum(
            1
            for c in cards
            if str(c.get("validation_status") or "").lower() in {"reachable", "derived"}
        )
        coverage_score = (
            len([p for p, rows in by_platform.items() if rows]) / max(1, len(by_platform))
        )
        evidence_strength_score = (
            (tier1_2_count / max(1, len(cards))) * 0.55
            + (reachable_like / max(1, len(cards))) * 0.45
        )
        cache_penalty = min(0.25, len(cached_cards) / max(1, len(cards)) * 0.25)

        # Agent-3: Synthesis
        overall = max(
            0.0,
            min(
                1.0,
                coverage_score * 0.25
                + evidence_strength_score * 0.65
                + min(0.1, len(cards) / 500.0)
                - cache_penalty,
            ),
        )
        if len(cards) < 8:
            overall = min(overall, 0.45)
        credibility_level = (
            "VERIFIED"
            if overall >= 0.85
            else "LIKELY_TRUE"
            if overall >= 0.65
            else "UNCERTAIN"
            if overall >= 0.45
            else "LIKELY_FALSE"
            if overall >= 0.25
            else "FALSE"
        )
        insufficient = len(cards) < 8 or len(by_platform) < 3
        if insufficient:
            credibility_level = "UNCERTAIN"
            overall = min(0.45, overall)

        risk_flags: List[str] = []
        if insufficient:
            risk_flags.extend(["INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW"])
        if len(cached_cards) > len(live_cards):
            risk_flags.append("CACHE_HEAVY_EVIDENCE")

        evidence_summary = {
            "total_platforms": len(by_platform),
            "platforms_with_data": len([p for p, rows in by_platform.items() if rows]),
            "total_items": len(cards),
            "specific_items": len([c for c in cards if str(c.get("url") or "").startswith("http")]),
            "keyword_match_items": len([c for c in cards if c.get("keyword_match") is True]),
            "keyword_match_ratio": round(
                len([c for c in cards if c.get("keyword_match") is True]) / max(1, len(cards)),
                4,
            ),
            "irrelevant_evidence_ratio": round(
                len([c for c in cards if c.get("keyword_match") is False]) / max(1, len(cards)),
                4,
            ),
            "platform_details": {
                p: {"total_items": len(rows), "specific_items": len(rows)}
                for p, rows in by_platform.items()
            },
        }
        input_source_breakdown = {
            "live_count": len(live_cards),
            "cached_count": len(cached_cards),
        }
        no_data_explainer = None
        status = "complete"
        if insufficient:
            status = "insufficient_evidence"
            no_data_explainer = self._build_no_data_explainer(
                keyword=keyword,
                evidence_summary=evidence_summary,
                platform_errors=(
                    {"evidence_registry": ["empty_registry"]}
                    if not cards
                    else {"evidence_registry": ["low_evidence_volume"]}
                ),
            )
            recommended = [
                str(x).strip()
                for x in list(llm_digest.get("recommended_queries") or [])
                if str(x).strip()
            ]
            if recommended:
                no_data_explainer["next_queries"] = list(
                    dict.fromkeys(recommended + list(no_data_explainer.get("next_queries") or []))
                )[:8]

        score_breakdown = {
            "platform_coverage_score": round(float(coverage_score), 4),
            "evidence_specificity_score": round(float(evidence_strength_score), 4),
            "model_consensus_score": round(float(overall), 4),
            "synthesis_score": round(float(overall), 4),
        }
        generated_article = {
            "title": f"{keyword} 动态证据报告",
            "lead": (
                str(llm_digest.get("summary") or "").strip()
                or "基于证据仓的三Agent分析结果。"
            ),
            "body_markdown": (
                f"### Agent拓扑\n{agent_topology}\n\n"
                f"### 证据规模\n- 总证据: {len(cards)}\n- 实时证据: {len(live_cards)}\n- 缓存证据: {len(cached_cards)}\n\n"
                f"### 低成本模型摘要\n{str(llm_digest.get('summary') or 'N/A')}\n\n"
                "### 低成本模型要点\n"
                + "\n".join(
                    [f"- {str(x)}" for x in list(llm_digest.get("key_points") or [])[:6]]
                )
                + "\n\n"
                + (
                    "### 低成本模型冲突点\n"
                    + "\n".join(
                        [f"- {str(x)}" for x in list(llm_digest.get("conflicts") or [])[:4]]
                    )
                    + "\n\n"
                    if list(llm_digest.get("conflicts") or [])
                    else ""
                )
                + f"### 结论\n- 可信度: {round(float(overall), 4)} ({credibility_level})\n"
            ),
            "highlights": [
                f"平台覆盖: {len(by_platform)}",
                f"证据总量: {len(cards)}",
                f"缓存占比: {round(len(cached_cards) / max(1, len(cards)), 4)}",
            ],
            "insufficient_evidence": (
                list(
                    dict.fromkeys(
                        (["INSUFFICIENT_EVIDENCE"] if insufficient else [])
                        + [str(x) for x in list(llm_digest.get("gaps") or [])[:4]]
                    )
                )
            ),
        }
        processing_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        # 辩论式推理分析
        debate_analysis: Dict[str, Any] = {}
        cot_thinking_chain: Dict[str, Any] = {}
        if len(cards) >= 5:
            try:
                debate_engine = DebateReasoningEngine()
                debate_analysis = await asyncio.wait_for(
                    debate_engine.analyze_with_debate(
                        claim=keyword,
                        evidence_pool=cards[:50],
                        keyword=keyword,
                    ),
                    timeout=30,
                )
                cot_thinking_chain = generate_cot_display(debate_analysis)
                logger.info(f"🎭 Debate reasoning completed: {debate_analysis.get('final_conclusion', {}).get('verdict', 'UNKNOWN')}")
            except asyncio.TimeoutError:
                debate_analysis = {"error": "debate_timeout", "verdict": "UNCERTAIN"}
                logger.warning("Debate reasoning timeout")
            except Exception as e:
                debate_analysis = {"error": str(e), "verdict": "UNCERTAIN"}
                logger.error(f"Debate reasoning failed: {e}")

        return {
            "keyword": keyword,
            "platform_results": platform_results,
            "overall_credibility": round(float(overall), 4),
            "credibility_level": credibility_level,
            "status": status,
            "risk_flags": sorted(list(set(risk_flags))),
            "consensus_points": [
                "证据仓驱动分析",
                "已区分实时证据与缓存证据",
                "来源分层已纳入评分",
            ],
            "conflicts": [],
            "recommendation": (
                "证据量不足，建议继续补采稳定信源并缩小关键词。"
                if insufficient
                else "可继续进入报告生成与人工抽检。"
            ),
            "evidence_summary": evidence_summary,
            "no_data_explainer": no_data_explainer,
            "score_breakdown": score_breakdown,
            "generated_article": generated_article,
            "llm_digest": llm_digest,
            "input_source_breakdown": input_source_breakdown,
            "agent_outputs": {
                "fact_extractor": extracted_facts[:30],
                "cross_verifier": {
                    "coverage_score": round(float(coverage_score), 4),
                    "evidence_strength_score": round(float(evidence_strength_score), 4),
                    "cache_penalty": round(float(cache_penalty), 4),
                },
                "synthesis": {
                    "overall_credibility": round(float(overall), 4),
                    "credibility_level": credibility_level,
                },
            },
            "processing_time_ms": processing_time,
            "timestamp": datetime.utcnow().isoformat(),
            "debate_analysis": debate_analysis,
            "cot_thinking_chain": cot_thinking_chain,
            "collection_rounds": 1,
            "freshness": self._calculate_freshness(platform_results, generated_article),
            "human_review": self._evaluate_human_review(
                {"overall_credibility": overall, "credibility_level": credibility_level, "risk_flags": list(risk_flags)},
                generated_article,
                None,
            ),
        }

    async def build_claim_reasoning_with_citations(
        self,
        *,
        keyword: str,
        claims: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        claim_rows = [row for row in (claims or []) if isinstance(row, dict)]
        if not claim_rows:
            return []
        max_claims = max(
            1,
            int(getattr(settings, "INVESTIGATION_CLAIM_REASONING_MAX_CLAIMS", 4) or 4),
        )
        concurrency = max(
            1,
            int(
                getattr(settings, "INVESTIGATION_CLAIM_REASONING_CONCURRENCY", 3) or 3
            ),
        )
        sem = asyncio.Semaphore(concurrency)

        async def _run_one(row: Dict[str, Any]) -> Dict[str, Any]:
            async with sem:
                try:
                    return await self.llm.summarize_claim_reasoning(
                        keyword=keyword,
                        claim_row=row,
                        max_citations=8,
                    )
                except Exception as exc:
                    logger.warning(f"claim reasoning item failed: {exc}")
                    return {
                        "claim_id": str(row.get("claim_id") or ""),
                        "conclusion_text": f"结论：{row.get('verdict', 'UNCERTAIN')}。",
                        "risk_text": f"风险：{','.join([str(x) for x in list(row.get('gate_reasons') or [])]) or '无显著风险码'}。",
                        "reasoning_steps": [
                            "LLM_CALL_FAILED",
                            "FALLBACK_HEURISTIC_USED",
                        ],
                        "citations": [
                            {
                                "evidence_id": str(ev.get("evidence_id") or ""),
                                "url": str(ev.get("url") or ""),
                                "source_name": str(ev.get("source_name") or "unknown"),
                                "source_tier": int(ev.get("source_tier") or 4),
                                "stance": str(ev.get("stance") or "unclear"),
                                "snippet_quote": str(ev.get("snippet") or "")[:180],
                            }
                            for ev in list(row.get("linked_evidence") or [])[:6]
                            if isinstance(ev, dict)
                        ],
                        "fallback": True,
                    }

        tasks = [_run_one(row) for row in claim_rows[:max_claims]]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return [row for row in results if isinstance(row, dict)]

    async def _crawl_platforms(
        self,
        keyword: str,
        platforms: Optional[List[str]],
        limit_per_platform: int,
        collection_rounds: int = 3,
        round_interval_sec: float = 1.0,
        platform_errors: Optional[Dict[str, List[str]]] = None,
        invalid_evidence: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """并行爬取各平台数据"""

        # 如果未指定平台，使用默认列表
        if platforms is None:
            if self.crawler_manager and self.crawler_manager.crawlers:
                platforms = list(self.crawler_manager.crawlers.keys())
            else:
                platforms = ["weibo", "twitter", "xiaohongshu", "zhihu", "bilibili"]

        # 多轮采集（避免一次采样导致 NO_DATA）
        rounds = max(1, int(collection_rounds or 1))
        results: Dict[str, List[Dict[str, Any]]] = {p: [] for p in platforms}

        for round_idx in range(rounds):
            logger.info(f"🔁 第 {round_idx + 1}/{rounds} 轮采集")
            crawl_coroutines = [
                self._crawl_single_platform(
                    platform=platform,
                    keyword=keyword,
                    limit=limit_per_platform,
                    platform_errors=platform_errors,
                    invalid_evidence=invalid_evidence,
                )
                for platform in platforms
            ]

            raw_results = await asyncio.gather(
                *crawl_coroutines, return_exceptions=True
            )
            for idx, platform in enumerate(platforms):
                data_or_err = raw_results[idx]
                if isinstance(data_or_err, Exception):
                    logger.warning(
                        f"  ⚠️ {platform}: 第{round_idx + 1}轮采集失败 - {data_or_err}"
                    )
                    if platform_errors is not None:
                        platform_errors.setdefault(platform, []).append(str(data_or_err))
                    continue

                platform_items = data_or_err if isinstance(data_or_err, list) else []
                if not platform_items:
                    continue

                merged = self._merge_unique_items(
                    results.get(platform, []), platform_items
                )
                results[platform] = merged

            if round_idx < rounds - 1:
                await asyncio.sleep(max(0.0, float(round_interval_sec)))

        for platform in platforms:
            logger.info(
                f"  ✅ {platform}: 多轮累计获取 {len(results.get(platform, []))} 条数据"
            )

        return results

    def _merge_unique_items(
        self, existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """按 url/id 去重合并多轮采集结果"""
        seen = set()
        merged: List[Dict[str, Any]] = []

        for item in existing + incoming:
            if not isinstance(item, dict):
                continue
            key = item.get("url") or item.get("id")
            if not key:
                key = f"fallback-{hash(str(item))}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

        return merged

    async def _crawl_single_platform(
        self,
        platform: str,
        keyword: str,
        limit: int,
        platform_errors: Optional[Dict[str, List[str]]] = None,
        invalid_evidence: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """爬取单个平台"""
        if self.crawler_manager:
            try:
                raw_items = await self.crawler_manager.search_single_platform(
                    platform=platform, keyword=keyword, limit=limit
                )
                sanitized = await self._sanitize_platform_items(
                    platform=platform,
                    items=raw_items,
                    invalid_evidence=invalid_evidence,
                )
                if sanitized:
                    return sanitized
                if self.allow_web_search_fallback:
                    fallback = await self._crawl_with_web_search(platform, keyword, limit)
                    if fallback:
                        if platform_errors is not None:
                            platform_errors.setdefault(platform, []).append(
                            "crawler_empty_use_web_search_fallback"
                            )
                        return fallback
                if platform_errors is not None:
                    platform_errors.setdefault(platform, []).append("crawler_empty")
                return []
            except Exception as e:
                logger.warning(f"爬取 {platform} 失败，按官方检索规则返回NO_DATA: {e}")
                if platform_errors is not None:
                    platform_errors.setdefault(platform, []).append(str(e))
                if self.allow_web_search_fallback:
                    fallback = await self._crawl_with_web_search(platform, keyword, limit)
                    if fallback:
                        if platform_errors is not None:
                            platform_errors.setdefault(platform, []).append(
                            "crawler_error_use_web_search_fallback"
                            )
                        return fallback
                return []

        if self.allow_web_search_fallback:
            return await self._crawl_with_web_search(platform, keyword, limit)

        logger.warning(
            f"{platform}: 官方平台爬虫不可用，且已禁用公开搜索兜底，返回空结果"
        )
        if platform_errors is not None:
            platform_errors.setdefault(platform, []).append("crawler_unavailable")
        return []

    async def _sanitize_platform_items(
        self,
        platform: str,
        items: List[Dict[str, Any]],
        invalid_evidence: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """过滤并标记无效链接，只返回有效证据。"""
        sanitized: List[Dict[str, Any]] = []
        invalid_records: List[Dict[str, Any]] = []

        validate_targets: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("original_url") or item.get("source_url") or ""
            normalized_item = dict(item)
            if url and not normalized_item.get("url"):
                normalized_item["url"] = url
            if not self._is_specific_evidence_url(platform, url):
                invalid_records.append(
                    {
                        "url": url,
                        "invalid_evidence": True,
                        "invalid_reason": "non_specific_url",
                    }
                )
                continue
            if not self._is_allowed_domain(url):
                invalid_records.append(
                    {
                        "url": url,
                        "invalid_evidence": True,
                        "invalid_reason": "domain_not_allowed",
                    }
                )
                continue
            normalized = self._normalize_source_item(platform, normalized_item)
            if not normalized.get("extract_status"):
                normalized["extract_status"] = "raw"
            validate_targets.append(normalized)

        # 可达性探测（HEAD/GET），超量样本仅做结构校验
        probe_items = validate_targets[: self.max_url_validation_items]
        if probe_items:
            checks = [
                self._probe_url_reachable(it.get("url", "")) for it in probe_items
            ]
            statuses = await asyncio.gather(*checks, return_exceptions=True)
            for item, status in zip(probe_items, statuses):
                if isinstance(status, Exception):
                    invalid_records.append(
                        {
                            "url": item.get("url", ""),
                            "invalid_evidence": True,
                            "invalid_reason": "probe_exception",
                        }
                    )
                    continue
                ok, reason = status
                if ok:
                    item["invalid_evidence"] = False
                    sanitized.append(item)
                else:
                    invalid_records.append(
                        {
                            "url": item.get("url", ""),
                            "invalid_evidence": True,
                            "invalid_reason": reason,
                        }
                    )

        # 未探测样本默认保留（避免过慢）
        for item in validate_targets[self.max_url_validation_items :]:
            item["invalid_evidence"] = False
            sanitized.append(item)

        if invalid_evidence is not None:
            invalid_evidence[platform] = invalid_records
        return sanitized

    def _is_allowed_domain(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        if not host:
            return False
        return any(host == d or host.endswith(f".{d}") for d in self.allowed_domains)

    async def _probe_url_reachable(self, url: str) -> Any:
        if not url:
            return False, "empty_url"
        try:
            async with httpx.AsyncClient(
                timeout=12.0,
                follow_redirects=True,
                max_redirects=3,
                trust_env=_HTTPX_TRUST_ENV,
            ) as client:
                try:
                    resp = await client.head(url)
                    code = resp.status_code
                    if code >= 400 or code in (301, 302, 303, 307, 308):
                        # 对可能不支持HEAD的站点回退GET
                        resp = await client.get(url)
                        code = resp.status_code
                except Exception:
                    resp = await client.get(url)
                    code = resp.status_code

            if 200 <= code < 400:
                return True, "ok"
            return False, f"status_{code}"
        except httpx.TooManyRedirects:
            return False, "redirect_loop"
        except httpx.TimeoutException:
            return False, "timeout"
        except Exception:
            return False, "unreachable"

    async def _crawl_with_web_search(
        self, platform: str, keyword: str, limit: int
    ) -> List[Dict[str, Any]]:
        """平台爬虫不可用时，使用公开搜索页兜底抓取链接"""
        platform_domains = {
            "weibo": ["weibo.com", "m.weibo.cn"],
            "twitter": ["x.com", "twitter.com"],
            "xiaohongshu": ["xiaohongshu.com"],
            "zhihu": ["zhihu.com", "zhuanlan.zhihu.com"],
            "bilibili": ["bilibili.com"],
            "news": ["news.cn", "xinhuanet.com", "sina.com.cn", "qq.com", "163.com"],
            "xinhua": ["news.cn", "xinhuanet.com"],
            "peoples_daily": ["people.com.cn"],
            "the_paper": ["thepaper.cn"],
            "reuters": ["reuters.com"],
            "ap_news": ["apnews.com"],
            "bbc": ["bbc.com"],
            "guardian": ["theguardian.com"],
            "who": ["who.int"],
            "un_news": ["un.org"],
            "sec": ["sec.gov"],
            "fca_uk": ["fca.org.uk"],
        }
        domains = platform_domains.get(platform, [platform])
        query_scope = " OR ".join(f"site:{dm}" for dm in domains)
        query = quote(f"{keyword} ({query_scope})")
        # 使用 r.jina.ai 代理，返回可解析的 markdown 文本
        url = f"https://r.jina.ai/http://duckduckgo.com/?q={query}"

        try:
            async with httpx.AsyncClient(
                timeout=self.http_timeout,
                follow_redirects=True,
                trust_env=_HTTPX_TRUST_ENV,
            ) as client:
                resp = await client.get(url)
                text = resp.text

            # 先匹配 markdown 链接：[title](url)
            links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
            # 再兜底匹配裸链接
            bare_links = re.findall(r"(https?://[^\s\])>\"']+)", text)
            for link in bare_links:
                links.append((link, link))
            results: List[Dict[str, Any]] = []

            def _domain_match(link: str) -> bool:
                try:
                    host = (urlparse(link).hostname or "").lower()
                except Exception:
                    return False
                return any(host == dm or host.endswith(f".{dm}") for dm in domains)

            for title, link in links:
                link = link.rstrip(".,;)]}>\"'")
                if "duckduckgo.com" in link or not _domain_match(link):
                    continue
                if not self._is_specific_content_url(platform, link):
                    continue
                idx = len(results)
                if idx >= limit:
                    break
                results.append(
                    {
                        "id": f"{platform}-{idx}",
                        "title": (title or f"{platform} 结果 {idx + 1}")[:120],
                        "url": link,
                        "content": f"通过公开搜索命中 {platform} 相关链接",
                        "author": "web-search",
                        "timestamp": datetime.utcnow().isoformat(),
            "debate_analysis": debate_analysis,
            "cot_thinking_chain": cot_thinking_chain,
                        "source": platform,
                        "fetch_method": "web-search+extract",
                    }
                )

            # 若没有直接链接，则从编号结果行提取域名并构造可访问链接
            if not results:
                numbered_lines = re.findall(
                    r"^\s*\d+\.\s+(.+)$", text, flags=re.MULTILINE
                )
                seen = set()
                for line in numbered_lines:
                    dm = re.search(r"([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", line)
                    if not dm:
                        continue
                    host = dm.group(1).lower()
                    if host in seen:
                        continue
                    # 保留目标域及其子域
                    if not any(host == dm or host.endswith(f".{dm}") for dm in domains):
                        continue
                    seen.add(host)

            # 不再把域名首页作为证据来源，避免虚假可追溯
            results = [
                item
                for item in results
                if self._is_specific_content_url(platform, item.get("url", ""))
            ]

            # 二次抓取：对命中的链接进行正文提取，补全内容字段
            enriched = await self._enrich_results_with_page_extract(results)
            normalized = [
                self._normalize_source_item(platform, item) for item in enriched
            ]
            logger.info(
                f"web-search fallback {platform}: candidates={len(links)}, accepted={len(normalized)}"
            )
            return normalized
        except Exception as e:
            logger.warning(f"兜底抓取 {platform} 失败: {e}")
            return []

    def _is_specific_content_url(self, platform: str, url: str) -> bool:
        """只接受可回溯到具体内容页的URL，不接受平台首页/搜索页。"""
        if not url:
            return False
        patterns = {
            "twitter": [r"https?://(x|twitter)\.com/[^/]+/status/\d+"],
            "weibo": [
                r"https?://weibo\.com/\d+/[A-Za-z0-9]+",
                r"https?://m\.weibo\.cn/detail/\d+",
            ],
            "xiaohongshu": [
                r"https?://www\.xiaohongshu\.com/explore/[A-Za-z0-9]+",
                r"https?://www\.xiaohongshu\.com/discovery/item/[A-Za-z0-9]+",
            ],
            "zhihu": [
                r"https?://www\.zhihu\.com/question/\d+",
                r"https?://zhuanlan\.zhihu\.com/p/\d+",
            ],
            "bilibili": [r"https?://www\.bilibili\.com/video/[A-Za-z0-9]+"],
            "news": [
                r"https?://[^/]*news\.cn/.+",
                r"https?://[^/]*xinhuanet\.com/.+",
                r"https?://[^/]*sina\.com\.cn/.+",
                r"https?://[^/]*qq\.com/.+",
                r"https?://[^/]*163\.com/.+",
            ],
            "xinhua": [r"https?://[^/]*(news\.cn|xinhuanet\.com)/.+"],
            "peoples_daily": [r"https?://[^/]*people\.com\.cn/.+"],
            "the_paper": [r"https?://[^/]*thepaper\.cn/.+"],
            "reuters": [r"https?://[^/]*reuters\.com/.+"],
            "ap_news": [r"https?://[^/]*apnews\.com/article/.+"],
            "bbc": [r"https?://[^/]*bbc\.com/.+"],
            "guardian": [r"https?://[^/]*theguardian\.com/.+"],
            "who": [r"https?://[^/]*who\.int/.+"],
            "un_news": [r"https?://[^/]*un\.org/.+"],
            "sec": [r"https?://[^/]*sec\.gov/.+"],
            "fca_uk": [r"https?://[^/]*fca\.org\.uk/.+"],
        }
        for p in patterns.get(platform, []):
            if re.search(p, url):
                return True
        # 通用兜底：有具体路径且不是首页/搜索页
        try:
            parsed = urlparse(url)
            path = (parsed.path or "").strip("/")
            if not path:
                return False
            if any(seg in path.lower() for seg in ["search", "s?", "query=", "tag/"]):
                return False
            return True
        except Exception:
            return False

    def _normalize_source_item(
        self, platform: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """补充证据链追溯字段。"""
        item["source_platform"] = platform
        item["source_url"] = item.get("url", "")
        item["fetched_at"] = datetime.utcnow().isoformat()
        if not item.get("fetch_method"):
            item["fetch_method"] = (
                "platform-crawler" if self.crawler_manager else "web-search+extract"
            )
        item["evidence_quality"] = (
            "high"
            if self._is_specific_content_url(platform, item.get("url", ""))
            else "low"
        )
        return item

    async def _enrich_results_with_page_extract(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """对搜索命中链接做二次抓取，提取正文摘要，提升小模型输入质量。"""
        if not results:
            return results

        targets = results[: self.max_enrich_items]
        tasks = [self._fetch_page_snippet(item.get("url", "")) for item in targets]
        snippets = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, item in enumerate(targets):
            snippet_or_err = snippets[idx]
            if isinstance(snippet_or_err, BaseException):
                continue
            snippet = snippet_or_err.strip() if isinstance(snippet_or_err, str) else ""
            if snippet:
                item["content"] = snippet[:1200]
                item["extract_status"] = "ok"
            else:
                item["extract_status"] = "empty"

        for item in results[self.max_enrich_items :]:
            item["extract_status"] = "skipped"

        return results

    async def _fetch_page_snippet(self, url: str) -> str:
        """通过 r.jina.ai 提取页面可读文本，返回短摘要。"""
        if not url:
            return ""
        try:
            extract_url = f"https://r.jina.ai/http://{url.replace('https://', '').replace('http://', '')}"
            async with httpx.AsyncClient(
                timeout=self.http_timeout,
                follow_redirects=True,
                trust_env=_HTTPX_TRUST_ENV,
            ) as client:
                resp = await client.get(extract_url)
                text = resp.text or ""

            # 去掉开头元信息，只保留正文部分前段
            marker = "Markdown Content:"
            body = text.split(marker, 1)[1] if marker in text else text
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            filtered = [
                line
                for line in lines
                if not line.startswith("URL Source:") and not line.startswith("Title:")
            ]
            return " ".join(filtered[:20])
        except Exception:
            return ""

    async def _analyze_with_small_models(
        self,
        raw_results: Dict[str, List[Dict[str, Any]]],
        platform_errors: Optional[Dict[str, List[str]]] = None,
        invalid_evidence: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """使用 SiliconFlow 小模型并行分析每个平台"""

        analysis_tasks = []
        for platform, data in raw_results.items():
            if data:  # 只有有数据才分析
                analysis_tasks.append(
                    (platform, self._analyze_single_platform(platform, data))
                )

        # 并行执行所有分析
        task_results = (
            await asyncio.gather(
                *[task for _, task in analysis_tasks],
                return_exceptions=True,
            )
            if analysis_tasks
            else []
        )

        analyses = {}
        for idx, (platform, _) in enumerate(analysis_tasks):
            try:
                analysis = task_results[idx]
                if isinstance(analysis, Exception):
                    raise analysis
                analyses[platform] = {
                    "raw_data": raw_results[platform],
                    "small_model_analysis": analysis,
                    "agent_metadata": {
                        "data_count": len(raw_results[platform]),
                        "invalid_evidence_count": len(
                            (invalid_evidence or {}).get(platform, [])
                        ),
                        "invalid_evidence_samples": (invalid_evidence or {}).get(
                            platform, []
                        )[:5],
                        "analyzed_at": datetime.utcnow().isoformat(),
                    },
                }
                logger.info(f"  🧠 {platform}: 小模型分析完成")
            except Exception as e:
                logger.error(f"  ❌ {platform}: 小模型分析失败 - {e}")
                analyses[platform] = {
                    "raw_data": raw_results[platform],
                    "small_model_analysis": self._create_fallback_analysis(),
                    "agent_metadata": {
                        "error": str(e),
                        "invalid_evidence_count": len(
                            (invalid_evidence or {}).get(platform, [])
                        ),
                        "invalid_evidence_samples": (invalid_evidence or {}).get(
                            platform, []
                        )[:5],
                    },
                }

        # 对于没有抓到数据的平台，返回占位分析，保证前端可展示每个信息源
        for platform, data in raw_results.items():
            if platform not in analyses:
                this_platform_errors = (platform_errors or {}).get(platform, [])
                no_data_text = (
                    f"平台 {platform} 未抓取到有效内容。"
                    f"错误信息: {', '.join(this_platform_errors) if this_platform_errors else 'none'}。"
                    "请基于该诊断给出风险标签和补证建议。"
                )
                model_analysis: Dict[str, Any]
                try:
                    model_analysis = await self.llm.analyze_with_small_model(
                        content=no_data_text,
                        platform=platform,
                        metadata={
                            "data_count": len(data),
                            "platform_errors": this_platform_errors,
                            "mode": "no_data_diagnostic",
                        },
                    )
                    flags = model_analysis.get("risk_flags", [])
                    if isinstance(flags, list) and "NO_DATA" not in flags:
                        flags.append("NO_DATA")
                        model_analysis["risk_flags"] = flags
                except Exception as diag_err:
                    logger.warning(f"{platform}: no-data diagnostic model failed: {diag_err}")
                    model_analysis = {
                        "credibility_score": 0.0,
                        "summary": "该平台暂未抓取到有效内容",
                        "key_claims": [],
                        "risk_flags": ["NO_DATA"],
                        "sources_mentioned": [],
                        "sentiment": "neutral",
                    }
                analyses[platform] = {
                    "raw_data": data,
                    "small_model_analysis": model_analysis,
                    "agent_metadata": {
                        "data_count": len(data),
                        "platform_errors": this_platform_errors,
                        "invalid_evidence_count": len(
                            (invalid_evidence or {}).get(platform, [])
                        ),
                        "invalid_evidence_samples": (invalid_evidence or {}).get(
                            platform, []
                        )[:5],
                        "analyzed_at": datetime.utcnow().isoformat(),
                    },
                }

        return analyses

    def _build_evidence_summary(
        self, platform_analyses: Dict[str, Dict[str, Any]], keyword: str
    ) -> Dict[str, Any]:
        """统计证据覆盖度，判断是否具备可回溯具体帖子。"""
        platform_details: Dict[str, Dict[str, int]] = {}
        total_items = 0
        specific_items = 0
        keyword_match_items = 0
        hot_fallback_items = 0

        for platform, data in platform_analyses.items():
            raw_data = data.get("raw_data", [])
            platform_total = len(raw_data)
            platform_specific = sum(
                1
                for item in raw_data
                if self._is_specific_evidence_url(platform, item.get("url", ""))
            )
            platform_keyword_hits = sum(
                1
                for item in raw_data
                if self._item_matches_keyword(item=item, keyword=keyword)
            )
            platform_hot_fallback = sum(
                1
                for item in raw_data
                if (
                    isinstance(item.get("metadata"), dict)
                    and item.get("metadata", {}).get("retrieval_mode")
                    == "hot_fallback"
                )
            )
            total_items += platform_total
            specific_items += platform_specific
            keyword_match_items += platform_keyword_hits
            hot_fallback_items += platform_hot_fallback
            platform_details[platform] = {
                "total_items": platform_total,
                "specific_items": platform_specific,
                "keyword_match_items": platform_keyword_hits,
                "hot_fallback_items": platform_hot_fallback,
            }

        platform_with_data = sum(
            1 for details in platform_details.values() if details["total_items"] > 0
        )
        platform_with_specific = sum(
            1 for details in platform_details.values() if details["specific_items"] > 0
        )

        return {
            "total_platforms": len(platform_analyses),
            "platforms_with_data": platform_with_data,
            "platforms_with_specific_posts": platform_with_specific,
            "total_items": total_items,
            "specific_items": specific_items,
            "specific_ratio": (
                round(specific_items / total_items, 4) if total_items > 0 else 0.0
            ),
            "keyword_match_items": keyword_match_items,
            "keyword_match_ratio": (
                round(keyword_match_items / total_items, 4) if total_items > 0 else 0.0
            ),
            "hot_fallback_items": hot_fallback_items,
            "irrelevant_evidence_ratio": (
                round((total_items - keyword_match_items) / total_items, 4)
                if total_items > 0
                else 0.0
            ),
            "platform_details": platform_details,
        }

    def _build_score_breakdown(
        self,
        platform_analyses: Dict[str, Dict[str, Any]],
        synthesis: Dict[str, Any],
        evidence_summary: Dict[str, Any],
    ) -> Dict[str, float]:
        """提供可解释评分拆解，避免只给单一总分。"""
        total_platforms = max(1, evidence_summary.get("total_platforms", 0))
        platform_coverage_score = round(
            evidence_summary.get("platforms_with_data", 0) / total_platforms, 4
        )
        evidence_specificity_score = round(
            evidence_summary.get("specific_ratio", 0.0), 4
        )

        scored_platforms = 0
        model_score_sum = 0.0
        for data in platform_analyses.values():
            score = data.get("small_model_analysis", {}).get("credibility_score", None)
            if isinstance(score, (int, float)):
                scored_platforms += 1
                model_score_sum += float(score)

        model_consensus_score = (
            round(model_score_sum / scored_platforms, 4)
            if scored_platforms > 0
            else 0.0
        )
        synthesis_score = float(synthesis.get("overall_credibility", 0.0) or 0.0)

        return {
            "platform_coverage_score": platform_coverage_score,
            "evidence_specificity_score": evidence_specificity_score,
            "model_consensus_score": model_consensus_score,
            "synthesis_score": round(synthesis_score, 4),
        }

    def _should_return_no_data(self, evidence_summary: Dict[str, Any], platform_analyses: Optional[Dict[str, Dict[str, Any]]] = None) -> bool:
        """判断是否应该返回无数据状态。

        对于官方新闻平台，放宽判断标准，因为这些平台本身具有较高可信度。
        """
        total_items = evidence_summary.get("total_items", 0)
        specific_items = evidence_summary.get("specific_items", 0)

        # 完全没有数据
        if total_items == 0:
            return True

        # 有具体帖子链接，不返回无数据
        if specific_items > 0:
            return False

        # 检查是否有官方新闻平台数据
        # 对于官方新闻平台，即使 URL 不符合特定模式，也应该被视为有效证据
        official_platforms = {"xinhua", "news", "reuters", "bbc", "guardian", "peoples_daily", "the_paper", "who", "un_news", "ap_news"}
        platform_details = evidence_summary.get("platform_details", {})

        for platform, details in platform_details.items():
            if platform in official_platforms and details.get("total_items", 0) > 0:
                # 官方平台有数据，不算无数据
                return False

        # 其他平台没有具体帖子链接
        return True

    def _build_no_data_synthesis(
        self,
        keyword: str,
        platform_analyses: Dict[str, Dict[str, Any]],
        evidence_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """统一证据不足返回，防止无证据却高置信。"""
        missing_platforms = [
            platform
            for platform, details in evidence_summary.get(
                "platform_details", {}
            ).items()
            if details.get("specific_items", 0) == 0
        ]
        return {
            # 证据不足场景分数封顶 <= 0.45
            "overall_credibility": 0.45,
            "credibility_level": "UNCERTAIN",
            "consensus_points": [],
            "conflicts": [],
            "cross_platform_verification": (
                f"关键词 '{keyword}' 未检索到可回溯的具体帖子/内容页，"
                "不满足证据链要求。"
            ),
            "recommendation": "证据不足：请补充平台、放宽关键词或添加权威来源后重试。",
            "risk_flags": ["INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW"],
            "missing_platforms": missing_platforms,
            "platform_count": len(platform_analyses),
        }

    def _build_no_data_article(
        self, keyword: str, evidence_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """证据不足场景下返回固定成文结构。"""
        return {
            "title": f"{keyword} 核验简报（INSUFFICIENT_EVIDENCE）",
            "lead": "未检索到可回溯具体帖子，当前不输出高置信结论。",
            "body_markdown": (
                "### 结论\n"
                "INSUFFICIENT_EVIDENCE\n\n"
                "### 原因\n"
                f"- 检索平台数: {evidence_summary.get('total_platforms', 0)}\n"
                f"- 命中条目数: {evidence_summary.get('total_items', 0)}\n"
                f"- 可回溯具体帖子数: {evidence_summary.get('specific_items', 0)}\n\n"
                "当前证据不足，不应给出高置信判断。"
            ),
            "highlights": [
                "已完成多平台检索",
                "未命中可回溯具体帖子",
                "已按规则降级为证据不足",
            ],
            "insufficient_evidence": ["缺少可回溯具体内容页链接"],
        }

    def _build_no_data_explainer(
        self,
        keyword: str,
        evidence_summary: Dict[str, Any],
        platform_errors: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """构建可解释证据不足面板数据。"""
        total_items = int(evidence_summary.get("total_items", 0) or 0)
        specific_items = int(evidence_summary.get("specific_items", 0) or 0)
        coverage_ratio = round((specific_items / total_items), 4) if total_items else 0.0
        attempted_platforms = sorted(
            list((evidence_summary.get("platform_details") or {}).keys())
        )
        reason_code = self._infer_no_data_reason_code(platform_errors or {})
        reason_text = self._get_no_data_reason_text(reason_code, platform_errors)

        return {
            "reason_code": reason_code,
            "reason_text": reason_text,
            "attempted_platforms": attempted_platforms,
            "hit_count": total_items,
            "retrievable_count": specific_items,
            "platform_errors": platform_errors or {"unknown": ["crawler_empty"]},
            "retrieval_scope": {
                "keyword": keyword,
                "total_platforms": int(evidence_summary.get("total_platforms", 0) or 0),
                "platforms_with_data": int(
                    evidence_summary.get("platforms_with_data", 0) or 0
                ),
                "total_items": total_items,
                "specific_items": specific_items,
            },
            "coverage_ratio": coverage_ratio,
            "suggested_queries": [
                keyword,
                f"{keyword} 官方 通告",
                f"{keyword} 官方 声明",
                f"{keyword} site:openai.com",
            ],
        }

    def _infer_no_data_reason_code(self, platform_errors: Dict[str, List[str]]) -> str:
        if not platform_errors:
            return "INSUFFICIENT_EVIDENCE"
        all_errors = [
            str(msg or "").lower()
            for msgs in platform_errors.values()
            for msg in (msgs or [])
        ]
        if not all_errors:
            return "INSUFFICIENT_EVIDENCE"
        network_hits = 0
        for msg in all_errors:
            if any(
                token in msg
                for token in [
                    "timed out",
                    "timeout",
                    "temporary failure in name resolution",
                    "name or service not known",
                    "nodename nor servname",
                    "dns",
                    "proxy",
                    "connection refused",
                    "unreachable",
                    "network",
                ]
            ):
                network_hits += 1
        if network_hits / max(1, len(all_errors)) >= 0.6:
            return "NETWORK_UNREACHABLE"
        return "INSUFFICIENT_EVIDENCE"

    def _get_no_data_reason_text(
        self, reason_code: str, platform_errors: Optional[Dict[str, List[str]]] = None
    ) -> str:
        """获取空结果原因的通俗化解释文案"""
        reason_map = {
            "FALLBACK_EMPTY": "所有平台均未返回相关结果，可能是关键词过于具体或无相关内容。",
            "NETWORK_UNREACHABLE": "网络连接出现问题，部分平台无法访问。",
            "MEDIACRAWLER_LOGIN_REQUIRED": "部分平台需要登录态才能访问，请配置 Cookies。",
            "INSUFFICIENT_EVIDENCE": "检索结果数量不足，无法形成有效证据链。",
            "TIMEOUT": "平台响应超时，建议稍后重试。",
            "MISSING_TOKEN": "缺少必要的 API 凭据，请联系管理员配置。",
        }

        base_text = reason_map.get(reason_code, "未知原因导致检索失败。")

        # 添加平台详情
        if platform_errors:
            failed_platforms = list(platform_errors.keys())[:3]
            if failed_platforms:
                base_text += f" 受影响平台：{', '.join(failed_platforms)}。"

        return base_text

    def _calculate_freshness(
        self,
        platform_results: Dict[str, Dict[str, Any]],
        article_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """计算证据时效性"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        def _ensure_aware(dt_value: Optional[datetime]) -> Optional[datetime]:
            if not isinstance(dt_value, datetime):
                return None
            if dt_value.tzinfo is None:
                return dt_value.replace(tzinfo=timezone.utc)
            return dt_value

        # 从已有数据中提取最新时间
        latest_evidence_at = None

        # 检查 article_data 中的 freshness
        if article_data and isinstance(article_data.get("freshness"), dict):
            existing = article_data["freshness"]
            if existing.get("latest_evidence_at"):
                try:
                    latest_evidence_at = _ensure_aware(
                        datetime.fromisoformat(
                            existing["latest_evidence_at"].replace("Z", "+00:00")
                        )
                    )
                except Exception:
                    pass

        # 从平台结果中提取时间戳
        if not latest_evidence_at and platform_results:
            all_timestamps = []
            for platform, data in platform_results.items():
                raw_data = data.get("raw_data", [])
                if isinstance(raw_data, list):
                    for item in raw_data:
                        if isinstance(item, dict):
                            for key in ["timestamp", "created_at", "publish_time", "published_at"]:
                                ts = item.get(key)
                                if ts:
                                    try:
                                        dt = datetime.fromisoformat(
                                            str(ts).replace("Z", "+00:00")
                                        )
                                        all_timestamps.append(_ensure_aware(dt))
                                    except Exception:
                                        pass

            if all_timestamps:
                latest_evidence_at = max(all_timestamps)

        # 计算时效性状态
        hours_old = None
        status = "TIME_UNKNOWN"
        degraded = True

        if latest_evidence_at:
            hours_old = (now - latest_evidence_at).total_seconds() / 3600

            if hours_old <= 24:
                status = "FRESH"
                degraded = False
            elif hours_old <= 72:
                status = "RECENT"
                degraded = False
            else:
                status = "STALE"
                degraded = True

        return {
            "as_of": now.isoformat(),
            "latest_evidence_at": latest_evidence_at.isoformat() if latest_evidence_at else None,
            "hours_old": round(hours_old, 2) if hours_old is not None else None,
            "status": status,
            "degraded": degraded,
        }

    def _evaluate_human_review(
        self,
        synthesis: Dict[str, Any],
        article_data: Optional[Dict[str, Any]] = None,
        freshness: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """评估是否需要人工复核"""
        reasons = []
        priority = "NORMAL"
        required = False

        overall_cred = float(synthesis.get("overall_credibility", 0.5))
        cred_level = str(synthesis.get("credibility_level", "UNCERTAIN"))
        risk_flags = list(synthesis.get("risk_flags", []))

        # 触发条件 1: 可信度过低
        if overall_cred < 0.5 or cred_level == "UNCERTAIN":
            reasons.append("EVIDENCE_INSUFFICIENT")
            required = True
            priority = "HIGH"

        # 触发条件 2: 存在风险标记
        high_risk_flags = {"INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW", "CONFLICTING_EVIDENCE"}
        if high_risk_flags & set(risk_flags):
            reasons.append("RISK_FLAGS_DETECTED")
            required = True

        # 触发条件 3: 时效性问题
        if freshness:
            if freshness.get("status") == "STALE":
                reasons.append("EVIDENCE_STALE")
                required = True
            if freshness.get("degraded"):
                reasons.append("TIME_UNKNOWN")

        # 触发条件 4: 证据边界问题（从 article_data 提取）
        if article_data and isinstance(article_data.get("evidence_boundary"), dict):
            boundary = article_data["evidence_boundary"]
            conflicting = boundary.get("conflicting", [])
            insufficient = boundary.get("insufficient", [])

            if conflicting:
                reasons.append("EVIDENCE_CONFLICT")
                required = True
                priority = "HIGH"
            if len(insufficient) > 2:
                reasons.append("INSUFFICIENT_COVERAGE")
                if not required:
                    required = True
                    priority = "MEDIUM"

        # 去重
        reasons = list(dict.fromkeys(reasons))

        handoff_packet = None
        if required:
            handoff_packet = {
                "claim": str(synthesis.get("keyword", "")),
                "key_evidence": list(article_data.get("highlights", []))[:5] if article_data else [],
                "conflicts": boundary.get("conflicting", [])[:3] if article_data and "evidence_boundary" in article_data else [],
                "insufficient": boundary.get("insufficient", [])[:3] if article_data and "evidence_boundary" in article_data else [],
                "recommended_action": "建议人工复核并补充权威信源",
            }

        return {
            "required": required,
            "priority": priority,
            "reasons": reasons,
            "handoff_packet": handoff_packet,
        }

    def _is_specific_evidence_url(self, platform: str, url: str) -> bool:
        """通用证据URL判定，社媒走严格规则，官方新闻源放宽标准。"""
        if self._is_specific_content_url(platform, url):
            return True
        if not url:
            return False

        # 官方新闻平台放宽标准：只要有有效路径就算有效证据
        official_platforms = {"xinhua", "news", "reuters", "bbc", "guardian", "peoples_daily", "the_paper", "who", "un_news", "ap_news"}
        if platform in official_platforms:
            # 检查是否是首页
            if re.search(r"https?://[^/]+/?$", url):
                return False
            # 检查是否是搜索页
            if re.search(r"[?&](q|query|search|keyword)=", url):
                return False
            # 有任何路径就接受
            return True

        # 社媒平台走严格规则
        if re.search(r"https?://[^/]+/?$", url):
            return False
        if re.search(r"[?&](q|query|search|keyword)=", url):
            return False
        return True

    def _item_matches_keyword(self, item: Dict[str, Any], keyword: str) -> bool:
        kw = (keyword or "").strip().lower()
        if not kw:
            return False
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if metadata.get("keyword_match") is True:
            return True
        text_blob = " ".join(
            [
                str(item.get("title", "")),
                str(item.get("content", "")),
                str(item.get("content_text", "")),
                str(item.get("text", "")),
            ]
        ).lower()
        return kw in text_blob

    async def _analyze_single_platform(
        self, platform: str, data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析单个平台数据"""
        sampled_data = self._sample_platform_items(data, top_k=self.small_model_top_k)
        # 合并所有内容为文本
        combined_content = self._combine_platform_content(platform, sampled_data)

        # 构建元数据
        metadata = {
            "platform": platform,
            "post_count": len(data),
            "sampled_count": len(sampled_data),
            "truncated_for_llm": len(sampled_data) < len(data),
            "sources": list(
                set(item.get("source", "") for item in data if item.get("source"))
            ),
        }

        # 调用 SiliconFlow 小模型分析
        analysis = await self.llm.analyze_with_small_model(
            content=combined_content, platform=platform, metadata=metadata
        )

        return analysis

    async def analyze_platform_realtime(
        self,
        *,
        keyword: str,
        platform: str,
        items: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """实时分析单个平台的采集结果（小模型）。"""
        if not items:
            return {
                "analysis": {
                    "credibility_score": 0.0,
                    "summary": "无可分析数据",
                    "key_claims": [],
                    "risk_flags": ["NO_DATA"],
                    "sources_mentioned": [],
                    "sentiment": "neutral",
                },
                "metadata": {
                    "platform": platform,
                    "post_count": 0,
                    "sampled_count": 0,
                    "keyword": keyword,
                },
                "fallback": True,
            }

        top_k = max(
            1,
            int(top_k or getattr(settings, "INVESTIGATION_REALTIME_PLATFORM_ANALYSIS_TOPK", 6) or 6),
        )
        sampled_data = self._sample_platform_items(items, top_k=top_k)
        combined_content = self._combine_platform_content(platform, sampled_data)
        metadata = {
            "platform": platform,
            "post_count": len(items),
            "sampled_count": len(sampled_data),
            "keyword": keyword,
            "truncated_for_llm": len(sampled_data) < len(items),
        }

        try:
            if timeout_sec and timeout_sec > 0:
                analysis = await asyncio.wait_for(
                    self.llm.analyze_with_small_model(
                        content=combined_content,
                        platform=platform,
                        metadata=metadata,
                    ),
                    timeout=float(timeout_sec),
                )
            else:
                analysis = await self.llm.analyze_with_small_model(
                    content=combined_content,
                    platform=platform,
                    metadata=metadata,
                )
            return {"analysis": analysis, "metadata": metadata, "fallback": False}
        except Exception as exc:
            return {
                "analysis": {
                    "credibility_score": 0.5,
                    "summary": f"实时分析失败: {str(exc)[:120]}",
                    "key_claims": [],
                    "risk_flags": ["REALTIME_ANALYSIS_FAILED"],
                    "sources_mentioned": [],
                    "sentiment": "neutral",
                },
                "metadata": {**metadata, "error": str(exc)},
                "fallback": True,
            }

    def _sample_platform_items(
        self, data: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """按证据质量分层抽样，优先具体内容页和关键词命中项。"""
        if not data:
            return []

        def _score(item: Dict[str, Any]) -> tuple:
            meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            url = str(item.get("url") or item.get("source_url") or "")
            specific = 1 if self._is_specific_evidence_url(str(item.get("source_platform") or ""), url) else 0
            keyword_match = 1 if (meta.get("keyword_match") is True) else 0
            quality = 1 if str(item.get("evidence_quality", "")).lower() == "high" else 0
            return (specific, keyword_match, quality)

        ordered = sorted(
            [it for it in data if isinstance(it, dict)],
            key=_score,
            reverse=True,
        )
        return ordered[: max(1, top_k)]

    async def _synthesize_with_large_model(
        self, keyword: str, platform_analyses: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """使用 SiliconFlow 大模型合成最终结果"""

        # 准备平台结果列表
        platform_results = []
        for platform, data in platform_analyses.items():
            platform_results.append(
                {
                    "platform": platform,
                    "small_model_analysis": data.get("small_model_analysis", {}),
                    "raw_count": len(data.get("raw_data", [])),
                }
            )

        # 调用大模型合成
        synthesis = await self.llm.cross_platform_synthesis(
            keyword=keyword, platform_results=platform_results
        )

        return synthesis

    def _combine_platform_content(
        self, platform: str, data: List[Dict[str, Any]]
    ) -> str:
        """合并平台内容为文本"""
        contents = []

        for i, item in enumerate(data[: self.small_model_top_k]):
            content_parts = []

            title = item.get("title") or item.get("headline")
            content = (
                item.get("content_text")
                or item.get("content")
                or item.get("text")
                or item.get("summary")
            )
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            author = item.get("author") or metadata.get("author_name") or metadata.get("author")
            timestamp = item.get("timestamp") or metadata.get("timestamp") or item.get("created_at")
            url = item.get("url") or item.get("source_url")

            if title:
                content_parts.append(f"标题: {title}")
            if content:
                content_parts.append(
                    f"内容: {str(content)[: self.small_model_max_content_chars]}..."
                )
            if author:
                content_parts.append(f"作者: {author}")
            if timestamp:
                content_parts.append(f"时间: {timestamp}")
            if url:
                content_parts.append(f"链接: {url}")
            retrieval_mode = metadata.get("retrieval_mode")
            if retrieval_mode:
                content_parts.append(f"检索模式: {retrieval_mode}")

            if content_parts:
                contents.append(f"[{i + 1}] " + " | ".join(content_parts))

        if not contents:
            return f"平台 {platform} 暂无可读内容，需补证。"
        return f"\n---\n".join(contents)

    def _collect_risk_flags(
        self, platform_analyses: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """收集所有风险标签"""
        all_flags = set()

        for platform_data in platform_analyses.values():
            analysis = platform_data.get("small_model_analysis", {})
            flags = analysis.get("risk_flags", [])
            all_flags.update(flags)

        return list(all_flags)

    def _create_fallback_analysis(self) -> Dict[str, Any]:
        """创建默认分析结果"""
        return {
            "credibility_score": 0.0,
            "summary": "分析失败",
            "key_claims": [],
            "risk_flags": ["ANALYSIS_FAILED"],
            "sources_mentioned": [],
            "sentiment": "neutral",
        }


# 全局处理器实例
_processor: Optional[MultiAgentSiliconFlowProcessor] = None


def get_multi_agent_processor() -> MultiAgentSiliconFlowProcessor:
    """获取多Agent处理器实例（默认每次返回独立实例，避免并发运行态串扰）。"""
    if bool(getattr(settings, "INVESTIGATION_MULTI_AGENT_SINGLETON", False)):
        global _processor
        if _processor is None:
            _processor = MultiAgentSiliconFlowProcessor()
        return _processor

    return MultiAgentSiliconFlowProcessor()


def get_multi_agent_processor_singleton() -> MultiAgentSiliconFlowProcessor:
    """兼容旧调用：显式获取单例实例。"""
    global _processor
    if _processor is None:
        _processor = MultiAgentSiliconFlowProcessor()
    return _processor
