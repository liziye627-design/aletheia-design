"""
LLM Provider Failover Module

Provides automatic failover for OpenAI-compatible providers with circuit breaker protection.
Each provider has its own circuit breaker, and the manager automatically tries providers
in priority order, skipping those with open circuit breakers.

Usage:
    from services.llm.llm_failover import LLMFailoverManager

    manager = LLMFailoverManager()
    manager.add_provider(
        name="primary",
        provider_type="openai_compatible",
        api_key="sk-...",
        model="deepseek-ai/DeepSeek-V3",
        base_url="https://api.siliconflow.cn/v1",
        priority=1
    )
    response = await manager.complete([{"role": "user", "content": "Hello!"}])
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
import aiohttp

from core.config import settings
from utils.stability import CircuitBreaker, RetryStrategy, retry_async
from utils.logging import logger


class ProviderStatus(Enum):
    """LLM Provider status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class LLMProviderConfig:
    """Configuration for a single LLM provider"""

    name: str  # Unique identifier for this provider
    provider_type: str  # openai-compatible
    api_key: str
    model: str
    base_url: str
    priority: int = 1  # Lower number = higher priority
    max_tokens: int = 4000
    temperature: float = 0.7
    timeout: int = 60

    # Circuit breaker configuration
    failure_threshold: int = 5
    recovery_timeout: int = 60

    # Internal state (not set during initialization)
    circuit_breaker: Optional[CircuitBreaker] = field(default=None, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def __post_init__(self):
        """Initialize circuit breaker after dataclass init"""
        self.circuit_breaker = CircuitBreaker(
            name=f"llm_{self.name}",
            failure_threshold=self.failure_threshold,
            recovery_timeout=self.recovery_timeout,
        )

    def is_available(self) -> bool:
        """Check if this provider is available (circuit breaker not open)"""
        return self.circuit_breaker.state != "OPEN"

    def get_status(self) -> ProviderStatus:
        """Get current provider status"""
        with self._lock:
            if self.circuit_breaker.state == "OPEN":
                return ProviderStatus.UNHEALTHY
            elif self.circuit_breaker.state == "HALF_OPEN":
                return ProviderStatus.DEGRADED
            else:
                return ProviderStatus.HEALTHY


class LLMFailoverManager:
    """
    Manages multiple LLM providers with automatic failover.

    Features:
    - Automatic failover between providers based on priority
    - Each provider has its own circuit breaker
    - Skips providers with open circuit breakers
    - Thread-safe provider management
    """

    def __init__(
        self,
        default_max_tokens: int = 4000,
        default_temperature: float = 0.7,
        default_timeout: int = 60,
    ):
        """
        Initialize the failover manager.

        Args:
            default_max_tokens: Default max tokens for completions
            default_temperature: Default temperature for completions
            default_timeout: Default timeout for API calls
        """
        self._providers: Dict[str, LLMProviderConfig] = {}
        self._sorted_providers: List[LLMProviderConfig] = []
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()

        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature
        self.default_timeout = default_timeout

        logger.info("LLMFailoverManager initialized")

    def add_provider(
        self,
        name: str,
        provider_type: str,
        api_key: str,
        model: str,
        base_url: str,
        priority: int = 1,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        """
        Add a new LLM provider.

        Args:
            name: Unique identifier for this provider
            provider_type: Type of provider (openai_compatible/openai/siliconflow)
            api_key: API key for authentication
            model: Model name to use
            base_url: Base URL for API calls
            priority: Priority level (lower = higher priority)
            max_tokens: Maximum tokens for responses
            temperature: Temperature for responses
            timeout: Request timeout in seconds
            failure_threshold: Circuit breaker failure threshold
            recovery_timeout: Circuit breaker recovery timeout
        """
        with self._lock:
            if name in self._providers:
                logger.warning(f"Provider '{name}' already exists, updating...")
                self.remove_provider(name)

            config = LLMProviderConfig(
                name=name,
                provider_type=provider_type,
                api_key=api_key,
                model=model,
                base_url=base_url,
                priority=priority,
                max_tokens=max_tokens or self.default_max_tokens,
                temperature=temperature or self.default_temperature,
                timeout=timeout or self.default_timeout,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )

            self._providers[name] = config
            self._resort_providers()

            logger.info(
                f"Added LLM provider '{name}' (type={provider_type}, model={model}, priority={priority})"
            )

    def remove_provider(self, name: str) -> bool:
        """
        Remove a provider.

        Args:
            name: Provider name to remove

        Returns:
            True if provider was removed, False if not found
        """
        with self._lock:
            if name in self._providers:
                del self._providers[name]
                self._resort_providers()
                logger.info(f"Removed LLM provider '{name}'")
                return True
            return False

    def _resort_providers(self) -> None:
        """Re-sort providers by priority (must be called with lock held)"""
        self._sorted_providers = sorted(
            self._providers.values(), key=lambda p: p.priority
        )

    def get_provider(self, name: str) -> Optional[LLMProviderConfig]:
        """
        Get a specific provider by name.

        Args:
            name: Provider name

        Returns:
            Provider config or None if not found
        """
        return self._providers.get(name)

    def get_active_provider(self) -> Optional[LLMProviderConfig]:
        """
        Get the current active provider (highest priority available).

        Returns:
            Active provider config or None if all are unavailable
        """
        with self._lock:
            for provider in self._sorted_providers:
                if provider.is_available():
                    return provider
        return None

    def get_all_providers(self) -> List[LLMProviderConfig]:
        """Get all configured providers sorted by priority."""
        with self._lock:
            return list(self._sorted_providers)

    def get_available_providers(self) -> List[LLMProviderConfig]:
        """Get all available providers (circuit breaker not open)."""
        with self._lock:
            return [p for p in self._sorted_providers if p.is_available()]

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Complete a chat conversation with automatic failover.

        Tries providers in priority order, skipping those with open circuit breakers.

        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            temperature: Override temperature
            max_tokens: Override max tokens
            **kwargs: Additional provider-specific arguments

        Returns:
            LLM response text

        Raises:
            Exception: If all providers fail
        """
        async with self._async_lock:
            available_providers = self.get_available_providers()

            if not available_providers:
                raise Exception(
                    "No LLM providers available - all circuit breakers are open"
                )

            last_error = None

            for provider in available_providers:
                try:
                    logger.debug(
                        f"Trying LLM provider '{provider.name}' (priority={provider.priority})"
                    )

                    response = await self._call_provider(
                        provider=provider,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )

                    # Success - record it and return
                    provider.circuit_breaker._on_success()
                    logger.info(
                        f"✅ LLM call succeeded with provider '{provider.name}'"
                    )
                    return response

                except Exception as e:
                    last_error = e
                    provider.circuit_breaker._on_failure()
                    logger.warning(
                        f"⚠️ LLM provider '{provider.name}' failed: {e}. "
                        f"Trying next provider..."
                    )

            # All providers failed
            logger.error(
                f"❌ All LLM providers failed. Last error: {last_error}"
            )
            raise Exception(
                f"All LLM providers failed. Last error: {last_error}"
            )

    async def _call_provider(
        self,
        provider: LLMProviderConfig,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Make an API call to a specific provider.

        Args:
            provider: Provider configuration
            messages: Chat messages
            temperature: Override temperature
            max_tokens: Override max tokens

        Returns:
            Response text
        """
        temp = temperature if temperature is not None else provider.temperature
        tokens = max_tokens if max_tokens is not None else provider.max_tokens

        allowed_types = {"siliconflow", "openai_compatible", "openai"}
        if provider.provider_type not in allowed_types:
            raise ValueError(f"Unsupported provider type: {provider.provider_type}")
        return await self._openai_compatible_call(provider, messages, temp, tokens)

    async def _openai_compatible_call(
        self,
        provider: LLMProviderConfig,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Make an OpenAI-compatible API call."""
        url = f"{provider.base_url.rstrip('/')}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}",
        }

        payload = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        timeout = aiohttp.ClientTimeout(total=provider.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"LLM API error ({response.status}): {error_text}"
                    )

                result = await response.json()
                return result["choices"][0]["message"]["content"]

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all providers.

        Returns:
            Dict with provider statuses and overall health
        """
        with self._lock:
            providers_status = {}
            available_count = 0

            for provider in self._sorted_providers:
                status = provider.get_status()
                providers_status[provider.name] = {
                    "type": provider.provider_type,
                    "model": provider.model,
                    "priority": provider.priority,
                    "status": status.value,
                    "circuit_breaker_state": provider.circuit_breaker.state,
                    "failure_count": provider.circuit_breaker.failure_count,
                }
                if status != ProviderStatus.UNHEALTHY:
                    available_count += 1

            return {
                "total_providers": len(self._providers),
                "available_providers": available_count,
                "providers": providers_status,
                "healthy": available_count > 0,
            }

    def reset_circuit_breaker(self, provider_name: str) -> bool:
        """
        Manually reset a provider's circuit breaker.

        Args:
            provider_name: Name of the provider

        Returns:
            True if reset, False if provider not found
        """
        provider = self._providers.get(provider_name)
        if provider:
            with provider._lock:
                provider.circuit_breaker.state = "CLOSED"
                provider.circuit_breaker.failure_count = 0
                logger.info(f"Reset circuit breaker for provider '{provider_name}'")
            return True
        return False

    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for provider in self._providers.values():
                with provider._lock:
                    provider.circuit_breaker.state = "CLOSED"
                    provider.circuit_breaker.failure_count = 0
            logger.info("Reset all circuit breakers")


# Convenience function for creating a manager from environment variables
def create_failover_manager_from_env() -> LLMFailoverManager:
    """
    Create an LLMFailoverManager configured from environment variables.

    Expected environment variables:
    - LLM_PROVIDERS: Comma-separated list of provider names
    - For each provider:
      - {PROVIDER}_API_KEY: API key
      - {PROVIDER}_MODEL: Model name
      - {PROVIDER}_API_BASE: Base URL (optional)
      - {PROVIDER}_PRIORITY: Priority (optional, default based on order)

    Returns:
        Configured LLMFailoverManager
    """
    import os

    def _cfg(name: str, default: str = "") -> str:
        """Read config from env first, then pydantic settings."""
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
        setting_value = getattr(settings, name, None)
        if setting_value is None:
            return default
        text = str(setting_value).strip()
        return text if text != "" else default

    manager = LLMFailoverManager()

    # Default provider configurations (OpenAI-compatible)
    default_configs = {
        "siliconflow": {
            "type": "openai_compatible",
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "deepseek-ai/DeepSeek-V3",
        },
    }

    provider_names_env = _cfg("LLM_PROVIDERS", "")
    if provider_names_env:
        provider_names = [p.strip() for p in provider_names_env.split(",") if p.strip()]
    else:
        provider_names = ["siliconflow"] if (
            _cfg("LLM_API_KEY") or _cfg("SILICONFLOW_API_KEY")
        ) else []

    # Add each provider
    for priority, name in enumerate(provider_names, 1):
        upper_name = name.upper()
        api_key = _cfg(f"{upper_name}_API_KEY", "")
        if not api_key:
            if name == "siliconflow" or len(provider_names) == 1:
                api_key = _cfg("LLM_API_KEY", "")
        if not api_key and name == "siliconflow":
            api_key = _cfg("SILICONFLOW_API_KEY", "")

        if not api_key:
            logger.warning(f"No API key found for provider '{name}', skipping")
            continue

        default_config = default_configs.get(
            name, {"type": "openai_compatible", "base_url": "", "model": ""}
        )

        base_url = (
            _cfg(f"{upper_name}_API_BASE")
            or _cfg(f"{upper_name}_BASE_URL", default_config.get("base_url", ""))
        )
        if not base_url and (name == "siliconflow" or len(provider_names) == 1):
            base_url = _cfg("LLM_API_BASE", "") or base_url
        if not base_url and name == "siliconflow":
            base_url = _cfg("SILICONFLOW_API_BASE", "")

        manager.add_provider(
            name=name,
            provider_type=_cfg(
                f"{upper_name}_TYPE", default_config.get("type", "openai_compatible")
            ),
            api_key=api_key,
            model=_cfg(f"{upper_name}_MODEL")
            or _cfg("LLM_MODEL")
            or default_config.get("model", ""),
            base_url=base_url,
            priority=int(_cfg(f"{upper_name}_PRIORITY", str(priority))),
        )

    return manager


# Global instance (lazy initialization)
_global_manager: Optional[LLMFailoverManager] = None
_global_manager_lock = threading.Lock()


def get_global_failover_manager() -> LLMFailoverManager:
    """
    Get the global LLMFailoverManager instance.

    Creates one from environment variables if not exists.

    Returns:
        Global LLMFailoverManager instance
    """
    global _global_manager

    if _global_manager is None:
        with _global_manager_lock:
            if _global_manager is None:
                _global_manager = create_failover_manager_from_env()

    return _global_manager


async def complete_with_failover(
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> str:
    """
    Convenience function to complete using the global failover manager.

    Args:
        messages: Chat messages
        temperature: Temperature override
        max_tokens: Max tokens override
        **kwargs: Additional arguments

    Returns:
        LLM response
    """
    manager = get_global_failover_manager()
    return await manager.complete(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
