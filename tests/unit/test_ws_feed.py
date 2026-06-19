"""
WebSocket Feed 模块单元测试

覆盖：
- WsFeed 消息解析
- WsFeed 客户端订阅/取消
- WsFeed 广播机制
- 模块导入

注意：项目 pytest 配置禁用了 asyncio 插件（-p no:asyncio），
因此使用 asyncio.run() 包装异步调用。
"""

import asyncio
import json

import pytest

from src.api.ws_feed import WsFeed, ws_feed, WATCH_SYMBOLS, _BINANCE_TO_STD


def _run(coro):
    """同步包装器运行 async 函数"""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestWsFeedParsing:
    """WsFeed 消息解析测试"""

    def test_handle_message_valid(self):
        """解析有效的 Binance ticker 消息"""
        feed = WsFeed()
        raw = json.dumps([
            {
                "e": "24hrTicker",
                "s": "BTCUSDT",
                "c": "67500.50",
                "P": "2.35",
                "q": "1250000000",
                "h": "68000.00",
                "l": "65500.00",
            },
            {
                "e": "24hrTicker",
                "s": "ETHUSDT",
                "c": "3500.25",
                "P": "-1.20",
                "q": "800000000",
                "h": "3600.00",
                "l": "3450.00",
            },
        ])

        _run(feed._handle_message(raw))

        tickers = feed.get_tickers()
        assert len(tickers) == 2

        btc = next(t for t in tickers if t["symbol"] == "BTC/USDT")
        assert btc["price"] == 67500.50
        assert btc["changePct"] == 2.35
        assert btc["volume"] == 1250000000

    def test_handle_message_filters_symbols(self):
        """只保留 WATCH_SYMBOLS 中的交易对"""
        feed = WsFeed()
        raw = json.dumps([
            {"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"},
            {"s": "UNKNOWNUSDT", "c": "1.0", "P": "0.5", "q": "10", "h": "1.1", "l": "0.9"},
        ])

        _run(feed._handle_message(raw))

        tickers = feed.get_tickers()
        assert len(tickers) == 1
        assert tickers[0]["symbol"] == "BTC/USDT"

    def test_handle_message_invalid_json(self):
        """无效 JSON 不崩溃"""
        feed = WsFeed()
        _run(feed._handle_message("not valid json"))
        assert feed.get_tickers() == []

    def test_handle_message_not_list(self):
        """非列表消息不崩溃"""
        feed = WsFeed()
        _run(feed._handle_message('{"type": "error"}'))
        assert feed.get_tickers() == []

    def test_handle_message_updates_cache(self):
        """相同 symbol 的消息更新缓存"""
        feed = WsFeed()
        raw1 = json.dumps([{"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"}])
        raw2 = json.dumps([{"s": "BTCUSDT", "c": "68000", "P": "2.0", "q": "200", "h": "69000", "l": "67000"}])

        _run(feed._handle_message(raw1))
        _run(feed._handle_message(raw2))

        tickers = feed.get_tickers()
        assert len(tickers) == 1
        assert tickers[0]["price"] == 68000


class TestWsFeedClients:
    """WsFeed 客户端管理测试"""

    def test_subscribe_creates_queue(self):
        """subscribe 创建消息队列"""
        feed = WsFeed()
        queue = feed.subscribe()
        assert queue is not None
        assert feed.client_count == 1

    def test_unsubscribe_removes_client(self):
        """unsubscribe 移除客户端"""
        feed = WsFeed()
        queue = feed.subscribe()
        assert feed.client_count == 1

        feed.unsubscribe(queue)
        assert feed.client_count == 0

    def test_multiple_clients(self):
        """支持多个客户端"""
        feed = WsFeed()
        q1 = feed.subscribe()
        q2 = feed.subscribe()
        q3 = feed.subscribe()

        assert feed.client_count == 3

        feed.unsubscribe(q2)
        assert feed.client_count == 2

    def test_broadcast_to_clients(self):
        """广播消息给所有客户端"""
        feed = WsFeed()
        q1 = feed.subscribe()
        q2 = feed.subscribe()

        # 手动调用 _handle_message 触发广播
        raw = json.dumps([
            {"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"}
        ])
        _run(feed._handle_message(raw))

        # 两个客户端都应收到消息
        assert not q1.empty()
        assert not q2.empty()

        msg1 = _run(q1.get())
        msg2 = _run(q2.get())

        data1 = json.loads(msg1)
        assert len(data1) == 1
        assert data1[0]["symbol"] == "BTC/USDT"


