"""
Aletheia Prometheus 监控指标模块

提供业务指标收集和监控
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from functools import wraps
from typing import Callable, Optional
import time


# ===== 业务指标 =====

# 爬虫请求计数
crawler_requests_total = Counter(
    "aletheia_crawler_requests_total", "Total crawler requests", ["platform", "status"]
)

# 爬虫请求耗时
crawler_request_duration_seconds = Histogram(
    "aletheia_crawler_request_duration_seconds",
    "Crawler request duration",
    ["platform"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# 分析任务计数
analysis_requests_total = Counter(
    "aletheia_analysis_requests_total",
    "Total analysis requests",
    ["analysis_type", "status"],
)

# 分析耗时
analysis_duration_seconds = Histogram(
    "aletheia_analysis_duration_seconds",
    "Analysis duration",
    ["analysis_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# 可信度分数分布
credibility_score_histogram = Histogram(
    "aletheia_credibility_score",
    "Credibility score distribution",
    buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
)

# 当前进行中的分析任务
analysis_in_progress = Gauge(
    "aletheia_analysis_in_progress", "Number of analysis tasks in progress"
)

# 搜索结果计数
search_results_count = Histogram(
    "aletheia_search_results_count",
    "Number of search results",
    buckets=[0, 5, 10, 20, 50, 100],
)

# 缓存命中率
cache_hits_total = Counter(
    "aletheia_cache_hits_total", "Total cache hits", ["cache_type"]
)

cache_misses_total = Counter(
    "aletheia_cache_misses_total", "Total cache misses", ["cache_type"]
)

# 错误计数
errors_total = Counter(
    "aletheia_errors_total", "Total errors", ["error_type", "component"]
)

# 外部 API 调用
external_api_calls_total = Counter(
    "aletheia_external_api_calls_total",
    "Total external API calls",
    ["service", "endpoint", "status"],
)

external_api_duration_seconds = Histogram(
    "aletheia_external_api_duration_seconds",
    "External API call duration",
    ["service", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# 数据库操作
db_operations_total = Counter(
    "aletheia_db_operations_total",
    "Total database operations",
    ["operation", "table", "status"],
)

db_operation_duration_seconds = Histogram(
    "aletheia_db_operation_duration_seconds",
    "Database operation duration",
    ["operation", "table"],
    buckets=[0.001, 0.01, 0.1, 0.5, 1.0, 5.0],
)

# 应用信息
app_info = Info("aletheia_app", "Application information")


# ===== 基础设施指标 (Phase 6) =====

# 熔断器状态
circuit_breaker_state = Gauge(
    "aletheia_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["name", "component"],
)

circuit_breaker_failures_total = Counter(
    "aletheia_circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["name", "component"],
)

circuit_breaker_successes_total = Counter(
    "aletheia_circuit_breaker_successes_total",
    "Total circuit breaker successes",
    ["name", "component"],
)

circuit_breaker_state_changes_total = Counter(
    "aletheia_circuit_breaker_state_changes_total",
    "Total circuit breaker state changes",
    ["name", "component", "from_state", "to_state"],
)

# LLM 提供商指标
llm_provider_requests_total = Counter(
    "aletheia_llm_provider_requests_total",
    "Total LLM provider requests",
    ["provider", "model", "status"],
)

llm_provider_duration_seconds = Histogram(
    "aletheia_llm_provider_duration_seconds",
    "LLM provider request duration",
    ["provider", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

llm_provider_tokens_total = Counter(
    "aletheia_llm_provider_tokens_total",
    "Total LLM tokens used",
    ["provider", "model", "type"],  # type: prompt, completion
)

llm_provider_failovers_total = Counter(
    "aletheia_llm_provider_failovers_total",
    "Total LLM provider failovers",
    ["from_provider", "to_provider", "reason"],
)

llm_provider_available = Gauge(
    "aletheia_llm_provider_available",
    "Whether LLM provider is available (1=yes, 0=no)",
    ["provider"],
)

# 数据库连接池指标
db_pool_size = Gauge(
    "aletheia_db_pool_size",
    "Database connection pool size",
    ["database"],
)

db_pool_in_use = Gauge(
    "aletheia_db_pool_in_use",
    "Database connections in use",
    ["database"],
)

db_pool_available = Gauge(
    "aletheia_db_pool_available",
    "Database connections available",
    ["database"],
)

db_pool_wait_time_seconds = Histogram(
    "aletheia_db_pool_wait_time_seconds",
    "Time waiting for database connection",
    ["database"],
    buckets=[0.001, 0.01, 0.1, 0.5, 1.0, 5.0, 10.0],
)

# Redis 连接指标
redis_connections_total = Gauge(
    "aletheia_redis_connections_total",
    "Total Redis connections",
)

redis_connections_in_use = Gauge(
    "aletheia_redis_connections_in_use",
    "Redis connections in use",
)

redis_commands_total = Counter(
    "aletheia_redis_commands_total",
    "Total Redis commands",
    ["command", "status"],
)

redis_command_duration_seconds = Histogram(
    "aletheia_redis_command_duration_seconds",
    "Redis command duration",
    ["command"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

redis_reconnects_total = Counter(
    "aletheia_redis_reconnects_total",
    "Total Redis reconnections",
    ["status"],  # success, failed
)

# 健康检查指标
health_check_status = Gauge(
    "aletheia_health_check_status",
    "Component health status (0=unhealthy, 1=degraded, 2=healthy, 3=unknown)",
    ["component"],
)

health_check_duration_seconds = Histogram(
    "aletheia_health_check_duration_seconds",
    "Health check duration",
    ["component"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)


# ===== Investigation 专项指标 =====

crawler_platform_timeout_total = Counter(
    "crawler_platform_timeout_total",
    "Total crawler timeouts per platform",
    ["platform"],
)

crawler_platform_success_total = Counter(
    "crawler_platform_success_total",
    "Total crawler successes per platform",
    ["platform"],
)

investigation_valid_evidence_count = Histogram(
    "investigation_valid_evidence_count",
    "Valid evidence count per investigation run",
    buckets=[0, 20, 50, 100, 150, 200, 300, 500, 800, 1200, 2000],
)

investigation_duration_seconds = Histogram(
    "investigation_duration_seconds",
    "Investigation end-to-end duration seconds",
    buckets=[1, 5, 10, 20, 30, 60, 90, 120, 180, 240, 300, 600],
)

investigation_target_reached_total = Counter(
    "investigation_target_reached_total",
    "Investigation target reached counter",
    ["reached"],
)

investigation_live_evidence_count = Histogram(
    "investigation_live_evidence_count",
    "Live evidence count per investigation run",
    buckets=[0, 1, 3, 5, 10, 20, 50, 100, 200],
)

investigation_cached_evidence_count = Histogram(
    "investigation_cached_evidence_count",
    "Cached evidence count per investigation run",
    buckets=[0, 1, 3, 5, 10, 20, 50, 100, 200],
)

manual_takeover_waiting_total = Counter(
    "manual_takeover_waiting_total",
    "Manual takeover waiting events",
    ["platform", "reason_code"],
)


# ===== 监控装饰器 =====


def monitor_crawler(platform: str):
    """爬虫监控装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                crawler_requests_total.labels(platform=platform, status="success").inc()
                return result
            except Exception as e:
                crawler_requests_total.labels(platform=platform, status="error").inc()
                raise
            finally:
                duration = time.time() - start_time
                crawler_request_duration_seconds.labels(platform=platform).observe(
                    duration
                )

        return wrapper

    return decorator


