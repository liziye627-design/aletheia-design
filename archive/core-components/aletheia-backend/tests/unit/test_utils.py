"""
Aletheia 单元测试套件

测试范围：
- 异常处理 (test_exceptions.py)
- 缓存工具 (test_cache.py)
- 重试机制 (test_retry.py)
- Agent Framework (test_agent_framework.py)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# ===== 测试异常处理 =====

from utils.exceptions import (
    AletheiaException,
    CrawlerException,
    AnalysisException,
    ValidationException,
    NotFoundException,
    handle_exception,
    raise_not_found,
)


class TestExceptions:
    """异常处理测试"""

    def test_base_exception(self):
        """测试基础异常"""
        exc = AletheiaException(
            message="Test error",
            error_code="TEST_ERROR",
            status_code=400,
            details={"field": "value"},
        )

        assert exc.message == "Test error"
        assert exc.error_code == "TEST_ERROR"
        assert exc.status_code == 400
        assert exc.details == {"field": "value"}

    def test_exception_to_dict(self):
        """测试异常转换为字典"""
        exc = AletheiaException("Test", "TEST", 500)
        result = exc.to_dict()

        assert result["success"] is False
        assert result["error"]["code"] == "TEST"
        assert result["error"]["message"] == "Test"

    def test_crawler_exception(self):
        """测试爬虫异常"""
        exc = CrawlerException(
            message="爬取失败", platform="weibo", url="https://example.com"
        )

        assert exc.error_code == "CRAWLER_ERROR"
        assert exc.details["platform"] == "weibo"
        assert exc.details["url"] == "https://example.com"

    def test_analysis_exception(self):
        """测试分析异常"""
        exc = AnalysisException(message="分析失败", analysis_type="credibility")

        assert exc.error_code == "ANALYSIS_ERROR"
        assert exc.details["analysis_type"] == "credibility"

    def test_validation_exception(self):
        """测试验证异常"""
        exc = ValidationException(message="字段不能为空", field="content")

        assert exc.status_code == 422
        assert exc.details["field"] == "content"

    def test_not_found_exception(self):
        """测试未找到异常"""
        exc = NotFoundException(
            message="资源未找到", resource_type="intel", resource_id="123"
        )

        assert exc.status_code == 404
        assert exc.details["resource_type"] == "intel"

    def test_raise_not_found(self):
        """测试抛出未找到异常"""
        with pytest.raises(NotFoundException) as exc_info:
            raise_not_found("user", "123")

        assert exc_info.value.status_code == 404
        assert "user" in exc_info.value.message
        assert "123" in exc_info.value.message


# ===== 测试缓存工具 =====

from utils.cache import CacheKeyBuilder, CacheStrategy


class TestCacheKeyBuilder:
    """缓存键构建器测试"""

    def test_build_simple_key(self):
        """测试构建简单键"""
        key = CacheKeyBuilder.build("search", "test_query")
        assert key == "aletheia:search:test_query"

    def test_build_with_args(self):
        """测试构建带参数的键"""
        key = CacheKeyBuilder.build("search", "query", "arg1", "arg2")
        assert "aletheia:search:query" in key
        assert "arg1" in key
        assert "arg2" in key

    def test_build_with_kwargs(self):
        """测试构建带关键字参数的键"""
        key = CacheKeyBuilder.build("search", "query", platform="weibo", limit=10)
        assert "platform:weibo" in key
        assert "limit:10" in key

    def test_build_hash(self):
        """测试构建哈希键"""
        data = {"query": "test", "platform": "weibo"}
        key = CacheKeyBuilder.build_hash("search", data)

        assert key.startswith("aletheia:search:")
        assert len(key.split(":")[-1]) == 16  # MD5 hash length


class TestCacheStrategy:
    """缓存策略测试"""

    def test_search_cache_times(self):
        """测试搜索缓存时间"""
        assert CacheStrategy.SEARCH_RESULTS == 300  # 5分钟
        assert CacheStrategy.HOT_TOPICS == 600  # 10分钟

    def test_analysis_cache_times(self):
        """测试分析缓存时间"""
        assert CacheStrategy.ANALYSIS_RESULT == 3600  # 1小时
        assert CacheStrategy.CREDIBILITY_SCORE == 1800  # 30分钟


# ===== 测试重试机制 =====

from utils.retry import RetryConfig, CircuitBreaker, with_retry, RetryHelper


class TestRetryConfig:
    """重试配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0

    def test_calculate_delay(self):
        """测试延迟计算"""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0)

        # 第一次重试
        delay1 = config.calculate_delay(1)
        assert 1.0 <= delay1 <= 1.3  # 基础延迟 + 0-30%抖动

        # 第二次重试（指数退避）
        delay2 = config.calculate_delay(2)
        assert 2.0 <= delay2 <= 2.6

    def test_max_delay_cap(self):
        """测试最大延迟限制"""
        config = RetryConfig(base_delay=1.0, max_delay=5.0)

        # 高尝试次数时应该被限制
        delay = config.calculate_delay(10)
        assert delay <= 5.0