class TestWsFeedProperties:
    """WsFeed 属性测试"""

    def test_initial_state(self):
        """初始状态"""
        feed = WsFeed()
        assert feed.is_connected is False
        assert feed.client_count == 0
        assert feed.get_tickers() == []

    def test_watch_symbols_default(self):
        """默认 WATCH_SYMBOLS"""
        feed = WsFeed()
        assert "BTC/USDT" in feed.watch_symbols
        assert "ETH/USDT" in feed.watch_symbols

    def test_custom_watch_symbols(self):
        """自定义 WATCH_SYMBOLS"""
        feed = WsFeed(watch_symbols=["BTC/USDT"])
        assert "BTC/USDT" in feed.watch_symbols
        assert "ETH/USDT" not in feed.watch_symbols


class TestWsFeedModule:
    """模块级测试"""

    def test_singleton_exists(self):
        """模块级单例存在"""
        assert ws_feed is not None
        assert isinstance(ws_feed, WsFeed)

    def test_exports(self):
        """导出验证"""
        from src.api.ws_feed import WsFeed, ws_feed, WATCH_SYMBOLS
        assert WsFeed is not None
        assert ws_feed is not None
        assert WATCH_SYMBOLS is not None

    def test_binance_to_std_mapping(self):
        """Binance symbol 映射"""
        assert _BINANCE_TO_STD["BTCUSDT"] == "BTC/USDT"
        assert _BINANCE_TO_STD["ETHUSDT"] == "ETH/USDT"
        assert _BINANCE_TO_STD["SOLUSDT"] == "SOL/USDT"

    def test_watch_symbols_constant(self):
        """WATCH_SYMBOLS 常量"""
        assert "BTC/USDT" in WATCH_SYMBOLS
        assert len(WATCH_SYMBOLS) == 6


class TestWsFeedBroadcastEdgeCases:
    """广播边界情况测试"""

    def test_broadcast_no_clients(self):
        """无客户端时广播不崩溃"""
        feed = WsFeed()
        raw = json.dumps([
            {"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"}
        ])
        # 不应抛出异常
        _run(feed._handle_message(raw))
        assert len(feed.get_tickers()) == 1

    def test_broadcast_full_queue_removes_client(self):
        """满队列的客户端被移除"""
        feed = WsFeed()

        # 创建一个容量很小的队列
        small_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        feed._clients.add(small_queue)

        # 第一次填充
        small_queue.put_nowait("fill")

        # 触发广播（队列已满，应被移除）
        raw = json.dumps([
            {"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"}
        ])
        _run(feed._handle_message(raw))

        # 满队列的客户端应被移除
        assert feed.client_count == 0

    def test_all_symbols_parsed(self):
        """所有 WATCH_SYMBOLS 都能被正确解析"""
        feed = WsFeed()

        all_tickers = [
            {"s": "BTCUSDT", "c": "67500", "P": "1.0", "q": "100", "h": "68000", "l": "66000"},
            {"s": "ETHUSDT", "c": "3500", "P": "2.0", "q": "200", "h": "3600", "l": "3400"},
            {"s": "SOLUSDT", "c": "150", "P": "3.0", "q": "300", "h": "160", "l": "140"},
            {"s": "BNBUSDT", "c": "600", "P": "1.5", "q": "400", "h": "620", "l": "580"},
            {"s": "XRPUSDT", "c": "0.5", "P": "-1.0", "q": "500", "h": "0.55", "l": "0.45"},
            {"s": "DOGEUSDT", "c": "0.1", "P": "5.0", "q": "600", "h": "0.12", "l": "0.08"},
        ]

        raw = json.dumps(all_tickers)
        _run(feed._handle_message(raw))

        tickers = feed.get_tickers()
        assert len(tickers) == 6

        symbols = {t["symbol"] for t in tickers}
        assert symbols == set(WATCH_SYMBOLS)
