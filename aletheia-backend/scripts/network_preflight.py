#!/usr/bin/env python3
"""
Network preflight checks for backend runtime.

Goals:
- Detect broken proxy settings (especially localhost proxy in WSL)
- Detect DNS resolution failures early
- Verify core outbound endpoints for LLM and RSS
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

DEFAULT_ENDPOINTS = [
    "https://api.siliconflow.cn/v1/models",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
]


def _read_nameservers() -> List[str]:
    resolv = Path("/etc/resolv.conf")
    if not resolv.exists():
        return []
    out: List[str] = []
    for line in resolv.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("nameserver "):
            out.append(line.split(maxsplit=1)[1].strip())
    return out


def _extract_proxy_env() -> Dict[str, str]:
    keys = [
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "no_proxy",
        "NO_PROXY",
    ]
    return {k: os.getenv(k, "").strip() for k in keys if os.getenv(k, "").strip()}


def _check_dns(host: str) -> Dict[str, Any]:
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({x[4][0] for x in infos if x and x[4]})
        return {"ok": True, "host": host, "ips": ips[:6]}
    except Exception as exc:
        return {"ok": False, "host": host, "error": str(exc)}


def _http_probe(url: str, trust_env: bool, timeout_sec: float = 6.0) -> Dict[str, Any]:
    timeout = httpx.Timeout(timeout_sec, connect=min(3.0, timeout_sec))
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=trust_env) as cli:
            resp = cli.get(url)
        return {
            "ok": True,
            "status_code": int(resp.status_code),
            "trust_env": trust_env,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "trust_env": trust_env}


def run_preflight(endpoints: List[str]) -> Dict[str, Any]:
    proxy_env = _extract_proxy_env()
    nameservers = _read_nameservers()

    hosts = sorted({urlparse(url).hostname for url in endpoints if urlparse(url).hostname})
    dns_checks = [_check_dns(host) for host in hosts if host]
    dns_ok = all(item.get("ok") for item in dns_checks) if dns_checks else False

    endpoint_checks: List[Dict[str, Any]] = []
    proxy_suspected = False
    direct_suspected = False
    for url in endpoints:
        direct = _http_probe(url, trust_env=False)
        proxied = _http_probe(url, trust_env=True)
        endpoint_checks.append({"url": url, "direct": direct, "proxied": proxied})
        if direct.get("ok") and not proxied.get("ok"):
            proxy_suspected = True
        if not direct.get("ok"):
            direct_suspected = True

    any_endpoint_ok = any(
        row.get("direct", {}).get("ok") or row.get("proxied", {}).get("ok")
        for row in endpoint_checks
    )
    llm_ok = False
    rss_ok = False
    for row in endpoint_checks:
        url = str(row.get("url") or "")
        reachable = bool(row.get("direct", {}).get("ok") or row.get("proxied", {}).get("ok"))
        if "/v1/models" in url:
            llm_ok = llm_ok or reachable
        else:
            rss_ok = rss_ok or reachable

    suggestions: List[str] = []
    if proxy_env:
        suggestions.append("检测到代理环境变量；若代理不可用，建议临时 unset 代理后再启动服务。")
    if proxy_suspected:
        suggestions.append("直连可用但代理链路失败：优先修复代理或关闭代理。")
    if not dns_ok:
        suggestions.append("DNS 解析失败：请修复 /etc/resolv.conf 或 WSL DNS 配置。")
    if direct_suspected and not proxy_suspected:
        suggestions.append("直连也失败：请检查出口网络策略、防火墙、DNS。")

    return {
        "ok": bool(dns_ok and llm_ok and rss_ok),
        "dns_ok": bool(dns_ok),
        "endpoints_ok": bool(any_endpoint_ok),
        "llm_ok": bool(llm_ok),
        "rss_ok": bool(rss_ok),
        "proxy_env": proxy_env,
        "nameservers": nameservers,
        "dns_checks": dns_checks,
        "endpoint_checks": endpoint_checks,
        "suggestions": suggestions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aletheia network preflight")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when check fails")
    parser.add_argument(
        "--endpoint",
        action="append",
        dest="endpoints",
        default=[],
        help="Additional endpoint to probe (can be repeated)",
    )
    args = parser.parse_args()

    endpoints = list(DEFAULT_ENDPOINTS)
    endpoints.extend([e.strip() for e in args.endpoints if e and e.strip()])

    result = run_preflight(endpoints)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and not result.get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
