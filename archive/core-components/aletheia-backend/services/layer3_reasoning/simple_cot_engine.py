"""
轻量级 CoT 推理引擎 - 开发模式
使用 SQLite 数据库替代 PostgreSQL
直接使用 SiliconFlow API
"""

import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from core.config import settings
from core.sqlite_database import get_sqlite_db
from utils.logging import logger


class ReasoningStage(str, Enum):
    """推理阶段"""

    PREPROCESSING = "preprocessing"
    PHYSICAL_CHECK = "physical_check"
    LOGICAL_CHECK = "logical_check"
    SOURCE_ANALYSIS = "source_analysis"
    CROSS_VALIDATION = "cross_validation"
    ANOMALY_DETECTION = "anomaly_detection"
    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    SELF_REFLECTION = "self_reflection"


class ReasoningStep(BaseModel):
    """单步推理结果"""

    stage: str
    timestamp: str
    reasoning: str
    conclusion: str
    confidence: float
    evidence: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    score_impact: float = 0.0


class ReasoningChain(BaseModel):
    """完整推理链"""

    steps: List[ReasoningStep]
    final_score: float
    final_level: str
    risk_flags: List[str]
    total_confidence: float
    processing_time_ms: int


class SimpleCoTEngine:
    """轻量级 CoT 推理引擎（开发模式）"""

    def __init__(self):
        llm_api_key = (
            getattr(settings, "LLM_API_KEY", None) or settings.SILICONFLOW_API_KEY
        )
        llm_base_url = (
            getattr(settings, "LLM_API_BASE", None) or settings.SILICONFLOW_API_BASE
        )
        self.llm = AsyncOpenAI(
            api_key=llm_api_key,
            base_url=llm_base_url,
        )

    async def analyze(
        self,
        content: str,
        source_platform: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        image_urls: Optional[List[str]] = None,
    ) -> ReasoningChain:
        """
        执行8步推理分析
        """
        start_time = time.time()
        logger.info(f"🧠 Simple CoT analyzing: {content[:80]}...")

        # 构建系统提示词
        system_prompt = self._build_system_prompt()

        # 构建用户输入
        user_prompt = self._build_user_prompt(
            content, source_platform, metadata, image_urls
        )

        try:
            # 调用 LLM 进行推理
            response = await self.llm.chat.completions.create(
                model=settings.SILICONFLOW_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.SILICONFLOW_TEMPERATURE,
                max_tokens=settings.SILICONFLOW_MAX_TOKENS,
            )

            # 解析 LLM 输出
            result_text = response.choices[0].message.content
            reasoning_chain = self._parse_llm_response(result_text)

            processing_time_ms = int((time.time() - start_time) * 1000)
            reasoning_chain.processing_time_ms = processing_time_ms

            logger.info(
                f"✅ Simple CoT completed - Score: {reasoning_chain.final_score:.2%} "
                f"in {processing_time_ms}ms"
            )

            return reasoning_chain

        except Exception as e:
            logger.error(f"❌ Simple CoT analysis failed: {e}")
            # 返回一个默认的失败响应
            return self._create_fallback_chain(content, str(e))

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是 Aletheia - 真相解蔽引擎的核心推理模块。

【核心使命】
以第一性原理和多步推理，审查信息的真实性。

【输出格式 - 必须严格遵守】
请严格按照以下JSON格式输出分析结果：

```json
{
  "steps": [
    {
      "stage": "preprocessing",
      "reasoning": "提取核心主张...",
      "conclusion": "识别出3个关键主张点",
      "confidence": 0.92,
      "evidence": ["原文提取", "关键词识别"],
      "concerns": [],
      "score_impact": 0.0
    },
    {
      "stage": "physical_check",
      "reasoning": "检查时间一致性、物理规律...",
      "conclusion": "时间线合理/不合理",
      "confidence": 0.85,
      "evidence": ["时间点A", "地点B"],
      "concerns": ["时间矛盾"],
      "score_impact": -0.15
    },
    {
      "stage": "logical_check",
      "reasoning": "分析逻辑链条、因果关系...",
      "conclusion": "逻辑链条完整/存在漏洞",
      "confidence": 0.88,
      "evidence": ["因果分析"],
      "concerns": ["因果不明"],
      "score_impact": -0.10
    },
    {
      "stage": "source_analysis",
      "reasoning": "评估信息来源可信度...",
      "conclusion": "来源可信/存疑",
      "confidence": 0.80,
      "evidence": ["平台A", "作者B"],
      "concerns": ["账号新注册"],
      "score_impact": -0.05
    },
    {
      "stage": "cross_validation",
      "reasoning": "交叉验证多个信息源...",
      "conclusion": "多方证实/无法证实",
      "confidence": 0.75,
      "evidence": ["媒体A报道", "官方声明"],
      "concerns": ["缺乏第三方证实"],
      "score_impact": -0.10
    },
    {
      "stage": "anomaly_detection",
      "reasoning": "检测异常模式、传播特征...",
      "conclusion": "传播正常/存在异常",
      "confidence": 0.82,
      "evidence": ["传播速度", "情感分析"],
      "concerns": ["水军痕迹"],
      "score_impact": -0.08
    },
    {
      "stage": "evidence_synthesis",
      "reasoning": "综合所有证据...",
      "conclusion": "证据链完整度评估",
      "confidence": 0.85,
      "evidence": ["综合证据"],
      "concerns": [],
      "score_impact": 0.05
    },
    {
      "stage": "self_reflection",
      "reasoning": "AI自我质疑、检查推理偏见...",
      "conclusion": "推理过程自检结果",
      "confidence": 0.90,
      "evidence": ["推理一致性检查"],
      "concerns": ["可能的认知偏差"],
      "score_impact": -0.02
    }
  ],
  "final_score": 0.65,
  "final_level": "UNCERTAIN",
  "risk_flags": ["UNVERIFIED_CLAIM", "NEEDS_REVIEW"],
  "total_confidence": 0.84
}
```

