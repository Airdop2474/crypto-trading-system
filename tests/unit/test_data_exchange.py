"""数据层交易所客户端测试（src/data/exchange.py）。

构造后替换 client.exchange 为替身，离线覆盖 OHLCV 拉取/分批终止/
交易对信息/连接测试，不触网。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.data.exchange import ExchangeClient, create_binance_client


def _ms(ts):
    return int(pd.Timestamp(ts, tz="UTC").timestamp() * 1000)


def _rows(*pairs):
    """[(ts_str, close), ...] -> ccxt OHLCV 原始行 [ms,o,h,l,c,v]。"""
    return [[_ms(t), c, c, c, c, 1.0] for t, c in pairs]


class FakeExchange:
    def __init__(self, batches=None, markets=None, time_raises=False):
        self._batches = list(batches) if batches else []
        self._markets = markets or {}
        self._time_raises = time_raises

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        if self._batches:
            return self._batches.pop(0)
        return []

    def load_markets(self):
        return self._markets

    def fetch_time(self):
        if self._time_raises:
            raise ConnectionError("down")
        return 1700000000000


def _client(fake):
    c = ExchangeClient(testnet=True)
    c.exchange = fake
    return c


def test_fetch_ohlcv_returns_dataframe():
    fake = FakeExchange(batches=[_rows(("2024-01-01 00:00", 100.0),
                                       ("2024-01-01 01:00", 101.0))])
    df = _client(fake).fetch_ohlcv("BTC/USDT", "1h")
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    assert df["close"].iloc[-1] == 101.0


def test_fetch_ohlcv_propagates_error():
    class Boom(FakeExchange):
        def fetch_ohlcv(self, *a, **k):
            raise RuntimeError("api down")
    with pytest.raises(RuntimeError):
        _client(Boom()).fetch_ohlcv("BTC/USDT", "1h")


def test_fetch_ohlcv_range_concatenates_then_stops_on_empty():
    fake = FakeExchange(batches=[
        _rows(("2024-01-01 00:00", 100.0), ("2024-01-01 12:00", 102.0)),
        [],  # 第二批空 -> 结束
    ])
    df = _client(fake).fetch_ohlcv_range("BTC/USDT", "1h",
                                         "2024-01-01", "2024-01-02")
    assert len(df) == 2
    assert df["close"].tolist() == [100.0, 102.0]


def test_fetch_ohlcv_range_breaks_when_timestamp_not_advancing():
    # 交易所重复返回同一批（last_ts 不前进）-> 防死循环 guard 必须中断
    same = _rows(("2024-01-01 00:00", 100.0))
    fake = FakeExchange(batches=[list(same), list(same), list(same)])
    df = _client(fake).fetch_ohlcv_range("BTC/USDT", "1h",
                                         "2024-01-01", "2024-01-03")
    assert len(df) == 1  # 只取到第一批，未无限循环


def test_fetch_ohlcv_range_empty_returns_empty_df():
    fake = FakeExchange(batches=[[]])
    df = _client(fake).fetch_ohlcv_range("BTC/USDT", "1h",
                                         "2024-01-01", "2024-01-02")
    assert df.empty


def test_get_exchange_info_found_and_missing():
    fake = FakeExchange(markets={"BTC/USDT": {"id": "BTCUSDT", "active": True}})
    c = _client(fake)
    assert c.get_exchange_info("BTC/USDT")["id"] == "BTCUSDT"
    with pytest.raises(ValueError):
        c.get_exchange_info("ZZZ/USDT")


def test_test_connection_ok_and_fail():
    assert _client(FakeExchange()).test_connection() is True
    assert _client(FakeExchange(time_raises=True)).test_connection() is False


def test_create_binance_client_defaults_testnet():
    c = create_binance_client()
    assert isinstance(c, ExchangeClient)
    assert c.testnet is True


def test_public_client_carries_no_credentials():
    """public=True 不带凭据：公开行情无需签名，且 testnet key 打主网会被拒(-2008)。"""
    from unittest.mock import patch
    from src.data import exchange as ex
    with patch.object(ex.config, "BINANCE_API_KEY", "TESTNET_KEY"), \
            patch.object(ex.config, "BINANCE_SECRET", "TESTNET_SECRET"):
        pub = create_binance_client(testnet=False, public=True)
        auth = create_binance_client(testnet=True)
    assert not pub.exchange.apiKey  # 公开客户端无 key
    assert auth.exchange.apiKey == "TESTNET_KEY"  # 非 public 仍带凭据
