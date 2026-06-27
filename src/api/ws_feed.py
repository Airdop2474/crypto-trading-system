"""
WebSocket 实时行情订阅与广播

后台 asyncio 服务，连接 Binance 公开 WebSocket 流 (!ticker@arr)，
维护实时 ticker 缓存，并广播给所有已连接的 FastAPI WebSocket 客户端。

设计：
- 订阅 Binance !ticker@arr（每秒推送全市场 24h ticker）
- 解析并转换为前端 Ticker 契约（symbol 格式 BTC/USDT）
- 只保留 WATCH_SYMBOLS 列表中的交易对
- 自动重连（指数退避）
- 线程安全广播给多个前端 WebSocket 连接

用法（FastAPI 生命周期）：
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ws_feed.start())
        yield
        await ws_feed.stop()
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Set

import websockets
import websockets.exceptions

from src.utils.logger import logger
from src.utils.cache import cache, CacheKeys
from src.utils.binance_proxy import get_ws_proxy_url

# Binance 公开 WebSocket 端点（直连；配置反代后自动改写）
BINANCE_WS_URL = get_ws_proxy_url("wss://stream.binance.com:9443/ws/!ticker@arr")

# 需要订阅的交易对（与 src/api/market.py 的 WATCH_SYMBOLS 对齐）
WATCH_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT",
]

# Binance symbol -> 标准格式 的映射
_BINANCE_TO_STD = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
    "BNBUSDT": "BNB/USDT",
    "XRPUSDT": "XRP/USDT",
    "DOGEUSDT": "DOGE/USDT",
}

# 反向映射
_STD_TO_BINANCE = {v: k for k, v in _BINANCE_TO_STD.items()}


class WsFeed:
    """Binance WebSocket 行情订阅与广播服务"""

    def __init__(
        self,
        url: str = BINANCE_WS_URL,
        watch_symbols: Optional[List[str]] = None,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = 60.0,
    ):
        self.url = url
        self.watch_symbols = set(watch_symbols or WATCH_SYMBOLS)
        self._binance_symbols = {
            _STD_TO_BINANCE[s] for s in self.watch_symbols if s in _STD_TO_BINANCE
        }

        # 最新 ticker 缓存
        self._tickers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

        # 已连接的前端客户端
        self._clients: Set[asyncio.Queue] = set()

        # 控制信号
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._ws = None

        # 重连参数
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay

    async def start(self) -> None:
        """启动后台订阅（长运行，应在 lifespan 中 create_task）"""
        if self._running:
            return
        self._running = True

        # 从 Redis 加载上次缓存的 ticker（启动即可提供旧数据）
        self._load_from_cache()

        logger.info("WsFeed starting...")

        delay = self._reconnect_delay
        while self._running:
            try:
                await self._connect_and_listen()
                delay = self._reconnect_delay  # 成功后重置
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                ConnectionError,
                OSError,
            ) as e:
                logger.warning(f"WsFeed connection lost: {type(e).__name__}: {e}")
            except Exception as e:
                logger.error(f"WsFeed unexpected error: {type(e).__name__}: {e}")

            if not self._running:
                break

            logger.info(f"WsFeed reconnecting in {delay:.1f}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_reconnect_delay)

        logger.info("WsFeed stopped")

    async def stop(self) -> None:
        """停止后台订阅"""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("WsFeed stop requested")

    async def _connect_and_listen(self) -> None:
        """连接 Binance WS 并持续读取"""
        async with websockets.connect(
            self.url,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            logger.info(f"WsFeed connected to {self.url}")

            async for message in ws:
                if not self._running:
                    break
                await self._handle_message(message)

    async def _handle_message(self, raw: str) -> None:
        """处理 Binance ticker 消息"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        if not isinstance(data, list):
            return

        updates: List[Dict[str, Any]] = []

        for item in data:
            binance_sym = item.get("s", "")
            if binance_sym not in self._binance_symbols:
                continue

            std_sym = _BINANCE_TO_STD.get(binance_sym, "")
            if not std_sym:
                continue

            ticker = {
                "symbol": std_sym,
                "price": float(item.get("c", 0)),
                "changePct": float(item.get("P", 0)),
                "volume": float(item.get("q", 0)),  # 24h 成交额（计价货币）
                "high": float(item.get("h", 0)),
                "low": float(item.get("l", 0)),
            }

            async with self._lock:
                self._tickers[std_sym] = ticker

            updates.append(ticker)

        if updates:
            await self._broadcast(updates)
            # 持久化到 Redis（非阻塞，静默失败）
            self._save_to_cache()

    async def _broadcast(self, tickers: List[Dict[str, Any]]) -> None:
        """广播 ticker更新给所有已连接的客户端"""
        if not self._clients:
            return

        payload = json.dumps(tickers, ensure_ascii=False)
        dead: Set[asyncio.Queue] = set()

        for q in self._clients:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.add(q)

        # 清理满队列（客户端消费太慢）
        self._clients -= dead

    def get_tickers(self) -> List[Dict[str, Any]]:
        """获取当前缓存的 ticker 快照（同步，REST 回退用）"""
        return list(self._tickers.values())

    def _load_from_cache(self) -> None:
        """从 Redis 加载上次的 ticker 快照（启动时调用）"""
        try:
            data = cache.get(CacheKeys.TICKERS_SNAPSHOT)
            if data and isinstance(data, list):
                for ticker in data:
                    sym = ticker.get("symbol", "")
                    if sym:
                        self._tickers[sym] = ticker
                logger.info(
                    f"WsFeed: loaded {len(self._tickers)} tickers from "
                    f"{cache.backend_type} cache"
                )
        except Exception as e:
            logger.debug(f"WsFeed: cache load skipped: {e}")

    def _save_to_cache(self) -> None:
        """将当前 ticker 快照持久化到 Redis"""
        try:
            tickers = list(self._tickers.values())
            if tickers:
                cache.set(CacheKeys.TICKERS_SNAPSHOT, tickers, ttl=120)
        except Exception:
            pass  # 缓存失败不影响核心功能

    def subscribe(self) -> asyncio.Queue:
        """注册一个新的前端客户端，返回消息队列"""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """注销客户端"""
        self._clients.discard(q)

    @property
    def is_connected(self) -> bool:
        """Binance WS 是否已连接"""
        return self._running and self._ws is not None and self._ws.open

    @property
    def client_count(self) -> int:
        """已连接的前端客户端数量"""
        return len(self._clients)


# 模块级单例
ws_feed = WsFeed()


# 导出
__all__ = ["WsFeed", "ws_feed", "WATCH_SYMBOLS"]