【评分标准】
- final_score: 0.0-1.0，信息可信度评分
- final_level: 枚举值 [VERIFIED, LIKELY_TRUE, UNCERTAIN, LIKELY_FALSE, FABRICATED]
- risk_flags: 风险标签数组，可选值：
  - FABRICATED: 完全捏造
  - MANIPULATED_MEDIA: 篡改的媒体
  - UNVERIFIED_CLAIM: 未证实的主张
  - OUT_OF_CONTEXT: 断章取义
  - BOT_AMPLIFICATION: 机器人放大
  - COORDINATED_INAUTHENTIC: 协同造假
  - NEEDS_REVIEW: 需要人工复核
  - LOW_CREDIBILITY_SOURCE: 低可信度来源

【推理原则】
1. 保持怀疑态度，要求证据支持
2. 识别逻辑谬误（滑坡谬误、虚假二分法等）
3. 检查来源可信度
4. 交叉验证关键信息
5. 标记不确定的地方

只输出JSON，不要其他文字。"""

    def _build_user_prompt(
        self,
        content: str,
        source_platform: Optional[str],
        metadata: Optional[Dict[str, Any]],
        image_urls: Optional[List[str]],
    ) -> str:
        """构建用户提示词"""
        prompt = f"请分析以下信息的真实性：\n\n"
        prompt += f"【内容】\n{content}\n\n"

        if source_platform:
            prompt += f"【来源平台】\n{source_platform}\n\n"

        if metadata:
            prompt += (
                f"【元数据】\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n"
            )

        if image_urls:
            prompt += f"【图片URL】\n{', '.join(image_urls)}\n\n"

        prompt += "请严格按照系统提示中的JSON格式输出8步推理链分析结果。"
        return prompt

    def _parse_llm_response(self, text: str) -> ReasoningChain:
        """解析 LLM 响应"""
        try:
            # 提取 JSON 部分
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0].strip()
            else:
                json_str = text.strip()

            data = json.loads(json_str)

            # 添加时间戳
            for step in data.get("steps", []):
                step["timestamp"] = datetime.utcnow().isoformat()

            return ReasoningChain(
                steps=[ReasoningStep(**step) for step in data.get("steps", [])],
                final_score=data.get("final_score", 0.5),
                final_level=data.get("final_level", "UNCERTAIN"),
                risk_flags=data.get("risk_flags", ["NEEDS_REVIEW"]),
                total_confidence=data.get("total_confidence", 0.5),
                processing_time_ms=0,
            )

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {text[:500]}")
            return self._create_fallback_chain(text, str(e))

    def _create_fallback_chain(self, content: str, error: str) -> ReasoningChain:
        """创建回退响应（当 LLM 调用失败时）"""
        return ReasoningChain(
            steps=[
                ReasoningStep(
                    stage="preprocessing",
                    timestamp=datetime.utcnow().isoformat(),
                    reasoning=f"处理用户输入: {content[:100]}...",
                    conclusion="提取核心主张",
                    confidence=0.7,
                    evidence=["用户输入"],
                    concerns=[],
                    score_impact=0.0,
                ),
                ReasoningStep(
                    stage="error",
                    timestamp=datetime.utcnow().isoformat(),
                    reasoning=f"分析过程中出现错误: {error}",
                    conclusion="无法完成完整分析",
                    confidence=0.0,
                    evidence=[],
                    concerns=["系统错误"],
                    score_impact=0.0,
                ),
            ],
            final_score=0.5,
            final_level="UNCERTAIN",
            risk_flags=["NEEDS_REVIEW", "SYSTEM_ERROR"],
            total_confidence=0.3,
            processing_time_ms=0,
        )


# 全局引擎实例
_simple_engine: Optional[SimpleCoTEngine] = None


def get_simple_engine() -> SimpleCoTEngine:
    """获取轻量级引擎实例"""
    global _simple_engine
    if _simple_engine is None:
        _simple_engine = SimpleCoTEngine()
    return _simple_engine


# 兼容原有接口
async def analyze_intel_enhanced(
    content: str,
    source_platform: Optional[str] = None,
    original_url: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db=None,
    cache=None,
):
    """
    增强版情报分析（SQLite 版本）

    使用 SQLite 数据库存储分析结果
    """
    engine = get_simple_engine()

    reasoning_chain = await engine.analyze(
        content=content,
        source_platform=source_platform,
        metadata=metadata,
        image_urls=image_urls,
    )

    # 创建 Intel 对象
    intel_id = f"intel_{int(time.time() * 1000)}"
    intel_dict = {
        "id": intel_id,
        "content_text": content,
        "source_platform": source_platform or "unknown",
        "original_url": original_url,
        "credibility_score": reasoning_chain.final_score,
        "credibility_level": reasoning_chain.final_level,
        "risk_flags": reasoning_chain.risk_flags,
        "verification_status": "analyzed",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }

    # 保存到 SQLite 数据库
    try:
        sqlite_db = get_sqlite_db()
        reasoning_dict = {
            "steps": [step.model_dump() for step in reasoning_chain.steps],
            "final_score": reasoning_chain.final_score,
            "final_level": reasoning_chain.final_level,
            "risk_flags": reasoning_chain.risk_flags,
            "total_confidence": reasoning_chain.total_confidence,
            "processing_time_ms": reasoning_chain.processing_time_ms,
        }
        sqlite_db.save_intel(intel_dict, reasoning_dict)
        logger.info(f"💾 Analysis result saved to SQLite: {intel_id}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to save to SQLite: {e}")

    return intel_dict, reasoning_chain
