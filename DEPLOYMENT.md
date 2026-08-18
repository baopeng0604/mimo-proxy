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

---

## 七、清理卸载

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
