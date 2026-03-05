"""
Aletheia 重试机制模块

提供指数退避、熔断器等容错机制
"""

import asyncio
import random
from typing import Callable, Optional, TypeVar, Any
from functools import wraps
from loguru import logger
from datetime import datetime, timedelta

# Import CircuitBreaker from stability module (thread-safe version)
from utils.stability import CircuitBreaker, RetryStrategy, retry_async

T = TypeVar("T")


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retryable_exceptions: tuple = (Exception,),
        on_retry: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
    ):
        """
        初始化重试配置

        Args:
            max_attempts: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数基数
            retryable_exceptions: 可重试的异常类型
            on_retry: 重试时的回调函数
            on_failure: 最终失败时的回调函数
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions
        self.on_retry = on_retry
        self.on_failure = on_failure

    def calculate_delay(self, attempt: int) -> float:
        """
        计算重试延迟（指数退避 + 抖动）

        Args:
            attempt: 当前尝试次数

        Returns:
            延迟时间（秒）
        """
        # 指数退避
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))

        # 添加随机抖动（0-30%）
        jitter = delay * 0.3 * random.random()
        delay += jitter

        # 限制最大延迟
        return min(delay, self.max_delay)


def with_retry(config: Optional[RetryConfig] = None):
    """
    重试装饰器

    使用示例:
        @with_retry(RetryConfig(max_attempts=3, base_delay=1.0))
        async def fetch_data():
            # 可能失败的网络请求
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    result = await func(*args, **kwargs)

                    # 成功时如果是半开状态，重置熔断器
                    if attempt > 1:
                        logger.info(
                            f"[Retry Success] {func.__name__} succeeded on attempt {attempt}"
                        )

                    return result

                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts:
                        break

                    # 计算延迟
                    delay = config.calculate_delay(attempt)

                    logger.warning(
                        f"[Retry] {func.__name__} failed (attempt {attempt}/{config.max_attempts}), "
                        f"retrying in {delay:.2f}s: {str(e)}"
                    )

                    # 调用重试回调
                    if config.on_retry:
                        try:
                            config.on_retry(attempt, e, delay)
                        except Exception:
                            pass

                    # 等待后重试
                    await asyncio.sleep(delay)

            # 所有重试都失败了
            logger.error(
                f"[Retry Failed] {func.__name__} failed after {config.max_attempts} attempts: {last_exception}"
            )

            if config.on_failure:
                try:
                    config.on_failure(last_exception)
                except Exception:
                    pass

            raise last_exception

        return wrapper

    return decorator


def with_circuit_breaker(breaker: CircuitBreaker):
    """
    熔断器装饰器

    使用示例:
        breaker = CircuitBreaker(failure_threshold=5)

        @with_circuit_breaker(breaker)
        async def external_api_call():
            # 外部 API 调用
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if not breaker.can_execute():
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")

            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result

            except breaker.expected_exception as e:
                breaker.record_failure()
                raise

        return wrapper

    return decorator


class RetryHelper:
    """重试辅助类"""

    # 预定义配置
    FAST = RetryConfig(max_attempts=3, base_delay=0.5, max_delay=5.0)
    NORMAL = RetryConfig(max_attempts=3, base_delay=1.0, max_delay=30.0)
    SLOW = RetryConfig(max_attempts=5, base_delay=2.0, max_delay=60.0)

    # 爬虫专用
    CRAWLER = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=(ConnectionError, TimeoutError, Exception),
    )

    # API 调用专用
    API_CALL = RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=5.0,
        retryable_exceptions=(ConnectionError, TimeoutError),
    )

    # 数据库专用
    DATABASE = RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=30.0,
        retryable_exceptions=(ConnectionError, Exception),
    )


# 便捷函数
async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> T:
    """
    使用指数退避重试执行函数

    Args:
        func: 要执行的函数
        *args: 位置参数
        max_attempts: 最大重试次数
        base_delay: 基础延迟
        **kwargs: 关键字参数

    Returns:
        函数执行结果
    """
    config = RetryConfig(max_attempts=max_attempts, base_delay=base_delay)

    @with_retry(config)
    async def wrapper():
        return await func(*args, **kwargs)

    return await wrapper()


def is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否可重试

    Args:
        error: 异常对象

    Returns:
        是否可重试
    """
    retryable_types = (
        ConnectionError,
        TimeoutError,
        ConnectionRefusedError,
        ConnectionResetError,
    )

    return isinstance(error, retryable_types)


# 全局熔断器实例
circuit_breakers = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """
    获取或创建熔断器

    Args:
        name: 熔断器名称
        **kwargs: 创建参数

    Returns:
        熔断器实例
    """
    if name not in circuit_breakers:
        circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    return circuit_breakers[name]
