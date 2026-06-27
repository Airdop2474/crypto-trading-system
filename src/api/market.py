"""
实时行情：通过 ccxt 拉取 Binance 公共现货 24h ticker（无需 API Key）。

- 一次 fetch_tickers 批量取多个交易对，带 TTL 缓存避免频繁外呼。
- 任何失败（无网络/限流/交易所异常）都抛出，由调用方回退到本地派生行情，
  不让前端 500。
"""

import time
import threading
from typing import List, Optional

import ccxt

# 前端 market-watch 展示的交易对（对齐 frontend/lib/mock-data.ts）
WATCH_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT",
]

_CACHE_TTL = 15.0  # 秒
_exchange = None
_exchange_lock = threading.Lock()
_cache: Optional[List[dict]] = None
_cache_ts = 0.0


def _client():
    global _exchange
    if _exchange is None:
        with _exchange_lock:
            if _exchange is None:
                # 公共行情走主网（真实价格），不需要密钥
                _exchange = ccxt.binance({
                    "enableRateLimit": True,
                    "timeout": 20000,  # 冷启动 load_markets 较慢，放宽避免首次回退
                    "options": {"defaultType": "spot"},
                })
                # 反代中转：美国 IP 被地域限制（HTTP 451），通过 Cloudflare Worker 绕过
                # 公共行情走主网，用 /main 前缀
                try:
                    from src.utils.config import config
                    proxy = config.BINANCE_PROXY_URL
                except Exception:
                    proxy = ""
                if proxy:
                    proxy_prefix = proxy.rstrip("/") + "/main"
                    api_urls = _exchange.urls.get("api")
                    if isinstance(api_urls, dict):
                        _exchange.urls["api"] = {
                            f: proxy_prefix + p for f, p in api_urls.items()
                        }
                    else:
                        _exchange.urls["api"] = proxy_prefix
    return _exchange


def _map(symbol: str, t: dict) -> dict:
    return {
        "symbol": symbol,
        "price": t.get("last") or 0.0,
        "changePct": t.get("percentage") or 0.0,
        "volume": t.get("quoteVolume") or 0.0,   # 24h 成交额（计价货币）
        "high": t.get("high") or 0.0,
        "low": t.get("low") or 0.0,
    }


def get_live_tickers(symbols: List[str] = WATCH_SYMBOLS) -> List[dict]:
    """返回实时行情（contract 结构）。失败抛异常，由调用方回退。"""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    raw = _client().fetch_tickers(symbols)  # 一次批量请求
    out = [_map(s, raw[s]) for s in symbols if s in raw]
    if not out:
        raise RuntimeError("交易所未返回任何 ticker")

    _cache, _cache_ts = out, now
    return out
