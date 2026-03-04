"""
LLM服务模块 - 多模型支持的智能分析

模块功能:
1. 统一LLM接口 (OpenAI兼容)
2. 情感分析
3. 事实核查
4. 增强报告生成
5. LLM Provider Failover with Circuit Breaker

使用方法:
    from services.llm import (
        LLMClient,
        SentimentAnalyzer,
        EnhancedReportGenerator,
        LLMFailoverManager,
        LLMProviderConfig
    )
"""

from .llm_provider import LLMClient, LLMProvider, analyze_sentiment_batch
from .sentiment_analyzer import SentimentAnalyzer, SentimentResult
from .enhanced_report_generator import EnhancedReportGenerator, AccuracyMetrics
from .llm_failover import (
    LLMFailoverManager,
    LLMProviderConfig,
    ProviderStatus,
    create_failover_manager_from_env,
    get_global_failover_manager,
    complete_with_failover,
)

__all__ = [
    "LLMClient",
    "LLMProvider",
    "analyze_sentiment_batch",
    "SentimentAnalyzer",
    "SentimentResult",
    "EnhancedReportGenerator",
    "AccuracyMetrics",
    "LLMFailoverManager",
    "LLMProviderConfig",
    "ProviderStatus",
    "create_failover_manager_from_env",
    "get_global_failover_manager",
    "complete_with_failover",
]
