@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [MiMo Proxy] 未找到 uv，请先安装：https://docs.astral.sh/uv/
    echo   或改用 start-proxy.bat（venv 方案，无需 uv）
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [MiMo Proxy] 初始化 uv 虚拟环境...
    uv venv --python 3.11
    if errorlevel 1 (
        echo [MiMo Proxy] 虚拟环境创建失败
        pause
        exit /b 1
    )
    uv pip install --python .venv -r requirements.txt
    if errorlevel 1 (
        echo [MiMo Proxy] 依赖安装失败
        pause
        exit /b 1
    )
)

echo [MiMo Proxy] 启动中 (uv)... 按 Ctrl+C 停止
uv run python mimo_proxy.py
pause
