#!/usr/bin/env python3
"""
多策略并行回测入口脚本

用法：
    python scripts/run_multi.py --strategies grid,rsi
    python scripts/run_multi.py --strategies grid,rsi,ma,buyhold
    python scripts/run_multi.py --strategies grid,rsi --symbol BTC/USDT --capital 20000

输出：
    对比表（收益率/夏普/最大回撤/胜率）+ 策略相关性矩阵
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.registry import get_strategy, list_strategies
from src.execution.multi_runner import MultiStrategyRunner
from src.utils.logger import setup_logger, logger
from src.execution.paper_trading_runner import ExecutionConfig
from src.execution.paper_broker import PaperBroker

# ---------------------------------------------------------------------------
# 策略工厂（默认参数 + 自动边界推算）
# ---------------------------------------------------------------------------
STRATEGY_FACTORY = {
    "grid": lambda df: get_strategy("grid")(
        lower_price=round(float(df["close"].mean()) * 0.85, 2),
        upper_price=round(float(df["close"].mean()) * 1.15, 2),
        grid_count=10,
        max_consecutive_losses=3,
        initial_capital=10000.0,
    ),
    "rsi": lambda df: get_strategy("rsi")(
        rsi_period=14,
        oversold=30.0,
        overbought=70.0,
        ema_period=50,
    ),
    "ma": lambda df: get_strategy("ma")(
        short_window=5,
        long_window=20,
    ),
    "buyhold": lambda df: get_strategy("buyhold")(),
    "donchian": lambda df: get_strategy("donchian")(
        period=20,
        max_consecutive_losses=3,
        max_daily_loss=0.02,
        initial_capital=10000.0,
    ),
    "structure": lambda df: get_strategy("structure")(
        lookback=10,
        max_consecutive_losses=3,
        max_daily_loss=0.02,
        initial_capital=10000.0,
    ),
    "supertrend": lambda df: get_strategy("supertrend")(
        period=10,
        multiplier=3.0,
        max_consecutive_losses=3,
        max_daily_loss=0.02,
        initial_capital=10000.0,
    ),
    "reversal": lambda df: get_strategy("reversal")(
        lookback=50,
        pin_threshold=2.0,
        stop_atr_mult=2.0,
        atr_period=14,
        max_consecutive_losses=3,
        max_daily_loss=0.02,
        initial_capital=10000.0,
    ),
}


def _extract_equity_curves(all_results: dict) -> dict[str, pd.Series]:
    """从 BacktestEngine 结果中提取权益曲线为 Series。

    返回：
        {strategy_id: equity_series}
    """
    curves = {}
    for sid, res in all_results.items():
        ec = res.get("equity_curve", [])
        if ec:
            curves[sid] = pd.Series(
                [e["total_equity"] for e in ec],
                name=sid,
            )
    return curves


def _calc_correlation(equity_curves: dict[str, pd.Series]) -> str:
    """计算并格式化策略相关性矩阵。"""
    if len(equity_curves) < 2:
        return "Need at least 2 strategies for correlation."

    ids = sorted(equity_curves.keys())
    df_eq = pd.DataFrame({sid: equity_curves[sid] for sid in ids})
    returns = df_eq.pct_change().dropna()
    corr = returns.corr()

    lines = [f"\n  Strategy Correlation Matrix (daily return)",
             f"  {'-' * 50}"]
    header = "  " + "".join(f"{sid:>10}" for sid in ids)
    lines.append(header)
    for sid_i in ids:
        row = "".join(f"{corr.loc[sid_i, sid_j]:>10.3f}" for sid_j in ids)
        lines.append(f"  {sid_i:<8}{row}")

    return "\n".join(lines)


def main() -> int:
    """主入口。"""
    parser = argparse.ArgumentParser(
        description="Multi-strategy parallel backtest with comparison table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available strategies: {', '.join(list_strategies())}",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default="grid,rsi",
        help="Comma-separated strategy names (default: grid,rsi)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair (default: BTC/USDT)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="4h",
        help="Timeframe (default: 4h)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital per strategy (default: 10000.0)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.001,
        help="Commission rate (default: 0.001)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0005,
        help="Slippage rate (default: 0.0005)",
    )
    parser.add_argument(
        "--shared-capital",
        action="store_true",
        help="Use shared capital pool (default: isolated)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: WARNING)",
    )

    args = parser.parse_args()
    strategy_names = [s.strip() for s in args.strategies.split(",")]

    # 验证策略名
    available = list_strategies()
    for name in strategy_names:
        if name not in available:
            print(f"ERROR: Unknown strategy '{name}'. Available: {available}")
            return 1

    setup_logger(log_level=args.log_level)

    print("=" * 80)
    print(f"Multi-Strategy Backtest: {', '.join(strategy_names)} on {args.symbol}")
    print("=" * 80)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol=args.symbol, timeframe=args.timeframe)

    if df.empty:
        print(f"    No data found. Generating mock...")
        from scripts.generate_mock_data import main as gen_mock
        gen_mock()
        df = downloader.load_data(symbol=args.symbol, timeframe=args.timeframe)

    if df.empty:
        print("    ERROR: Failed to load data")
        return 1

    print(f"    Loaded {len(df)} bars, {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    # 运行每个策略的回测
    print(f"\n[2] Running {len(strategy_names)} strategy(s) with "
          f"{'shared' if args.shared_capital else 'isolated'} capital...")

    all_results = {}
    equity_curves = {}

    for name in strategy_names:
        print(f"    Running: {name}...")

        factory = STRATEGY_FACTORY.get(name)
        if factory is None:
            print(f"    SKIP: No factory for '{name}'")
            continue

        strategy = factory(df)

        engine = BacktestEngine(
            initial_capital=args.capital,
            commission=args.commission,
            slippage=args.slippage,
        )
        results = engine.run(data=df, strategy=strategy)

        if results.get("success"):
            all_results[name] = results
            ec = results.get("equity_curve", [])
            if ec:
                equity_curves[name] = pd.Series(
                    [e["total_equity"] for e in ec],
                    name=name,
                )
            print(f"         return={results['total_return']:.2%}, "
                  f"trades={results['total_trades']}")
        else:
            print(f"         FAILED: {results.get('message', 'Unknown')}")

    if not all_results:
        print("\nERROR: All strategies failed")
        return 1

    # 对比表
    print(f"\n[3] Comparison Table:")
    table = MultiStrategyRunner.comparison_table_backtest(all_results)
    print(table)

    # 相关性矩阵
    if len(all_results) >= 2:
        print(f"\n[4] Correlation Matrix:")
        corr_table = _calc_correlation(equity_curves)
        print(corr_table)

    # 最佳策略
    best = max(all_results.items(), key=lambda x: x[1].get("total_return", -999))
    best_sharpe = max(all_results.items(),
                      key=lambda x: x[1].get("metrics", {}).get("sharpe_ratio", -999))
    best_dd = min(all_results.items(),
                  key=lambda x: x[1].get("metrics", {}).get("max_drawdown", 999))

    print(f"\n[5] Summary:")
    print(f"    Best Return:  {best[0]} ({best[1]['total_return']:.2%})")
    print(f"    Best Sharpe:  {best_sharpe[0]} "
          f"({best_sharpe[1]['metrics']['sharpe_ratio']:.2f})")
    print(f"    Lowest MaxDD: {best_dd[0]} "
          f"({best_dd[1]['metrics']['max_drawdown']:.2%})")

    print("\n" + "=" * 80)
    print("Multi-strategy backtest complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
