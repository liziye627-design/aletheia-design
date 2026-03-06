"""
稳定性增强模块 - 错误处理、重试机制、熔断器
"""

import asyncio
import threading
import time
from typing import Optional, Callable, Any, TypeVar
from functools import wraps
from datetime import datetime, timedelta
from collections import deque
from utils.logging import logger

T = TypeVar("T")


class CircuitBreaker:
    """熔断器模式实现 - 防止级联故障（线程安全）"""

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """
        初始化熔断器

        Args:
            name: 熔断器名称（可选，用于日志标识）
            failure_threshold: 失败阈值（连续失败次数）
            recovery_timeout: 恢复超时（秒）
            expected_exception: 期望的异常类型
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

        # Thread safety locks
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        调用受保护的函数（线程安全）

        Args:
            func: 要调用的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            Exception: 如果熔断器打开或函数失败
        """
        with self._lock:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                    logger.info(
                        f"🔄 Circuit breaker '{self.name}' entering HALF_OPEN state"
                    )
                else:
                    raise Exception(
                        f"⚡ Circuit breaker '{self.name}' is OPEN (too many failures)"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """异步版本的call（线程安全）"""
        async with self._async_lock:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                    logger.info(
                        f"🔄 Circuit breaker '{self.name}' entering HALF_OPEN state"
                    )
                else:
                    raise Exception(
                        f"⚡ Circuit breaker '{self.name}' is OPEN (too many failures)"
                    )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置"""
        if self.last_failure_time is None:
            return True
        return (
            datetime.now() - self.last_failure_time
        ).seconds >= self.recovery_timeout

    def _on_success(self):
        """成功回调（线程安全）"""
        with self._lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"✅ Circuit breaker '{self.name}' reset to CLOSED")

    def _on_failure(self):
        """失败回调（线程安全）"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(
                    f"🔥 Circuit breaker '{self.name}' opened after {self.failure_count} failures"
                )

    # Backward compatibility methods (delegates to internal methods)
    def can_execute(self) -> bool:
        """
        检查是否可以执行（向后兼容方法）

        Returns:
            True if circuit breaker allows execution
        """
        with self._lock:
            if self.state == "CLOSED":
                return True

            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                    return True
                return False

            # HALF_OPEN state
            return True

    def record_success(self) -> None:
        """
        记录成功（向后兼容方法）
        """
        self._on_success()

    def record_failure(self) -> None:
        """
        记录失败（向后兼容方法）
        """
        self._on_failure()

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is open"""
        return self.state == "OPEN"


class RetryStrategy:
    """重试策略 - 指数退避"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """
        初始化重试策略

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数基数
            jitter: 是否添加随机抖动
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        计算延迟时间

        Args:
            attempt: 当前重试次数（从1开始）

        Returns:
            延迟时间（秒）
        """
        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay,
        )

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random())

        return delay


async def retry_async(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
    **kwargs,
) -> Any:
    """
    异步重试装饰器

    Args:
        func: 要重试的异步函数
        max_retries: 最大重试次数
        base_delay: 基础延迟
        exceptions: 需要重试的异常类型
        on_retry: 重试回调函数

    Returns:
        函数返回值

    Raises:
        Exception: 如果所有重试都失败
    """
    strategy = RetryStrategy(max_retries=max_retries, base_delay=base_delay)
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"❌ Function {func.__name__} failed after {max_retries} retries: {e}"
                )
                raise

            delay = strategy.get_delay(attempt)
            logger.warning(
                f"⚠️ Function {func.__name__} failed (attempt {attempt}/{max_retries}), "
                f"retrying in {delay:.2f}s... Error: {e}"
            )

            if on_retry:
                on_retry(attempt, e)

            await asyncio.sleep(delay)

    raise last_exception


def with_circuit_breaker(breaker: CircuitBreaker):
    """熔断器装饰器"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call_async(func, *args, **kwargs)

        return wrapper

    return decorator


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
):
    """重试装饰器"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                exceptions=exceptions,
                **kwargs,
            )

        return wrapper

    return decorator


class RateLimiter:
    """滑动窗口速率限制器 - 更精确的速率控制"""

    def __init__(self, max_calls: int, time_window: int):
        """
        初始化速率限制器

        Args:
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()

    async def acquire(self):
        """获取调用许可"""
        now = time.time()

        # 清除过期的调用记录
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()

        # 检查是否超过限制
        if len(self.calls) >= self.max_calls:
            # 计算需要等待的时间
            oldest_call = self.calls[0]
            wait_time = self.time_window - (now - oldest_call)

            if wait_time > 0:
                logger.debug(f"⏱️ Rate limit reached, waiting {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)
                return await self.acquire()

        # 记录本次调用
        self.calls.append(time.time())


class HealthCheck:
    """健康检查 - 监控服务状态"""

    def __init__(self, name: str, check_interval: int = 60):
        """
        初始化健康检查

        Args:
            name: 服务名称
            check_interval: 检查间隔（秒）
        """
        self.name = name
        self.check_interval = check_interval
        self.is_healthy = True
        self.last_check_time = None
        self.error_count = 0
        self.success_count = 0

    async def check(self, check_func: Callable) -> bool:
        """
        执行健康检查

        Args:
            check_func: 检查函数（异步）

        Returns:
            是否健康
        """
        try:
            await check_func()
            self.is_healthy = True
            self.success_count += 1
            self.last_check_time = datetime.now()
            logger.debug(f"✅ Health check passed for {self.name}")
            return True
        except Exception as e:
            self.is_healthy = False
            self.error_count += 1
            self.last_check_time = datetime.now()
            logger.error(f"❌ Health check failed for {self.name}: {e}")
            return False

    def get_status(self) -> dict:
        """获取健康状态"""
        return {
            "name": self.name,
            "is_healthy": self.is_healthy,
            "last_check_time": self.last_check_time.isoformat()
            if self.last_check_time
            else None,
            "error_count": self.error_count,
            "success_count": self.success_count,
            "uptime_ratio": (
                self.success_count / (self.success_count + self.error_count)
                if (self.success_count + self.error_count) > 0
                else 0.0
            ),
        }


class GracefulDegradation:
    """优雅降级 - 在部分服务不可用时提供降级服务"""

    def __init__(self, name: str):
        """
        初始化降级策略

        Args:
            name: 服务名称
        """
        self.name = name
        self.degraded = False
        self.degradation_reason = None

    async def call_with_fallback(
        self,
        primary_func: Callable,
        fallback_func: Optional[Callable] = None,
        *args,
        **kwargs,
    ) -> Any:
        """
        使用降级策略调用函数

        Args:
            primary_func: 主函数
            fallback_func: 降级函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值
        """
        try:
            result = await primary_func(*args, **kwargs)
            if self.degraded:
                self.degraded = False
                logger.info(f"✅ Service {self.name} recovered from degradation")
            return result
        except Exception as e:
            if not self.degraded:
                self.degraded = True
                self.degradation_reason = str(e)
                logger.warning(f"⚠️ Service {self.name} degraded due to: {e}")

            if fallback_func:
                logger.info(f"🔄 Using fallback for {self.name}")
                return await fallback_func(*args, **kwargs)
            else:
                # 返回默认值或空结果
                logger.warning(
                    f"⚠️ No fallback available for {self.name}, returning None"
                )
                return None


# 全局熔断器实例
circuit_breakers = {
    "weibo": CircuitBreaker("weibo", failure_threshold=5, recovery_timeout=60),
    "twitter": CircuitBreaker("twitter", failure_threshold=3, recovery_timeout=120),
    "douyin": CircuitBreaker("douyin", failure_threshold=5, recovery_timeout=60),
    "zhihu": CircuitBreaker("zhihu", failure_threshold=5, recovery_timeout=60),
    "bilibili": CircuitBreaker("bilibili", failure_threshold=5, recovery_timeout=60),
    "xiaohongshu": CircuitBreaker(
        "xiaohongshu", failure_threshold=5, recovery_timeout=60
    ),
    "news": CircuitBreaker("news", failure_threshold=3, recovery_timeout=30),
}


def get_circuit_breaker(platform: str) -> CircuitBreaker:
    """获取平台的熔断器"""
    if platform not in circuit_breakers:
        circuit_breakers[platform] = CircuitBreaker(
            platform, failure_threshold=5, recovery_timeout=60
        )
    return circuit_breakers[platform]


class CircuitBreakerRegistry:
    """熔断器注册表 - 用于监控所有熔断器状态"""

    def __init__(self):
        self._breakers: dict = circuit_breakers

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """获取指定熔断器"""
        return self._breakers.get(name)

    def get_all(self) -> dict:
        """获取所有熔断器"""
        return self._breakers.copy()

    def get_status(self) -> dict:
        """获取所有熔断器状态"""
        return {
            name: {
                "state": breaker.state,
                "failure_count": breaker.failure_count,
                "is_open": breaker.state == "OPEN",
                "last_failure_time": (
                    breaker.last_failure_time.isoformat()
                    if breaker.last_failure_time
                    else None
                ),
            }
            for name, breaker in self._breakers.items()
        }

    def any_open(self) -> bool:
        """检查是否有任何熔断器打开"""
        return any(cb.state == "OPEN" for cb in self._breakers.values())


# 全局注册表实例
_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """获取全局熔断器注册表"""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry


class CircuitBreakerRegistry:
    """熔断器注册表 - 用于监控所有熔断器状态"""

    def __init__(self):
        self._breakers: dict = circuit_breakers

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """获取指定熔断器"""
        return self._breakers.get(name)

    def get_all(self) -> dict:
        """获取所有熔断器"""
        return self._breakers.copy()

    def get_status(self) -> dict:
        """获取所有熔断器状态"""
        return {
            name: {
                "state": breaker.state,
                "failure_count": breaker.failure_count,
                "is_open": breaker.state == "OPEN",
                "last_failure_time": (
                    breaker.last_failure_time.isoformat()
                    if breaker.last_failure_time
                    else None
                ),
            }
            for name, breaker in self._breakers.items()
        }

    def any_open(self) -> bool:
        """检查是否有任何熔断器打开"""
        return any(cb.state == "OPEN" for cb in self._breakers.values())


# 全局注册表实例
_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """获取全局熔断器注册表"""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry
