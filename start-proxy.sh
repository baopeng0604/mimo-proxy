#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VENV_PYTHON=".venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[MiMo Proxy] 未找到虚拟环境，开始自动初始化..."
    python3 -m venv .venv
    "$VENV_PYTHON" -m pip install -r requirements.txt
fi

echo "[MiMo Proxy] 启动中... 按 Ctrl+C 停止"
exec "$VENV_PYTHON" mimo_proxy.py
