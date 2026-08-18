#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[MiMo Proxy] 未找到 uv，请先安装：https://docs.astral.sh/uv/"
    echo "   或改用 ./start-proxy.sh（venv 方案，无需 uv）"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[MiMo Proxy] 初始化 uv 虚拟环境..."
    uv venv --python 3.11
    uv pip install --python .venv -r requirements.txt
fi

echo "[MiMo Proxy] 启动中 (uv)... 按 Ctrl+C 停止"
exec uv run python mimo_proxy.py
