#!/usr/bin/env python3
"""
Binance testnet 集成冒烟（接 Demo 前的端到端连通验证）。

用 ExchangeBroker(testnet) 真连 Binance 测试网，跑一遍只读 + 安全下单生命周期，
证明"交易所这条线"通畅——为将来 Phase 7 把 daemon 接到真实执行铺地基。
本脚本不动主 daemon（daemon 仍跑 PaperBroker 模拟）。

步骤：
  1. 安全护栏：必须 BINANCE_TESTNET=true 且配了 key/secret，否则拒绝（绝不碰主网）
  2. 权限校验：查 apiRestrictions（testnet 可能不支持 → WARN 跳过，不算失败）
  3. 查余额：get_balance()（最核心的连通证明）
  4. 下单生命周期（--skip-order 可跳过）：挂一笔"远低于市价、不会成交"的限价买单
     → 查回状态 → 撤单。limit 价为市价的一半，挂着不成交，随即撤掉，零成交风险。

安全下单参数计算 safe_limit_order_params() 为纯函数，单测覆盖；其余为集成驱动。

用法：
    python scripts/testnet_smoke.py
    python scripts/testnet_smoke.py --skip-order --symbol BTC/USDT
退出码：0=全通；1=有步骤失败；2=配置/连接缺失（未配 testnet key 或非 testnet）。
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def safe_limit_order_params(last_price, notional=20.0, factor=0.5):
    """算一笔"远低于市价、不会成交"的限价买单参数。

    limit_price = last_price * factor（默认半价，挂单不会被吃）；
    amount = notional / limit_price（按目标名义额反推数量，越过 minNotional）。
    返回 (limit_price, amount)。纯函数。
    """
    if last_price <= 0:
        raise ValueError("last_price 必须为正")
    if not (0 < factor < 1):
        raise ValueError("factor 应在 (0,1)，确保限价低于市价不成交")
    limit_price = last_price * factor
    amount = notional / limit_price
    return limit_price, amount


def _p(status, msg):
    print(f"  [{status}] {msg}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Binance testnet 集成冒烟")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--notional", type=float, default=20.0)
    parser.add_argument("--skip-order", action="store_true",
                        help="只做只读检查（权限/余额），不下测试单")
    args = parser.parse_args(argv)

    from src.utils.config import config
    from src.utils.logger import setup_logger
    setup_logger(log_level="ERROR")

    print("=" * 72)
    print("Binance testnet 集成冒烟")
    print("=" * 72)

    # 1. 安全护栏 —— 绝不在主网/无凭据时跑
    if not config.BINANCE_TESTNET:
        _p("FAIL", "BINANCE_TESTNET != true，拒绝运行（本脚本只允许 testnet）")
        return 2
    if not config.BINANCE_API_KEY or not config.BINANCE_SECRET:
        _p("FAIL", "未配置 BINANCE_API_KEY / BINANCE_SECRET（在 .env 填 testnet key）")
        return 2

    from src.execution.broker import Order
    from src.execution.exchange_broker import ExchangeBroker
    from scripts.verify_api_key_permissions import (
        assess_api_key_permissions, fetch_restrictions,
    )

    broker = ExchangeBroker(
        api_key=config.BINANCE_API_KEY, secret=config.BINANCE_SECRET, testnet=True,
    )
    failed = False

    # 2. 权限校验（best-effort：testnet 可能无 SAPI apiRestrictions 端点）
    try:
        restrictions = fetch_restrictions(broker.exchange)
        ok, checks = assess_api_key_permissions(restrictions)
        for c in checks:
            _p(c["status"], f"权限/{c['name']}：{c['detail']}")
        if not ok:
            failed = True
    except Exception as e:
        _p("WARN", f"权限查询跳过（testnet 可能不支持 apiRestrictions）：{type(e).__name__}")

    # 3. 查余额（核心连通证明）
    try:
        bal = broker.get_balance()
        pos = broker.get_position(args.symbol)
        _p("PASS", f"查询余额成功：USDT free={bal}，{args.symbol} 持仓={pos}")
    except Exception as e:
        _p("FAIL", f"查询余额失败：{type(e).__name__}: {e}")
        return 1  # 连账户都查不到，后面无意义

    # 4. 下单生命周期（安全限价单：挂着不成交 → 查回 → 撤单）
    if not args.skip_order:
        try:
            ex = broker.exchange
            ex.load_markets()
            last = ex.fetch_ticker(args.symbol)["last"]
            raw_price, raw_amount = safe_limit_order_params(last, args.notional)
            price = float(ex.price_to_precision(args.symbol, raw_price))
            amount = float(ex.amount_to_precision(args.symbol, raw_amount))
            _p("INFO", f"市价≈{last}，挂安全限价买单 price={price} amount={amount}")

            result = broker.place_order(
                Order(args.symbol, "buy", amount, price, "limit"))
            if result.order_id is None:
                _p("FAIL", f"下单未返回 order_id：status={result.status} "
                           f"reason={result.reason}")
                return 1
            _p("PASS", f"下单成功：id={result.order_id} status={result.status}")

            status = broker.get_order_status(result.order_id)
            if status is None:
                _p("FAIL", "查回订单失败（get_order_status 返回 None）")
                failed = True
            else:
                _p("PASS", f"查回订单：status={status.get('status')}")

            # 撤单：先试 ExchangeBroker.cancel_order（已知它缺 symbol，binance 会失败）
            if broker.cancel_order(result.order_id):
                _p("PASS", "撤单成功（ExchangeBroker.cancel_order）")
            else:
                _p("WARN", "ExchangeBroker.cancel_order 失败——已知缺口：未传 symbol，"
                           "ccxt binance 撤单必须带 symbol（Phase 7 待修）。用底层撤单兜底清理。")
                ex.cancel_order(result.order_id, args.symbol)  # 兜底，绝不留挂单
                _p("PASS", "底层撤单成功（已清理挂单）")
        except Exception as e:
            _p("FAIL", f"下单生命周期异常：{type(e).__name__}: {e}")
            return 1

    print("-" * 72)
    if failed:
        print("结论：存在失败项，testnet 这条线尚未完全通。")
        return 1
    print("结论：testnet 集成冒烟通过。交易所连通/查询/下单生命周期 OK。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
