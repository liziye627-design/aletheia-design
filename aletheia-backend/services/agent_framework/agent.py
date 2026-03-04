"""
Aletheia Verification Agent
===========================

借鉴 BettaFish 的 DeepSearchAgent 设计，
为 Aletheia 提供统一的验证 Agent，整合：
- 状态管理 (State)
- 处理节点 (Nodes)
- 工具函数 (Tools)
- LLM 推理
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from loguru import logger

from .state import AgentState, SearchResult, ReasoningStep
from .nodes import BaseNode, SearchNode, ReasoningNode, SummaryNode, ReflectionNode
from .tools import KeywordOptimizer, SentimentAnalyzer


class VerificationAgent:
    """
    验证 Agent 主类

    负责执行完整的信息验证流程：
    1. 关键词优化
    2. 多平台搜索
    3. 推理链构建
    4. 可信度评估
    5. 报告生成

    Attributes:
        keyword_optimizer: 关键词优化器
        sentiment_analyzer: 情感分析器
        state: 当前 Agent 状态
        search_tool: 搜索工具函数
        llm_client: LLM 客户端
    """

    def __init__(
        self,
        llm_client: Any = None,
        search_tool: Callable = None,
        enable_sentiment: bool = True,
        enable_keyword_optimization: bool = True,
        max_reflections: int = 2,
    ):
        """
        初始化验证 Agent

        Args:
            llm_client: LLM 客户端实例
            search_tool: 搜索工具函数
            enable_sentiment: 是否启用情感分析
            enable_keyword_optimization: 是否启用关键词优化
            max_reflections: 最大反思次数
        """
        self.llm_client = llm_client
        self.search_tool = search_tool
        self.max_reflections = max_reflections

        # 初始化工具
        self.keyword_optimizer = None
        self.sentiment_analyzer = None

        if enable_keyword_optimization:
            try:
                self.keyword_optimizer = KeywordOptimizer()
                logger.info("✅ 关键词优化器已初始化")
            except Exception as e:
                logger.warning(f"⚠️ 关键词优化器初始化失败: {e}")

        if enable_sentiment:
            self.sentiment_analyzer = SentimentAnalyzer()
            logger.info("✅ 情感分析器已初始化")

        # 初始化节点
        self.search_node = SearchNode(
            llm_client=llm_client,
            search_tool=search_tool,
            node_name="VerificationSearchNode",
        )

        self.reasoning_node = ReasoningNode(
            llm_client=llm_client,
            stage_name="verification",
            node_name="VerificationReasoningNode",
        )

        self.summary_node = SummaryNode(
            llm_client=llm_client, node_name="VerificationSummaryNode"
        )

        self.reflection_node = ReflectionNode(
            llm_client=llm_client,
            max_reflections=max_reflections,
            node_name="VerificationReflectionNode",
        )

        # 状态
        self.state = AgentState()

        logger.info("VerificationAgent 已初始化")

    def verify(
        self,
        content: str,
        task_id: str = None,
        source_platform: str = "manual",
        save_state: bool = False,
        output_dir: str = "./agent_states",
    ) -> AgentState:
        """
        执行验证

        Args:
            content: 待验证的内容
            task_id: 任务 ID（可选）
            source_platform: 内容来源平台
            save_state: 是否保存状态到文件
            output_dir: 状态文件输出目录

        Returns:
            最终状态
        """
        import uuid

        # 初始化状态
        self.state = AgentState(
            task_id=task_id or f"verify-{uuid.uuid4().hex[:8]}",
            query=content,
            content_text=content,
            source_platform=source_platform,
        )

        logger.info(f"\n{'=' * 60}")
        logger.info(
            f"开始验证: {content[:50]}..."
            if len(content) > 50
            else f"开始验证: {content}"
        )
        logger.info(f"{'=' * 60}")

        try:
            start_time = datetime.now()

            # Step 1: 关键词优化（如果启用）
            optimized_keywords = self._optimize_keywords(content)

            # Step 2: 初始搜索
            self._perform_search(optimized_keywords or [content])

            # Step 3: 推理链构建
            self._build_reasoning_chain()

            # Step 4: 反思循环
            self._reflection_loop()

            # Step 5: 生成总结
            self._generate_summary()

            # Step 6: 可信度评估
            self._evaluate_credibility()

            # 计算处理时间
            end_time = datetime.now()
            processing_time = int((end_time - start_time).total_seconds() * 1000)
            self.state.processing_time_ms = processing_time

            logger.info(f"\n{'=' * 60}")
            logger.info(f"验证完成!")
            logger.info(
                f"可信度: {self.state.credibility_score:.2%} ({self.state.credibility_level})"
            )
            logger.info(f"处理时间: {processing_time}ms")
            logger.info(f"{'=' * 60}\n")

            # 保存状态
            if save_state:
                self._save_state(output_dir)

            return self.state

        except Exception as e:
            logger.exception(f"验证过程中发生错误: {e}")
            raise

    def _optimize_keywords(self, content: str) -> Optional[List[str]]:
        """优化关键词"""
        if not self.keyword_optimizer:
            return None

        try:
            logger.info("[Step 1] 优化关键词...")
            response = self.keyword_optimizer.optimize(content)

            if response.success and response.optimized_keywords:
                logger.info(f"  原始查询: '{content[:30]}...'")
                logger.info(f"  优化后关键词: {len(response.optimized_keywords)}个")
                for i, kw in enumerate(response.optimized_keywords[:5], 1):
                    logger.debug(f"    {i}. '{kw}'")
                return response.optimized_keywords
            else:
                logger.warning(f"  关键词优化失败: {response.error_message}")
                return None

        except Exception as e:
            logger.warning(f"  关键词优化异常: {e}")
            return None

    def _perform_search(self, keywords: List[str]):
        """执行搜索"""
        if not self.search_tool:
            logger.warning("  未配置搜索工具，跳过搜索")
            return

        logger.info("[Step 2] 执行搜索...")

        all_results = []
        for keyword in keywords[:5]:  # 最多搜索前5个关键词
            try:
                logger.info(f"  搜索关键词: '{keyword}'")
                results = self.search_tool(keyword)

                if results:
                    logger.info(f"    找到 {len(results)} 条结果")
                    all_results.extend(results)
                else:
                    logger.info(f"    未找到结果")

            except Exception as e:
                logger.error(f"    搜索失败: {e}")
                continue

        # 添加到状态
        if all_results:
            # 去重
            seen_urls = set()
            unique_results = []
            for result in all_results:
                url = result.get("url", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(result)

            logger.info(f"  总计 {len(unique_results)} 条唯一结果")
            self.state.verification.add_search_results_batch(
                "optimized_search", unique_results
            )

            # 情感分析（如果启用）
            if self.sentiment_analyzer:
                self._analyze_sentiment(unique_results)

    def _analyze_sentiment(self, results: List[Dict]):
        """分析情感"""
        try:
            logger.info("  执行情感分析...")
            sentiment_result = self.sentiment_analyzer.analyze_query_results(results)

            summary = sentiment_result.get("sentiment_analysis", {}).get("summary", "")
            if summary:
                logger.info(f"    {summary}")

        except Exception as e:
            logger.warning(f"    情感分析失败: {e}")

    def _build_reasoning_chain(self):
        """构建推理链"""
        logger.info("[Step 3] 构建推理链...")

        # 获取搜索结果
        search_results = self.state.verification.search_history

        if not search_results:
            logger.warning("  无搜索结果，跳过推理")
            return

        # 执行多步推理
        reasoning_stages = [
            ("claim_parse", "命题解析"),
            ("source_verification", "信源验证"),
            ("cross_check", "交叉验证"),
            ("evidence_consistency", "证据一致性"),
            ("final_decision", "最终决策"),
        ]

        for stage_key, stage_name in reasoning_stages:
            try:
                logger.info(f"  推理阶段: {stage_name}")

                # 生成推理结果
                reasoning_result = self._generate_reasoning(
                    stage_key, stage_name, search_results
                )

                # 创建推理步骤
                step = ReasoningStep(
                    step=len(self.state.verification.reasoning_chain) + 1,
                    stage=stage_key,
                    reasoning=reasoning_result.get("reasoning", ""),
                    conclusion=reasoning_result.get("conclusion", ""),
                    confidence=reasoning_result.get("confidence", 0.5),
                    evidence=reasoning_result.get("evidence", []),
                    concerns=reasoning_result.get("concerns", []),
                    score_impact=reasoning_result.get("score_impact", 0.0),
                )

                self.state.verification.add_reasoning_step(step)
                logger.info(f"    置信度: {step.confidence:.2f}")

            except Exception as e:
                logger.error(f"    推理失败: {e}")

    def _generate_reasoning(
        self, stage: str, stage_name: str, search_results: List[SearchResult]
    ) -> Dict[str, Any]:
        """
        生成推理结果

        子类可覆盖此方法实现更复杂的推理逻辑
        """
        # 简单实现：基于搜索结果生成推理
        if not search_results:
            return {
                "reasoning": f"{stage_name}: 缺少搜索结果",
                "conclusion": "无法得出结论",
                "confidence": 0.3,
                "evidence": [],
                "concerns": ["缺少证据"],
                "score_impact": -0.1,
            }

        # 统计证据质量
        high_quality = sum(1 for r in search_results if r.evidence_quality == "high")
        total = len(search_results)

        # 根据阶段生成不同的推理
        if stage == "claim_parse":
            return {
                "reasoning": "解析原始命题，拆解为可验证的子命题",
                "conclusion": f"命题涉及 {len(set(r.platform for r in search_results))} 个平台",
                "confidence": 0.8,
                "evidence": [r.url for r in search_results[:3] if r.url],
                "concerns": [],
                "score_impact": 0.05,
            }

        elif stage == "source_verification":
            confidence = 0.5 + (high_quality / total * 0.4) if total > 0 else 0.3
            return {
                "reasoning": "验证信源的可信度和权威性",
                "conclusion": f"高可信度信源: {high_quality}/{total}",
                "confidence": min(confidence, 0.95),
                "evidence": [
                    r.url for r in search_results if r.evidence_quality == "high"
                ][:3],
                "concerns": ["部分信源质量未知"] if high_quality < total else [],
                "score_impact": 0.1 if high_quality > total * 0.5 else 0.0,
            }

        elif stage == "cross_check":
            platforms = set(r.platform for r in search_results)
            confidence = min(0.5 + len(platforms) * 0.1, 0.9)
            return {
                "reasoning": "交叉验证不同平台的报道一致性",
                "conclusion": f"覆盖 {len(platforms)} 个平台",
                "confidence": confidence,
                "evidence": list(platforms)[:5],
                "concerns": [],
                "score_impact": 0.05,
            }

        elif stage == "final_decision":
            avg_confidence = (
                sum(r.confidence for r in self.state.verification.reasoning_chain)
                / len(self.state.verification.reasoning_chain)
                if self.state.verification.reasoning_chain
                else 0.5
            )
            return {
                "reasoning": "综合所有推理步骤，生成最终判断",
                "conclusion": "基于现有证据，给出可信度评估",
                "confidence": avg_confidence,
                "evidence": ["所有推理步骤结论"],
                "concerns": [],
                "score_impact": 0.1,
            }

        else:
            return {
                "reasoning": f"{stage_name}推理",
                "conclusion": "分析完成",
                "confidence": 0.6,
                "evidence": [r.url for r in search_results[:2] if r.url],
                "concerns": [],
                "score_impact": 0.05,
            }

    def _reflection_loop(self):
        """反思循环"""
        logger.info("[Step 4] 反思循环...")

        for i in range(self.max_reflections):
            if self.state.verification.reflection_count >= self.max_reflections:
                break

            logger.info(f"  反思 {i + 1}/{self.max_reflections}...")

            # 检查是否需要补充搜索
            needs_more = self._check_needs_more_search()

            if needs_more and self.search_tool:
                # 补充搜索
                gap_queries = self._identify_gaps()
                for query in gap_queries[:2]:
                    try:
                        logger.info(f"    补充搜索: '{query}'")
                        results = self.search_tool(query)
                        if results:
                            self.state.verification.add_search_results_batch(
                                query, results
                            )
                            logger.info(f"      找到 {len(results)} 条结果")
                    except Exception as e:
                        logger.error(f"      搜索失败: {e}")

            self.state.verification.increment_reflection()

    def _check_needs_more_search(self) -> bool:
        """检查是否需要补充搜索"""
        # 简单规则：如果证据不足，需要补充搜索
        search_count = len(self.state.verification.search_history)
        return search_count < 10

    def _identify_gaps(self) -> List[str]:
        """识别知识缺口"""
        # 简单实现：基于当前搜索历史的平台分布
        platforms = set(r.platform for r in self.state.verification.search_history)

        gaps = []
        if "xinhua" not in platforms and "peoples_daily" not in platforms:
            gaps.append("官方媒体")
        if "zhihu" not in platforms:
            gaps.append("知乎讨论")
        if "weibo" not in platforms:
            gaps.append("微博话题")

        return gaps if gaps else ["补充证据"]

    def _generate_summary(self):
        """生成总结"""
        logger.info("[Step 5] 生成总结...")

        conclusions = [
            step.conclusion
            for step in self.state.verification.reasoning_chain
            if step.conclusion
        ]

        if conclusions:
            summary = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(conclusions))
            self.state.verification.current_summary = summary
            logger.info(f"  总结长度: {len(summary)} 字符")
        else:
            self.state.verification.current_summary = "暂无足够证据生成总结"

    def _evaluate_credibility(self):
        """评估可信度"""
        logger.info("[Step 6] 评估可信度...")

        # 计算基础分数
        reasoning_chain = self.state.verification.reasoning_chain
        if reasoning_chain:
            avg_confidence = sum(r.confidence for r in reasoning_chain) / len(
                reasoning_chain
            )
            base_score = avg_confidence * 0.8  # 推理链贡献 80%
        else:
            base_score = 0.3

        # 搜索质量加分
        search_results = self.state.verification.search_history
        if search_results:
            high_quality = sum(
                1 for r in search_results if r.evidence_quality == "high"
            )
            quality_bonus = (high_quality / len(search_results)) * 0.15  # 质量贡献 15%
            base_score += quality_bonus

        # 平台覆盖加分
        platforms = set(r.platform for r in search_results)
        platform_bonus = min(len(platforms) * 0.02, 0.05)  # 覆盖度贡献最多 5%
        base_score += platform_bonus

        # 确保分数在 0-1 之间
        final_score = max(0.0, min(1.0, base_score))

        # 确定等级
        if final_score >= 0.8:
            level = "HIGH"
        elif final_score >= 0.6:
            level = "MEDIUM"
        elif final_score >= 0.4:
            level = "LOW"
        else:
            level = "UNCERTAIN"

        # 风险标记
        risk_flags = []
        if final_score < 0.5:
            risk_flags.append("LOW_CREDIBILITY")
        if len(search_results) < 5:
            risk_flags.append("INSUFFICIENT_EVIDENCE")

        # 标记完成
        self.state.mark_completed(final_score, level, risk_flags)

        logger.info(f"  可信度分数: {final_score:.2%}")
        logger.info(f"  可信度等级: {level}")
        logger.info(f"  风险标记: {risk_flags}")

    def _save_state(self, output_dir: str):
        """保存状态到文件"""
        try:
            os.makedirs(output_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"agent_state_{self.state.task_id}_{timestamp}.json"
            filepath = os.path.join(output_dir, filename)

            self.state.save_to_file(filepath)
            logger.info(f"  状态已保存: {filepath}")

        except Exception as e:
            logger.error(f"  保存状态失败: {e}")

    def get_progress_summary(self) -> Dict[str, Any]:
        """获取进度摘要"""
        return self.state.get_progress_summary()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.state.to_dict()

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON"""
        return self.state.to_json(indent)


# 便捷函数
def verify_content(
    content: str, search_tool: Callable = None, llm_client: Any = None, **kwargs
) -> AgentState:
    """
    便捷函数：验证内容

    Args:
        content: 待验证内容
        search_tool: 搜索工具函数
        llm_client: LLM 客户端
        **kwargs: 其他参数

    Returns:
        验证状态
    """
    agent = VerificationAgent(llm_client=llm_client, search_tool=search_tool, **kwargs)
    return agent.verify(content)
