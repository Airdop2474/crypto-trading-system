"""Binance API 反代 URL 改写工具

美国 IP 访问 Binance（含 testnet 和主网）返回 HTTP 451 地域限制。
用 Cloudflare Worker 中转，Worker 用路径前缀区分上游：
- /testnet/* → testnet.binance.vision
- /main/*    → api.binance.com

本模块统一三处反代调用：
- src/execution/exchange_broker.py（ExchangeBroker，下单/查单）
- src/api/market.py（公共行情）
- src/data/exchange.py（ExchangeClient，daemon 拉历史 K 线）

反代逻辑仅在 config.BINANCE_PROXY_URL 非空时生效，留空保持直连。
"""

from typing import Optional

from src.utils.logger import logger


def get_proxy_url() -> str:
    """读取 Binance 反代 URL（延迟导入 config 避免循环依赖）。

    返回空字符串表示直连。
    """
    try:
        from src.utils.config import config
        return config.BINANCE_PROXY_URL
    except Exception:
        return ""


def apply_proxy_to_ccxt(exchange, testnet: bool = False, public: bool = False) -> bool:
    """把 ccxt exchange 实例的 urls["api"] 改写为反代 URL。

    参数：
        exchange: ccxt exchange 实例（已构造，已 set_sandbox_mode）
        testnet: 是否测试网模式（决定 /testnet 还是 /main 前缀）
        public: 是否仅公开数据（公开行情/历史 K 线走主网 /main，
                即使 testnet=True 也用 /main，因为公开数据不需要 testnet 端点）

    返回：
        True 表示已应用反代，False 表示直连（BINANCE_PROXY_URL 为空）
    """
    proxy_url = get_proxy_url()
    if not proxy_url:
        return False

    # 前缀判断：
    # - public=True（公开行情/历史数据）→ 走主网 /main
    # - public=False 且 testnet=True → 走测试网 /testnet
    # - public=False 且 testnet=False → 走主网 /main
    if public or not testnet:
        prefix_path = "/main"
    else:
        prefix_path = "/testnet"

    proxy_prefix = proxy_url.rstrip("/") + prefix_path

    def _rewrite(value):
        """改写 URL：如果是完整 URL（含 https://），提取 path 部分；如果是纯路径，直接拼接。"""
        if isinstance(value, str):
            # 完整 URL：https://api.binance.com/api/v3 → /api/v3
            if value.startswith("http://") or value.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(value)
                path = parsed.path
                return proxy_prefix + path
            # 纯路径：/api/v3 → proxy_prefix + /api/v3
            return proxy_prefix + value
        return value

    api_urls = exchange.urls.get("api")
    if isinstance(api_urls, dict):
        exchange.urls["api"] = {
            f: _rewrite(p) for f, p in api_urls.items()
        }
    else:
        exchange.urls["api"] = _rewrite(api_urls)

    logger.info(f"Binance API 通过反代访问: {proxy_prefix}")
    return True


def get_ws_proxy_url(default_url: str = "wss://stream.binance.com:9443/ws/!ticker@arr") -> str:
    """构造 WebSocket 反代 URL。

    Cloudflare Worker 支持 WebSocket 代理。如果配置了 BINANCE_PROXY_URL，
    把 wss://stream.binance.com:9443/ws/<path> 改写为
    wss://<worker-host>/main/ws/<path>（Worker 需监听 /ws/* 路径并代理到 stream.binance.com:9443）。

    参数：
        default_url: 默认 WebSocket URL（直连 Binance）

    返回：
        反代后的 WebSocket URL，或原 URL（未配置反代时）
    """
    proxy_url = get_proxy_url()
    if not proxy_url:
        return default_url

    # 把 https:// 转成 wss://，http:// 转成 ws://
    worker_ws = proxy_url.replace("https://", "wss://").replace("http://", "ws://")
    worker_ws = worker_ws.rstrip("/")

    # 从默认 URL 提取路径部分：wss://stream.binance.com:9443/ws/!ticker@arr → /ws/!ticker@arr
    # Worker 路由：/main/ws/* → stream.binance.com:9443/ws/*
    if "/ws/" in default_url:
        ws_path = default_url[default_url.index("/ws/"):]
        return f"{worker_ws}/main{ws_path}"
    return default_url


__all__ = ["get_proxy_url", "apply_proxy_to_ccxt", "get_ws_proxy_url"]
