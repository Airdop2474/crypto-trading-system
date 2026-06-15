#!/usr/bin/env python3
"""
Paper Trading 运行脚本（Phase 4 收尾）

端到端串起：数据加载 → 网格策略 → PaperBroker 模拟成交 → 报告生成。
可复现地模拟一段连续行情下的 Paper Trading，并与回测路径对账。

用法：
    python scripts/run_paper_trading.py

前置：先运行 scripts/generate_oscillating_data.py 生成震荡数据。
"""

import sys
import glob
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution import (
    PaperBroker,
    PaperTradingRunner,
    PaperTradingReportGenerator,
)
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import setup_logger


def load_data() -> pd.DataFrame:
    files = sorted(glob.glob("data/raw/BTC_USDT_4h_osc_*.csv"))
    if not files:
        raise FileNotFoundError(
            "未找到震荡数据，请先运行 scripts/generate_oscillating_data.py"
        )
    df = pd.read_csv(files[-1])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def main() -> int:
    setup_logger(log_level="WARNING")

    print("=" * 60)
    print("Phase 4: Paper Trading Run")
    print("=" * 60)

    df = load_data()
    print(f"\n[1] Data loaded: {len(df)} bars "
          f"({df['timestamp'].min()} → {df['timestamp'].max()})")

    # 策略 + Broker
    lo, hi = df["low"].min(), df["high"].max()
    pr = hi - lo
    lower, upper = lo + pr * 0.1, hi - pr * 0.1
    initial = 10000.0

    strategy = GridTradingStrategy(
        lower_price=lower, upper_price=upper, grid_count=10,
        initial_capital=initial,
    )
    # 网格多档需放开 Broker 仓位上限（默认 60% 会拒部分档位）
    broker = PaperBroker(
        initial, commission=0.001, slippage={"BTC/USDT": 0.0005},
        max_position_per_trade=1.0, max_total_position=1.0,
    )

    print(f"\n[2] Grid: range [{lower:.0f}, {upper:.0f}], 10 grids")
    print("    Broker: PaperBroker, commission 0.1%, slippage 0.05%")

    # 运行
    runner = PaperTradingRunner(broker, "BTC/USDT")
    result = runner.run(df, strategy)

    last_price = df.iloc[-1]["close"]
    stats = result["statistics"]
    print(f"\n[3] Run completed:")
    print(f"    Trades:        {stats['total_trades']}")
    print(f"    Cash:          ${stats['current_balance']:,.2f}")
    print(f"    Open lots:     {len(result['open_lots'])}")
    print(f"    Realized PnL:  ${result['realized_pnl']:,.2f}")
    print(f"    Paused:        {strategy.paused}")

    # 报告
    gen = PaperTradingReportGenerator()
    out = gen.generate(result, {"BTC/USDT": last_price})
    rep = out["report"]
    acc = rep["account"]

    print(f"\n[4] Report:")
    print(f"    Total value:   ${acc['total_value']:,.2f}")
    print(f"    Total return:  {acc['total_return']:.2%}")
    print(f"    Realized:      ${rep['pnl']['realized']:,.2f}")
    print(f"    Unrealized:    ${rep['pnl']['unrealized']:,.2f}")
    print(f"    Total cost:    ${rep['cost_analysis']['total_cost']:,.2f}")
    print(f"    JSON: {out['json_path']}")
    print(f"    MD:   {out['markdown_path']}")

    # 对账检查：已实现 + 未实现 == 总盈亏
    total_gain = acc["total_value"] - initial
    reconciled = abs(
        (rep["pnl"]["realized"] + rep["pnl"]["unrealized"]) - total_gain
    ) < 1e-6
    print(f"\n[5] PnL reconciliation: "
          f"{'PASS' if reconciled else 'FAIL'} "
          f"(realized + unrealized == total gain)")

    print("\n" + "=" * 60)
    print("Paper Trading run completed")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
