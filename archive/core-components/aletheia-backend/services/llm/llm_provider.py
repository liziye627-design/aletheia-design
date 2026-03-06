#!/usr/bin/env python3
"""
多LLM提供商统一接口

支持的LLM:
- OpenAI 兼容接口（默认 SiliconFlow）

使用方法:
    from services.llm.llm_provider import LLMProvider

    llm = LLMProvider()

    # 情感分析
    sentiment = await llm.analyze_sentiment("这个产品真的很棒!")

    # 事实核查
    fact_check = await llm.verify_fact("某平台发布了新模型")

    # 报告生成
    report = await llm.generate_report(data)
"""

import os
import asyncio
import logging
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass
from enum import Enum
import aiohttp
import json


class LLMProvider(Enum):
    """LLM提供商"""

    SILICONFLOW = "siliconflow"
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI = "openai"


@dataclass
class LLMConfig:
    """LLM配置"""

    provider: LLMProvider
    api_key: str
    model: str
    base_url: str
    max_tokens: int = 4000
    temperature: float = 0.7


class LLMClient:
    """统一LLM客户端"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.logger = logging.getLogger(__name__)

        # 如果未提供配置，从环境变量加载
        if config is None:
            config = self._load_config_from_env()

        self.config = config
        self.logger.info(f"初始化LLM客户端: {config.provider.value} ({config.model})")

    def _load_config_from_env(self) -> LLMConfig:
        """从环境变量加载配置"""
        provider_env = os.getenv("LLM_PROVIDER", "siliconflow").lower()
        try:
            provider = LLMProvider(provider_env)
        except ValueError:
            provider = LLMProvider.SILICONFLOW
        return LLMConfig(
            provider=provider,
            api_key=os.getenv("LLM_API_KEY")
            or os.getenv("SILICONFLOW_API_KEY", ""),
            model=os.getenv("LLM_MODEL")
            or os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
            base_url=os.getenv("LLM_API_BASE")
            or os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1"),
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        统一的聊天补全接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            LLM响应文本
        """
        if temperature is None:
            temperature = self.config.temperature
        if max_tokens is None:
            max_tokens = self.config.max_tokens

        # 检查是否跳过LLM调用（测试用）
        if os.getenv("SKIP_LLM_CALLS", "false").lower() == "true":
            self.logger.warning("跳过LLM调用（测试模式）")
            return "测试响应"

        try:
            return await self._openai_compatible_chat(
                messages, temperature, max_tokens
            )

        except Exception as e:
            self.logger.error(f"LLM调用失败: {e}")
            raise

    async def _openai_compatible_chat(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        """OpenAI兼容API调用"""
        url = f"{self.config.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"LLM API错误 ({response.status}): {error_text}")

                result = await response.json()
                return result["choices"][0]["message"]["content"]

    async def analyze_sentiment(
        self, text: str, granularity: Literal[3, 5] = 5
    ) -> Dict[str, Any]:
        """
        情感分析

        Args:
            text: 待分析文本
            granularity: 细粒度 (3: 正/中/负, 5: 很正/正/中/负/很负)

        Returns:
            {
                "sentiment": "positive",  # positive/neutral/negative/very_positive/very_negative
                "score": 0.85,  # 情感强度 0-1
                "confidence": 0.92,  # 置信度
                "reasoning": "分析理由"
            }
        """
        self.logger.info(f"情感分析: {text[:50]}...")

        if granularity == 3:
            sentiment_options = "正面(positive)、中性(neutral)、负面(negative)"
        else:
            sentiment_options = "非常正面(very_positive)、正面(positive)、中性(neutral)、负面(negative)、非常负面(very_negative)"

        prompt = f"""请分析以下文本的情感倾向。

文本: "{text}"

请按照以下JSON格式返回分析结果:
{{
    "sentiment": "{sentiment_options}之一",
    "score": "情感强度(0-1之间的小数)",
    "confidence": "置信度(0-1之间的小数)",
    "reasoning": "简要分析理由(1-2句话)"
}}

要求:
1. 只返回JSON，不要其他内容
2. sentiment必须是指定选项之一
3. score和confidence必须是0-1之间的小数
"""

        messages = [{"role": "user", "content": prompt}]

        response = await self.chat_completion(messages, temperature=0.3)

        # 解析JSON响应
        try:
            # 提取JSON部分 (处理可能的markdown代码块)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            result = json.loads(response)
            return result
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}, 响应: {response}")
            # 返回默认值
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "confidence": 0.5,
                "reasoning": "解析失败",
            }

    async def verify_fact(
        self, claim: str, evidence: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        事实核查

        Args:
            claim: 待验证声明
            evidence: 证据列表

        Returns:
            {
                "verified": true/false,
                "confidence": 0.85,
                "supporting_evidence": [...],
                "contradicting_evidence": [...],
                "reasoning": "分析理由"
            }
        """
        self.logger.info(f"事实核查: {claim}")

        # 构建证据摘要
        evidence_summary = []
        for i, ev in enumerate(evidence[:20], 1):  # 最多20条证据
            evidence_summary.append(
                f"{i}. [{ev.get('source', 'unknown')}] {ev.get('title', '')}"
            )

        evidence_text = "\n".join(evidence_summary)

        prompt = f"""请基于以下证据，验证这个声明的真实性。

声明: "{claim}"

证据:
{evidence_text}

请按照以下JSON格式返回验证结果:
{{
    "verified": true或false,
    "confidence": "置信度(0-1之间的小数)",
    "supporting_count": "支持证据数量",
    "contradicting_count": "矛盾证据数量",
    "reasoning": "详细分析(2-3句话)"
}}

要求:
1. 只返回JSON，不要其他内容
2. 仔细分析证据的来源可信度
3. 如果证据不足或矛盾，confidence应该较低
"""

        messages = [{"role": "user", "content": prompt}]

        response = await self.chat_completion(messages, temperature=0.2)

        # 解析JSON响应
        try:
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            result = json.loads(response)
            return result
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}")
            return {
                "verified": False,
                "confidence": 0.5,
                "supporting_count": 0,
                "contradicting_count": 0,
                "reasoning": "解析失败",
            }

    async def generate_summary(self, texts: List[str], max_length: int = 200) -> str:
        """
        生成摘要

        Args:
            texts: 文本列表
            max_length: 摘要最大长度

        Returns:
            摘要文本
        """
        self.logger.info(f"生成摘要: {len(texts)} 条文本")

        # 合并文本
        combined_text = "\n\n".join(texts[:50])  # 最多50条

        prompt = f"""请为以下内容生成一个简洁的摘要，不超过{max_length}字。

内容:
{combined_text}

要求:
1. 提取核心信息
2. 保持客观中立
3. 不超过{max_length}字
4. 只返回摘要文本，不要其他内容
"""

        messages = [{"role": "user", "content": prompt}]

        response = await self.chat_completion(messages, temperature=0.5)

        return response.strip()


# 便捷函数
async def analyze_sentiment_batch(
    texts: List[str], provider: Optional[str] = None
) -> List[Dict[str, Any]]:
    """批量情感分析"""
    if provider:
        config = LLMClient()._load_config_from_env()
        config.provider = LLMProvider(provider)
        client = LLMClient(config)
    else:
        client = LLMClient()

    results = []
    for text in texts:
        result = await client.analyze_sentiment(text)
        results.append(result)

    return results


# 测试代码
async def main():
    """测试LLM客户端"""
    print("\n" + "=" * 70)
    print("🤖 LLM客户端测试")
    print("=" * 70)

    # 设置测试模式
    os.environ["SKIP_LLM_CALLS"] = "false"
    client = LLMClient()

    # 测试1: 情感分析
    print("\n📊 测试1: 情感分析")
    print("-" * 70)

    test_texts = [
        "这个产品真的太棒了！强烈推荐！",
        "一般般，没什么特别的。",
        "非常失望，完全是浪费钱。",
    ]

    for text in test_texts:
        result = await client.analyze_sentiment(text, granularity=5)
        print(f"\n文本: {text}")
        print(f"情感: {result['sentiment']}")
        print(f"强度: {result['score']:.2f}")
        print(f"置信度: {result['confidence']:.2f}")
        print(f"理由: {result['reasoning']}")

    # 测试2: 事实核查
    print("\n" + "=" * 70)
    print("🔍 测试2: 事实核查")
    print("-" * 70)

    claim = "某平台发布了新模型"
    evidence = [
        {"source": "BBC", "title": "未经证实的GPT-5传闻"},
        {"source": "知乎", "title": "GPT-5尚未发布"},
        {"source": "B站", "title": "辟谣：GPT-5假消息"},
    ]

    result = await client.verify_fact(claim, evidence)
    print(f"\n声明: {claim}")
    print(f"验证结果: {'✅ 真实' if result['verified'] else '❌ 不实'}")
    print(f"置信度: {result['confidence']:.2f}")
    print(f"理由: {result['reasoning']}")

    # 测试3: 摘要生成
    print("\n" + "=" * 70)
    print("📝 测试3: 摘要生成")
    print("-" * 70)

    texts = [
        "人工智能技术在2024年取得了重大突破。",
        "各大科技公司纷纷发布新的AI模型。",
        "AI应用已经深入到各行各业。",
    ]

    summary = await client.generate_summary(texts, max_length=50)
    print(f"\n原文: {len(texts)} 条")
    print(f"摘要: {summary}")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