def monitor_analysis(analysis_type: str):
    """分析任务监控装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            analysis_in_progress.inc()
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                analysis_requests_total.labels(
                    analysis_type=analysis_type, status="success"
                ).inc()

                # 如果返回结果包含可信度分数，记录它
                if hasattr(result, "credibility_score"):
                    credibility_score_histogram.observe(result.credibility_score)
                elif isinstance(result, dict) and "credibility_score" in result:
                    credibility_score_histogram.observe(result["credibility_score"])

                return result
            except Exception as e:
                analysis_requests_total.labels(
                    analysis_type=analysis_type, status="error"
                ).inc()
                raise
            finally:
                analysis_in_progress.dec()
                duration = time.time() - start_time
                analysis_duration_seconds.labels(analysis_type=analysis_type).observe(
                    duration
                )

        return wrapper

    return decorator


def monitor_external_api(service: str, endpoint: str):
    """外部 API 监控装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                external_api_calls_total.labels(
                    service=service, endpoint=endpoint, status="success"
                ).inc()
                return result
            except Exception as e:
                external_api_calls_total.labels(
                    service=service, endpoint=endpoint, status="error"
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                external_api_duration_seconds.labels(
                    service=service, endpoint=endpoint
                ).observe(duration)

        return wrapper

    return decorator


def monitor_db_operation(operation: str, table: str):
    """数据库操作监控装饰器"""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                db_operations_total.labels(
                    operation=operation, table=table, status="success"
                ).inc()
                return result
            except Exception as e:
                db_operations_total.labels(
                    operation=operation, table=table, status="error"
                ).inc()
                raise
            finally:
                duration = time.time() - start_time
                db_operation_duration_seconds.labels(
                    operation=operation, table=table
                ).observe(duration)

        return wrapper

    return decorator


# ===== 便捷函数 =====


def record_error(error_type: str, component: str):
    """记录错误"""
    errors_total.labels(error_type=error_type, component=component).inc()


def record_cache_hit(cache_type: str = "redis"):
    """记录缓存命中"""
    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str = "redis"):
    """记录缓存未命中"""
    cache_misses_total.labels(cache_type=cache_type).inc()


def record_search_results(count: int):
    """记录搜索结果数量"""
    search_results_count.observe(count)


def set_app_info(version: str, environment: str):
    """设置应用信息"""
    app_info.info({"version": version, "environment": environment})


