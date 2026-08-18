#!/usr/bin/env bash
# =============================================================================
# MiMo Proxy - 卸载 systemd 服务
#
# 用法（需 root，或 sudo）：
#   sudo bash deploy/uninstall.sh
#
# 可选环境变量：
#   MIMO_PROXY_DIR   安装目录（默认 /opt/mimo-proxy，与 install.sh 保持一致）
# =============================================================================
set -euo pipefail

SERVICE_NAME="mimo-proxy"
APP_DIR="${MIMO_PROXY_DIR:-/opt/mimo-proxy}"

[ "$(id -u)" -eq 0 ] || { echo "请以 root 运行：sudo bash deploy/uninstall.sh"; exit 1; }

# 停止并移除服务
systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
echo "[MiMo] 服务 $SERVICE_NAME 已停止并移除。"

# 询问是否删除代码目录
if [ -d "$APP_DIR" ]; then
    read -rp "[MiMo] 是否同时删除代码目录 $APP_DIR ？[y/N] " ans
    case "$ans" in
        y|Y) rm -rf "$APP_DIR"; echo "[MiMo] 已删除 $APP_DIR。";;
        *)   echo "[MiMo] 保留 $APP_DIR（如需手动删除：sudo rm -rf $APP_DIR）";;
    esac
fi
echo "[MiMo] 卸载完成。"
