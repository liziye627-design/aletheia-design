"""
Network environment helpers.

Resolve whether HTTP clients should trust proxy-related environment variables.
"""

from __future__ import annotations

import os
import socket
from functools import lru_cache
from typing import Dict, List, Tuple
from urllib.parse import urlparse


_PROXY_ENV_KEYS = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
)
_LOCAL_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}
_NO_PROXY_ENV_KEYS = ("NO_PROXY", "no_proxy")
_LOCAL_DIRECT_BYPASS_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _normalize_proxy_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        return f"http://{raw}"
    return raw


@lru_cache(maxsize=64)
def _probe_local_proxy(host: str, port: int, timeout_sec: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def detect_broken_local_proxies(
    *,
    env: Dict[str, str] | None = None,
    probe_timeout_sec: float = 0.2,
) -> List[str]:
    source = env if env is not None else os.environ
    broken: List[str] = []
    seen: set[str] = set()
    for key in _PROXY_ENV_KEYS:
        proxy = _normalize_proxy_url(source.get(key, ""))
        if not proxy:
            continue
        try:
            parsed = urlparse(proxy)
        except Exception:
            continue
        host = (parsed.hostname or "").lower()
        if host not in _LOCAL_PROXY_HOSTS:
            continue
        port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        hp = f"{host}:{port}"
        if hp in seen:
            continue
        seen.add(hp)
        if not _probe_local_proxy(host, port, probe_timeout_sec):
            broken.append(hp)
    return broken


def ensure_local_no_proxy(env: Dict[str, str] | None = None) -> List[str]:
    """
    Ensure localhost targets bypass proxy.

    Returns appended hosts for observability/tests.
    """
    source = env if env is not None else os.environ
    current = ""
    if source.get("NO_PROXY"):
        current = str(source.get("NO_PROXY") or "")
    elif source.get("no_proxy"):
        current = str(source.get("no_proxy") or "")

    tokens = {part.strip() for part in current.split(",") if part.strip()}
    appended: List[str] = []
    for host in sorted(_LOCAL_DIRECT_BYPASS_HOSTS):
        if host not in tokens:
            tokens.add(host)
            appended.append(host)
    if not appended:
        return []

    merged = ",".join(sorted(tokens))
    if env is None:
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged
    else:
        source["NO_PROXY"] = merged
        source["no_proxy"] = merged
    return appended


def evaluate_trust_env(
    *,
    default: bool,
    auto_disable_local_proxy: bool = True,
    probe_timeout_sec: float = 0.2,
    env: Dict[str, str] | None = None,
) -> Tuple[bool, List[str]]:
    """
    Return (trust_env, broken_local_proxies).

    If `default` is False, always return (False, []).
    If enabled and a local proxy in env is unreachable, automatically disable
    trust_env to avoid global crawler failure caused by broken localhost proxy.
    """
    if not default:
        return False, []
    ensure_local_no_proxy(env=env)
    if not auto_disable_local_proxy:
        return True, []
    broken = detect_broken_local_proxies(
        env=env,
        probe_timeout_sec=probe_timeout_sec,
    )
    if broken:
        return False, broken
    return True, []