# ===== 性能追踪上下文管理器 =====


class PerformanceTimer:
    """性能计时器（上下文管理器）"""

    def __init__(self, histogram, labels: Optional[dict] = None):
        self.histogram = histogram
        self.labels = labels or {}
        self.start_time = None

    async def __aenter__(self):
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            if self.labels:
                self.histogram.labels(**self.labels).observe(duration)
            else:
                self.histogram.observe(duration)


# 便捷上下文管理器
def timed(histogram, **labels):
    """
    计时上下文管理器

    使用示例:
        async with timed(analysis_duration_seconds, analysis_type='cot'):
            await perform_analysis()
    """
    return PerformanceTimer(histogram, labels)


# ===== Phase 6: 基础设施指标便捷函数 =====


def record_circuit_breaker_state(name: str, component: str, state: int):
    """
    记录熔断器状态

    Args:
        name: 熔断器名称
        component: 所属组件
        state: 状态码 (0=closed, 1=open, 2=half_open)
    """
    circuit_breaker_state.labels(name=name, component=component).set(state)


def record_circuit_breaker_failure(name: str, component: str):
    """记录熔断器失败"""
    circuit_breaker_failures_total.labels(name=name, component=component).inc()


def record_circuit_breaker_success(name: str, component: str):
    """记录熔断器成功"""
    circuit_breaker_successes_total.labels(name=name, component=component).inc()


def record_circuit_breaker_state_change(
    name: str, component: str, from_state: str, to_state: str
):
    """记录熔断器状态变更"""
    circuit_breaker_state_changes_total.labels(
        name=name, component=component, from_state=from_state, to_state=to_state
    ).inc()


def record_llm_request(
    provider: str, model: str, status: str, duration: float,
    prompt_tokens: int = 0, completion_tokens: int = 0
):
    """
    记录 LLM 请求

    Args:
        provider: 提供商名称 (siliconflow)
        model: 模型名称
        status: 请求状态 (success, error, timeout)
        duration: 请求耗时（秒）
        prompt_tokens: 提示词 token 数
        completion_tokens: 生成 token 数
    """
    llm_provider_requests_total.labels(
        provider=provider, model=model, status=status
    ).inc()
    llm_provider_duration_seconds.labels(
        provider=provider, model=model
    ).observe(duration)

    if prompt_tokens > 0:
        llm_provider_tokens_total.labels(
            provider=provider, model=model, type="prompt"
        ).inc(prompt_tokens)
    if completion_tokens > 0:
        llm_provider_tokens_total.labels(
            provider=provider, model=model, type="completion"
        ).inc(completion_tokens)


def record_llm_failover(from_provider: str, to_provider: str, reason: str):
    """
    记录 LLM 故障转移

    Args:
        from_provider: 原提供商
        to_provider: 目标提供商
        reason: 故障转移原因 (error, timeout, circuit_open, etc.)
    """
    llm_provider_failovers_total.labels(
        from_provider=from_provider, to_provider=to_provider, reason=reason
    ).inc()


def set_llm_provider_available(provider: str, available: bool):
    """设置 LLM 提供商可用性"""
    llm_provider_available.labels(provider=provider).set(1 if available else 0)


def update_db_pool_metrics(
    database: str, size: int, in_use: int, available: int
):
    """
    更新数据库连接池指标

    Args:
        database: 数据库名称 (postgres, sqlite)
        size: 连接池大小
        in_use: 使用中的连接数
        available: 可用连接数
    """
    db_pool_size.labels(database=database).set(size)
    db_pool_in_use.labels(database=database).set(in_use)
    db_pool_available.labels(database=database).set(available)


def record_db_pool_wait_time(database: str, wait_time: float):
    """记录数据库连接池等待时间"""
    db_pool_wait_time_seconds.labels(database=database).observe(wait_time)


def update_redis_metrics(total_connections: int, in_use: int):
    """更新 Redis 连接指标"""
    redis_connections_total.set(total_connections)
    redis_connections_in_use.set(in_use)


def record_redis_command(command: str, status: str, duration: float):
    """
    记录 Redis 命令

    Args:
        command: 命令名称 (get, set, mget, etc.)
        status: 执行状态 (success, error)
        duration: 执行耗时（秒）
    """
    redis_commands_total.labels(command=command, status=status).inc()
    redis_command_duration_seconds.labels(command=command).observe(duration)


def record_redis_reconnect(status: str):
    """
    记录 Redis 重连

    Args:
        status: 重连状态 (success, failed)
    """
    redis_reconnects_total.labels(status=status).inc()


def update_health_check_status(component: str, status: int):
    """
    更新健康检查状态

    Args:
        component: 组件名称
        status: 状态码 (0=unhealthy, 1=degraded, 2=healthy, 3=unknown)
    """
    health_check_status.labels(component=component).set(status)


def record_health_check_duration(component: str, duration: float):
    """记录健康检查耗时"""
    health_check_duration_seconds.labels(component=component).observe(duration)
