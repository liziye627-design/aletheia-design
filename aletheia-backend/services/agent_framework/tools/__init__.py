"""
Aletheia Agent Tools
====================

借鉴 BettaFish 项目的工具设计，提供：
- KeywordOptimizer: 关键词优化器
- SentimentAnalyzer: 情感分析器
"""

import os
import sys
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from openai import OpenAI
from loguru import logger

# 添加父目录到路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)
from core.config import settings


@dataclass
class KeywordOptimizationResponse:
    """关键词优化响应"""

    original_query: str
    optimized_keywords: List[str]
    reasoning: str
    success: bool
    error_message: str = ""


class KeywordOptimizer:
    """
    关键词优化器

    使用 LLM 将用户查询优化为更适合舆情数据库查询的关键词，
    主要解决：
    1. 官方术语 vs 网民语言不匹配
    2. 搜索词过于笼统
    3. 缺少情感/态度关键词
    """

    def __init__(
        self, api_key: str = None, base_url: str = None, model_name: str = None
    ):
        """
        初始化关键词优化器

        Args:
            api_key: API密钥，默认从配置读取
            base_url: 接口基础地址
            model_name: 模型名称
        """
        self.api_key = api_key or getattr(settings, "KEYWORD_OPTIMIZER_API_KEY", None)
        self.api_key = self.api_key or getattr(settings, "SILICONFLOW_API_KEY", None)

        if not self.api_key:
            raise ValueError(
                "未找到 API 密钥，请在配置中设置 KEYWORD_OPTIMIZER_API_KEY 或 SILICONFLOW_API_KEY"
            )

        self.base_url = base_url or getattr(
            settings, "KEYWORD_OPTIMIZER_BASE_URL", "https://api.siliconflow.cn/v1"
        )
        self.model = model_name or getattr(
            settings, "KEYWORD_OPTIMIZER_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct"
        )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def optimize(
        self, original_query: str, context: str = ""
    ) -> KeywordOptimizationResponse:
        """
        优化搜索关键词

        Args:
            original_query: 原始搜索查询
            context: 额外的上下文信息

        Returns:
            优化后的关键词列表
        """
        logger.info(
            f"🔍 关键词优化: '{original_query[:50]}...' "
            if len(original_query) > 50
            else f"🔍 关键词优化: '{original_query}'"
        )

        try:
            # 构建提示词
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(original_query, context)

            # 调用 LLM
            response = self._call_llm(system_prompt, user_prompt)

            if response["success"]:
                # 解析响应
                content = response["content"]
                parsed = self._parse_response(content)

                keywords = parsed.get("keywords", [])
                reasoning = parsed.get("reasoning", "")

                # 验证关键词质量
                validated_keywords = self._validate_keywords(keywords)

                logger.info(f"✅ 优化成功: {len(validated_keywords)}个关键词")
                for i, kw in enumerate(validated_keywords[:5], 1):
                    logger.debug(f"   {i}. '{kw}'")

                return KeywordOptimizationResponse(
                    original_query=original_query,
                    optimized_keywords=validated_keywords,
                    reasoning=reasoning,
                    success=True,
                )
            else:
                logger.error(f"❌ API调用失败: {response['error']}")
                # 使用备用方案
                fallback_keywords = self._fallback_extraction(original_query)
                return KeywordOptimizationResponse(
                    original_query=original_query,
                    optimized_keywords=fallback_keywords,
                    reasoning="API调用失败，使用备用关键词提取",
                    success=True,
                    error_message=response["error"],
                )

        except Exception as e:
            logger.error(f"❌ 关键词优化失败: {str(e)}")
            fallback_keywords = self._fallback_extraction(original_query)
            return KeywordOptimizationResponse(
                original_query=original_query,
                optimized_keywords=fallback_keywords,
                reasoning="系统错误，使用备用关键词提取",
                success=False,
                error_message=str(e),
            )

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是一位专业的舆情数据挖掘专家。你的任务是将用户提供的搜索查询优化为更适合在社交媒体舆情数据库中查找的关键词。

**核心原则**：
1. **贴近网民语言**：使用普通网友在社交媒体上会使用的词汇
2. **避免专业术语**：不使用"舆情"、"传播"、"倾向"、"展望"等官方词汇
3. **简洁具体**：每个关键词要非常简洁明了，便于数据库匹配
4. **情感丰富**：包含网民常用的情感表达词汇
5. **数量控制**：最少提供5个关键词，最多提供15个关键词
6. **避免重复**：不要脱离初始查询的主题

**重要提醒**：
- 每个关键词都必须是一个不可分割的独立词条
- 严禁在词条内部包含空格
- 例如：应使用 "雷军班争议" 而不是错误的 "雷军班 争议"

**输出格式**：
请以JSON格式返回结果：
{
    "keywords": ["关键词1", "关键词2", "关键词3"],
    "reasoning": "选择这些关键词的理由"
}

