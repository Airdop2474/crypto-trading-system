#!/usr/bin/env python3
"""诊断 Binance 代理是否真的生效。

用法（VPS 容器内）：
    docker compose exec paper_daemon python scripts/test_proxy_debug.py
"""
import os
import sys

# 1. 确认环境变量
proxy_url = os.getenv("BINANCE_PROXY_URL", "")
print(f"[1] BINANCE_PROXY_URL = {proxy_url!r}")

# 2. 构造 ccxt 实例并应用代理
import ccxt
from src.utils.binance_proxy import apply_proxy_to_ccxt, _is_http_proxy

exchange = ccxt.binance({"options": {"defaultType": "spot"}})
print(f"[2] exchange.proxies (应用前) = {getattr(exchange, 'proxies', None)}")

applied = apply_proxy_to_ccxt(exchange, testnet=False, public=True)
print(f"[3] apply_proxy_to_ccxt 返回: {applied}")
print(f"[4] _is_http_proxy 判断: {_is_http_proxy(proxy_url)}")
print(f"[5] exchange.proxies (应用后) = {getattr(exchange, 'proxies', None)}")
print(f"[6] exchange.aiohttp_proxy = {getattr(exchange, 'aiohttp_proxy', None)}")
print(f"[7] exchange.session_proxies = {getattr(exchange, 'session_proxies', None)}")

# 3. 检查 session（ccxt 同步版用 requests.Session）
session = getattr(exchange, 'session', None)
if session:
    print(f"[8] exchange.session.proxies = {getattr(session, 'proxies', None)}")
else:
    print(f"[8] exchange.session = None（尚未初始化）")

# 4. 实际测试访问 Binance
print("\n[9] 实际访问 Binance api.binance.com/api/v3/ping:")
try:
    # 先用 fetch_time 测试（最简单的公共端点）
    result = exchange.fetch_time()
    print(f"    ✓ 成功: {result}")
except Exception as e:
    print(f"    ✗ 失败: {type(e).__name__}: {e}")
    print(f"    HTTP 状态码: {getattr(e, 'http_status_code', 'N/A')}")

# 5. 测试 exchangeInfo（这是报错的端点）
print("\n[10] 访问 Binance api.binance.com/api/v3/exchangeInfo:")
try:
    markets = exchange.load_markets()
    print(f"    ✓ 成功: 加载了 {len(markets)} 个交易对")
except Exception as e:
    print(f"    ✗ 失败: {type(e).__name__}: {e}")
    print(f"    HTTP 状态码: {getattr(e, 'http_status_code', 'N/A')}")

# 6. 对比：用 requests 直接通过代理访问
print("\n[11] 用 requests 直接通过代理访问 Binance:")
import requests
proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
try:
    r = requests.get("https://api.binance.com/api/v3/ping", proxies=proxies, timeout=10)
    print(f"    状态码: {r.status_code}")
    print(f"    响应: {r.text[:200]}")
except Exception as e:
    print(f"    ✗ 失败: {type(e).__name__}: {e}")
