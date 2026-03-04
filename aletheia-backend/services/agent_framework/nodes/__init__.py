"""
Aletheia Agent Nodes
====================

处理节点抽象层，提供：
- BaseNode: 基础节点抽象类
- StateMutationNode: 带状态变更的节点
- 各类具体处理节点
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
from loguru import logger

from ..state import AgentState


class BaseNode(ABC):
    """
    节点基类

    所有处理节点的基础接口，定义了：
    - 节点初始化
    - 输入验证
    - 执行逻辑
    - 输出处理
    - 日志记录
    """

    def __init__(self, node_name: str = "", llm_client: Any = None):
        """
        初始化节点

        Args:
            node_name: 节点名称，用于日志标识
            llm_client: LLM 客户端实例（可选）
        """
        self.node_name = node_name or self.__class__.__name__
        self.llm_client = llm_client

    @abstractmethod
    def run(self, input_data: Any, **kwargs) -> Any:
        """
        执行节点处理逻辑

        Args:
            input_data: 输入数据
            **kwargs: 额外参数

        Returns:
            处理结果
        """
        pass

    def validate_input(self, input_data: Any) -> bool:
        """
        验证输入数据

        Args:
            input_data: 输入数据

        Returns:
            验证是否通过
        """
        return True

    def process_output(self, output: Any) -> Any:
        """
        处理输出数据

        Args:
            output: 原始输出

        Returns:
            处理后的输出
        """
        return output

    def log_info(self, message: str):
        """记录信息日志"""
        logger.info(f"[{self.node_name}] {message}")

    def log_warning(self, message: str):
        """记录警告日志"""
        logger.warning(f"[{self.node_name}] ⚠️ {message}")

    def log_error(self, message: str):
        """记录错误日志"""
        logger.error(f"[{self.node_name}] ❌ {message}")

    def log_debug(self, message: str):
        """记录调试日志"""
        logger.debug(f"[{self.node_name}] {message}")


class StateMutationNode(BaseNode):
    """
    带状态修改功能的节点基类

    继承自 BaseNode，增加了状态变更能力，
    适用于需要修改 AgentState 的处理节点。
    """

    @abstractmethod
    def mutate_state(self, input_data: Any, state: AgentState, **kwargs) -> AgentState:
        """
        修改状态

        Args:
            input_data: 输入数据
            state: 当前状态
            **kwargs: 额外参数

        Returns:
            修改后的状态
        """
        pass

    def run(self, input_data: Any, **kwargs) -> Any:
        """
        默认实现：如果提供了 state，则调用 mutate_state
        """
        state = kwargs.get("state")
        if state is not None:
            return self.mutate_state(input_data, state, **kwargs)
        return self._run_without_state(input_data, **kwargs)

    def _run_without_state(self, input_data: Any, **kwargs) -> Any:
        """
        无状态运行（子类可覆盖）
        """
        raise NotImplementedError(
            f"{self.node_name} 需要提供 state 参数或覆盖 _run_without_state 方法"
        )


class SearchNode(StateMutationNode):
    """
    搜索节点

    负责生成搜索查询并执行搜索，
    将结果添加到状态的搜索历史中。
    """

    def __init__(
        self,
        llm_client: Any = None,
        search_tool: Callable = None,
        node_name: str = "SearchNode",
    ):
        super().__init__(node_name=node_name, llm_client=llm_client)
        self.search_tool = search_tool

    def mutate_state(self, input_data: Any, state: AgentState, **kwargs) -> AgentState:
        """
        执行搜索并更新状态
        """
        self.log_info(f"开始搜索: {input_data}")

        # 生成搜索查询（如果有 LLM）
        search_query = self._generate_search_query(input_data, state)

        # 执行搜索
        if self.search_tool:
            results = self.search_tool(search_query, **kwargs)
            state.verification.add_search_results_batch(search_query, results)
            self.log_info(f"搜索完成，找到 {len(results)} 条结果")

        state.update_timestamp()
        return state

    def _generate_search_query(self, input_data: Any, state: AgentState) -> str:
        """
        生成搜索查询

        子类可覆盖此方法实现更复杂的查询生成逻辑
        """
        if isinstance(input_data, str):
            return input_data
        if isinstance(input_data, dict):
            return input_data.get("query", input_data.get("content", str(input_data)))
        return str(input_data)


class ReasoningNode(StateMutationNode):
    """
    推理节点

    负责执行推理步骤，生成结论和置信度，
    将推理步骤添加到状态的推理链中。
    """

    def __init__(
        self,
        llm_client: Any = None,
        stage_name: str = "reasoning",
        node_name: str = "ReasoningNode",
    ):
        super().__init__(node_name=node_name, llm_client=llm_client)
        self.stage_name = stage_name

    def mutate_state(self, input_data: Any, state: AgentState, **kwargs) -> AgentState:
        """
        执行推理并更新状态
        """
        from ..state import ReasoningStep

        self.log_info(f"开始推理阶段: {self.stage_name}")

        # 执行推理
        reasoning_result = self._execute_reasoning(input_data, state, **kwargs)

        # 创建推理步骤
        step = ReasoningStep(
            step=len(state.verification.reasoning_chain) + 1,
            stage=self.stage_name,
            reasoning=reasoning_result.get("reasoning", ""),
            conclusion=reasoning_result.get("conclusion", ""),
            confidence=reasoning_result.get("confidence", 0.0),
            evidence=reasoning_result.get("evidence", []),
            concerns=reasoning_result.get("concerns", []),
            score_impact=reasoning_result.get("score_impact", 0.0),
        )

        state.verification.add_reasoning_step(step)
        state.update_timestamp()

        self.log_info(f"推理完成，置信度: {step.confidence:.2f}")
        return state

    def _execute_reasoning(
        self, input_data: Any, state: AgentState, **kwargs
    ) -> Dict[str, Any]:
        """
        执行推理逻辑

        子类应覆盖此方法实现具体的推理逻辑
        """
        return {
            "reasoning": "默认推理",
            "conclusion": "需要更多信息",
            "confidence": 0.5,
            "evidence": [],
            "concerns": [],
            "score_impact": 0.0,
        }


class SummaryNode(StateMutationNode):
    """
    总结节点

    负责生成当前状态的总结，
    更新状态中的 current_summary。
    """

    def __init__(self, llm_client: Any = None, node_name: str = "SummaryNode"):
        super().__init__(node_name=node_name, llm_client=llm_client)

    def mutate_state(self, input_data: Any, state: AgentState, **kwargs) -> AgentState:
        """
        生成总结并更新状态
        """
        self.log_info("生成总结...")

        summary = self._generate_summary(input_data, state, **kwargs)
        state.verification.current_summary = summary
        state.update_timestamp()

        self.log_info(f"总结完成，长度: {len(summary)} 字符")
        return state

    def _generate_summary(self, input_data: Any, state: AgentState, **kwargs) -> str:
        """
        生成总结

        子类应覆盖此方法实现具体的总结逻辑
        """
        # 默认实现：汇总推理链的结论
        conclusions = [
            step.conclusion
            for step in state.verification.reasoning_chain
            if step.conclusion
        ]
        return "\n".join(conclusions) if conclusions else "暂无总结"


class ReflectionNode(StateMutationNode):
    """
    反思节点

    负责对当前状态进行反思，
    生成新的搜索方向或补充验证。
    """

    def __init__(
        self,
        llm_client: Any = None,
        max_reflections: int = 3,
        node_name: str = "ReflectionNode",
    ):
        super().__init__(node_name=node_name, llm_client=llm_client)
        self.max_reflections = max_reflections

    def mutate_state(self, input_data: Any, state: AgentState, **kwargs) -> AgentState:
        """
        执行反思并更新状态
        """
        if state.verification.reflection_count >= self.max_reflections:
            self.log_info(f"已达到最大反思次数 ({self.max_reflections})，跳过")
            return state

        self.log_info(
            f"开始反思 ({state.verification.reflection_count + 1}/{self.max_reflections})"
        )

        reflection_result = self._execute_reflection(input_data, state, **kwargs)
        state.verification.increment_reflection()
        state.update_timestamp()

        self.log_info("反思完成")
        return state

    def _execute_reflection(
        self, input_data: Any, state: AgentState, **kwargs
    ) -> Dict[str, Any]:
        """
        执行反思逻辑

        子类应覆盖此方法实现具体的反思逻辑
        """
        return {
            "needs_more_search": False,
            "new_queries": [],
            "gaps_identified": [],
        }
