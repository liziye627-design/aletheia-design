"""
硅基流动视觉模型集成 - 用于图片/视频内容分析
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import base64

from utils.logging import logger
from utils.stability import retry_async, CircuitBreaker, with_retry


class SiliconFlowVisionService:
    """硅基流动视觉模型服务"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化服务

        Args:
            api_key: 硅基流动API密钥
        """
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        self.base_url = "https://api.siliconflow.cn/v1"
        self.model = "Pro/Qwen/Qwen2-VL-72B-Instruct"  # 默认使用Qwen2-VL视觉模型
        self.session = None
        self.circuit_breaker = CircuitBreaker(
            "siliconflow",
            failure_threshold=3,
            recovery_timeout=120,
        )
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        try:
            import aiohttp

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            self.session = aiohttp.ClientSession(headers=headers)
            logger.info("✅ SiliconFlow vision service initialized")
        except ImportError:
            logger.warning("⚠️ aiohttp not installed. Install with: pip install aiohttp")

    async def download_image(self, url: str) -> Optional[bytes]:
        """
        下载图片

        Args:
            url: 图片URL

        Returns:
            图片字节数据
        """
        if not self.session:
            return None

        try:
            async with self.session.get(url, timeout=15) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.warning(f"⚠️ Failed to download image: {url}")
                    return None
        except Exception as e:
            logger.error(f"❌ Error downloading image: {e}")
            return None

    def encode_image_to_base64(self, image_bytes: bytes) -> str:
        """
        将图片编码为Base64

        Args:
            image_bytes: 图片字节数据

        Returns:
            Base64编码字符串
        """
        return base64.b64encode(image_bytes).decode("utf-8")

    @with_retry(max_retries=3, base_delay=2.0, exceptions=(Exception,))
    async def analyze_image(
        self,
        image_url: str,
        prompt: str = "请详细描述这张图片的内容，包括：1) 主要对象和场景 2) 文字内容（如有）3) 是否存在异常或可疑之处",
        use_base64: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        使用视觉模型分析图片

        Args:
            image_url: 图片URL
            prompt: 分析提示词
            use_base64: 是否使用Base64编码（适用于私有图片）

        Returns:
            分析结果
        """
        if not self.api_key:
            logger.error("❌ SiliconFlow API key not configured")
            return None

        if not self.session:
            logger.error("❌ Session not initialized")
            return None

        logger.info(f"🔍 Analyzing image: {image_url}")

        try:
            # 构建消息
            if use_base64:
                # 下载图片并转换为Base64
                image_bytes = await self.download_image(image_url)
                if not image_bytes:
                    return None

                image_b64 = self.encode_image_to_base64(image_bytes)
                image_content = f"data:image/jpeg;base64,{image_b64}"
            else:
                # 直接使用URL
                image_content = image_url

            # 构建请求
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_content},
                            },
                        ],
                    }
                ],
                "max_tokens": 1024,
                "temperature": 0.7,
            }

            # 发起请求
            async with self.circuit_breaker.call_async(
                self._make_request, f"{self.base_url}/chat/completions", payload
            ) as response_data:
                if not response_data:
                    return None

                # 解析响应
                content = (
                    response_data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )

                result = {
                    "image_url": image_url,
                    "prompt": prompt,
                    "analysis": content,
                    "model": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "usage": response_data.get("usage", {}),
                }

                logger.info(f"✅ Image analysis completed: {len(content)} chars")
                return result

        except Exception as e:
            logger.error(f"❌ Error analyzing image: {e}")
            return None

    async def _make_request(self, url: str, payload: dict) -> Optional[dict]:
        """
        发起API请求

        Args:
            url: 请求URL
            payload: 请求数据

        Returns:
            响应数据
        """
        if not self.session:
            return None

        async with self.session.post(url, json=payload, timeout=30) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                logger.error(
                    f"❌ SiliconFlow API error: {response.status} - {error_text}"
                )
                return None

    async def detect_fake_image(
        self,
        image_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        检测图片是否为伪造/PS

        Args:
            image_url: 图片URL

        Returns:
            检测结果
        """
        prompt = (
            "请仔细分析这张图片，判断是否存在以下问题：\n"
            "1. PS痕迹（光影不自然、边缘模糊等）\n"
            "2. 合成痕迹（多张图片拼接）\n"
            "3. 内容不合理（物理规律违背、逻辑矛盾）\n"
            "4. 其他可疑之处\n\n"
            "请给出：\n"
            "- 是否伪造（是/否/不确定）\n"
            "- 可疑程度（1-10分）\n"
            "- 具体原因"
        )

        result = await self.analyze_image(image_url, prompt=prompt)

        if not result:
            return None

        # 解析结果（简化版，实际应使用NLP提取结构化信息）
        analysis = result["analysis"].lower()

        is_fake = "是" in analysis or "伪造" in analysis or "ps" in analysis
        confidence = 0.0

        # 简单的置信度评估
        if "可疑程度" in analysis:
            # 尝试提取数字
            import re

            matches = re.findall(r"(\d+)分", analysis)
            if matches:
                confidence = int(matches[0]) / 10.0

        return {
            "image_url": image_url,
            "is_fake": is_fake,
            "confidence": confidence,
            "analysis": result["analysis"],
            "model": self.model,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def extract_text_from_image(
        self,
        image_url: str,
    ) -> Optional[Dict[str, Any]]:
        """
        从图片中提取文字（OCR）

        Args:
            image_url: 图片URL

        Returns:
            提取的文字
        """
        prompt = (
            "请提取这张图片中的所有文字内容。\n"
            "要求：\n"
            "1. 按原文顺序输出\n"
            "2. 保留格式（换行、标点等）\n"
            '3. 如果没有文字，请回答"无文字"'
        )

        result = await self.analyze_image(image_url, prompt=prompt)

        if not result:
            return None

        return {
            "image_url": image_url,
            "extracted_text": result["analysis"],
            "model": self.model,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def analyze_batch_images(
        self,
        image_urls: List[str],
        prompt: Optional[str] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        批量分析图片

        Args:
            image_urls: 图片URL列表
            prompt: 分析提示词
            max_concurrent: 最大并发数

        Returns:
            分析结果列表
        """
        logger.info(f"🔍 Analyzing {len(image_urls)} images in batches...")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_semaphore(url):
            async with semaphore:
                return await self.analyze_image(url, prompt=prompt or "请描述这张图片")

        tasks = [analyze_with_semaphore(url) for url in image_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤异常
        valid_results = [
            r for r in results if not isinstance(r, Exception) and r is not None
        ]

        logger.info(
            f"✅ Batch analysis completed: {len(valid_results)}/{len(image_urls)} successful"
        )
        return valid_results

    async def verify_news_image(
        self,
        image_url: str,
        news_content: str,
    ) -> Optional[Dict[str, Any]]:
        """
        验证新闻图片与内容是否匹配

        Args:
            image_url: 图片URL
            news_content: 新闻内容

        Returns:
            验证结果
        """
        prompt = f"""
请判断这张图片是否与以下新闻内容相符：

新闻内容：
{news_content[:500]}

请分析：
1. 图片与新闻是否相关（是/否）
2. 匹配程度（1-10分）
3. 具体原因
4. 是否存在移花接木的可能性
"""

        result = await self.analyze_image(image_url, prompt=prompt)

        if not result:
            return None

        analysis = result["analysis"]

        # 简单解析
        is_match = "是" in analysis and "相关" in analysis

        return {
            "image_url": image_url,
            "news_content_preview": news_content[:200],
            "is_match": is_match,
            "analysis": analysis,
            "model": self.model,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def close(self):
        """关闭服务"""
        if self.session:
            await self.session.close()
            logger.info("✅ SiliconFlow vision service closed")


# 全局单例
_siliconflow_service: Optional[SiliconFlowVisionService] = None


def get_vision_service() -> SiliconFlowVisionService:
    """获取视觉服务单例"""
    global _siliconflow_service

    if _siliconflow_service is None:
        _siliconflow_service = SiliconFlowVisionService()

    return _siliconflow_service
