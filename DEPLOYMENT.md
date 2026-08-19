# MiMo Proxy 部署说明

> 项目地址：https://github.com/Mintneko/mimo-proxy
> 类型：Python 单文件代理（**非 NodeJS**），核心逻辑全部在 `mimo_proxy.py` 一个文件里。
>
> 用途：解决 `mimo-v2.5-pro` 在 Trae / DeepSeek Harness 等客户端开启工具调用时，
> 历史 assistant 消息缺少 `reasoning_content` 导致的上游 400 报错。
> 关键差异：`mimo-v2.5` 标准版校验宽松；**`mimo-v2.5-pro` 强制要求历史消息携带 `reasoning_content`**。

---

## 一、它大概是如何运行的

```
Trae / Harness / 任意 OpenAI 兼容客户端
        │  POST http://127.0.0.1:8899/v1/chat/completions
        ▼
┌─────────────────────────────────────────────┐
│  mimo_proxy.py  (Starlette, 监听 0.0.0.0:8899) │
│                                             │
│  1. 检查历史 assistant 消息                  │
│     ├─ 有缓存 → 注入 reasoning_content       │
│     └─ 无缓存 → 剥离 tool_calls 降级为纯文本  │
│  2. 把客户端 Authorization 头原样透传        │
│  3. 转发请求到小米 API (MIMO_API_BASE)       │
│  4. 流式/非流式返回，并把返回的              │
│     reasoning_content 写入内存缓存           │
└─────────────────────────────────────────────┘
        │  MIMO_API_BASE（.env 中配置）
        ▼
   小米 MiMo API（token-plan-cn / api.xiaomimimo.com）
```

要点：

- **鉴权是透传的**：代理不校验、不替换密钥，客户端请求里的 `Authorization` 头会原样发给小米 API。
  因此客户端填写的 API Key **必须是真实有效的小米 key**（`tp-` 或 `sk-` 开头），随便填会被小米拒绝（401）。
- **`.env` 中的 `MIMO_API_KEY` 当前代码并不读取**（代码只读 `MIMO_API_BASE`）。它可以留着当备忘，
  但真正生效的鉴权来自客户端请求头。（如果希望"客户端随便填、代理统一从 `.env` 注入 key"，见文末「可选：启用 .env 密钥注入」。）
- **`.env` 的加载已内置**：`mimo_proxy.py` 顶部已经写好 `load_dotenv()` + `os.getenv()`，
  启动时会自动读取脚本所在目录的 `.env`，**不需要再手动修改代码**。
- 缓存为内存缓存（重启即清空），`CACHE_MAX_SIZE=2000` 条、TTL 2 小时。

---

## 二、密钥与地址对照（重要）

| 密钥前缀 | 类型       | MIMO_API_BASE 值                            |
| -------- | ---------- | ------------------------------------------- |
| `tp-`    | Token Plan | `https://token-plan-cn.xiaomimimo.com/v1`   |
| `sk-`    | 按量付费   | `https://api.xiaomimimo.com/v1`             |

> ⚠️ `tp-` / `sk-` 不能混用对方的地址，否则鉴权失败。

---

## 三、快速开始

### 0. 准备 `.env`（唯一需要手动配置的文件）

在项目根目录新建（或直接编辑已有的）`.env`：

```env
MIMO_API_KEY=tp-xxxxxxxxxxxxxxxx
MIMO_API_BASE=https://token-plan-cn.xiaomimimo.com/v1
```

按你的密钥类型调整 `MIMO_API_BASE`。**不需要改任何 Python 代码。**

### 1. 安装依赖（二选一，只需执行一次）

**方式 A：uv（推荐，快）**

```bash
uv venv --python 3.11
uv pip install --python .venv -r requirements.txt
```

> 注意：`uv pip install` 必须加 `--python .venv`（或先激活 venv），否则会装到系统 Python，
> 之后 `uv run` 找不到依赖。

**方式 B：原生 venv + pip**

```bash
# Mac / Linux
python3 -m venv .venv
./.venv/bin/python3 -m pip install -r requirements.txt

# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Windows CMD
python -m venv .venv && .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 全程无需手动执行 `activate`，直接调用虚拟环境内完整路径的 Python 解释器即可。

### 2. 启动

```bash
# Mac / Linux
./.venv/bin/python3 mimo_proxy.py

# Windows PowerShell / CMD
.\.venv\Scripts\python.exe mimo_proxy.py

