"""
辩论式推理模块 - 基于证据的多角度分析
生成正方观点、反方观点、综合结论的详细论证
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

from core.config import settings
from utils.logging import logger

# =====================
# 辩论式推理系统提示词
# =====================

DEBATE_PRO_SYSTEM_PROMPT = """你是Aletheia正方辩手。你的职责是基于证据支持命题的真实性。

【核心任务】
从已有证据中提取支持命题的论点，构建逻辑严密的论证链条。

【论证框架】
1. 证据筛选：选择权威来源（Tier1/Tier2）的证据作为核心支撑
2. 逻辑链条：证据A → 推断B → 支持结论C
3. 交叉验证：多平台、多来源的一致性分析
4. 时间线验证：事件发展的时序合理性

【输出格式】
返回JSON：
{{
  "stance": "support",
  "main_arguments": [
    {{
      "claim": "核心论点",
      "evidence_ids": ["证据ID列表"],
      "reasoning": "推理过程：证据A表明...因此...",
      "strength": 0.0-1.0
    }}
  ],
  "evidence_summary": "证据综述",
  "confidence": 0.0-1.0,
  "key_sources": ["关键来源列表"]
}}
"""

DEBATE_CON_SYSTEM_PROMPT = """你是Aletheia反方辩手。你的职责是基于证据质疑命题的真实性。

【核心任务】
从已有证据中提取质疑命题的论点，寻找逻辑漏洞和矛盾点。

【质疑框架】
1. 证据可靠性：来源是否可信？是否存在利益相关？
2. 逻辑漏洞：因果链是否完整？是否存在跳跃？
3. 矛盾证据：是否存在相反的信息？
4. 信息缺失：关键细节是否缺失？

【输出格式】
返回JSON：
{{
  "stance": "oppose",
  "main_arguments": [
    {{
      "claim": "质疑论点",
      "evidence_ids": ["证据ID列表"],
      "reasoning": "质疑过程：证据A显示...但...因此存在疑点...",
      "weakness_type": "LOGIC_GAP/CONFLICT/RELIABILITY/MISSING"
    }}
  ],
  "doubts_summary": "疑点综述",
  "risk_level": 0.0-1.0,
  "critical_issues": ["关键问题列表"]
}}
"""

DEBATE_JUDGE_SYSTEM_PROMPT = """你是Aletheia裁判。你的职责是综合正反双方论点，给出最终裁决。

【核心任务】
权衡正反双方的论点和证据，给出客观的综合判断。

【裁决框架】
1. 论点强度对比：哪方论点更有力？
2. 证据质量对比：哪方证据更可靠？
3. 逻辑完整性：哪方推理更严密？
4. 不确定性分析：存在哪些未知因素？

