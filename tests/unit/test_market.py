"""实时行情模块测试（src/api/market.py）。

用替身交易所注入模块全局，离线覆盖映射/缓存/空结果/client 构造。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.api import market


class FakeExchange:
    def __init__(self, tickers):
        self._tickers = tickers
        self.calls = 0

    def fetch_tickers(self, symbols):
        self.calls += 1
        return self._tickers


def _ticker(last, pct, qv, high, low):
    return {"last": last, "percentage": pct, "quoteVolume": qv,
            "high": high, "low": low}


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    """每个用例重置模块缓存与交易所单例。"""
    monkeypatch.setattr(market, "_cache", None)
    monkeypatch.setattr(market, "_cache_ts", 0.0)
    monkeypatch.setattr(market, "_exchange", None)


def test_map_full_fields():
    out = market._map("BTC/USDT", _ticker(100.0, 2.5, 9.9, 110.0, 90.0))
    assert out == {"symbol": "BTC/USDT", "price": 100.0, "changePct": 2.5,
                   "volume": 9.9, "high": 110.0, "low": 90.0}


def test_map_missing_fields_default_zero():
    out = market._map("ETH/USDT", {})
    assert out["price"] == 0.0 and out["changePct"] == 0.0
    assert out["volume"] == 0.0 and out["high"] == 0.0 and out["low"] == 0.0


def test_get_live_tickers_maps_symbols(monkeypatch):
    fake = FakeExchange({
        "BTC/USDT": _ticker(65000.0, 1.2, 1e9, 66000.0, 64000.0),
        "ETH/USDT": _ticker(3500.0, -0.5, 5e8, 3600.0, 3400.0),
    })
    monkeypatch.setattr(market, "_exchange", fake)
    out = market.get_live_tickers(["BTC/USDT", "ETH/USDT"])
    assert [r["symbol"] for r in out] == ["BTC/USDT", "ETH/USDT"]
    assert out[0]["price"] == 65000.0 and out[1]["changePct"] == -0.5


def test_get_live_tickers_uses_cache_within_ttl(monkeypatch):
    fake = FakeExchange({"BTC/USDT": _ticker(1.0, 0.0, 0.0, 0.0, 0.0)})
    monkeypatch.setattr(market, "_exchange", fake)
    market.get_live_tickers(["BTC/USDT"])
    market.get_live_tickers(["BTC/USDT"])  # 第二次应命中缓存
    assert fake.calls == 1


def test_get_live_tickers_empty_raises(monkeypatch):
    # 交易所返回里没有请求的 symbol → out 为空 → 抛出由调用方回退
    fake = FakeExchange({"NOPE/USDT": _ticker(1.0, 0.0, 0.0, 0.0, 0.0)})
    monkeypatch.setattr(market, "_exchange", fake)
    with pytest.raises(RuntimeError):
        market.get_live_tickers(["BTC/USDT"])


def test_client_constructs_spot_exchange(monkeypatch):
    """_client() 懒构造（不触网），配置为现货 + 限流。"""
    c = market._client()
    assert c.options.get("defaultType") == "spot"
    # 再次调用返回同一单例
    assert market._client() is c
