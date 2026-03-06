"""
SiliconFlow LLM 客户端 - 小模型用于Agent处理
"""

import asyncio
import json
import re
import httpx
from typing import Dict, Any, List, Optional, cast
from openai import AsyncOpenAI
from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env


_HTTPX_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "HTTPX_TRUST_ENV", True)),
    auto_disable_local_proxy=bool(
        getattr(settings, "HTTPX_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "HTTPX_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        "⚠️ SiliconFlow disable httpx trust_env due unreachable local proxy: "
        + ",".join(_BROKEN_LOCAL_PROXY)
    )


class SiliconFlowClient:
    """SiliconFlow API 客户端 - 小模型处理"""

    def __init__(self):
        api_key = getattr(settings, "LLM_API_KEY", None) or settings.SILICONFLOW_API_KEY
        base_url = getattr(settings, "LLM_API_BASE", None) or settings.SILICONFLOW_API_BASE
        default_model = (
            getattr(settings, "LLM_MODEL", None) or settings.SILICONFLOW_MODEL
        )
        self.api_key = api_key
        self.base_url = base_url
        self._trust_env_candidates: List[bool] = []
        for v in (_HTTPX_TRUST_ENV, not _HTTPX_TRUST_ENV):
            if v not in self._trust_env_candidates:
                self._trust_env_candidates.append(v)
        self._clients: Dict[bool, AsyncOpenAI] = {}
        for trust_env in self._trust_env_candidates:
            self._clients[trust_env] = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=httpx.AsyncClient(trust_env=trust_env),
            )
        self.client = self._clients[self._trust_env_candidates[0]]
        self.small_model = getattr(
            settings, "LLM_SMALL_MODEL", None
        ) or getattr(settings, "SILICONFLOW_SMALL_MODEL", default_model)
        self.large_model = getattr(
            settings, "LLM_LARGE_MODEL", None
        ) or getattr(settings, "SILICONFLOW_LARGE_MODEL", default_model)
        self.rerank_model = getattr(
            settings, "LLM_RERANK_MODEL", None
        ) or getattr(settings, "SILICONFLOW_RERANK_MODEL", "Qwen/Qwen3-Reranker-8B")
        self.small_fallback_models = [
            default_model,
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ]
        self.large_fallback_models = [
            default_model,
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ]
        self.article_top_k_per_platform = int(
            getattr(settings, "SILICONFLOW_ARTICLE_TOP_K_PER_PLATFORM", 3)
        )
        self.article_max_chars = int(
            getattr(settings, "SILICONFLOW_ARTICLE_MAX_INPUT_CHARS", 12000)
        )

    async def rerank_documents(
        self,
        *,
        query: str,
        documents: List[str],
        model: Optional[str] = None,
        top_n: Optional[int] = None,
        return_documents: bool = False,
        timeout_sec: float = 12.0,
    ) -> Dict[str, Any]:
        """调用 SiliconFlow 重排序接口。"""
        if not documents:
            return {"results": []}
        if not self.api_key:
            raise RuntimeError("Missing LLM API key for rerank")
        url = f"{str(self.base_url).rstrip('/')}/rerank"
        payload: Dict[str, Any] = {
            "model": model or self.rerank_model,
            "query": str(query or "").strip(),
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = int(top_n)
        if return_documents:
            payload["return_documents"] = True

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(timeout_sec, connect=min(5.0, timeout_sec))
        last_exc: Optional[Exception] = None
        for trust_env in self._trust_env_candidates:
            try:
                async with httpx.AsyncClient(
                    timeout=timeout, trust_env=trust_env
                ) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"Rerank API error ({resp.status_code}): {resp.text}"
                        )
                    return cast(Dict[str, Any], resp.json())
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"Rerank request failed trust_env={int(bool(trust_env))}: {exc}"
                )
        raise RuntimeError(f"Rerank API failed on all trust_env strategies: {last_exc}")

    async def analyze_with_small_model(
        self, content: str, platform: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用小模型（step-3.5-mini）对单个平台数据进行初步分析

        Returns:
            {
                "credibility_score": 0.0-1.0,
                "summary": "内容摘要",
                "key_claims": ["主张1", "主张2"],
                "risk_flags": ["风险标签"],
                "sources_mentioned": ["提到的来源"],
                "sentiment": "positive/negative/neutral"
            }
        """
        system_prompt = f"""你是 {platform} 平台的信息分析助手。你的任务是快速分析帖子内容，提取关键信息。

【分析维度】
1. 可信度评分 (0.0-1.0): 基于账号信息、内容质量、是否有来源等
2. 内容摘要: 用1-2句话总结核心内容
3. 关键主张: 提取所有事实性声明
4. 风险标签: [UNVERIFIED_CLAIM, LOW_CREDIBILITY_SOURCE, BOT_ACCOUNT, NEEDS_REVIEW, 等]
5. 提到的来源: 文章中引用的媒体/官方来源
6. 情感倾向: positive/negative/neutral

【输出格式 - JSON】
{{
  "credibility_score": 0.65,
  "summary": "内容摘要",
  "key_claims": ["主张1", "主张2"],
  "risk_flags": ["UNVERIFIED_CLAIM"],
  "sources_mentioned": ["某媒体报道"],
  "sentiment": "neutral"
}}

只输出JSON，不要其他文字。"""

        user_prompt = f"【平台】{platform}\n"
        if metadata:
            user_prompt += f"【元数据】{json.dumps(metadata, ensure_ascii=False)}\n"
        user_prompt += f"【内容】\n{content}\n\n请分析以上内容并输出JSON结果。"

        try:
            response = await self._chat_with_fallback(
                preferred_model=self.small_model,
                fallback_models=self.small_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                route="processing",
            )

            result_text = str(response.choices[0].message.content or "")
            return self._parse_json_response(result_text)

        except Exception as e:
            logger.error(f"SiliconFlow small model analysis failed: {e}")
            return self._create_fallback_analysis(str(e))

    async def score_semantic_relevance(
        self,
        *,
        claim: str,
        keyword: str,
        evidence_text: str,
        source: str = "",
    ) -> Dict[str, Any]:
        """用小模型对证据与主张的语义相关性打分。"""
        system_prompt = (
            "你是证据语义相关性评估器。"
            "请判断证据内容与给定主张/关键词的相关程度，输出 JSON："
            '{"semantic_score": 0.0-1.0, "is_relevant": true/false, "reason": "简短原因"}'
            "只输出 JSON。"
        )
        user_prompt = (
            f"主张: {claim}\n"
            f"关键词: {keyword}\n"
            f"来源: {source}\n"
            f"证据内容: {self._trim_text(evidence_text, 900)}\n"
        )
        try:
            response = await self._chat_with_fallback(
                preferred_model=self.small_model,
                fallback_models=self.small_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=180,
                route="semantic_score",
            )
            result_text = str(response.choices[0].message.content or "")
            data = self._parse_json_response(result_text)
            score = float(data.get("semantic_score") or data.get("score") or 0.0)
            score = max(0.0, min(1.0, score))
            is_relevant = data.get("is_relevant")
            if is_relevant is None:
                is_relevant = score >= 0.5
            return {
                "semantic_score": score,
                "is_relevant": bool(is_relevant),
                "reason": str(data.get("reason") or ""),
                "fallback": bool(data.get("fallback")),
            }
        except Exception as e:
            logger.warning(f"Semantic relevance scoring failed: {e}")
            fallback = self._fallback_semantic_relevance(
                claim=claim, keyword=keyword, evidence_text=evidence_text
            )
            return {
                "semantic_score": float(fallback["semantic_score"]),
                "is_relevant": bool(fallback["is_relevant"]),
                "reason": f"fallback:{fallback['reason']}; error:{e}",
                "fallback": True,
                "fallback_method": "keyword_overlap",
            }

    async def cross_platform_synthesis(
        self, keyword: str, platform_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        使用大模型（step-3.5）合成多平台数据

        Args:
            keyword: 搜索关键词
            platform_results: 各平台小模型的分析结果
        """
        system_prompt = """你是跨平台信息合成专家。你的任务是综合多个平台的分析结果，给出整体判断。

【任务】
1. 对比不同平台的信息差异
2. 识别共识和矛盾点
3. 评估整体可信度
4. 给出综合结论

【重要：官方媒体权重规则】
1. Tier1 官方媒体（新华社、人民日报、央视、WHO、CDC 等）的报道应给予最高权重
2. 如果有多家独立 Tier1 官方媒体一致报道同一事件，可信度应大幅提升（建议 0.85+）
3. 新华社 + 人民日报 同时报道 = 极高可信度（建议 0.90+）
4. 社交媒体内容仅作为辅助参考，权重较低
5. 官方媒体报道的时间、内容一致性也是重要考量因素

【输出格式 - JSON】
{
  "overall_credibility": 0.6,
  "credibility_level": "UNCERTAIN",
  "consensus_points": ["共识点1", "共识点2"],
  "conflicts": ["矛盾点1"],
  "cross_platform_verification": "跨平台验证结果说明",
  "recommendation": "建议采取的行动"
}

可信度等级: VERIFIED(>0.8), LIKELY_TRUE(0.6-0.8), UNCERTAIN(0.4-0.6), LIKELY_FALSE(0.2-0.4), FABRICATED(<0.2)"""

        # 构建平台结果摘要
        platform_summary = []
        for result in platform_results:
            platform = result.get("platform", "unknown")
            summary = result.get("small_model_analysis", {})
            platform_summary.append(f"\n【{platform}平台】")
            platform_summary.append(f"可信度: {summary.get('credibility_score', 0)}")
            platform_summary.append(f"摘要: {summary.get('summary', '')}")
            platform_summary.append(f"风险: {', '.join(summary.get('risk_flags', []))}")

        user_prompt = f"【关键词】{keyword}\n\n【各平台分析结果】\n{'\n'.join(platform_summary)}\n\n请综合以上信息给出整体判断，输出JSON格式。"

        try:
            response = await self._chat_with_fallback(
                preferred_model=self.large_model,
                fallback_models=self.large_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
                route="processing",
            )

            result_text = str(response.choices[0].message.content or "")
            return self._parse_json_response(result_text)

        except Exception as e:
            logger.error(f"SiliconFlow large model synthesis failed: {e}")
            return self._create_fallback_synthesis(str(e))

    async def generate_verification_article(
        self,
        keyword: str,
        synthesis: Dict[str, Any],
        platform_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """基于证据链生成可发布文章。采用双层结论结构，强调可核查性。"""
        system_prompt = """你是事实核查编辑。请生成一篇基于证据链的核验文章。

【核心原则】
1. 结论必须有传播性：第一句 30-45 字，普通人能直接理解
2. 结论必须可核查：每条结论配”读者如何验证”，不是只给链接
3. 诚实面对不确定性：明确指出哪些点证据不足
4. 时效性透明：如果证据超过 24 小时，必须在结论中标注

【双层结论结构】
- 短结论（headline）：30-45 字，一句话说明核心判断，可直接传播
- 解释段（explain）：90-130 字，说明为什么得出这个判断

【可核查动作要求】
每条结论必须配套 1-3 条”读者可执行的验证步骤”，格式：
- “去哪里查”（具体平台或搜索方式）
- “查什么”（关键词或时间节点）
- “怎么判断”（预期看到什么算证实/证伪）

【证据边界说明】
明确指出：
- 哪些点有充分证据（多源交叉验证）
- 哪些点证据不足（单一信源或无信源）
- 哪些点存在矛盾（不同信源说法不一致）

【输出 JSON 结构】
{
  “public_verdict”: {
    “headline”: “经多方核实，某事件基本可信”,
    “explain”: “新华社、澎湃等 3 家媒体独立报道一致...”,
    “label”: “VERIFIED”,
    “confidence”: 0.85,
    “as_of”: “2026-03-01T20:00:00+08:00”
  },
  “reader_checklist”: [
    {
      “claim_point”: “核心主张点”,
      “status”: “SUPPORTED”,
      “how_to_check”: “去新华社官网搜索关键词，查看 3 月 1 日报道”,
      “source_hint”: “新华社、澎湃新闻”,
      “url”: “https://...”
    }
  ],
  “evidence_boundary”: {
    “well_supported”: [“有 3 家以上权威媒体独立报道”],
    “insufficient”: [“缺少官方通报原文”],
    “conflicting”: [“微博部分账号说法与主流媒体不一致”]
  },
  “freshness”: {
    “as_of”: “2026-03-01T20:00:00+08:00”,
    “latest_evidence_at”: “2026-03-01T18:30:00+08:00”,
    “hours_old”: 1.5,
    “status”: “FRESH”,
    “degraded”: false
  },
  “human_review”: {
    “required”: false,
    “priority”: “NORMAL”,
    “reasons”: [],
    “handoff_packet”: null
  },
  “title”: “...”,
  “lead”: “...”,
  “body_markdown”: “...”,
  “highlights”: [“...”, “...”],
  “insufficient_evidence”: [“...”]
}

【可信度标签】
- VERIFIED：多方权威信源交叉验证，基本可信
- LIKELY_TRUE：有一定证据支持，但仍需关注后续
- UNCERTAIN：证据不足或存在矛盾，无法做出判断
- LIKELY_FALSE：多处疑点，可能不实
- FABRICATED：确认为虚假或已被官方辟谣

【人审触发条件】（自动判断）
- confidence < 0.5 或 label = UNCERTAIN
- evidence_boundary.conflicting 不为空
- freshness.hours_old > 24 或 status = STALE
- evidence_boundary.insufficient 超过 2 条

只输出 JSON，不要其他文字。"""

        user_prompt = json.dumps(
            self._build_article_prompt_payload(
                keyword=keyword, synthesis=synthesis, platform_results=platform_results
            ),
            ensure_ascii=False,
        )

        try:
            response = await self._chat_with_fallback(
                preferred_model=self.large_model,
                fallback_models=self.large_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=2800,
                route="auto",
            )
            result_text = str(response.choices[0].message.content or "")
            data = self._parse_json_response(result_text)
            if isinstance(data, dict) and data:
                # 确保必要字段存在
                if "body_markdown" not in data:
                    data["body_markdown"] = ""
                if "highlights" not in data or not isinstance(data["highlights"], list):
                    data["highlights"] = []
                if "insufficient_evidence" not in data or not isinstance(
                    data["insufficient_evidence"], list
                ):
                    data["insufficient_evidence"] = []

                # 新增：确保双层结论结构存在
                if "public_verdict" not in data or not isinstance(data["public_verdict"], dict):
                    data["public_verdict"] = self._build_default_verdict(keyword, synthesis)

                # 新增：确保可核查动作列表存在
                if "reader_checklist" not in data or not isinstance(data["reader_checklist"], list):
                    data["reader_checklist"] = []

                # 新增：确保证据边界存在
                if "evidence_boundary" not in data or not isinstance(data["evidence_boundary"], dict):
                    data["evidence_boundary"] = {
                        "well_supported": [],
                        "insufficient": data.get("insufficient_evidence", []),
                        "conflicting": []
                    }

                # 新增：确保时效性信息存在
                if "freshness" not in data or not isinstance(data["freshness"], dict):
                    data["freshness"] = self._build_default_freshness()

                # 新增：确保人审信息存在
                if "human_review" not in data or not isinstance(data["human_review"], dict):
                    data["human_review"] = self._evaluate_human_review(data)

                return data
        except Exception as e:
            logger.error(f"SiliconFlow article generation failed: {e}")

        return self._build_fallback_article(keyword, synthesis)

    async def summarize_intent_preview(
        self,
        *,
        claim: str,
        keyword: str,
        claims_draft: List[Dict[str, Any]],
        source_plan: Dict[str, Any],
        risk_notes: List[str],
    ) -> str:
        """生成预分析阶段意图摘要。"""
        system_prompt = """你是事实核验系统的预分析助手。请基于输入生成执行意图说明。
要求：
1) 只输出纯文本，中文；
2) 180-240字（目标约200字）；
3) 必须覆盖：要验证什么、为何选这些信源、主要风险与降级策略、预期输出；
4) 不得虚构外部事实。"""
        user_payload = {
            "claim": self._trim_text(claim, 400),
            "keyword": self._trim_text(keyword, 120),
            "claims_draft": [
                {
                    "claim_id": str(row.get("claim_id") or ""),
                    "text": self._trim_text(row.get("text"), 220),
                    "type": str(row.get("type") or "generic_claim"),
                }
                for row in (claims_draft or [])[:6]
            ],
            "source_plan": {
                "event_type": str(source_plan.get("event_type") or "generic_claim"),
                "domain": str(source_plan.get("domain") or "general_news"),
                "must_have_platforms": list(source_plan.get("must_have_platforms") or [])[:8],
                "selected_platforms": list(source_plan.get("selected_platforms") or [])[:12],
                "excluded_platforms": list(source_plan.get("excluded_platforms") or [])[:8],
                "selection_confidence": float(source_plan.get("selection_confidence") or 0.0),
            },
            "risk_notes": [str(x) for x in (risk_notes or [])[:8]],
        }
        response = await self._chat_with_fallback(
            preferred_model=self.small_model,
            fallback_models=self.small_fallback_models,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=420,
            route="auto",  # 使用 auto 优先硅基流动
        )
        text = str(response.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("empty preview summary")
        if text.startswith("```"):
            text = text.strip("`")
        return text

    async def summarize_evidence_digest(
        self,
        keyword: str,
        evidence_cards: List[Dict[str, Any]],
        max_cards: int = 24,
    ) -> Dict[str, Any]:
        """
        使用低成本模型对证据仓做摘要，不做二次爬取。
        """
        if not isinstance(evidence_cards, list) or not evidence_cards:
            return self._build_fallback_digest(keyword, [], reason="empty_evidence")

        cards = [c for c in evidence_cards if isinstance(c, dict)]
        cards.sort(
            key=lambda x: (
                int(x.get("source_tier") or 3),
                0 if not x.get("is_cached") else 1,
                0 if x.get("keyword_match") else 1,
                -float(x.get("confidence") or 0.0),
            )
        )

        hard_limit = max(
            2500, int(getattr(settings, "SILICONFLOW_DIGEST_MAX_INPUT_CHARS", 8000))
        )
        compact: List[Dict[str, Any]] = []
        used_chars = 0
        for card in cards[: max(1, int(max_cards))]:
            row = {
                "source_name": self._trim_text(card.get("source_name"), 50),
                "source_tier": int(card.get("source_tier") or 3),
                "url": self._trim_text(card.get("url"), 180),
                "published_at": self._trim_text(card.get("published_at"), 40),
                "retrieval_mode": self._trim_text(card.get("retrieval_mode"), 40),
                "is_cached": bool(card.get("is_cached")),
                "confidence": round(float(card.get("confidence") or 0.0), 4),
                "snippet": self._trim_text(card.get("snippet"), 220),
            }
            encoded = json.dumps(row, ensure_ascii=False)
            if used_chars + len(encoded) > hard_limit:
                break
            compact.append(row)
            used_chars += len(encoded)

        if not compact:
            return self._build_fallback_digest(keyword, cards, reason="payload_too_large")

        system_prompt = """你是舆情核验系统的低成本摘要助手。请基于证据卡输出结构化总结。
要求：
1) 不要编造新事实，只能基于输入证据；
2) 如果证据不足要明确指出；
3) 输出 JSON 且字段完整。

输出 JSON：
{
  "summary": "150字以内摘要",
  "key_points": ["要点1","要点2"],
  "conflicts": ["冲突点1"],
  "gaps": ["证据缺口1"],
  "recommended_queries": ["后续检索词1","后续检索词2"],
  "confidence_hint": 0.0
}
"""
        user_prompt = json.dumps(
            {
                "keyword": keyword,
                "evidence_count": len(cards),
                "sampled_count": len(compact),
                "evidence_cards": compact,
            },
            ensure_ascii=False,
        )
        try:
            response = await self._chat_with_fallback(
                preferred_model=self.small_model,
                fallback_models=self.small_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=900,
                route="auto",
            )
            result_text = str(response.choices[0].message.content or "")
            payload = self._parse_json_response(result_text)
            if isinstance(payload, dict) and payload:
                payload.setdefault("summary", "")
                payload["key_points"] = (
                    payload.get("key_points")
                    if isinstance(payload.get("key_points"), list)
                    else []
                )
                payload["conflicts"] = (
                    payload.get("conflicts")
                    if isinstance(payload.get("conflicts"), list)
                    else []
                )
                payload["gaps"] = (
                    payload.get("gaps")
                    if isinstance(payload.get("gaps"), list)
                    else []
                )
                payload["recommended_queries"] = (
                    payload.get("recommended_queries")
                    if isinstance(payload.get("recommended_queries"), list)
                    else []
                )
                payload["confidence_hint"] = max(
                    0.0, min(1.0, float(payload.get("confidence_hint") or 0.0))
                )
                payload["sampled_count"] = len(compact)
                payload["total_count"] = len(cards)
                return payload
        except Exception as e:
            logger.warning(f"Evidence digest summary failed, fallback to heuristic: {e}")

        return self._build_fallback_digest(keyword, cards, reason="llm_unavailable")

    async def summarize_claim_reasoning(
        self,
        *,
        keyword: str,
        claim_row: Dict[str, Any],
        max_citations: int = 8,
    ) -> Dict[str, Any]:
        claim_id = str(claim_row.get("claim_id") or "")
        claim_text = str(claim_row.get("text") or "")
        linked = [
            row
            for row in list(claim_row.get("linked_evidence") or [])
            if isinstance(row, dict)
        ][: max(1, int(max_citations))]
        if not claim_text:
            return self._build_fallback_claim_reasoning(claim_row, linked, reason="empty_claim")

        compact_evidence: List[Dict[str, Any]] = []
        for row in linked:
            compact_evidence.append(
                {
                    "evidence_id": self._trim_text(row.get("evidence_id"), 60),
                    "source_name": self._trim_text(row.get("source_name"), 40),
                    "source_tier": int(row.get("source_tier") or 4),
                    "stance": self._trim_text(row.get("stance"), 24),
                    "url": self._trim_text(row.get("url"), 220),
                    "snippet": self._trim_text(row.get("snippet"), 220),
                    "quality_score": round(float(row.get("quality_score") or 0.0), 4),
                }
            )

        system_prompt = """你是事实核验分析助手。请对单条 claim 生成带证据引用的可读分析。
要求：
1) 结论必须与 claim_row.verdict 一致；
2) 风险段必须体现 gate_reasons；
3) reasoning_steps 用简短步骤，避免空洞描述；
4) citations 必须来自输入 evidence，不要捏造 URL；
5) 只输出 JSON。

输出 JSON：
{
  "claim_id": "clm_xxx",
  "conclusion_text": "...",
  "risk_text": "...",
  "reasoning_steps": ["步骤1","步骤2"],
  "citations": [
    {
      "evidence_id": "ev_1",
      "url": "https://...",
      "source_name": "bbc",
      "source_tier": 2,
      "stance": "support",
      "snippet_quote": "..."
    }
  ],
  "fallback": false
}
"""
        user_payload = {
            "keyword": keyword,
            "claim_row": {
                "claim_id": claim_id,
                "text": claim_text,
                "verdict": claim_row.get("verdict"),
                "score": claim_row.get("score"),
                "gate_passed": claim_row.get("gate_passed"),
                "gate_reasons": claim_row.get("gate_reasons") or [],
                "stance_summary": claim_row.get("stance_summary") or {},
            },
            "evidence": compact_evidence,
        }
        try:
            response = await self._chat_with_fallback(
                preferred_model=self.small_model,
                fallback_models=self.small_fallback_models,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=1200,
                route="auto",
            )
            result_text = str(response.choices[0].message.content or "")
            payload = self._parse_json_response(result_text)
            if isinstance(payload, dict) and payload:
                payload["claim_id"] = str(payload.get("claim_id") or claim_id)
                payload["conclusion_text"] = str(payload.get("conclusion_text") or "").strip()
                payload["risk_text"] = str(payload.get("risk_text") or "").strip()
                payload["reasoning_steps"] = (
                    payload.get("reasoning_steps")
                    if isinstance(payload.get("reasoning_steps"), list)
                    else []
                )
                citations = (
                    payload.get("citations") if isinstance(payload.get("citations"), list) else []
                )
                clean_citations: List[Dict[str, Any]] = []
                for row in citations:
                    if not isinstance(row, dict):
                        continue
                    clean_citations.append(
                        {
                            "evidence_id": str(row.get("evidence_id") or ""),
                            "url": str(row.get("url") or ""),
                            "source_name": str(row.get("source_name") or "unknown"),
                            "source_tier": int(row.get("source_tier") or 4),
                            "stance": str(row.get("stance") or "unclear"),
                            "snippet_quote": self._trim_text(row.get("snippet_quote"), 220),
                        }
                    )
                if not clean_citations:
                    clean_citations = self._fallback_citations(linked, max_citations=max_citations)
                payload["citations"] = clean_citations[: max(1, int(max_citations))]
                payload["fallback"] = bool(payload.get("fallback"))
                if not payload["conclusion_text"]:
                    payload["conclusion_text"] = f"结论：{claim_row.get('verdict', 'UNCERTAIN')}。"
                if not payload["risk_text"]:
                    payload["risk_text"] = (
                        f"风险：{','.join([str(x) for x in list(claim_row.get('gate_reasons') or [])]) or '无显著风险码'}。"
                    )
                return payload
        except Exception as e:
            logger.warning(f"Claim reasoning summary failed: {e}")

        return self._build_fallback_claim_reasoning(
            claim_row=claim_row,
            linked=linked,
            reason="llm_unavailable",
        )

    async def _chat_with_fallback(
        self,
        preferred_model: str,
        fallback_models: List[str],
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        route: str = "auto",
    ):
        """按任务路由调用模型（统一使用 SiliconFlow）。"""
        candidates: List[str] = [preferred_model] + [m for m in fallback_models if m != preferred_model]
        last_error: Optional[Exception] = None

        timeout_sec = max(6, int(getattr(settings, "LLM_READ_TIMEOUT", 60) or 60))

        async def _call_candidates() -> tuple[Any, str, bool]:
            nonlocal last_error
            for trust_env in self._trust_env_candidates:
                client = self._clients[trust_env]
                for model_name in candidates:
                    try:
                        response = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model_name,
                                messages=cast(Any, messages),
                                temperature=temperature,
                                max_tokens=max_tokens,
                            ),
                            timeout=timeout_sec,
                        )
                        return response, model_name, trust_env
                    except asyncio.TimeoutError as e:
                        last_error = e
                        logger.warning(
                            "SiliconFlow model timeout: "
                            f"{model_name} trust_env={int(bool(trust_env))} "
                            f"after {timeout_sec}s"
                        )
                        continue
                    except Exception as e:
                        last_error = e
                        err_text = str(e)
                        logger.warning(
                            "SiliconFlow model unavailable: "
                            f"{model_name} trust_env={int(bool(trust_env))} -> {err_text}"
                        )
            raise RuntimeError(f"All SiliconFlow models failed: {last_error}")

        result, used_model, used_trust_env = await _call_candidates()
        logger.info(
            f"LLM route {route} -> siliconflow model={used_model} "
            f"trust_env={int(bool(used_trust_env))}"
        )
        return result

    def _trim_text(self, value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + " ...[truncated_for_llm]"

    def _tokenize_for_fallback(self, text: str) -> set[str]:
        out: set[str] = set()
        raw = str(text or "").lower()
        for token in re.findall(r"[a-z0-9\u4e00-\u9fff]{2,}", raw):
            tok = token.strip()
            if len(tok) >= 2:
                out.add(tok)
        return out

    def _fallback_semantic_relevance(
        self, *, claim: str, keyword: str, evidence_text: str
    ) -> Dict[str, Any]:
        """
        Heuristic fallback when LLM scoring is unavailable.
        Avoids collapsing all results to is_relevant=False.
        """
        ev = str(evidence_text or "").lower()
        kw = str(keyword or "").strip().lower()
        claim_tokens = self._tokenize_for_fallback(claim)
        kw_tokens = self._tokenize_for_fallback(keyword)
        ev_tokens = self._tokenize_for_fallback(evidence_text)

        overlap_claim = (
            len(claim_tokens & ev_tokens) / max(1, len(claim_tokens))
            if claim_tokens
            else 0.0
        )
        overlap_kw = (
            len(kw_tokens & ev_tokens) / max(1, len(kw_tokens))
            if kw_tokens
            else 0.0
        )
        keyword_hit = 1.0 if kw and kw in ev else 0.0
        score = max(overlap_claim, overlap_kw) * 0.75 + keyword_hit * 0.25
        score = max(0.0, min(1.0, score))
        is_relevant = bool(score >= 0.35)
        return {
            "semantic_score": round(score, 4),
            "is_relevant": is_relevant,
            "reason": (
                f"claim_overlap={overlap_claim:.3f}, "
                f"keyword_overlap={overlap_kw:.3f}, keyword_hit={int(keyword_hit)}"
            ),
        }

    def _build_article_prompt_payload(
        self, keyword: str, synthesis: Dict[str, Any], platform_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload = {
            "keyword": keyword,
            "synthesis": synthesis,
            "platform_results": [],
            "truncated_for_llm": False,
        }
        used_chars = 0
        hard_limit = max(4000, self.article_max_chars)
        stop = False

        for row in platform_results:
            if stop:
                break
            platform = row.get("platform")
            small_model_analysis = row.get("small_model_analysis", {})
            raw_data = row.get("raw_data", []) or []
            compact_items = []
            for item in raw_data[: self.article_top_k_per_platform]:
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                compact = {
                    "title": self._trim_text(item.get("title") or item.get("headline"), 120),
                    "content": self._trim_text(
                        item.get("content_text")
                        or item.get("content")
                        or item.get("summary")
                        or item.get("text"),
                        320,
                    ),
                    "url": self._trim_text(item.get("url") or item.get("source_url"), 220),
                    "author": self._trim_text(
                        item.get("author")
                        or metadata.get("author_name"),
                        80,
                    ),
                    "timestamp": self._trim_text(
                        item.get("timestamp")
                        or metadata.get("timestamp")
                        or item.get("created_at"),
                        48,
                    ),
                }
                encoded = json.dumps(compact, ensure_ascii=False)
                if used_chars + len(encoded) > hard_limit:
                    payload["truncated_for_llm"] = True
                    stop = True
                    break
                used_chars += len(encoded)
                compact_items.append(compact)

            section = {
                "platform": platform,
                "small_model_analysis": small_model_analysis,
                "raw_data": compact_items,
            }
            section_encoded = json.dumps(section, ensure_ascii=False)
            if used_chars + len(section_encoded) > hard_limit:
                payload["truncated_for_llm"] = True
                break
            used_chars += len(section_encoded)
            payload["platform_results"].append(section)

        return payload

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """解析JSON响应"""
        try:
            # 提取JSON部分
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0].strip()
            else:
                json_str = text.strip()

            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
            # 模型偶发返回数组/标量，统一降级为字典，避免上游 .get() 崩溃
            return {
                "_non_object_json": True,
                "raw_type": type(parsed).__name__,
                "raw_preview": str(parsed)[:800],
            }
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return {}

    def _create_fallback_analysis(self, reason: str = "") -> Dict[str, Any]:
        """创建默认的分析结果"""
        return {
            "credibility_score": 0.5,
            "summary": f"分析失败: {reason[:120]}" if reason else "分析失败",
            "key_claims": [],
            "risk_flags": ["ANALYSIS_FAILED"],
            "sources_mentioned": [],
            "sentiment": "neutral",
        }

    def _create_fallback_synthesis(self, reason: str = "") -> Dict[str, Any]:
        """创建默认的合成结果"""
        return {
            "overall_credibility": 0.5,
            "credibility_level": "UNCERTAIN",
            "consensus_points": [],
            "conflicts": [],
            "cross_platform_verification": (
                f"合成失败: {reason[:120]}" if reason else "合成失败"
            ),
            "recommendation": "需要人工复核",
        }

    def _build_fallback_digest(
        self, keyword: str, evidence_cards: List[Dict[str, Any]], reason: str = ""
    ) -> Dict[str, Any]:
        cards = [c for c in evidence_cards if isinstance(c, dict)]
        top = cards[:8]
        key_points = []
        for row in top:
            src = str(row.get("source_name") or "unknown")
            snippet = str(row.get("snippet") or "").strip()
            if snippet:
                key_points.append(f"{src}: {snippet[:80]}")
        source_count = len(
            {
                str(r.get("source_name") or "unknown")
                for r in cards
                if isinstance(r, dict)
            }
        )
        low_evidence = len(cards) < 8 or source_count < 3
        gaps = []
        if low_evidence:
            gaps.append("证据数量或平台覆盖不足")
        if sum(1 for r in cards if r.get("is_cached")) > max(0, len(cards) // 2):
            gaps.append("缓存证据占比过高，实时性不足")
        if not gaps:
            gaps.append("需人工抽检重点证据")
        return {
            "summary": (
                f"基于 {len(cards)} 条证据完成快速摘要，覆盖 {source_count} 个来源。"
                + (f" 降级原因: {reason}。" if reason else "")
            ),
            "key_points": key_points[:6],
            "conflicts": [],
            "gaps": gaps,
            "recommended_queries": [keyword, f"{keyword} 官方 通告", f"{keyword} site:reuters.com"],
            "confidence_hint": 0.35 if low_evidence else 0.55,
            "sampled_count": len(top),
            "total_count": len(cards),
            "fallback": True,
        }

    def _fallback_citations(
        self,
        linked: List[Dict[str, Any]],
        *,
        max_citations: int,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in linked[: max(1, int(max_citations))]:
            out.append(
                {
                    "evidence_id": str(row.get("evidence_id") or ""),
                    "url": str(row.get("url") or ""),
                    "source_name": str(row.get("source_name") or "unknown"),
                    "source_tier": int(row.get("source_tier") or 4),
                    "stance": str(row.get("stance") or "unclear"),
                    "snippet_quote": self._trim_text(row.get("snippet"), 220),
                }
            )
        return out

    def _build_fallback_claim_reasoning(
        self,
        claim_row: Dict[str, Any],
        linked: List[Dict[str, Any]],
        *,
        reason: str = "",
    ) -> Dict[str, Any]:
        gate_reasons = [str(x) for x in list(claim_row.get("gate_reasons") or []) if x]
        stance = claim_row.get("stance_summary") or {}
        return {
            "claim_id": str(claim_row.get("claim_id") or ""),
            "conclusion_text": (
                f"结论：{claim_row.get('verdict', 'UNCERTAIN')}，置信度 {float(claim_row.get('score') or 0.0):.2f}。"
            ),
            "risk_text": (
                f"风险：{','.join(gate_reasons) if gate_reasons else '无显著风险码'}。"
                + (f" 降级原因：{reason}。" if reason else "")
            ),
            "reasoning_steps": [
                f"支持证据={int(stance.get('support', 0))}",
                f"反驳证据={int(stance.get('refute', 0))}",
                f"不确定证据={int(stance.get('unclear', 0))}",
            ],
            "citations": self._fallback_citations(linked, max_citations=8),
            "fallback": True,
        }

    def _build_default_verdict(
        self, keyword: str, synthesis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建默认的双层结论结构"""
        from datetime import datetime, timezone

        credibility = float(synthesis.get("overall_credibility", 0.5))
        level = synthesis.get("credibility_level", "UNCERTAIN")

        # 根据 level 确定 label 和文案
        if credibility >= 0.75:
            label = "VERIFIED"
            headline = f"经多方核实，「{keyword}」基本可信"
            explain = f"跨平台检索显示多家权威信源报道一致，证据链较为完整。"
        elif credibility >= 0.5:
            label = "LIKELY_TRUE"
            headline = f"「{keyword}」有一定证据支持，但仍需关注后续"
            explain = f"部分信源支持该说法，但证据覆盖或时效性存在不足。"
        elif credibility >= 0.35:
            label = "UNCERTAIN"
            headline = f"「{keyword}」目前证据不足，无法做出明确判断"
            explain = f"现有证据存在矛盾或缺失，建议等待更多权威信息。"
        elif credibility >= 0.2:
            label = "LIKELY_FALSE"
            headline = f"「{keyword}」存在多处疑点，可能不实"
            explain = f"多个维度检测到异常或矛盾，建议谨慎对待。"
        else:
            label = "FABRICATED"
            headline = f"「{keyword}」已被证实为虚假信息"
            explain = f"权威信源已辟谣或证据确凿证明其不实。"

        return {
            "headline": headline[:50],  # 限制长度
            "explain": explain[:150],
            "label": label,
            "confidence": round(credibility, 4),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def _build_default_freshness(self) -> Dict[str, Any]:
        """构建默认的时效性信息"""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return {
            "as_of": now.isoformat(),
            "latest_evidence_at": None,
            "hours_old": None,
            "status": "TIME_UNKNOWN",
            "degraded": True,
        }

    def _evaluate_human_review(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """评估是否需要人工复核"""
        reasons = []
        priority = "NORMAL"
        required = False

        verdict = data.get("public_verdict", {})
        freshness = data.get("freshness", {})
        evidence_boundary = data.get("evidence_boundary", {})

        confidence = float(verdict.get("confidence", 0.5))
        label = str(verdict.get("label", "UNCERTAIN"))
        hours_old = freshness.get("hours_old")
        degraded = bool(freshness.get("degraded", False))

        # 触发条件 1: 可信度过低或标签为 UNCERTAIN
        if confidence < 0.5 or label == "UNCERTAIN":
            reasons.append("EVIDENCE_INSUFFICIENT")
            required = True
            priority = "HIGH"

        # 触发条件 2: 存在冲突证据
        conflicting = evidence_boundary.get("conflicting", [])
        if conflicting and len(conflicting) > 0:
            reasons.append("EVIDENCE_CONFLICT")
            required = True
            priority = "HIGH"

        # 触发条件 3: 时效性问题
        if hours_old is not None and float(hours_old) > 24:
            reasons.append("EVIDENCE_STALE")
            required = True
        if degraded:
            reasons.append("TIME_UNKNOWN")

        # 触发条件 4: 证据不足项过多
        insufficient = evidence_boundary.get("insufficient", [])
        if insufficient and len(insufficient) > 2:
            reasons.append("INSUFFICIENT_COVERAGE")
            if not required:
                required = True
                priority = "MEDIUM"

        handoff_packet = None
        if required:
            handoff_packet = {
                "claim": data.get("title", ""),
                "key_evidence": data.get("highlights", [])[:5],
                "conflicts": conflicting[:3] if conflicting else [],
                "insufficient": insufficient[:3] if insufficient else [],
                "recommended_action": "建议人工复核并补充权威信源",
            }

        return {
            "required": required,
            "priority": priority,
            "reasons": reasons,
            "handoff_packet": handoff_packet,
        }

    def _build_fallback_article(
        self, keyword: str, synthesis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建失败时的降级文章"""
        verdict = self._build_default_verdict(keyword, synthesis)
        freshness = self._build_default_freshness()
        human_review = self._evaluate_human_review({
            "public_verdict": verdict,
            "freshness": freshness,
            "evidence_boundary": {"insufficient": ["自动成文失败"], "conflicting": []},
            "title": keyword,
            "highlights": [],
        })

        return {
            "title": f"{keyword} 真实性核验简报",
            "lead": verdict["explain"],
            "body_markdown": (
                f"## 结论\n\n{verdict['headline']}\n\n{verdict['explain']}\n\n"
                f"## 说明\n\n当前自动成文功能异常，已返回结构化分析结果。"
                f"建议人工补充可回溯证据链接。"
            ),
            "highlights": ["已完成跨平台检索", "已完成可信度综合判断"],
            "insufficient_evidence": ["自动成文失败", "缺少可回溯具体内容页链接"],
            "public_verdict": verdict,
            "reader_checklist": [],
            "evidence_boundary": {
                "well_supported": [],
                "insufficient": ["自动成文失败"],
                "conflicting": [],
            },
            "freshness": freshness,
            "human_review": human_review,
        }


# 全局客户端实例
_siliconflow_client: Optional[SiliconFlowClient] = None


def get_siliconflow_client() -> SiliconFlowClient:
    """获取 SiliconFlow 客户端实例"""
    global _siliconflow_client
    if _siliconflow_client is None:
        _siliconflow_client = SiliconFlowClient()
    return _siliconflow_client
