"""
Aletheia Verification Agent (Enhanced)
======================================

使用详细提示词的增强版验证 Agent

改进：
1. 详细的 Step 提示词
2. LLM 驱动的推理
3. 更具体的推理内容
4. 符合 Step 要求的内容生成
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from loguru import logger

from .state import AgentState, SearchResult, ReasoningStep
from .nodes import BaseNode, SearchNode, ReasoningNode, SummaryNode, ReflectionNode
from .tools import KeywordOptimizer, SentimentAnalyzer
from .prompts import LLMReasoningEngine, generate_step_reasoning
from .prompts.verification_prompts import STEP_ORDER, get_step_number


class EnhancedVerificationAgent:
    """
    增强版验证 Agent

    特点：
    - 使用详细提示词进行 Step 推理
    - LLM 驱动的详细内容生成
    - 符合 Step 要求的具体分析
    """

    def __init__(
        self,
        llm_client: Any = None,
        search_tool: Callable = None,
        enable_sentiment: bool = True,
        enable_keyword_optimization: bool = True,
        max_reflections: int = 2,
        use_llm_reasoning: bool = True,
    ):
        """
        初始化增强版验证 Agent

        Args:
            llm_client: LLM 客户端实例
            search_tool: 搜索工具函数
            enable_sentiment: 是否启用情感分析
            enable_keyword_optimization: 是否启用关键词优化
            max_reflections: 最大反思次数
            use_llm_reasoning: 是否使用 LLM 进行推理
        """
        self.llm_client = llm_client
        self.search_tool = search_tool
        self.max_reflections = max_reflections
        self.use_llm_reasoning = use_llm_reasoning

        # 初始化 LLM 推理引擎
        if use_llm_reasoning:
            try:
                self.reasoning_engine = LLMReasoningEngine()
                logger.info("✅ LLM 推理引擎已初始化")
            except Exception as e:
                logger.warning(f"⚠️ LLM 推理引擎初始化失败: {e}")
                self.reasoning_engine = None
                self.use_llm_reasoning = False
        else:
            self.reasoning_engine = None

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

        # 状态
        self.state = AgentState()

        logger.info(
            f"EnhancedVerificationAgent 已初始化 (LLM推理: {use_llm_reasoning})"
        )

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

            # Step 1: 关键词优化
            optimized_keywords = self._optimize_keywords(content)

            # Step 2: 初始搜索
            self._perform_search(optimized_keywords or [content])

            # Step 3: 详细的 Step 推理（使用提示词系统）
            self._execute_detailed_reasoning()

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
            logger.info(f"推理步骤: {len(self.state.verification.reasoning_chain)}")
            logger.info(f"处理时间: {processing_time}ms")
            logger.info(f"{'=' * 60}\n")

            # 保存状态
            if save_state:
                self._save_state(output_dir)

            return self.state

        except Exception as e:
            logger.exception(f"验证过程中发生错误: {e}")
            raise

    def _execute_detailed_reasoning(self):
        """执行详细的 Step 推理"""
        logger.info("\n[详细推理阶段] 开始执行 5 步推理流程...")

        for step_key in STEP_ORDER:
            step_number = get_step_number(step_key)

            logger.info(f"\n[Step {step_number}] 执行 {step_key}...")

            # 准备数据
            state_data = self.state.to_dict()
            search_results = [
                result.to_dict() for result in self.state.verification.search_history
            ]
            previous_steps = [
                step.to_dict() for step in self.state.verification.reasoning_chain
            ]

            # 执行推理
            if self.use_llm_reasoning and self.reasoning_engine:
                result = self.reasoning_engine.reason(
                    step_key=step_key,
                    state_data=state_data,
                    search_results=search_results,
                    previous_steps=previous_steps,
                )
            else:
                # 使用模拟推理
                result = self._mock_reasoning(
                    step_key=step_key,
                    state_data=state_data,
                    search_results=search_results,
                )

            # 创建推理步骤
            from .prompts.verification_prompts import get_step_prompt

            step_info = get_step_prompt(step_key)

            step = ReasoningStep(
                step=step_number,
                stage=step_key,
                reasoning=result.get("reasoning", ""),
                conclusion=result.get("conclusion", ""),
                confidence=result.get("confidence", 0.5),
                evidence=result.get("evidence", []),
                concerns=result.get("concerns", []),
                score_impact=result.get("score_impact", 0.0),
            )

            self.state.verification.add_reasoning_step(step)
            self.state.update_timestamp()

            # 记录详细结果
            logger.info(f"  ✓ {step_info['name']} 完成")
            logger.info(f"    置信度: {step.confidence:.2f}")
            logger.info(f"    结论: {step.conclusion[:80]}...")
            if step.evidence:
                logger.info(f"    证据: {len(step.evidence)} 条")
            if step.concerns:
                logger.info(f"    疑点: {len(step.concerns)} 个")

            # 保存详细的 Step 结果到 metadata
            if "detailed_source_analysis" in result:
                logger.info(
                    f"    详细分析: {len(result['detailed_source_analysis'])} 个信源"
                )
            if "contradictions_found" in result:
                logger.info(f"    发现矛盾: {len(result['contradictions_found'])} 处")
            if "anomalies_summary" in result:
                logger.info(f"    发现异常: {len(result['anomalies_summary'])} 个")

    def _mock_reasoning(
        self, step_key: str, state_data: Dict, search_results: List[Dict]
    ) -> Dict:
        """模拟推理"""
        if self.reasoning_engine:
            return self.reasoning_engine._mock_reasoning(
                step_key=step_key, state_data=state_data, search_results=search_results
            )

        # 基础模拟
        return {
            "reasoning": f"【基础模拟】执行了 {step_key} 的分析",
            "conclusion": f"{step_key} 分析完成",
            "confidence": 0.6,
            "evidence": [],
            "concerns": [],
            "score_impact": 0.1,
        }

    # 以下方法保持不变（与之前的 VerificationAgent 相同）
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

        logger.info("\n[搜索阶段] 执行多关键词搜索...")

        all_results = []
        for keyword in keywords[:5]:
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

    def _reflection_loop(self):
        """反思循环"""
        logger.info("\n[反思阶段] 执行反思循环...")

        for i in range(self.max_reflections):
            if self.state.verification.reflection_count >= self.max_reflections:
                break

            logger.info(f"  反思 {i + 1}/{self.max_reflections}...")

            needs_more = len(self.state.verification.search_history) < 10

            if needs_more and self.search_tool:
                try:
                    logger.info(f"    补充搜索...")
                    results = self.search_tool("补充证据")
                    if results:
                        self.state.verification.add_search_results_batch(
                            "reflection", results
                        )
                        logger.info(f"      找到 {len(results)} 条结果")
                except Exception as e:
                    logger.error(f"      搜索失败: {e}")

            self.state.verification.increment_reflection()

    def _generate_summary(self):
        """生成总结"""
        logger.info("\n[总结阶段] 生成验证总结...")

        conclusions = [
            step.conclusion
            for step in self.state.verification.reasoning_chain
            if step.conclusion
        ]

        if conclusions:
            summary = "\n\n".join(
                f"【Step {i + 1}】{c}" for i, c in enumerate(conclusions)
            )
            self.state.verification.current_summary = summary
            logger.info(f"  总结长度: {len(summary)} 字符")
        else:
            self.state.verification.current_summary = "暂无足够证据生成总结"

    def _evaluate_credibility(self):
        """评估可信度"""
        logger.info("\n[评估阶段] 评估可信度...")

        reasoning_chain = self.state.verification.reasoning_chain
        if reasoning_chain:
            avg_confidence = sum(r.confidence for r in reasoning_chain) / len(
                reasoning_chain
            )
            base_score = avg_confidence * 0.8
        else:
            base_score = 0.3

        search_results = self.state.verification.search_history
        if search_results:
            high_quality = sum(
                1 for r in search_results if r.evidence_quality == "high"
            )
            quality_bonus = (high_quality / len(search_results)) * 0.15
            base_score += quality_bonus

        platforms = set(r.platform for r in search_results)
        platform_bonus = min(len(platforms) * 0.02, 0.05)
        base_score += platform_bonus

        final_score = max(0.0, min(1.0, base_score))

        if final_score >= 0.8:
            level = "HIGH"
        elif final_score >= 0.6:
            level = "MEDIUM"
        elif final_score >= 0.4:
            level = "LOW"
        else:
            level = "UNCERTAIN"

        risk_flags = []
        if final_score < 0.5:
            risk_flags.append("LOW_CREDIBILITY")
        if len(search_results) < 5:
            risk_flags.append("INSUFFICIENT_EVIDENCE")

        self.state.mark_completed(final_score, level, risk_flags)

        logger.info(f"  可信度分数: {final_score:.2%}")
        logger.info(f"  可信度等级: {level}")
        logger.info(f"  风险标记: {risk_flags}")

    def _save_state(self, output_dir: str):
        """保存状态"""
        try:
            os.makedirs(output_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"agent_state_{self.state.task_id}_{timestamp}.json"
            filepath = os.path.join(output_dir, filename)

            self.state.save_to_file(filepath)
            logger.info(f"  状态已保存: {filepath}")

        except Exception as e:
            logger.error(f"  保存状态失败: {e}")

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON"""
        return self.state.to_json(indent)


# 便捷函数
def verify_with_llm(
    content: str, search_tool: Callable = None, use_llm: bool = True, **kwargs
) -> AgentState:
    """
    便捷函数：使用 LLM 进行详细验证

    Args:
        content: 待验证内容
        search_tool: 搜索工具函数
        use_llm: 是否使用 LLM 推理
        **kwargs: 其他参数

    Returns:
        验证状态
    """
    agent = EnhancedVerificationAgent(
        search_tool=search_tool, use_llm_reasoning=use_llm, **kwargs
    )
    return agent.verify(content)