**示例**：
输入："武汉大学舆情管理 未来展望 发展趋势"
输出：
{
    "keywords": ["武大", "武汉大学", "学校管理", "武大教育", "校园事件"],
    "reasoning": "选择'武大'和'武汉大学'作为核心词汇，这是网民最常使用的称呼；'学校管理'比'舆情管理'更贴近日常表达；避免使用'未来展望'、'发展趋势'等网民很少使用的专业术语"
}"""

    def _build_user_prompt(self, original_query: str, context: str) -> str:
        """构建用户提示词"""
        prompt = f"请将以下搜索查询优化为适合舆情数据库查询的关键词：\n\n原始查询：{original_query}"

        if context:
            prompt += f"\n\n上下文信息：{context}"

        prompt += (
            "\n\n请记住：要使用网民在社交媒体上真实使用的词汇，避免官方术语和专业词汇。"
        )

        return prompt

    def _call_llm(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """调用 LLM API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
            )

            if response.choices:
                content = response.choices[0].message.content
                return {"success": True, "content": content}
            else:
                return {"success": False, "error": "API返回格式异常"}

        except Exception as e:
            return {"success": False, "error": f"API调用异常: {str(e)}"}

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        try:
            # 尝试解析 JSON 格式
            content = content.strip()
            if content.startswith("{"):
                return json.loads(content)

            # 尝试从文本中提取
            return self._extract_from_text(content)

        except json.JSONDecodeError:
            return self._extract_from_text(content)

    def _extract_from_text(self, text: str) -> Dict[str, Any]:
        """从文本中提取关键词"""
        keywords = []

        # 查找引号中的内容
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        keywords.extend(quoted)

        # 查找编号列表
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            # 匹配 "1. 关键词" 或 "- 关键词" 格式
            match = re.match(r"^(?:\d+[.．、]|[-*])\s*(.+)$", line)
            if match:
                keywords.append(match.group(1).strip())

        # 清理
        cleaned = []
        for kw in keywords:
            kw = kw.strip().strip('"\'""')
            if kw and len(kw) <= 20 and kw not in cleaned:
                cleaned.append(kw)

        return {"keywords": cleaned[:15], "reasoning": "从文本中提取的关键词"}

    def _validate_keywords(self, keywords: List[str]) -> List[str]:
        """验证和清理关键词"""
        validated = []

        # 不良关键词（过于专业或官方）
        bad_keywords = {
            "舆情",
            "传播",
            "倾向",
            "分析",
            "展望",
            "趋势",
            "战略",
            "规划",
            "政策",
            "导向",
            "机制",
            "态度",
            "公众反应",
            "情绪倾向",
            "未来展望",
            "发展趋势",
            "管理机制",
        }

        for keyword in keywords:
            if not isinstance(keyword, str):
                continue

            keyword = keyword.strip().strip('"\'""')

            # 基本验证
            if (
                keyword
                and len(keyword) <= 20
                and len(keyword) >= 2
                and not any(bad in keyword for bad in bad_keywords)
            ):
                validated.append(keyword)

        return validated[:15]  # 最多15个

    def _fallback_extraction(self, original_query: str) -> List[str]:
        """备用关键词提取方案"""
        # 按空格、标点分割
        tokens = re.split(r"[\s，。！？；：、]+", original_query)

        keywords = []
        for token in tokens:
            token = token.strip()
            if token and len(token) >= 2 and len(token) <= 15:
                keywords.append(token)

        # 如果没有有效关键词，使用原始查询
        if not keywords and original_query.strip():
            keywords = [original_query.strip()[:20]]

        return keywords[:10]


# 全局实例
_keyword_optimizer = None


def get_keyword_optimizer() -> KeywordOptimizer:
    """获取全局关键词优化器实例"""
    global _keyword_optimizer
    if _keyword_optimizer is None:
        _keyword_optimizer = KeywordOptimizer()
    return _keyword_optimizer


def optimize_keywords(query: str, context: str = "") -> KeywordOptimizationResponse:
    """
    便捷函数：优化关键词

    Args:
        query: 原始查询
        context: 上下文信息

    Returns:
        优化响应
    """
    optimizer = get_keyword_optimizer()
    return optimizer.optimize(query, context)


# 从 sentiment.py 导入
from .sentiment import (
    SentimentResult,
    BatchSentimentResult,
    SentimentAnalyzer,
    get_sentiment_analyzer,
    analyze_sentiment,
    analyze_sentiment_batch,
)


__all__ = [
    # Keyword Optimizer
    "KeywordOptimizationResponse",
    "KeywordOptimizer",
    "get_keyword_optimizer",
    "optimize_keywords",
    # Sentiment Analyzer
    "SentimentResult",
    "BatchSentimentResult",
    "SentimentAnalyzer",
    "get_sentiment_analyzer",
    "analyze_sentiment",
    "analyze_sentiment_batch",
]
