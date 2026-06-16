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


def safe_limit_order_params(last_price, notional=20.0, factor=0.7):
    """算一笔"低于市价、不会成交"的限价买单参数。

    limit_price = last_price * factor（默认市价 7 折）；amount = notional / limit_price
    （按目标名义额反推数量，越过 minNotional）。返回 (limit_price, amount)。纯函数。

    factor 取 0.7 而非更低：币安 PERCENT_PRICE_BY_SIDE 过滤器限制买单限价不得低于
    近 5 分钟均价的 bidMultiplierDown（BTC/USDT 为 0.5）。0.7 稳在价格带内、又有
    30% 价差挂着不成交；取 0.5 会卡边界被拒。
    """
    if last_price <= 0:
        raise ValueError("last_price 必须为正")
    if not (0 < factor < 1):
        raise ValueError("factor 应在 (0,1)，确保限价低于市价不成交")
    limit_price = last_price * factor
    amount = notional / limit_price
    return limit_price, amount


def extract_fill(place_result, order_status=None):
    """从下单结果（+ 可选查单结果）提取真实成交价/量。纯函数。

    市价单可能在 place_order 返回里直接带 average/filled，也可能要再查单才有。
    优先用 place_result 的 filled_price/filled_amount，缺失则回退到 order_status
    的 average/filled。返回 (price, amount, source)，source ∈ {place, status, none}。

    这是 Stage 1 place_and_confirm 的取价核心。
    """
    p = getattr(place_result, "filled_price", None)
    a = getattr(place_result, "filled_amount", None)
    if p and a:
        return float(p), float(a), "place"
    if order_status:
        sp = order_status.get("average") or order_status.get("price")
        sa = order_status.get("filled")
        if sp and sa:
            return float(sp), float(sa), "status"
    return None, None, "none"


def _p(status, msg):
    print(f"  [{status}] {msg}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Binance testnet 集成冒烟")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--notional", type=float, default=20.0)
    parser.add_argument("--skip-order", action="store_true",
                        help="只做只读检查（权限/余额），不下测试单")
    parser.add_argument("--market-spike", action="store_true",
                        help="Phase 7 Stage 0：下一笔极小市价买+卖回，实测成交字段"
                             "（会真实改动 testnet 持仓，仅 testnet）")
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

            # 撤单：ExchangeBroker.cancel_order（symbol 已在 7b506a3 修复）
            if broker.cancel_order(result.order_id):
                _p("PASS", "撤单成功（ExchangeBroker.cancel_order）")
            else:
                _p("WARN", "ExchangeBroker.cancel_order 失败，用底层撤单兜底清理。")
                ex.cancel_order(result.order_id, args.symbol)  # 兜底，绝不留挂单
                _p("PASS", "底层撤单成功（已清理挂单）")
        except Exception as e:
            _p("FAIL", f"下单生命周期异常：{type(e).__name__}: {e}")
            return 1

    # 5. Phase 7 Stage 0：市价单 spike —— 实测市价成交字段（会改动 testnet 持仓）
    if args.market_spike:
        try:
            ex = broker.exchange
            ex.load_markets()
            last = ex.fetch_ticker(args.symbol)["last"]
            # minNotional 守卫：买够最小名义额（带余量），再原样卖回平掉
            raw_amount = max(args.notional, 6.0) / last
            amount = float(ex.amount_to_precision(args.symbol, raw_amount))
            _p("INFO", f"市价 spike：市价≈{last}，市价买 amount={amount}")

            buy = broker.place_order(Order(args.symbol, "buy", amount, last, "market"))
            if buy.order_id is None:
                _p("FAIL", f"市价买失败：status={buy.status} reason={buy.reason}")
                return 1
            bstatus = broker.get_order_status(buy.order_id)
            bp, ba, bsrc = extract_fill(buy, bstatus)
            if bp is None:
                _p("FAIL", "市价买未能取到成交价量（place 与 status 都缺）")
                failed = True
            else:
                _p("PASS", f"市价买成交：price={bp} amount={ba}（来源={bsrc}）")

            # 卖回平掉本次买入，避免在 testnet 留持仓
            sell_amt = float(ex.amount_to_precision(args.symbol, ba or amount))
            sell = broker.place_order(Order(args.symbol, "sell", sell_amt, last, "market"))
            if sell.order_id is None:
                _p("WARN", f"市价卖回失败（testnet 留少量持仓）：{sell.reason}")
            else:
                sp, sa, ssrc = extract_fill(sell, broker.get_order_status(sell.order_id))
                _p("PASS", f"市价卖回成交：price={sp} amount={sa}（来源={ssrc}）")
            _p("INFO", f"Stage 0 结论：市价成交字段来源={bsrc}"
                       f"（'place'=下单即返回成交，Stage 1 无需轮询；"
                       f"'status'=须下单后查单取价）")
        except Exception as e:
            _p("FAIL", f"市价 spike 异常：{type(e).__name__}: {e}")
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
