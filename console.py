"""MiMo Proxy 远程只读网页控制台。

提供：
- 绿/红状态指示（绿 = 进程健康且近期无 ERROR；红 = 进程不可达或近期有 ERROR）
- 实时日志终端（WebSocket 推送 + 内存环形缓冲历史，支持报错着色）
- Cookie 一次性口令登录，过闸免打扰

接入方式见 `mimo_proxy.py`：import console 后把 `console.CONSOLE_ROUTES`
并入 Starlette routes，并在日志初始化后调用 `console.install_ring_handler()`。
"""

import asyncio
import hmac
import logging
import os
import threading
from collections import deque

from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import unquote_plus
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

load_dotenv(Path(__file__).resolve().parent / ".env")

CONSOLE_TOKEN = os.getenv("CONSOLE_TOKEN", "")
RING_MAX = int(os.getenv("CONSOLE_RING_MAX", "1000"))

_COOKIE_NAME = "mimo_console_token"
_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 天

_ring: deque = deque(maxlen=RING_MAX)
_ring_lock = threading.Lock()

_ws_queues: set[asyncio.Queue] = set()
_ws_lock = threading.Lock()

LOG_FMT = "%(asctime)s [%(name)s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"


class _RingBufferHandler(logging.Handler):
    """把日志灌进环形缓冲，同时推给所有已连接的控制台."""

    def emit(self, record: logging.LogRecord):
        if record.name == "uvicorn.access":
            # 过滤 uvicorn 自身的 HTTP access 日志，避免控制台自己刷屏
            return
        try:
            msg = self.format(record)
        except Exception:
            return
        entry = {
            "ts": record.created,
            "level": record.levelname,
            "msg": msg,
        }
        with _ring_lock:
            _ring.append(entry)
        with _ws_lock:
            queues = list(_ws_queues)
        for q in queues:
            try:
                q.put_nowait({"type": "line", "data": entry})
            except asyncio.QueueFull:
                pass


def install_ring_handler():
    """挂到 root logger（但不影响 uvicorn.access 的原始输出），返回该 handler."""
    handler = _RingBufferHandler()
    handler.setFormatter(logging.Formatter(LOG_FMT, datefmt=LOG_DATEFMT))
    logging.getLogger().addHandler(handler)
    return handler


# ─── 鉴权 ──────────────────────────────────────────────────────

def _is_authed(cookies: dict) -> bool:
    if not CONSOLE_TOKEN:
        return True
    given = cookies.get(_COOKIE_NAME, "")
    return bool(given) and hmac.compare_digest(given, CONSOLE_TOKEN)