class TestCircuitBreaker:
    """熔断器测试"""

    def test_initial_state(self):
        """测试初始状态"""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitBreaker.STATE_CLOSED
        assert breaker.can_execute() is True

    def test_open_after_failures(self):
        """测试失败后熔断"""
        breaker = CircuitBreaker(failure_threshold=3)

        # 记录3次失败
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state == CircuitBreaker.STATE_OPEN
        assert breaker.can_execute() is False

    def test_half_open_after_timeout(self):
        """测试超时后半开"""
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0,  # 立即恢复
        )

        breaker.record_failure()
        assert breaker.state == CircuitBreaker.STATE_OPEN

        # 应该可以执行（半开状态）
        assert breaker.can_execute() is True

    def test_close_after_success(self):
        """测试成功后关闭"""
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2

        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.state == CircuitBreaker.STATE_CLOSED


class TestRetryHelper:
    """重试辅助类测试"""

    def test_fast_config(self):
        """测试快速配置"""
        assert RetryHelper.FAST.max_attempts == 3
        assert RetryHelper.FAST.base_delay == 0.5

    def test_crawler_config(self):
        """测试爬虫配置"""
        assert RetryHelper.CRAWLER.max_attempts == 3
        assert ConnectionError in RetryHelper.CRAWLER.retryable_exceptions


# ===== 测试 Agent Framework =====

from services.agent_framework import (
    AgentState,
    ReasoningStep,
    SearchResult,
    VerificationState,
)


class TestAgentState:
    """Agent 状态测试"""

    def test_state_initialization(self):
        """测试状态初始化"""
        state = AgentState(
            task_id="test-001", query="测试查询", content_text="测试内容"
        )

        assert state.task_id == "test-001"
        assert state.query == "测试查询"
        assert state.credibility_score == 0.0
        assert state.credibility_level == "UNCERTAIN"

    def test_add_reasoning_step(self):
        """测试添加推理步骤"""
        state = AgentState()

        step = ReasoningStep(
            step=1,
            stage="test",
            reasoning="测试推理",
            conclusion="测试结论",
            confidence=0.8,
        )

        state.verification.add_reasoning_step(step)
        assert len(state.verification.reasoning_chain) == 1
        assert state.verification.reasoning_chain[0].confidence == 0.8

    def test_mark_completed(self):
        """测试标记完成"""
        state = AgentState()
        state.mark_completed(0.85, "HIGH", ["TEST_FLAG"])

        assert state.credibility_score == 0.85
        assert state.credibility_level == "HIGH"
        assert state.risk_flags == ["TEST_FLAG"]
        assert state.is_completed is True

    def test_to_dict(self):
        """测试转换为字典"""
        state = AgentState(task_id="test", query="query")
        state.mark_completed(0.9, "HIGH")

        data = state.to_dict()
        assert data["task_id"] == "test"
        assert data["credibility_score"] == 0.9
        assert data["is_completed"] is True


class TestReasoningStep:
    """推理步骤测试"""

    def test_step_creation(self):
        """测试步骤创建"""
        step = ReasoningStep(
            step=1,
            stage="claim_parse",
            reasoning="详细推理过程",
            conclusion="结论",
            confidence=0.85,
            evidence=["证据1", "证据2"],
            concerns=["疑点1"],
            score_impact=0.1,
        )

        assert step.step == 1
        assert step.stage == "claim_parse"
        assert len(step.evidence) == 2
        assert len(step.concerns) == 1

    def test_to_dict(self):
        """测试转换为字典"""
        step = ReasoningStep(step=1, stage="test", confidence=0.8)
        data = step.to_dict()

        assert data["step"] == 1
        assert data["stage"] == "test"
        assert data["confidence"] == 0.8


class TestSearchResult:
    """搜索结果测试"""

    def test_result_creation(self):
        """测试结果创建"""
        result = SearchResult(
            query="测试",
            platform="weibo",
            url="https://example.com",
            title="标题",
            content="内容",
            evidence_quality="high",
        )

        assert result.platform == "weibo"
        assert result.evidence_quality == "high"

    def test_to_dict(self):
        """测试转换为字典"""
        result = SearchResult(query="test", platform="zhihu")
        data = result.to_dict()

        assert data["query"] == "test"
        assert data["platform"] == "zhihu"


# ===== 运行测试 =====

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
