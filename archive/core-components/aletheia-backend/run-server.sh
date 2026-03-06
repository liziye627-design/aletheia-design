#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 可选强制直连（默认关闭）。在代理异常时可手动开启。
if [ "${FORCE_DIRECT_NETWORK:-0}" = "1" ]; then
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
  export NO_PROXY="127.0.0.1,localhost"
fi

# 启动前网络预检（可通过 SKIP_NETWORK_PREFLIGHT=1 跳过）
if [ "${SKIP_NETWORK_PREFLIGHT:-0}" != "1" ]; then
  echo "[preflight] Running network preflight..."
  ./venv/bin/python scripts/network_preflight.py --strict
fi

./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
