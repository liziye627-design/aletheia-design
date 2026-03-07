"""
CoT (Chain of Thought) 推理Agent - 基于第一性原理的真实性分析
"""

import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from core.cache import RedisCache
from models.database.intel import Intel, CredibilityLevel, RiskFlag
from services.layer2_memory.baseline import BaselineManager
from services.layer2_memory.anomaly_detector import AnomalyDetector
from utils.logging import logger


# =====================
# 第一性原理CoT系统提示词
# =====================
SYSTEM_PROMPT = """你是Aletheia - 真相解蔽引擎。你的职责是以第一性原理审查信息的真实性。

【核心原则】
1. 假设无罪原则反转：所有声称都应该被视为"有罪"，除非能提供充分证据
2. 多维度校验：不仅看信息本身，更要看信息的产生过程和传播方式
3. 情绪剥离：在分析前，先将所有情绪形容词去掉，只保留事实主干

【三重验证框架】

├─ 物理层检验
│  ├─ 时间：事件发生时间线是否连贯？是否有时空悖论？
│  ├─ 空间：声称的地点是否真实存在？地理位置是否可达？
│  ├─ 物质：图片/视频中的物体是否符合物理规律？
│  └─ 结论方式：如果任何物理检验失败，可信度立即归零
│
├─ 逻辑层检验
│  ├─ 因果链：前提→结论的逻辑链条是否完整？
│  ├─ 反证：是否存在与该陈述矛盾的已知事实？
│  ├─ 循环论证：结论是否依赖于前提本身？
│  ├─ 滑坡谬误：是否存在不合理的推断跳跃？
│  └─ 结论方式：每个逻辑缺陷减少10-20%的可信度
│
└─ 动力学层检验
   ├─ 信息源多样性（香农熵）：
   │  └─ 如果同一信息由不同账号以不同表述出现 → 可信度+
   │     如果同一信息由相同账号集群以相同措辞转发 → 可信度-
   ├─ 账号行为特征：
   │  ├─ 新注册账号集中转发 → 风险+
   │  ├─ 已认证的媒体账号确认 → 风险-
   │  ├─ 零粉丝账号发布 → 风险+
   │  └─ 历史账号基于合理讨论 → 风险-
   └─ 结论方式：熵值低(<0.3)直接标记为"人工放大"

【工作流程】
1. 输入清理：移除情绪词汇，提取纯事实主干
2. 物理扫描：检查时间线、地点合理性
3. 逻辑检验：逐一检查因果链、反证、循环论证
4. 动力学分析：计算信息源熵和账号风险评分
5. 综合评分：
   - 物理失败 → 信度0
   - 逻辑缺陷N个 → 每个-15%
   - 熵值低 → -30%
   - 新账号发布 → -20%
   - 已认证确认 → +25%
6. 生成报告：输出可信度光谱和建议

【输出格式】
始终返回JSON格式：
{{
  "credibility_score": 0.0-1.0,
  "confidence_level": "VERY_HIGH/HIGH/MEDIUM/LOW/VERY_LOW",
  "reasoning_chain": [
    "物理层：...",
    "逻辑层：...",
    "动力学层：..."
  ],
  "risk_flags": ["DEEPFAKE", "WATER_ARMY", "LOGIC_FALLACY"],
  "explanation": "详细解释分析过程"
}}
"""


