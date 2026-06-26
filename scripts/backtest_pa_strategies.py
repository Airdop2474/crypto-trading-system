"""P1.8 训练集回测 + 胜率门槛筛选

用 2024 全年 BTCUSDT 1h 数据回测 5 个纯 K 线策略，
按门槛（胜率 > 45% 且 PF > 1.2）筛选进 P1.9。

用法：
    python scripts/backtest_pa_strategies.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import PerformanceMetrics
from src.strategy.pa import (
    StructureSwingStrategy,
    LiquiditySweepStrategy,
    FVGPullbackStrategy,
    MomentumSequenceStrategy,
    EngulfingReversalStrategy,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "Binance" / "BTCUSDT_1h.csv"

STRATEGIES = [
    ("A_StructureSwing", StructureSwingStrategy),
    ("B_LiquiditySweep", LiquiditySweepStrategy),
    ("C_FVGPullback", FVGPullbackStrategy),
    ("F_MomentumSequence", MomentumSequenceStrategy),
    ("G_EngulfingReversal", EngulfingReversalStrategy),
]

WIN_RATE_THRESHOLD = 0.45
PF_THRESHOLD = 1.2


def load_training_data() -> pd.DataFrame:
    """加载 2024 全年 1h 数据（训练集）"""
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["open_time_str"])
    df = df[df["timestamp"].dt.year == 2024].reset_index(drop=True)
    cols = ["timestamp", "open", "high", "low", "close", "volume", "taker_buy_base_volume"]
    return df[cols].copy()


class SlicingAdapter:
    """BacktestEngine 传全量 DF，PA 策略用 data.iloc[-1] 期望切片。此适配器按 bar 序号切片。"""

    def __init__(self, strategy):
        self._strategy = strategy
        self._bar_count = 0

    def __getattr__(self, name):
        return getattr(self._strategy, name)

    def reset(self):
        self._bar_count = 0
        self._strategy.reset()

    def on_bar(self, data: pd.DataFrame, current_time):
        self._bar_count += 1
        sliced = data.iloc[:self._bar_count]
        return self._strategy.on_bar(sliced, current_time)


def run_backtest(strategy_cls, data: pd.DataFrame, disable_breaker=False) -> dict:
    engine = BacktestEngine(initial_capital=10000.0, commission=0.001, slippage=0.0005)
    kwargs = {}
    if disable_breaker:
        kwargs["max_consecutive_losses"] = 9999
        kwargs["max_daily_loss"] = 1.0
    strategy = SlicingAdapter(strategy_cls(**kwargs))
    results = engine.run(data, strategy)
    metrics = PerformanceMetrics.calculate_all(results)
    return metrics


def main():
    print("=" * 70)
    print("P1.8 纯K线策略训练集回测（2024 BTCUSDT 1h）")
    print("=" * 70)

    data = load_training_data()
    print(f"\n数据：{len(data)} 根 bar（{data['timestamp'].iloc[0]} ~ {data['timestamp'].iloc[-1]}）\n")

    results = []
    for name, cls in STRATEGIES:
        print(f"  回测 {name} ...", end=" ", flush=True)
        metrics = run_backtest(cls, data, disable_breaker=True)
        results.append((name, metrics))
        print(f"完成 | 交易 {metrics['total_trades']:.0f} 笔")

    print("\n" + "=" * 70)
    print(f"{'策略':<22} {'交易数':>6} {'胜率':>7} {'PF':>7} {'MaxDD':>8} {'Sharpe':>7} {'总收益%':>8} {'通过'}")
    print("-" * 70)

    passed = []
    for name, m in results:
        wr = m["win_rate"]
        pf = m["profit_factor"]
        ok = wr > WIN_RATE_THRESHOLD and pf > PF_THRESHOLD
        mark = "✓" if ok else "✗"
        if ok:
            passed.append(name)
        print(
            f"{name:<22} {m['total_trades']:>6.0f} {wr:>6.1%} {pf:>7.2f} "
            f"{m['max_drawdown']:>7.2%} {m['sharpe_ratio']:>7.2f} "
            f"{m['total_return']:>7.2%}  {mark}"
        )

    print("-" * 70)
    print(f"\n门槛：胜率 > {WIN_RATE_THRESHOLD:.0%} 且 PF > {PF_THRESHOLD:.1f}")
    print(f"通过：{len(passed)}/{len(STRATEGIES)} — {', '.join(passed) if passed else '无'}")
    print()

    if not passed:
        print("⚠ 所有策略均未达标，需调参或重新审视策略逻辑。")
    else:
        print(f"→ 进入 P1.9 参数敏感性分析：{', '.join(passed)}")


if __name__ == "__main__":
    main()