【输出格式】
返回JSON：
{{
  "final_verdict": "SUPPORTED/PARTIALLY_SUPPORTED/UNCERTAIN/PARTIALLY_REFUTED/REFUTED",
  "credibility_score": 0.0-1.0,
  "reasoning_summary": "综合推理过程",
  "key_findings": [
    {{
      "finding": "关键发现",
      "evidence_support": ["支持证据"],
      "confidence": 0.0-1.0
    }}
  ],
  "unresolved_questions": ["未解决问题"],
  "recommendation": "处置建议"
}}
"""


class DebateReasoningEngine:
    """辩论式推理引擎 - 使用 OpenAI 兼容 API"""

    def __init__(self, llm_client=None):
        # 优先使用传入的 llm_client，否则使用硅基流动配置
        if llm_client:
            self.llm_client = llm_client
            self.client = llm_client.client
            self.model = llm_client.large_model
        else:
            # 使用通用配置（默认回退到 SiliconFlow）
            self.model = (
                getattr(settings, "LLM_LARGE_MODEL", None)
                or getattr(settings, "SILICONFLOW_LARGE_MODEL", None)
                or getattr(settings, "LLM_MODEL", None)
                or settings.SILICONFLOW_MODEL
            )
            self.api_key = (
                getattr(settings, "LLM_API_KEY", None)
                or getattr(settings, "SILICONFLOW_API_KEY", None)
            )
            self.base_url = (
                getattr(settings, "LLM_API_BASE", None)
                or getattr(settings, "SILICONFLOW_API_BASE", None)
                or "https://api.siliconflow.cn/v1"
            )
    
    async def analyze_with_debate(
        self,
        claim: str,
        evidence_pool: List[Dict[str, Any]],
        keyword: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        使用辩论式推理分析命题
        
        Args:
            claim: 待验证的命题
            evidence_pool: 证据池
            keyword: 关键词
            context: 额外上下文
            
        Returns:
            辩论式推理结果
        """
        logger.info(f"🎭 DebateReasoning: 开始辩论式分析 - {keyword}")
        
        # 准备证据摘要
        evidence_summary = self._prepare_evidence_summary(evidence_pool)
        
        # 并行执行正方、反方分析
        pro_task = self._run_debate_side(
            prompt=DEBATE_PRO_SYSTEM_PROMPT,
            claim=claim,
            evidence_summary=evidence_summary,
            side="正方"
        )
        con_task = self._run_debate_side(
            prompt=DEBATE_CON_SYSTEM_PROMPT,
            claim=claim,
            evidence_summary=evidence_summary,
            side="反方"
        )
        
        pro_result, con_result = await asyncio.gather(pro_task, con_task)
        
        # 执行裁判综合
        judge_result = await self._run_judge(
            claim=claim,
            pro_result=pro_result,
            con_result=con_result,
            evidence_summary=evidence_summary
        )
        
        # 构建完整辩论结果
        debate_result = {
            "claim": claim,
            "keyword": keyword,
            "timestamp": datetime.utcnow().isoformat(),
            "debate_process": {
                "proponent": pro_result,
                "opponent": con_result,
                "judge": judge_result
            },
            "final_conclusion": {
                "verdict": judge_result.get("final_verdict", "UNCERTAIN"),
                "credibility_score": judge_result.get("credibility_score", 0.5),
                "reasoning_summary": judge_result.get("reasoning_summary", ""),
                "key_findings": judge_result.get("key_findings", []),
                "recommendation": judge_result.get("recommendation", "")
            },
            "evidence_used": len(evidence_pool),
            "unresolved_questions": judge_result.get("unresolved_questions", [])
        }
        
        logger.info(f"🎭 DebateReasoning: 辩论完成 - 结论: {debate_result['final_conclusion']['verdict']}")
        
        return debate_result
    
    def _prepare_evidence_summary(self, evidence_pool: List[Dict[str, Any]]) -> str:
        """准备证据摘要供LLM分析"""
        summaries = []
        
        # 按tier分组
        tier_groups = {1: [], 2: [], 3: []}
        for ev in evidence_pool[:30]:  # 限制数量
            tier = int(ev.get("source_tier") or 3)
            if tier in tier_groups:
                tier_groups[tier].append(ev)
        
        for tier in [1, 2, 3]:
            if tier_groups[tier]:
                summaries.append(f"\n=== Tier{tier} 证据 ({len(tier_groups[tier])}条) ===")
                for i, ev in enumerate(tier_groups[tier][:5], 1):
                    source = ev.get("source_name", "未知来源")
                    snippet = (ev.get("snippet") or ev.get("title") or "")[:150]
                    url = ev.get("url", "")
                    published = ev.get("published_at", "未知时间")
                    summaries.append(f"{i}. [{source}] {snippet}")
                    summaries.append(f"   时间: {published} | URL: {url}")
        
        return "\n".join(summaries)
    
    async def _run_debate_side(
        self,
        prompt: str,
        claim: str,
        evidence_summary: str,
        side: str
    ) -> Dict[str, Any]:
        """执行单方辩论"""
        try:
            import httpx
            
            user_message = f"""
待验证命题：{claim}

可用证据：
{evidence_summary}

请基于以上证据，从{side}角度进行分析论证。
"""
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                }
                
                base_url = self.base_url or "https://api.siliconflow.cn/v1"
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    # 尝试解析JSON
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {
                            "stance": side,
                            "raw_response": content,
                            "error": "JSON解析失败"
                        }
                else:
                    return {"error": f"API错误: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"辩论{side}分析失败: {e}")
            return {"error": str(e)}
    
    async def _run_judge(
        self,
        claim: str,
        pro_result: Dict[str, Any],
        con_result: Dict[str, Any],
        evidence_summary: str
    ) -> Dict[str, Any]:
        """执行裁判综合"""
        try:
            import httpx
            
            user_message = f"""
待验证命题：{claim}

【正方论点】
{json.dumps(pro_result, ensure_ascii=False, indent=2)}

【反方论点】
{json.dumps(con_result, ensure_ascii=False, indent=2)}

【证据摘要】
{evidence_summary}

请综合正反双方论点，给出最终裁决。
"""
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DEBATE_JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2000
                }
                
                base_url = self.base_url or "https://api.siliconflow.cn/v1"
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {
                            "final_verdict": "UNCERTAIN",
                            "raw_response": content
                        }
                else:
                    return {"error": f"API错误: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"裁判分析失败: {e}")
            return {"error": str(e)}


def generate_cot_display(debate_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成用于前端展示的CoT思维链结构
    """
    debate_process = debate_result.get("debate_process", {})
    proponent = debate_process.get("proponent", {})
    opponent = debate_process.get("opponent", {})
    judge = debate_process.get("judge", {})
    
    return {
        "thinking_chain": {
            "phase1_evidence_review": {
                "title": "证据审查",
                "description": "审查收集到的证据，评估来源可信度和内容相关性",
                "evidence_count": debate_result.get("evidence_used", 0)
            },
            "phase2_proponent_analysis": {
                "title": "正方论证",
                "description": "从支持命题的角度构建论证链条",
                "arguments": proponent.get("main_arguments", []),
                "confidence": proponent.get("confidence", 0.5),
                "key_sources": proponent.get("key_sources", [])
            },
            "phase3_opponent_analysis": {
                "title": "反方质疑",
                "description": "从质疑命题的角度寻找逻辑漏洞和矛盾点",
                "arguments": opponent.get("main_arguments", []),
                "risk_level": opponent.get("risk_level", 0.5),
                "critical_issues": opponent.get("critical_issues", [])
            },
            "phase4_judge_synthesis": {
                "title": "综合裁决",
                "description": "权衡正反双方论点，给出最终判断",
                "verdict": judge.get("final_verdict", "UNCERTAIN"),
                "credibility_score": judge.get("credibility_score", 0.5),
                "key_findings": judge.get("key_findings", []),
                "recommendation": judge.get("recommendation", "")
            }
        },
        "final_conclusion": debate_result.get("final_conclusion", {}),
        "unresolved_questions": debate_result.get("unresolved_questions", [])
    }
