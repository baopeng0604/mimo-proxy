#!/usr/bin/env bash
# =============================================================================
# MiMo Proxy - Linux systemd 服务一键安装/更新脚本
#
# 用法（需 root，或 sudo）：
#   sudo bash deploy/install.sh
#
# 可选环境变量：
#   MIMO_PROXY_DIR   安装目录（默认 /opt/mimo-proxy）
#   MIMO_PROXY_USER  服务运行用户（默认 root）
#   MIMO_PROXY_REPO  仓库地址（默认 https://github.com/baopeng0604/mimo-proxy.git）
#   MIMO_API_KEY     安装时直接写入 .env（可选）
#   MIMO_API_BASE    安装时直接写入 .env（可选）
#
# 重复运行 = 更新（git pull + 重启服务）
# =============================================================================
set -euo pipefail

APP_DIR="${MIMO_PROXY_DIR:-/opt/mimo-proxy}"
SERVICE_USER="${MIMO_PROXY_USER:-root}"
SERVICE_NAME="mimo-proxy"
REPO_URL="${MIMO_PROXY_REPO:-https://github.com/baopeng0604/mimo-proxy.git}"
BRANCH="master"

log()  { echo -e "\033[1;32m[MiMo]\033[0m $*"; }
warn() { echo -e "\033[1;33m[MiMo]\033[0m $*"; }
die()  { echo -e "\033[1;31m[MiMo]\033[0m $*" >&2; exit 1; }

# ── 0. 权限检查 ────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "请以 root 运行：sudo bash deploy/install.sh"

# ── 1. 依赖检查 ────────────────────────────────────────────────
for cmd in git python3; do
    command -v "$cmd" >/dev/null 2>&1 || die "缺少命令: $cmd"
done
python3 -m venv --help >/dev/null 2>&1 || \
    die "python3 缺少 venv 模块。Debian/Ubuntu 请先执行: apt install -y python3-venv"

# ── 2. 获取/更新代码 ───────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    log "检测到 $APP_DIR 已存在，执行更新..."
    git -C "$APP_DIR" fetch origin
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
    log "克隆代码到 $APP_DIR ..."
    mkdir -p "$(dirname "$APP_DIR")"
    git clone -b "$BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 3. 虚拟环境 + 依赖 ─────────────────────────────────────────
if [ ! -x ".venv/bin/python" ]; then
    log "创建虚拟环境 .venv ..."
    python3 -m venv .venv
fi
log "安装依赖..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# ── 4. 配置 .env ───────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "已生成 $APP_DIR/.env（含占位密钥），请编辑填入真实密钥后重启服务："
    warn "  sudo nano $APP_DIR/.env"
fi
# 支持安装时通过环境变量直接写入（可选）
if [ -n "${MIMO_API_KEY:-}" ]; then
    sed -i "s|^MIMO_API_KEY=.*|MIMO_API_KEY=$MIMO_API_KEY|" "$APP_DIR/.env"
fi
if [ -n "${MIMO_API_BASE:-}" ]; then
    sed -i "s|^MIMO_API_BASE=.*|MIMO_API_BASE=$MIMO_API_BASE|" "$APP_DIR/.env"
fi

# ── 5. 生成 systemd 服务 ───────────────────────────────────────
log "写入 systemd 服务 /etc/systemd/system/$SERVICE_NAME.service ..."
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=MiMo Reasoning Content Proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/mimo_proxy.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── 6. 检查状态 ────────────────────────────────────────────────
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "✅ 服务已启动并设置开机自启：$SERVICE_NAME"
    log "  查看状态:  systemctl status $SERVICE_NAME"
    log "  实时日志:  journalctl -u $SERVICE_NAME -f"
    log "  客户端 BaseURL: http://<服务器IP>:8899/v1 （模型 mimo-v2.5-pro）"
else
    warn "服务启动失败，请查看日志：journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
