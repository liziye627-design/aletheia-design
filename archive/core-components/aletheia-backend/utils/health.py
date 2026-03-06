"""
Aletheia Health Check Module

Provides comprehensive health check functionality for all system components:
- Database (PostgreSQL/SQLite)
- Redis Cache
- LLM Providers
- Kafka Message Queue
- Media Crawler Services
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from utils.logging import logger
from core.config import settings


class HealthStatus(str, Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: Optional[datetime] = None


class HealthChecker:
    """Comprehensive health checker for all system components"""

    def __init__(self):
        self._last_full_check: Optional[datetime] = None
        self._cached_results: Dict[str, ComponentHealth] = {}

    async def check_all(self) -> Dict[str, Any]:
        """
        Run health checks on all components.

        Returns:
            Dict with overall status and individual component statuses
        """
        start_time = time.time()
        results = {}

        # Run all checks in parallel
        check_tasks = [
            ("database", self._check_database()),
            ("redis", self._check_redis()),
            ("llm", self._check_llm()),
            ("kafka", self._check_kafka()),
            ("mediacrawler", self._check_mediacrawler()),
        ]

        check_results = await asyncio.gather(
            *[check for _, check in check_tasks],
            return_exceptions=True
        )

        for (name, _), result in zip(check_tasks, check_results):
            if isinstance(result, Exception):
                results[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}",
                )
            else:
                results[name] = result

        # Determine overall status
        overall_status = self._calculate_overall_status(results)

        total_latency = (time.time() - start_time) * 1000
        self._last_full_check = datetime.now()
        self._cached_results = results

        return {
            "status": overall_status.value,
            "timestamp": datetime.now().isoformat(),
            "latency_ms": round(total_latency, 2),
            "components": {
                name: {
                    "status": health.status.value,
                    "message": health.message,
                    "latency_ms": round(health.latency_ms, 2),
                    "details": health.details,
                }
                for name, health in results.items()
            },
        }

    async def check_readiness(self) -> Dict[str, Any]:
        """
        Check if the service is ready to accept traffic.

        Returns ready only if critical components are healthy.
        """
        critical_components = ["database"]

        # Check only critical components
        results = {}
        for component in critical_components:
            check_method = getattr(self, f"_check_{component}", None)
            if check_method:
                try:
                    results[component] = await check_method()
                except Exception as e:
                    results[component] = ComponentHealth(
                        name=component,
                        status=HealthStatus.UNHEALTHY,
                        message=str(e),
                    )

        # Ready if all critical components are healthy
        is_ready = all(
            h.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            for h in results.values()
        )

        return {
            "ready": is_ready,
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now().isoformat(),
            "components": {
                name: {
                    "status": health.status.value,
                    "message": health.message,
                }
                for name, health in results.items()
            },
        }

    async def check_liveness(self) -> Dict[str, Any]:
        """
        Check if the service is alive (basic process health).

        This is a lightweight check that doesn't verify dependencies.
        """
        return {
            "alive": True,
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
        }

    async def _check_database(self) -> ComponentHealth:
        """Check database health"""
        start_time = time.time()

        try:
            # Check if using SQLite or PostgreSQL
            if hasattr(settings, 'REDIS_ENABLED') and not settings.REDIS_ENABLED:
                # Likely using SQLite for local dev
                from core.sqlite_database import check_sqlite_health_async
                result = await check_sqlite_health_async()
            else:
                # Try PostgreSQL
                try:
                    from core.database import check_db_health
                    result = await check_db_health()
                except ImportError:
                    # Fall back to SQLite
                    from core.sqlite_database import check_sqlite_health_async
                    result = await check_sqlite_health_async()

            latency = (time.time() - start_time) * 1000

            status = HealthStatus.HEALTHY if result.get("status") == "healthy" else HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="database",
                status=status,
                message="Database connection OK" if status == HealthStatus.HEALTHY else result.get("error", "Unknown error"),
                latency_ms=latency,
                details={
                    "type": result.get("type", "unknown"),
                    "path": result.get("path"),
                },
                last_check=datetime.now(),
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database check failed: {str(e)}",
                latency_ms=latency,
            )

    async def _check_redis(self) -> ComponentHealth:
        """Check Redis health"""
        start_time = time.time()

        if not settings.REDIS_ENABLED:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNKNOWN,
                message="Redis is disabled",
                details={"enabled": False},
            )

        try:
            from core.cache import check_redis_health
            result = await check_redis_health()

            latency = (time.time() - start_time) * 1000

            if result.get("status") == "healthy":
                status = HealthStatus.HEALTHY
            elif result.get("status") == "unavailable":
                status = HealthStatus.UNKNOWN
            else:
                status = HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="redis",
                status=status,
                message="Redis connection OK" if status == HealthStatus.HEALTHY else result.get("error", "Unknown error"),
                latency_ms=latency,
                details={
                    "enabled": True,
                    "connected": result.get("connected", False),
                    "used_memory": result.get("used_memory_human"),
                    "connected_clients": result.get("connected_clients"),
                },
                last_check=datetime.now(),
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis check failed: {str(e)}",
                latency_ms=latency,
            )

    async def _check_llm(self) -> ComponentHealth:
        """Check LLM provider health"""
        start_time = time.time()

        try:
            # Check if failover manager is available
            from services.llm.llm_failover import get_global_failover_manager

            manager = get_global_failover_manager()
            status_info = manager.get_status()

            latency = (time.time() - start_time) * 1000

            if status_info.get("healthy"):
                status = HealthStatus.HEALTHY
            elif status_info.get("available_providers", 0) > 0:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="llm",
                status=status,
                message=f"{status_info.get('available_providers', 0)}/{status_info.get('total_providers', 0)} providers available",
                latency_ms=latency,
                details={
                    "total_providers": status_info.get("total_providers", 0),
                    "available_providers": status_info.get("available_providers", 0),
                    "providers": status_info.get("providers", {}),
                },
                last_check=datetime.now(),
            )

        except ImportError:
            # Fall back to checking if primary LLM is configured
            latency = (time.time() - start_time) * 1000

            has_api_key = bool(settings.SILICONFLOW_API_KEY)

            return ComponentHealth(
                name="llm",
                status=HealthStatus.HEALTHY if has_api_key else HealthStatus.UNHEALTHY,
                message="LLM API key configured" if has_api_key else "No LLM API key configured",
                latency_ms=latency,
                details={
                    "siliconflow_configured": bool(settings.SILICONFLOW_API_KEY),
                },
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="llm",
                status=HealthStatus.UNHEALTHY,
                message=f"LLM check failed: {str(e)}",
                latency_ms=latency,
            )

    async def _check_kafka(self) -> ComponentHealth:
        """Check Kafka health"""
        start_time = time.time()

        # Kafka is optional, check if configured
        if not settings.KAFKA_BOOTSTRAP_SERVERS:
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.UNKNOWN,
                message="Kafka not configured",
                details={"configured": False},
            )

        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                request_timeout_ms=5000,
            )

            await producer.start()
            await producer.stop()

            latency = (time.time() - start_time) * 1000

            return ComponentHealth(
                name="kafka",
                status=HealthStatus.HEALTHY,
                message="Kafka connection OK",
                latency_ms=latency,
                details={
                    "configured": True,
                    "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                },
                last_check=datetime.now(),
            )

        except ImportError:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.UNKNOWN,
                message="aiokafka not installed",
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="kafka",
                status=HealthStatus.UNHEALTHY,
                message=f"Kafka check failed: {str(e)}",
                latency_ms=latency,
            )

    async def _check_mediacrawler(self) -> ComponentHealth:
        """Check MediaCrawler health"""
        start_time = time.time()

        if not settings.MEDIACRAWLER_ENABLED:
            return ComponentHealth(
                name="mediacrawler",
                status=HealthStatus.UNKNOWN,
                message="MediaCrawler is disabled",
                details={"enabled": False},
            )

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                endpoints = ["/api/health", "/health"]
                for endpoint in endpoints:
                    try:
                        async with session.get(
                            f"{settings.MEDIACRAWLER_BASE_URL}{endpoint}",
                            timeout=aiohttp.ClientTimeout(total=5),
                        ) as response:
                            latency = (time.time() - start_time) * 1000
                            if response.status == 200:
                                return ComponentHealth(
                                    name="mediacrawler",
                                    status=HealthStatus.HEALTHY,
                                    message="MediaCrawler is running",
                                    latency_ms=latency,
                                    details={
                                        "enabled": True,
                                        "base_url": settings.MEDIACRAWLER_BASE_URL,
                                        "health_endpoint": endpoint,
                                    },
                                    last_check=datetime.now(),
                                )
                    except Exception:
                        continue

                latency = (time.time() - start_time) * 1000
                return ComponentHealth(
                    name="mediacrawler",
                    status=HealthStatus.DEGRADED,
                    message="MediaCrawler health endpoint unavailable",
                    latency_ms=latency,
                    details={
                        "enabled": True,
                        "base_url": settings.MEDIACRAWLER_BASE_URL,
                    },
                )

        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="mediacrawler",
                status=HealthStatus.UNHEALTHY,
                message="MediaCrawler health check timed out",
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return ComponentHealth(
                name="mediacrawler",
                status=HealthStatus.UNHEALTHY,
                message=f"MediaCrawler check failed: {str(e)}",
                latency_ms=latency,
            )

    def _calculate_overall_status(self, results: Dict[str, ComponentHealth]) -> HealthStatus:
        """Calculate overall health status from component results"""
        if not results:
            return HealthStatus.UNKNOWN

        statuses = [h.status for h in results.values()]

        # If any critical component is unhealthy, overall is unhealthy
        critical_components = ["database"]
        for component in critical_components:
            if component in results and results[component].status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY

        # If any component is unhealthy, overall is degraded
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.DEGRADED

        # If any component is degraded, overall is degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED

        # If all are healthy, overall is healthy
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY

        # Otherwise unknown
        return HealthStatus.UNKNOWN


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


# Convenience functions
async def check_health() -> Dict[str, Any]:
    """Run full health check"""
    return await get_health_checker().check_all()


async def check_readiness() -> Dict[str, Any]:
    """Check service readiness"""
    return await get_health_checker().check_readiness()


async def check_liveness() -> Dict[str, Any]:
    """Check service liveness"""
    return await get_health_checker().check_liveness()
