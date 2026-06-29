"""Binance API 反代/代理 URL 工具

美国 IP 访问 Binance（含 testnet 和主网）返回 HTTP 451 地域限制。
支持两种绕过方式：

1. **HTTP 代理**（推荐，VPS 本地 Clash/mihomo）
   BINANCE_PROXY_URL=http://172.17.0.1:7890
   通过 ccxt 的 proxies / aiohttp_proxy 参数走 HTTP 代理，URL 不变。

2. **Cloudflare Worker 反代**（历史方案）
   BINANCE_PROXY_URL=https://xxx.workers.dev
   改写 urls["api"] 为 worker/main/api/v3，用路径前缀区分上游。

本模块统一三处调用：
- src/execution/exchange_broker.py（ExchangeBroker，下单/查单）
- src/api/market.py（公共行情）
- src/data/exchange.py（ExchangeClient，daemon 拉历史 K 线）

配置留空时保持直连。
"""

from typing import Optional

from src.utils.logger import logger


def get_proxy_url() -> str:
    """读取 Binance 反代/代理 URL（延迟导入 config 避免循环依赖）。

    返回空字符串表示直连。
    """
    try:
        from src.utils.config import config
        return config.BINANCE_PROXY_URL
    except Exception:
        return ""


def _is_http_proxy(url: str) -> bool:
    """判断 BINANCE_PROXY_URL 是否是 HTTP 代理（而非 Cloudflare Worker 反代）。

    HTTP 代理特征：以 http:// 或 https:// 开头，且包含端口号（如 :7890），
    通常指向本地或内网 IP（127.0.0.1、172.17.0.1、host.docker.internal 等）。

    Cloudflare Worker 特征：以 https:// 开头，域名是 workers.dev 或自定义域名，
    没有端口号。
    """
    if not url:
        return False
    # 含端口号的 http(s):// 视为 HTTP 代理
    if url.startswith(("http://", "https://")):
        # 提取 host:port 部分
        from urllib.parse import urlparse
        parsed = urlparse(url)
        # 有显式端口号 → HTTP 代理
        if parsed.port is not None:
            return True
        # host 是 IP 地址（非域名）→ 也视为 HTTP 代理
        host = parsed.hostname or ""
        if host in ("127.0.0.1", "localhost") or host.startswith("172.") or host.startswith("192.168.") or host.startswith("10."):
            return True
    return False


def apply_proxy_to_ccxt(exchange, testnet: bool = False, public: bool = False) -> bool:
    """为 ccxt exchange 实例应用反代或 HTTP 代理。

    参数：
        exchange: ccxt exchange 实例（已构造，已 set_sandbox_mode）
        testnet: 是否测试网模式（Worker 模式下决定 /testnet 还是 /main 前缀）
        public: 是否仅公开数据（公开行情/历史 K 线走主网 /main，
                即使 testnet=True 也用 /main，因为公开数据不需要 testnet 端点）

    返回：
        True 表示已应用代理，False 表示直连（BINANCE_PROXY_URL 为空）
    """
    proxy_url = get_proxy_url()
    if not proxy_url:
        return False

    # ── 模式 1：HTTP 代理（Clash/mihomo 等）──
    # 用 ccxt 的 proxies 参数，不改写 URL
    if _is_http_proxy(proxy_url):
        # ccxt 同步版用 proxies，异步版用 aiohttp_proxy
        # 为兼容两种调用方式，都设置
        exchange.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        # aiohttp 异步客户端专用
        exchange.aiohttp_proxy = proxy_url
        # requests 同步客户端专用（部分 ccxt 版本）
        exchange.session_proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        logger.info(f"Binance API 通过 HTTP 代理访问: {proxy_url}")
        return True

    # ── 模式 2：Cloudflare Worker 反代 ──
    # 改写 urls["api"] 为 worker/<prefix>/<path>
    if public or not testnet:
        prefix_path = "/main"
    else:
        prefix_path = "/testnet"

    proxy_prefix = proxy_url.rstrip("/") + prefix_path

    def _rewrite(value):
        """改写 URL：如果是完整 URL（含 https://），提取 path 部分；如果是纯路径，直接拼接。"""
        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://"):
                from urllib.parse import urlparse
                parsed = urlparse(value)
                path = parsed.path
                return proxy_prefix + path
            return proxy_prefix + value
        return value

    api_urls = exchange.urls.get("api")
    if isinstance(api_urls, dict):
        exchange.urls["api"] = {
            f: _rewrite(p) for f, p in api_urls.items()
        }
    else:
        exchange.urls["api"] = _rewrite(api_urls)

    logger.info(f"Binance API 通过 Worker 反代访问: {proxy_prefix}")
    return True


def get_ws_proxy_url(default_url: str = "wss://stream.binance.com:9443/ws/!ticker@arr") -> str:
    """构造 WebSocket 反代 URL。

    Cloudflare Worker 支持 WebSocket 代理。如果配置了 BINANCE_PROXY_URL，
    把 wss://stream.binance.com:9443/ws/<path> 改写为
    wss://<worker-host>/main/ws/<path>（Worker 需监听 /ws/* 路径并代理到 stream.binance.com:9443）。

    HTTP 代理模式下 WebSocket 由 ccxt/websockets 库自动走系统代理，此函数返回原 URL。

    参数：
        default_url: 默认 WebSocket URL（直连 Binance）

    返回：
        反代后的 WebSocket URL，或原 URL（未配置反代或 HTTP 代理模式）
    """
    proxy_url = get_proxy_url()
    if not proxy_url:
        return default_url

    # HTTP 代理模式：WebSocket 由底层库处理，返回原 URL
    if _is_http_proxy(proxy_url):
        return default_url

    # Worker 反代模式：改写 URL
    worker_ws = proxy_url.replace("https://", "wss://").replace("http://", "ws://")
    worker_ws = worker_ws.rstrip("/")

    if "/ws/" in default_url:
        ws_path = default_url[default_url.index("/ws/"):]
        return f"{worker_ws}/main{ws_path}"
    return default_url


__all__ = ["get_proxy_url", "apply_proxy_to_ccxt", "get_ws_proxy_url", "is_http_proxy"]

# 公开 _is_http_proxy 便于其他模块判断模式
is_http_proxy = _is_http_proxy