# 如果用 uv
uv run python mimo_proxy.py
```

看到 `✅ 代理已启动！` 即成功。停止：`Ctrl + C`。

---

## 四、一键启动脚本

脚本放在项目根目录，自动完成「检测虚拟环境 → 缺则创建并装依赖 → 启动」：

| 脚本                    | 平台   | 依赖管理 | 用法                          |
| ----------------------- | ------ | -------- | ----------------------------- |
| `start-proxy.bat`       | Windows| venv+pip | 双击，或 `.\start-proxy.bat`  |
| `start-proxy-uv.bat`    | Windows| uv       | 双击（需已安装 uv）           |
| `start-proxy.sh`        | Mac/Linux | venv+pip | `./start-proxy.sh`            |
| `start-proxy-uv.sh`     | Mac/Linux | uv       | `./start-proxy-uv.sh`（需 uv）|

Mac/Linux 首次使用需先加执行权限：

```bash
chmod +x start-proxy.sh start-proxy-uv.sh
```

> Windows 的 `.bat` 双击即可；`pause` 保证出错时窗口不闪退，方便查看报错。

---

## 五、客户端配置（Trae / DeepSeek Harness）

1. 添加服务商：OpenAI（自定义 / Compatible）
2. Base URL：`http://127.0.0.1:8899/v1`（**不要**再手动追加 `/chat/completions`）
3. API Key：**填你的真实小米 API Key**（`tp-` 或 `sk-` 开头）——代理会把它透传给小米 API 鉴权
4. 模型 ID：`mimo-v2.5-pro`
5. 所有请求走本地代理，不要混用小米官方地址

---

## 六、常见问题排查

| 现象                                     | 处理                                                                 |
| ---------------------------------------- | -------------------------------------------------------------------- |
| 404 报错                                 | 客户端 BaseURL 不要重复拼接 `/chat/completions`，用 `http://127.0.0.1:8899/v1` |
| 401 鉴权失败                             | 核对客户端填的 key 是否真实有效，且与 `MIMO_API_BASE` 的地址匹配（tp / sk 不混用） |
| 仅第一轮正常，多轮工具调用后 400         | 确认代理在运行；小米原生接口无法规避该限制，必须走代理                 |
| 想临时绕过代理                           | 模型改为 `mimo-v2.5`（标准版校验宽松），可直连官方接口                 |
| 启动时 MIMO_API_BASE 不是 .env 里的值    | 确认 `.env` 在项目根目录（与 `mimo_proxy.py` 同级）；改动后重启         |
| Windows 日志刷 `ConnectionResetError: [WinError 10054]` | 无害噪音，代理已内置修复，详见「七、平台差异说明」；重启代理生效 |

---

## 七、平台差异说明（Windows / Linux / macOS）

**结论：代码在所有平台行为一致，平台差异只影响日志噪音，不影响任何功能。**

| 平台   | asyncio 默认事件循环 | 说明 |
| ------ | -------------------- | ---- |
| Windows | Proactor | **uvicorn 0.36+ 在 Windows 上强制使用 Proactor 事件循环**（见 `uvicorn/loops/asyncio.py`）。Proactor 在连接关闭时会对**已关闭的 socket 再次 `shutdown()`**，抛出无害的 `ConnectionResetError: [WinError 10054]`。不影响任何请求结果，纯日志噪音，**但已实测解决**：代理提供 `mimo_loop.py` 自定义 Selector 事件循环工厂，`mimo_proxy.py` 启动时**仅 Windows** 通过 `loop="mimo_loop:selector_loop_factory"` 传给 uvicorn，连接断开场景实测不再出现 10054。 |
| Linux  | Selector | 默认就是 Selector 事件循环，不存在上述问题；`mimo_proxy.py` 只在 `sys.platform == "win32"` 时传自定义 loop 参数，Linux 上**完全不生效**，无任何影响。 |
| macOS  | Selector | 同 Linux，不受影响。 |

> 细节：`mimo_proxy.py` 的 `__main__` 块里，只有 `sys.platform == "win32"` 才会在 `uvicorn.run(**)` 参数中加入 `loop="mimo_loop:selector_loop_factory"`；`mimo_loop.py` 也只是在 Windows 上才会被加载。因此 **Linux / macOS 上这些代码直接跳过，不会引入任何行为变化**，部署在 Linux systemd 服务（见下节）时无需任何额外处理。
>
> 备注：如果 Windows 上仍想观察该噪音是否出现，可查看启动日志——正常情况下连接断开后日志只有 uvicorn 的 access log，不再有 `Exception in callback` / `WinError 10054` traceback。

