"""
WebSocket 日志广播：将子进程的输出实时推送给前端。

与 ws_feed.py（Binance 行情转发）分离，职责不同：
  - ws_feed：外部 WebSocket → 内部 Queue → 前端
  - ws_logs：子进程 stdout → 环形缓冲 + 内部 Queue → 前端

设计：
  - 每个运行模式独立订阅组
  - 环形缓冲 500 行/模式（用户打开日志面板时先看到历史）
  - Queue 满时丢弃（不阻塞子进程读取协程）
"""

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api.mode_manager import RunningMode

_MAX_BUFFER = 500
_MAX_QUEUE = 200


class WsLogBroadcaster:
    def __init__(self):
        # mode -> set of subscriber queues
        self._clients: dict[str, set[asyncio.Queue]] = defaultdict(set)
        # mode -> ring buffer of recent log lines
        self._buffers: dict[str, list[str]] = defaultdict(list)

    def subscribe(self, mode: "RunningMode") -> asyncio.Queue:
        """订阅指定模式的日志流，返回接收 Queue。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._clients[mode.value].add(q)
        return q

    def unsubscribe(self, mode: "RunningMode", q: asyncio.Queue):
        """取消订阅。"""
        self._clients[mode.value].discard(q)

    async def broadcast(self, mode: "RunningMode", line: str):
        """将一行日志广播给所有订阅者，并写入环形缓冲。"""
        key = mode.value

        # 写环形缓冲
        buf = self._buffers[key]
        buf.append(line)
        if len(buf) > _MAX_BUFFER:
            buf.pop(0)

        # 推给所有订阅者
        dead: set[asyncio.Queue] = set()
        for q in self._clients[key]:
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                dead.add(q)
        if dead:
            self._clients[key] -= dead

    def get_buffer(self, mode: "RunningMode", limit: int = 200) -> list[str]:
        """获取缓冲的历史日志（REST fallback 用）。"""
        buf = self._buffers[mode.value]
        return list(buf[-limit:])

    def clear_buffer(self, mode: "RunningMode"):
        """清空指定模式的缓冲。"""
        self._buffers[mode.value].clear()


# 模块级单例
ws_logs = WsLogBroadcaster()