class CotAgent:
    """CoT推理Agent"""

    def __init__(self, db: AsyncSession, cache: RedisCache):
        self.db = db
        self.cache = cache

        # LLM配置
        llm_model = getattr(settings, "LLM_MODEL", None) or settings.SILICONFLOW_MODEL
        llm_api_key = (
            getattr(settings, "LLM_API_KEY", None) or settings.SILICONFLOW_API_KEY
        )
        llm_base_url = (
            getattr(settings, "LLM_API_BASE", None) or settings.SILICONFLOW_API_BASE
        )
        self.llm = ChatOpenAI(
            model=llm_model,
            temperature=0.2,
            max_tokens=2000,
            api_key=llm_api_key,
            base_url=llm_base_url,
        )

        # Layer 2模块
        self.baseline_manager = BaselineManager(db)
        self.anomaly_detector = AnomalyDetector(db)

    async def analyze(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        image_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        分析信息真实性

        Args:
            content: 待分析文本
            metadata: 元数据
            image_urls: 图片URL列表

        Returns:
            分析结果
        """
        logger.info(f"🧠 CoT analyzing: {content[:50]}...")

        # 1. 检查缓存
        cache_key = f"cot_analysis:{self._hash_content(content)}"
        cached = await self.cache.get(cache_key)
        if cached:
            logger.info("✅ Returning cached analysis")
            return cached

        # 2. 构建分析上下文
        context = await self._build_analysis_context(content, metadata)

        # 3. 调用LLM进行CoT推理
        analysis_result = await self._run_cot_reasoning(content, context)

        # 4. 解析LLM输出
        parsed_result = self._parse_llm_output(analysis_result)

        # 5. 增强分析结果(添加Layer 2的检测结果)
        enhanced_result = await self._enhance_with_layer2(
            content=content, metadata=metadata, base_result=parsed_result
        )

        # 6. 缓存结果(1小时)
        await self.cache.set(cache_key, enhanced_result, expire=3600)

        logger.info(
            f"✅ Analysis completed - Credibility: {enhanced_result['credibility_score']:.2%}"
        )

        return enhanced_result

    async def _build_analysis_context(
        self, content: str, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """构建分析上下文"""
        context = {
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 如果有作者信息,添加账号特征
        if metadata and metadata.get("author_follower_count"):
            context["account_features"] = {
                "followers": metadata["author_follower_count"],
                "account_age_days": metadata.get("account_age_days", 0),
                "is_new_account": (metadata.get("account_age_days", 999) < 30),
            }

        return context

    async def _run_cot_reasoning(self, content: str, context: Dict[str, Any]) -> str:
        """运行CoT推理"""

        # 构建提示词
        human_prompt = f"""
请分析以下信息的真实性：

【待分析内容】
{content}

【上下文信息】
{json.dumps(context, ensure_ascii=False, indent=2)}

【任务】
请按照三重验证框架（物理层→逻辑层→动力学层），逐步分析这个信息的真实性。

请严格按照JSON格式返回结果。
"""

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        # 调用LLM
        try:
            response = await self.llm.ainvoke(messages)
            return response.content

        except Exception as e:
            logger.error(f"❌ LLM invocation error: {e}", exc_info=True)
            # 返回默认响应
            return json.dumps(
                {
                    "credibility_score": 0.5,
                    "confidence_level": "LOW",
                    "reasoning_chain": ["LLM调用失败,使用默认分析"],
                    "risk_flags": [],
                    "explanation": f"由于LLM服务异常,无法完成深度分析: {str(e)}",
                }
            )

    def _parse_llm_output(self, llm_response: str) -> Dict[str, Any]:
        """解析LLM输出"""
        try:
            # 尝试提取JSON
            # 有时LLM会在```json...```代码块中返回
            if "```json" in llm_response:
                json_str = llm_response.split("```json")[1].split("```")[0]
            elif "```" in llm_response:
                json_str = llm_response.split("```")[1].split("```")[0]
            else:
                json_str = llm_response

            result = json.loads(json_str)

            # 验证必要字段
            required_fields = [
                "credibility_score",
                "confidence_level",
                "reasoning_chain",
            ]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")

            return result

        except Exception as e:
            logger.error(f"❌ Failed to parse LLM output: {e}")
            logger.debug(f"LLM raw output: {llm_response}")

            # 返回默认结果
            return {
                "credibility_score": 0.5,
                "confidence_level": "LOW",
                "reasoning_chain": ["解析LLM输出失败"],
                "risk_flags": [],
                "explanation": f"解析错误: {str(e)}",
            }

    async def _enhance_with_layer2(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]],
        base_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用Layer 2的检测结果增强分析"""

        # 提取关键词/实体
        # TODO: 实现更精准的实体识别
        keywords = self._extract_keywords(content)

        if not keywords:
            return base_result

        # 针对第一个关键词检查异常(简化逻辑)
        entity_name = keywords[0]
        entity_id = f"entity_{self._hash_content(entity_name)}"

        try:
            # 检测异常
            anomaly_result = await self.anomaly_detector.detect_anomaly(
                entity_id=entity_id, entity_name=entity_name, time_window_hours=24
            )

            if anomaly_result and anomaly_result.get("has_anomaly"):
                # 如果检测到异常,降低可信度
                anomaly_count = len(anomaly_result["anomalies"])
                penalty = min(anomaly_count * 0.1, 0.3)  # 最多-30%

                base_result["credibility_score"] = max(
                    0.0, base_result["credibility_score"] - penalty
                )

                # 添加风险标签
                if "risk_flags" not in base_result:
                    base_result["risk_flags"] = []

                base_result["risk_flags"].append("ANOMALY_DETECTED")

                # 添加到推理链
                base_result["reasoning_chain"].append(
                    f"动力学层（Layer2增强）：检测到{anomaly_count}个异常信号，可信度降低{penalty:.1%}"
                )

                # 添加异常详情
                base_result["anomaly_details"] = anomaly_result["anomalies"]

        except Exception as e:
            logger.warning(f"⚠️ Failed to enhance with Layer2: {e}")

        return base_result

    def _hash_content(self, content: str) -> str:
        """计算内容哈希"""
        import hashlib

        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词(简化版)"""
        # TODO: 使用jieba分词+TF-IDF
        import re

        # 提取#话题#
        topics = re.findall(r"#([^#]+)#", text)

        # 提取高频词(简化)
        words = re.findall(r"[\u4e00-\u9fa5]{2,}", text)

        # 去重并返回前5个
        keywords = list(set(topics + words))[:5]

        return keywords


# =====================
# 导出函数供API调用
# =====================
async def analyze_intel(
    content: str,
    source_platform: Optional[str] = None,
    original_url: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: AsyncSession = None,
    cache: RedisCache = None,
) -> Intel:
    """
    分析情报并保存到数据库

    Returns:
        Intel对象
    """
    logger.info(f"📝 Analyzing intel: {content[:100]}...")

    # 初始化Agent
    agent = CotAgent(db=db, cache=cache)

    # 运行分析
    analysis_result = await agent.analyze(
        content=content, metadata=metadata, image_urls=image_urls
    )

    # 构建Intel对象
    intel = Intel(
        id=f"intel_{uuid.uuid4().hex[:12]}",
        source_platform=source_platform or "unknown",
        original_url=original_url or "",
        content_text=content,
        content_type="TEXT",  # 简化
        image_urls=image_urls,
        meta=metadata or {},
        # 分析结果
        credibility_score=analysis_result["credibility_score"],
        credibility_level=_map_credibility_level(analysis_result["credibility_score"]),
        confidence=analysis_result["confidence_level"],
        risk_flags=analysis_result.get("risk_flags", []),
        reasoning_chain=analysis_result["reasoning_chain"],
        # 验证详情
        logic_verification={"explanation": analysis_result.get("explanation", "")},
        entropy_analysis=analysis_result.get("anomaly_details"),
        # 时间
        created_at=datetime.utcnow(),
        analyzed_at=datetime.utcnow(),
        is_analyzed=1,
    )

    # 保存到数据库
    db.add(intel)
    await db.commit()
    await db.refresh(intel)

    logger.info(f"✅ Intel analyzed and saved: {intel.id}")

    return intel


def _map_credibility_level(score: float) -> CredibilityLevel:
    """映射可信度等级"""
    if score >= 0.9:
        return CredibilityLevel.VERY_HIGH
    elif score >= 0.7:
        return CredibilityLevel.HIGH
    elif score >= 0.4:
        return CredibilityLevel.MEDIUM
    elif score >= 0.2:
        return CredibilityLevel.LOW
    else:
        return CredibilityLevel.VERY_LOW
