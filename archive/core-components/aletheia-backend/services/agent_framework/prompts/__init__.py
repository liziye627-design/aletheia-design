"""
Aletheia LLM Reasoning Node
===========================

使用详细提示词进行 LLM 推理的节点
借鉴 BettaFish 的章节生成机制
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from loguru import logger

# 添加父目录到路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)

from core.config import settings


class LLMReasoningEngine:
    """
    LLM 推理引擎

    基于详细提示词进行各 Step 的推理，
    生成详细具体的推理结果。
    """

    def __init__(
        self, api_key: str = None, base_url: str = None, model_name: str = None
    ):
        """
        初始化 LLM 推理引擎

        Args:
            api_key: API 密钥
            base_url: API 基础地址
            model_name: 模型名称
        """
        self.api_key = api_key or getattr(settings, "SILICONFLOW_API_KEY", None)
        self.base_url = base_url or "https://api.siliconflow.cn/v1"
        self.model = model_name or "Qwen/Qwen2.5-32B-Instruct"

        if not self.api_key:
            logger.warning("未找到 API 密钥，LLM 推理功能将不可用")
            self.client = None
        else:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                logger.info("LLM 推理引擎已初始化")
            except ImportError:
                logger.error("未安装 openai 库，LLM 推理功能将不可用")
                self.client = None

    def reason(
        self,
        step_key: str,
        state_data: Dict[str, Any],
        search_results: List[Dict],
        previous_steps: List[Dict],
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        执行推理

        Args:
            step_key: Step 标识
            state_data: 状态数据
            search_results: 搜索结果
            previous_steps: 之前的推理步骤
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            推理结果
        """
        # 导入提示词
        from .verification_prompts import (
            get_step_prompt,
            build_step_user_prompt,
            get_step_number,
        )

        # 获取提示词
        prompt_info = get_step_prompt(step_key)
        system_prompt = prompt_info["system_prompt"]
        step_name = prompt_info["name"]
        step_number = get_step_number(step_key)

        logger.info(f"[Step {step_number}] 开始 {step_name} 推理...")

        # 构建用户提示词
        user_prompt = build_step_user_prompt(
            step_key=step_key,
            state_data=state_data,
            search_results=search_results,
            previous_steps=previous_steps,
        )

        # 如果没有 LLM 客户端，使用模拟推理
        if not self.client:
            logger.warning(f"LLM 客户端不可用，使用模拟推理")
            return self._mock_reasoning(step_key, state_data, search_results)

        try:
            # 调用 LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 解析响应
            content = response.choices[0].message.content
            result = self._parse_llm_response(content, step_key)

            logger.info(f"[Step {step_number}] {step_name} 推理完成")
            logger.debug(f"置信度: {result.get('confidence', 0)}")
            logger.debug(f"结论: {result.get('conclusion', 'N/A')[:100]}...")

            return result

        except Exception as e:
            logger.error(f"LLM 推理失败: {e}")
            return self._mock_reasoning(step_key, state_data, search_results)

    def _parse_llm_response(self, content: str, step_key: str) -> Dict[str, Any]:
        """
        解析 LLM 响应

        Args:
            content: LLM 返回的内容
            step_key: Step 标识

        Returns:
            解析后的结果
        """
        try:
            # 尝试直接解析 JSON
            content = content.strip()

            # 移除可能的 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            content = content.strip()

            # 解析 JSON
            result = json.loads(content)

            # 确保包含必要字段
            required_fields = [
                "reasoning",
                "conclusion",
                "confidence",
                "evidence",
                "concerns",
                "score_impact",
            ]
            for field in required_fields:
                if field not in result:
                    result[field] = (
                        ""
                        if field in ["reasoning", "conclusion"]
                        else ([] if field in ["evidence", "concerns"] else 0.0)
                    )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            # 尝试提取关键信息
            return self._extract_from_text(content, step_key)

    def _extract_from_text(self, text: str, step_key: str) -> Dict[str, Any]:
        """
        从文本中提取关键信息（当 JSON 解析失败时）
        """
        result = {
            "reasoning": "LLM 输出格式异常，从文本提取关键信息",
            "conclusion": "",
            "confidence": 0.5,
            "evidence": [],
            "concerns": [],
            "score_impact": 0.0,
        }

        # 尝试提取结论
        conclusion_patterns = [
            r"结论[:：]\s*(.+?)(?:\n|$)",
            r"总结[:：]\s*(.+?)(?:\n|$)",
            r"判定[:：]\s*(.+?)(?:\n|$)",
        ]

        for pattern in conclusion_patterns:
            import re

            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["conclusion"] = match.group(1).strip()
                break

        # 尝试提取置信度
        confidence_patterns = [
            r"置信度[:：]?\s*(\d+\.?\d*)",
            r"confidence[:：]?\s*(\d+\.?\d*)",
            r"(\d+\.?\d*)\s*分",
        ]

        for pattern in confidence_patterns:
            import re

            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    conf = float(match.group(1))
                    if conf > 1:
                        conf = conf / 100
                    result["confidence"] = min(max(conf, 0), 1)
                    break
                except:
                    pass

        # 如果没有提取到结论，使用文本前200字
        if not result["conclusion"]:
            result["conclusion"] = text[:200] + "..." if len(text) > 200 else text

        # 提取推理过程
        result["reasoning"] = text[:500] + "..." if len(text) > 500 else text

        return result

    def _mock_reasoning(
        self, step_key: str, state_data: Dict[str, Any], search_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        模拟推理（当 LLM 不可用时）
        """
        from .verification_prompts import get_step_prompt

        prompt_info = get_step_prompt(step_key)
        step_name = prompt_info["name"]
        query = state_data.get("query", "")

        # 基于 Step 类型生成模拟结果
        if step_key == "claim_parse":
            return {
                "reasoning": f"【模拟推理】对命题'{query}'进行了详细解析。识别出这是一个事实性命题，涉及具体事件和主体。通过分析命题结构，提取了3个关键子命题，每个子命题都有明确的验证标准。考虑到命题的明确性和可验证性，给予了较高的初始置信度。",
                "conclusion": f"命题'{query}'可拆解为3个可验证的子命题，命题类型为事实性命题，具有明确的验证路径。",
                "confidence": 0.80,
                "evidence": ["命题结构清晰", "关键要素明确"],
                "concerns": ["部分信息需要进一步核实"],
                "score_impact": 0.05,
                "proposition_type": "事实性命题",
                "sub_propositions": [
                    {"id": 1, "content": "子命题1", "verification_criteria": "可验证"},
                    {"id": 2, "content": "子命题2", "verification_criteria": "可验证"},
                    {"id": 3, "content": "子命题3", "verification_criteria": "可验证"},
                ],
            }

        elif step_key == "source_verification":
            high_quality = sum(
                1 for r in search_results if r.get("evidence_quality") == "high"
            )
            total = len(search_results)
            confidence = 0.5 + (high_quality / max(total, 1)) * 0.4

            return {
                "reasoning": f"【模拟推理】对{total}个信息来源进行了详细评估。发现{high_quality}个高可信度信源，主要为官方媒体和专业机构。其余信源分布在自媒体和UGC平台。通过分析信源的权威性、时效性和可溯源性，综合评估了整体可信度。部分信源虽然来自社交媒体，但内容可被多方验证，增加了整体可信度。",
                "conclusion": f"共评估{total}个信源，其中{high_quality}个高可信度信源。官方媒体和权威机构提供了核心证据支撑。",
                "confidence": round(confidence, 2),
                "evidence": [f"高可信度信源{high_quality}个", "官方媒体报道"],
                "concerns": ["部分信源为社交媒体内容"] if high_quality < total else [],
                "score_impact": 0.15,
                "detailed_source_analysis": [
                    {
                        "platform": r.get("platform", "unknown"),
                        "credibility_score": 0.9
                        if r.get("evidence_quality") == "high"
                        else 0.6,
                        "evidence_quality": r.get("evidence_quality", "unknown"),
                    }
                    for r in search_results[:5]
                ],
            }

        elif step_key == "cross_validation":
            return {
                "reasoning": f"【模拟推理】对多个独立信源进行了交叉验证。通过对比不同信源对同一事件或事实的描述，发现核心事实基本一致，但在细节描述上存在一定差异。这种差异在合理范围内，不影响核心结论的可信度。多个权威信源的独立报道增强了命题的可信度。",
                "conclusion": "多源交叉验证显示核心事实一致，不同信源的报道相互印证，增强了整体可信度。",
                "confidence": 0.78,
                "evidence": ["多源一致证实", "核心事实无矛盾"],
                "concerns": ["次要细节存在差异"],
                "score_impact": 0.20,
            }

        elif step_key == "evidence_consistency":
            return {
                "reasoning": f"【模拟推理】对所有证据进行了内在一致性和逻辑合理性分析。检查了时间线、空间关系、数量逻辑、人物行为等多个维度。整体证据链完整，逻辑自洽，未发现明显的逻辑矛盾或异常。时间顺序合理，数量关系协调，因果关系成立。",
                "conclusion": "证据整体一致，逻辑合理，时间线清晰，未发现明显矛盾或异常。",
                "confidence": 0.75,
                "evidence": ["时间线一致", "逻辑关系合理"],
                "concerns": ["部分细节需要更多佐证"],
                "score_impact": 0.15,
            }

        elif step_key == "final_decision":
            # 基于搜索结果数量给出评分
            search_count = len(search_results)
            if search_count >= 10:
                score = 0.80
                level = "HIGH"
            elif search_count >= 5:
                score = 0.65
                level = "MEDIUM"
            elif search_count >= 3:
                score = 0.50
                level = "LOW"
            else:
                score = 0.35
                level = "UNCERTAIN"

            return {
                "reasoning": f"【模拟推理】综合所有推理步骤的结果，做出了最终判定。考虑了证据充分性、证据质量、多源一致性、逻辑合理性、时效性等多个维度。整体证据较为充分，多个权威信源一致证实，逻辑链条完整，未发现有力反证。基于以上分析，给出了综合可信度评分。",
                "conclusion": f"基于综合评估，命题'{query}'的可信度为{score:.0%}，等级为{level}。建议谨慎采信，注意核实。",
                "confidence": score,
                "evidence": ["综合评估结果"],
                "concerns": ["部分信息需要持续跟踪"] if score < 0.8 else [],
                "score_impact": 0.10,
                "decision_summary": {
                    "final_credibility_score": score,
                    "credibility_level": level,
                    "truth_status": "基本属实" if score >= 0.6 else "存疑",
                },
            }

        else:
            return {
                "reasoning": f"【模拟推理】执行了{step_name}的分析",
                "conclusion": f"{step_name}完成，需要进一步验证",
                "confidence": 0.60,
                "evidence": [],
                "concerns": ["需要更多信息"],
                "score_impact": 0.10,
            }


# 便捷函数
def generate_step_reasoning(
    step_key: str,
    state_data: Dict[str, Any],
    search_results: List[Dict],
    previous_steps: List[Dict] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    便捷函数：生成 Step 推理

    Args:
        step_key: Step 标识
        state_data: 状态数据
        search_results: 搜索结果
        previous_steps: 之前的推理步骤
        **kwargs: 其他参数

    Returns:
        推理结果
    """
    engine = LLMReasoningEngine(**kwargs)
    return engine.reason(
        step_key=step_key,
        state_data=state_data,
        search_results=search_results,
        previous_steps=previous_steps or [],
    )
