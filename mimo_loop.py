"""
uvicorn 自定义事件循环工厂（仅 Windows 需要）。

背景：uvicorn 0.36+ 在 Windows 上强制使用 ProactorEventLoop
（见 uvicorn/loops/asyncio.py），而 Proactor 在连接关闭时会对已关闭的
socket 再次 shutdown，抛出无害但刷屏的 ConnectionResetError
(WinError 10054)。

解决：通过 uvicorn.run(..., loop="mimo_loop:selector_loop_factory")
让 uvicorn 使用 Selector 事件循环。Selector 在连接关闭时只 close
socket、不 shutdown，因此不会出现该噪音。

Linux / macOS 的 asyncio 默认就是 SelectorEventLoop，且 mimo_proxy.py
只在 Windows 上传入该 loop 参数，因此本模块不影响 Linux / macOS。
"""

import asyncio


def selector_loop_factory():
    """直接返回一个 Selector 事件循环实例。

    uvicorn 对自定义 loop 字符串（如 "mimo_loop:selector_loop_factory"）
    的处理是：get_loop_factory() 原样返回本函数，asyncio.Runner 再调用
    本函数（loop_factory()），因此这里必须返回事件循环实例。
    """
    return asyncio.SelectorEventLoop()
