"""
Aletheia Agent Framework
========================

借鉴 BettaFish 项目的分层架构设计，为 Aletheia 提供：
- 统一的 Agent 状态管理
- 可组合的处理节点 (Nodes)
- 可复用的工具集 (Tools)
- 标准化的 LLM 客户端接口
- 详细的 Step 提示词系统

架构层次：
1. State Layer - 状态管理与持久化
2. Node Layer - 处理节点抽象
3. Tool Layer - 工具函数封装
4. LLM Layer - 大模型客户端
5. Prompts Layer - 详细提示词

快速开始：
    from services.agent_framework import VerificationAgent

    agent = VerificationAgent(search_tool=your_search_function)
    state = agent.verify("要验证的内容")
    print(f"可信度: {state.credibility_score}")

增强版（使用详细提示词）：
    from services.agent_framework import EnhancedVerificationAgent

    agent = EnhancedVerificationAgent(search_tool=your_search_function)
    state = agent.verify("要验证的内容")
"""

# State
from .state import (
    SearchResult,
    ReasoningStep,
    VerificationState,
    AgentState,
)

# Nodes
from .nodes import (
    BaseNode,
    StateMutationNode,
    SearchNode,
    ReasoningNode,
    SummaryNode,
    ReflectionNode,
)

# Tools
from .tools import (
    KeywordOptimizer,
    SentimentAnalyzer,
    KeywordOptimizationResponse,
    SentimentResult,
    BatchSentimentResult,
)

# Bot Detection
from .bot_detector import (
    BotDetector,
    BotDetectionResult,
    AccountProfile,
    ContentItem,
    detect_bot,
    batch_detect_bots,
)

# Report Generator
from .report_generator import (
    ReportGenerator,
    ReportSection,
    ReportTemplate,
    generate_report,
)

# Prompts
from .prompts import (
    LLMReasoningEngine,
    generate_step_reasoning,
)
from .prompts.verification_prompts import (
    STEP_PROMPTS,
    get_step_prompt,
    build_step_user_prompt,
    STEP_ORDER,
)

# Agent (基础版)
from .agent import (
    VerificationAgent,
    verify_content,
)

# Agent (增强版)
from .enhanced_agent import (
    EnhancedVerificationAgent,
    verify_with_llm,
)

__version__ = "0.3.0"

__all__ = [
    # State
    "SearchResult",
    "ReasoningStep",
    "VerificationState",
    "AgentState",
    # Nodes
    "BaseNode",
    "StateMutationNode",
    "SearchNode",
    "ReasoningNode",
    "SummaryNode",
    "ReflectionNode",
    # Tools
    "KeywordOptimizer",
    "SentimentAnalyzer",
    "KeywordOptimizationResponse",
    "SentimentResult",
    "BatchSentimentResult",
    # Bot Detection
    "BotDetector",
    "BotDetectionResult",
    "AccountProfile",
    "ContentItem",
    "detect_bot",
    "batch_detect_bots",
    # Report Generator
    "ReportGenerator",
    "ReportSection",
    "ReportTemplate",
    "generate_report",
    # Prompts
    "LLMReasoningEngine",
    "generate_step_reasoning",
    "STEP_PROMPTS",
    "get_step_prompt",
    "build_step_user_prompt",
    "STEP_ORDER",
    # Agent (基础版)
    "VerificationAgent",
    "verify_content",
    # Agent (增强版)
    "EnhancedVerificationAgent",
    "verify_with_llm",
]
