"""
爬虫增强工具类 - 反爬、性能、稳定性优化
"""

import asyncio
import random
import aiohttp
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timedelta
from functools import wraps
from core.config import settings
from utils.logging import logger
from utils.network_env import evaluate_trust_env


_AIOHTTP_TRUST_ENV, _BROKEN_LOCAL_PROXY = evaluate_trust_env(
    default=bool(getattr(settings, "CRAWLER_TRUST_ENV", False)),
    auto_disable_local_proxy=bool(
        getattr(settings, "CRAWLER_AUTO_DISABLE_BROKEN_LOCAL_PROXY", True)
    ),
    probe_timeout_sec=float(getattr(settings, "CRAWLER_PROXY_PROBE_TIMEOUT_SEC", 0.2)),
)
if _BROKEN_LOCAL_PROXY:
    logger.warning(
        f"⚠️ Detected unreachable local proxy in env ({','.join(_BROKEN_LOCAL_PROXY)}), "
        "disable crawler trust_env"
    )


class UserAgentPool:
    """User-Agent池 - 随机轮换"""

    DESKTOP_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    MOBILE_USER_AGENTS = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
        "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    ]

    @classmethod
    def get_random(cls, mobile: bool = False) -> str:
        """获取随机User-Agent"""
        pool = cls.MOBILE_USER_AGENTS if mobile else cls.DESKTOP_USER_AGENTS
        return random.choice(pool)


class HeaderBuilder:
    """请求头构建器 - 完整伪装"""

    @staticmethod
    def build_standard_headers(
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
        accept_language: str = "zh-CN,zh;q=0.9,en;q=0.8",
    ) -> Dict[str, str]:
        """构建标准HTTP请求头"""
        headers = {
            "User-Agent": user_agent or UserAgentPool.get_random(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": accept_language,
            # 避免服务端返回 br 编码而运行环境缺少 Brotli 解码器
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        if referer:
            headers["Referer"] = referer

        return headers

    @staticmethod
    def build_api_headers(
        api_key: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, str]:
        """构建API请求头"""
        headers = {
            "User-Agent": user_agent or UserAgentPool.get_random(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return headers


class RetryStrategy:
    """重试策略 - 指数退避"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ):
        """
        初始化重试策略

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟(秒)
            max_delay: 最大延迟(秒)
            exponential_base: 指数基数
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base

    def get_delay(self, attempt: int) -> float:
        """计算重试延迟(指数退避 + 随机抖动)"""
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        # 添加随机抖动(±20%)
        jitter = delay * 0.2 * (random.random() * 2 - 1)
        return max(0, delay + jitter)


def retry_on_failure(
    max_retries: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)
):
    """重试装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            strategy = RetryStrategy(max_retries=max_retries, base_delay=base_delay)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = strategy.get_delay(attempt)
                        logger.warning(
                            f"⚠️ {func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries + 1} attempts"
                        )

            raise last_exception

        return wrapper

    return decorator


class RateLimiter:
    """速率限制器 - 令牌桶算法"""

    def __init__(self, rate: float, burst: int = 1):
        """
        初始化速率限制器

        Args:
            rate: 每秒请求数
            burst: 突发容量
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = datetime.now()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """获取令牌(等待直到有可用令牌)"""
        async with self._lock:
            while self.tokens < 1:
                # 计算需要等待的时间
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self._add_tokens()

            self.tokens -= 1
            self._add_tokens()

    def _add_tokens(self):
        """根据时间流逝添加令牌"""
        now = datetime.now()
        time_passed = (now - self.last_update).total_seconds()
        self.tokens = min(self.burst, self.tokens + time_passed * self.rate)
        self.last_update = now


class CircuitBreaker:
    """熔断器 - 防止级联故障"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception,
    ):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时(秒)
            expected_exception: 预期异常类型
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

    async def call(self, func: Callable, *args, **kwargs):
        """通过熔断器调用函数"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
            else:
                raise Exception(
                    f"Circuit breaker is OPEN. Last failure: {self.last_failure_time}"
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """成功回调"""
        self.failure_count = 0
        self.state = "closed"

    def _on_failure(self):
        """失败回调"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"🔴 Circuit breaker opened after {self.failure_count} failures. "
                f"Will retry after {self.recovery_timeout}s"
            )

    def _should_attempt_reset(self) -> bool:
        """是否应该尝试重置"""
        return (
            self.last_failure_time is not None
            and (datetime.now() - self.last_failure_time).total_seconds()
            >= self.recovery_timeout
        )


class SessionPool:
    """HTTP会话池 - 连接复用"""

    def __init__(self, pool_size: int = 10):
        """
        初始化会话池

        Args:
            pool_size: 连接池大小
        """
        self.pool_size = pool_size
        # 延迟创建 connector/session，避免在无事件循环上下文实例化时报错
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """获取会话实例"""
        if self._connector is None or self._connector.closed:
            self._connector = aiohttp.TCPConnector(
                limit=self.pool_size,
                limit_per_host=5,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=aiohttp.ClientTimeout(total=30),
                trust_env=_AIOHTTP_TRUST_ENV,
            )
        return self._session

    async def close(self):
        """关闭会话池"""
        if self._session and not self._session.closed:
            await self._session.close()
            await asyncio.sleep(0.25)  # 等待清理
        self._session = None
        if self._connector and not self._connector.closed:
            await self._connector.close()
        self._connector = None


class CrawlerStats:
    """爬虫统计 - 监控与健康检查"""

    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_latency = 0.0
        self.start_time = datetime.now()

    def record_request(self, success: bool, latency: float):
        """记录请求"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        self.total_latency += latency

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": self.successful_requests / max(1, self.total_requests),
            "average_latency": self.total_latency / max(1, self.total_requests),
            "requests_per_second": self.total_requests / max(1, uptime),
            "uptime_seconds": uptime,
        }

    def is_healthy(self, min_success_rate: float = 0.8) -> bool:
        """健康检查"""
        if self.total_requests == 0:
            return True
        return (self.successful_requests / self.total_requests) >= min_success_rate