# ─── 路由：登录 ────────────────────────────────────────────────

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiMo 控制台 · 登录</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
         background:#0d1117; color:#e6edf3; display:flex; align-items:center;
         justify-content:center; min-height:100vh; }
  .card { background:#161b22; border:1px solid #30363d; border-radius:10px;
          padding:28px 30px; width:320px; box-shadow:0 8px 30px rgba(0,0,0,.4); }
  h1 { font-size:18px; margin:0 0 6px; }
  p.sub { color:#8b949e; font-size:13px; margin:0 0 18px; }
  input { width:100%; box-sizing:border-box; padding:10px 12px; border-radius:6px;
          border:1px solid #30363d; background:#0d1117; color:#e6edf3; font-size:14px; }
  input:focus { outline:none; border-color:#2f81f7; }
  button { width:100%; margin-top:14px; padding:10px; border:none; border-radius:6px;
           background:#238636; color:#fff; font-size:14px; cursor:pointer; }
  button:hover { background:#2ea043; }
  .err { color:#f85149; font-size:13px; margin-top:10px; min-height:18px; }
</style>
</head>
<body>
  <form class="card" method="post" action="/console/login">
    <h1>MiMo 代理控制台</h1>
    <p class="sub">请输入访问口令以查看服务和实时日志</p>
    <input type="password" name="token" placeholder="访问令牌" autofocus required>
    <button type="submit">进入控制台</button>
    <div class="err" id="err">{{error}}</div>
  </form>
</body>
</html>"""


async def console_index(request: Request) -> HTMLResponse:
    if not _is_authed(request.cookies):
        return HTMLResponse(_LOGIN_HTML.replace("{{error}}", ""))
    return HTMLResponse(_CONSOLE_HTML)


async def console_login(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    token = ""
    for part in raw.split("&"):
        key, _, val = part.partition("=")
        if key == "token":
            token = unquote_plus(val).strip()
    if CONSOLE_TOKEN and not hmac.compare_digest(token, CONSOLE_TOKEN):
        return HTMLResponse(_LOGIN_HTML.replace("{{error}}", "口令错误，请重试"))
    resp = RedirectResponse("/console", status_code=303)
    resp.set_cookie(
        _COOKIE_NAME, CONSOLE_TOKEN or token,
        max_age=_COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return resp


# ─── 路由：状态 ────────────────────────────────────────────────

async def console_status(request: Request) -> JSONResponse:
    if not _is_authed(request.cookies):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    with _ring_lock:
        errors = [e for e in _ring if e["level"] == "ERROR"]
        size = len(_ring)
    return JSONResponse({
        "has_error": bool(errors),
        "last_error_ts": errors[-1]["ts"] if errors else None,
        "buffer_size": size,
        "ring_max": RING_MAX,
    })


# ─── 路由：WebSocket 实时日志 ──────────────────────────────────

async def console_ws(websocket: WebSocket):
    if not _is_authed(websocket.cookies):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    with _ws_lock:
        _ws_queues.add(queue)
    try:
        await _send_history(websocket)
        while True:
            entry = await queue.get()
            await websocket.send_json(entry)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        with _ws_lock:
            _ws_queues.discard(queue)


async def _send_history(websocket: WebSocket):
    with _ring_lock:
        history = list(_ring)
    await websocket.send_json({"type": "history", "data": history})


# ─── 前端页面 ─────────────────────────────────────────────────

_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiMo 代理控制台</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui,-apple-system,"Segoe UI","PingFang SC",sans-serif;
         background:#0d1117; color:#e6edf3; height:100vh; display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:12px; padding:10px 16px;
           background:#161b22; border-bottom:1px solid #30363d; flex:0 0 auto; }
  .dot { width:12px; height:12px; border-radius:50%; background:#f85149; flex:0 0 auto; }
  .dot.green { background:#2ea043; box-shadow:0 0 8px #2ea043aa; }
  .dot.red   { background:#f85149; box-shadow:0 0 8px #f85149aa; }
  .title { font-size:14px; font-weight:600; }
  .meta { font-size:12px; color:#8b949e; }
  .spacer { flex:1; }
  #updated { font-size:12px; color:#8b949e; }
  #togglePause { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                 border-radius:6px; padding:6px 12px; font-size:12px; cursor:pointer; }
  #togglePause:hover { background:#30363d; }
  #togglePause.paused { border-color:#1f6feb; color:#58a6ff; }
  main { flex:1 1 auto; overflow-y:auto; padding:8px 16px; background:#0d1117; }
  main.paused { overflow-y:scroll; }
  .line { font-family: ui-monospace,SFMono-Regular,Consolas,"Courier New",monospace;
          font-size:12.5px; line-height:1.6; white-space:pre-wrap; word-break:break-all;
          color:#c9d1d9; }
  .line .ts { color:#57606a; margin-right:8px; }
  .line.level-ERROR   { color:#f85149; }
  .line.level-WARNING { color:#d29922; }
  .empty { color:#57606a; font-size:13px; text-align:center; padding:40px 0; }
  .spinner { color:#8b949e; font-size:13px; padding:8px 0; }
</style>
</head>
<body>
  <header>
    <div class="dot" id="dot"></div>
    <span class="title" id="statusText">连接中…</span>
    <span class="meta" id="version"></span>
    <span class="spacer"></span>
    <span id="updated"></span>
    <button id="togglePause">暂停滚动</button>
  </header>
  <main id="log">
    <div class="spinner">正在连接实时日志…</div>
  </main>
  <script>
  const dot = document.getElementById('dot');
  const statusText = document.getElementById('statusText');
  const updated = document.getElementById('updated');
  const logEl = document.getElementById('log');
  const versions = document.getElementById('version');
  const toggleBtn = document.getElementById('togglePause');
  let paused = false;

  function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
  function addLine(entry){
    const div=document.createElement('div');
    div.className='line level-'+(entry.level||'INFO');
    const ts=entry.ts?new Date(entry.ts*1000).toLocaleTimeString():'';
    div.innerHTML='<span class="ts">['+esc(ts)+']</span>'+esc(entry.msg);
    logEl.appendChild(div);
    if(!paused){ logEl.scrollTop=logEl.scrollHeight; }
  }
  function showStatus(){
    const now=Date.now();
    updated.textContent='更新于 '+new Date(now).toLocaleTimeString();
  }

  async function refreshStatus(){
    let healthOk=false;
    try{ const r=await fetch('/health'); healthOk=r.ok; }catch(e){ healthOk=false; }
    let hasError=false, lastErr=null, size=0;
    try{
      const s=await fetch('/console/status');
      if(s.ok){ const j=await s.json(); hasError=j.has_error; lastErr=j.last_error_ts; size=j.buffer_size; }
    }catch(e){}
    if(!healthOk){ dot.className='dot red'; statusText.textContent='服务不可达'; }
    else if(hasError){ dot.className='dot red'; statusText.textContent='运行中 · 近期有报错'; }
    else { dot.className='dot green'; statusText.textContent='运行正常'; }
    versions.textContent='缓冲 '+size+' 条';
    showStatus();
  }

  function connect(){
    const proto = location.protocol==='https:'?'wss':'ws';
    const ws = new WebSocket(proto+'://'+location.host+'/console/ws');
    ws.onopen=function(){ refreshStatus(); };
    ws.onmessage=function(ev){
      const m=JSON.parse(ev.data);
      if(m.type==='history'){
        logEl.innerHTML='';
        if(!m.data || !m.data.length){ logEl.innerHTML='<div class="empty">暂无日志</div>'; }
        else { for(const e of m.data){ addLine(e); } }
      } else if(m.type==='line'){
        addLine(m.data);
      }
    };
    ws.onclose=function(){
      if(!logEl.querySelector('.empty') && !logEl.querySelector('.line')){
        logEl.innerHTML='<div class="empty">与实时日志的连接已断开，正在重连…</div>';
      }
      dot.className='dot red'; statusText.textContent='日志连接断开，重连中';
      setTimeout(connect, 2000);
    };
  }

  toggleBtn.addEventListener('click', function(){
    paused=!paused;
    logEl.classList.toggle('paused', paused);
    toggleBtn.classList.toggle('paused', paused);
    toggleBtn.textContent = paused?'恢复滚动':'暂停滚动';
  });

  refreshStatus();
  connect();
  setInterval(refreshStatus, 10000);
  </script>
</body>
</html>"""


console_routes = [
    Route("/console", console_index),
    Route("/console/login", console_login, methods=["POST"]),
    Route("/console/status", console_status),
    WebSocketRoute("/console/ws", console_ws),
]