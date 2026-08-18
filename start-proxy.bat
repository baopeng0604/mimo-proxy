@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PYTHON_PATH=.\.venv\Scripts\python.exe"

if not exist "%PYTHON_PATH%" (
    echo [MiMo Proxy] 未找到虚拟环境，开始自动初始化...
    where python >nul 2>nul
    if errorlevel 1 (
        echo [MiMo Proxy] 未找到 python 命令，尝试 py launcher...
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    "%PYTHON_PATH%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [MiMo Proxy] 依赖安装失败，请检查网络后手动执行：
        echo   %PYTHON_PATH% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [MiMo Proxy] 启动中... 按 Ctrl+C 停止
"%PYTHON_PATH%" mimo_proxy.py
pause