---

## 八、Linux 服务器：部署为 systemd 服务（开机自启 + 崩溃自动重启）

适合把代理长期跑在 Linux 服务器上，重启服务器自动拉起、进程崩溃自动恢复。
脚本在仓库 `deploy/` 目录：`install.sh`（安装/更新）、`uninstall.sh`（卸载）。

### 1. 获取脚本（在服务器上二选一）

```bash
# 方式 A：git clone 整个仓库（推荐，脚本在 deploy/ 目录里）
git clone --depth 1 https://github.com/baopeng0604/mimo-proxy.git
cd mimo-proxy

# 方式 B：只上传脚本（在本地执行）
scp deploy/install.sh deploy/uninstall.sh user@服务器IP:~/
```

### 2. 一键安装

```bash
sudo bash deploy/install.sh
```

脚本自动完成：克隆代码到 `/opt/mimo-proxy`（可用环境变量 `MIMO_PROXY_DIR` 改）→ 创建 `.venv` 装依赖 → 生成 `.env`（若不存在）→ 写 systemd 服务 `mimo-proxy` → 设置开机自启 → 启动并检查状态。

### 3. 填写密钥（脚本只会在 `.env` 缺失时生成占位文件，必须填入真实值）

```bash
sudo nano /opt/mimo-proxy/.env
```

`MIMO_API_BASE` 必须与密钥类型匹配（`tp-` 用 `token-plan-cn` 地址，`sk-` 用 `api.xiaomimimo.com` 地址），改完重启：

```bash
sudo systemctl restart mimo-proxy
```

也可以在安装时直接带上：

```bash
sudo MIMO_API_KEY=tp-xxxxxxxx MIMO_API_BASE=https://token-plan-cn.xiaomimimo.com/v1 bash deploy/install.sh
```

### 4. 常用管理命令

```bash
systemctl status mimo-proxy        # 查看状态（含最近日志）
journalctl -u mimo-proxy -f        # 实时日志
journalctl -u mimo-proxy -n 100    # 最近 100 行
sudo systemctl restart mimo-proxy  # 重启
sudo systemctl stop mimo-proxy     # 停止
sudo systemctl disable mimo-proxy  # 取消开机自启
```

### 5. 更新版本

```bash
cd /opt/mimo-proxy && sudo git pull && sudo systemctl restart mimo-proxy
```

或直接重跑 `sudo bash deploy/install.sh`（会自动 `git pull` + 重启）。

### 6. 卸载

```bash
sudo bash deploy/uninstall.sh
```

### 7. 防火墙（可选）

服务监听 `0.0.0.0:8899`，仅内网使用则无需放行；需公网访问时：

```bash
# ufw
sudo ufw allow 8899/tcp
# firewalld
sudo firewall-cmd --permanent --add-port=8899/tcp && sudo firewall-cmd --reload
```

> ⚠️ 安全提醒：8899 暴露公网后，任何拿到你 API Key 的人都能借道调用小米 API（按量付费会扣费）。
> 建议用防火墙把 8899 限制在可信 IP 段内。

### 8. 客户端配置

Base URL 改为服务器的地址：`http://<服务器IP>:8899/v1`，模型 `mimo-v2.5-pro`，
API Key 填真实小米 key（代理透传鉴权）。

---

## 九、清理卸载

直接删除整个 `mimo-proxy` 文件夹即可。虚拟环境（`.venv`）都在项目目录内，无全局污染。

---

## 附录：可选——启用 `.env` 密钥注入（让客户端随便填 key）

当前代码是**透传**客户端 `Authorization` 头。如果你希望客户端随意填 key、
由代理统一从 `.env` 的 `MIMO_API_KEY` 注入真实密钥，可以把 `mimo_proxy.py` 中
`chat_completions` 和 `list_models` 两处构造 `headers` 的地方改成：

```python
headers = {}
auth = request.headers.get("authorization")
if auth:
    headers["authorization"] = auth          # 客户端带了就用客户端的
elif os.getenv("MIMO_API_KEY"):
    headers["authorization"] = f"Bearer {os.getenv('MIMO_API_KEY')}"  # 没带则用 .env 注入
```

注意：注入模式会让所有客户端共享同一个 key，适合个人本地使用；多用户场景建议保持透传。
