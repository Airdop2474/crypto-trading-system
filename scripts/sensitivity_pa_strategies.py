"""P1.9 参数敏感性分析

对 P1.8 筛选通过的策略，逐参数扰动回测，找出敏感参数和稳健参数。
使用轻量回测循环（非 BacktestEngine）以支持大量参数组合。

用法：
    python scripts/sensitivity_pa_strategies.py
"""

import sys
from pathlib import Path
from itertools import product
from typing import Dict, List, Tuple, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.strategy.pa import (
    StructureSwingStrategy,
    LiquiditySweepStrategy,
    FVGPullbackStrategy,
    MomentumSequenceStrategy,
    EngulfingReversalStrategy,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "Binance" / "BTCUSDT_1h.csv"

COMMISSION = 0.001
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 10000.0

STRATEGIES = {
    "A_StructureSwing": StructureSwingStrategy,
    "B_LiquiditySweep": LiquiditySweepStrategy,
    "C_FVGPullback": FVGPullbackStrategy,
    "F_MomentumSequence": MomentumSequenceStrategy,
    "G_EngulfingReversal": EngulfingReversalStrategy,
}

# 每个参数取 5 个等距点（含 default、min、max 和两个中间值）
N_POINTS = 5


def load_training_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["open_time_str"])
    df = df[df["timestamp"].dt.year == 2024].reset_index(drop=True)
    cols = ["timestamp", "open", "high", "low", "close", "volume", "taker_buy_base_volume"]
    return df[cols].copy()


def fast_backtest(strategy, data: pd.DataFrame) -> Dict[str, float]:
    """轻量回测：bar-by-bar 切片 + t+1 开盘成交。返回核心指标。"""
    cash = INITIAL_CAPITAL
    position = 0.0
    entry_price = 0.0
    trades: List[float] = []  # 每笔盈亏

    n = len(data)
    for i in range(n):
        sliced = data.iloc[: i + 1]
        current_time = data.iloc[i]["timestamp"]
        signal = strategy.on_bar(sliced, current_time)

        if signal and i < n - 1:
            next_open = float(data.iloc[i + 1]["open"])

            if signal == "BUY" and position == 0:
                exec_price = next_open * (1 + SLIPPAGE)
                cost_per_unit = exec_price * (1 + COMMISSION)
                position = cash / cost_per_unit
                entry_price = exec_price
                cash = 0.0

            elif signal in ("SELL", "LIQUIDATE") and position > 0:
                exec_price = next_open * (1 - SLIPPAGE)
                proceeds = position * exec_price * (1 - COMMISSION)
                pnl = proceeds - position * entry_price * (1 + COMMISSION)
                trades.append(pnl)
                cash = proceeds
                position = 0.0

    # 强制平仓（如果还持仓）
    if position > 0:
        last_close = float(data.iloc[-1]["close"])
        exec_price = last_close * (1 - SLIPPAGE)
        proceeds = position * exec_price * (1 - COMMISSION)
        pnl = proceeds - position * entry_price * (1 + COMMISSION)
        trades.append(pnl)
        cash = proceeds
        position = 0.0

    total_trades = len(trades)
    if total_trades == 0:
        return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "total_return": 0.0, "max_drawdown": 0.0}

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / total_trades
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1e-9
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    total_return = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL

    # Max drawdown from trade-level equity
    equity = INITIAL_CAPITAL
    peak = equity
    max_dd = 0.0
    for pnl in trades:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_return": total_return,
        "max_drawdown": max_dd,
    }


def generate_param_values(schema: dict, param_name: str) -> List[Any]:
    """从 PARAM_SCHEMA 生成 N_POINTS 个测试值"""
    spec = schema[param_name]
    lo, hi, default = spec["min"], spec["max"], spec["default"]
    if spec["type"] == int:
        values = sorted(set([int(round(v)) for v in np.linspace(lo, hi, N_POINTS)]))
        if default not in values:
            values.append(default)
            values.sort()
    else:
        values = list(np.linspace(lo, hi, N_POINTS))
        if default not in values:
            values.append(default)
            values.sort()
    return values


def run_sensitivity(strategy_name: str, strategy_cls, data: pd.DataFrame):
    """对单策略做逐参数扰动，打印敏感性表"""
    schema = strategy_cls.PARAM_SCHEMA
    defaults = {k: v["default"] for k, v in schema.items()}

    print(f"\n{'=' * 70}")
    print(f"  {strategy_name} 参数敏感性")
    print(f"{'=' * 70}")

    # Baseline
    strategy = strategy_cls(**defaults)
    baseline = fast_backtest(strategy, data)
    print(f"  Baseline: 交易 {baseline['total_trades']}, 胜率 {baseline['win_rate']:.1%}, "
          f"PF {baseline['profit_factor']:.2f}, 收益 {baseline['total_return']:.2%}")

    sensitivity_scores = {}

    for param_name in schema:
        values = generate_param_values(schema, param_name)
        print(f"\n  {param_name} ({len(values)} 值: {values[0]}..{values[-1]}, 默认={defaults[param_name]})")
        print(f"    {'值':<12} {'交易':>5} {'胜率':>7} {'PF':>7} {'收益%':>8} {'MaxDD':>7}")
        print(f"    {'-' * 50}")

        results = []
        for val in values:
            params = {**defaults, param_name: val}
            try:
                strategy = strategy_cls(**params)
                m = fast_backtest(strategy, data)
            except Exception:
                m = {"total_trades": 0, "win_rate": 0, "profit_factor": 0,
                     "total_return": 0, "max_drawdown": 0}
            results.append(m)
            marker = " *" if val == defaults[param_name] else ""
            print(f"    {str(val):<12} {m['total_trades']:>5} {m['win_rate']:>6.1%} "
                  f"{m['profit_factor']:>7.2f} {m['total_return']:>7.2%} {m['max_drawdown']:>6.2%}{marker}")

        # 敏感性分数 = PF 的变异系数
        pfs = [r["profit_factor"] for r in results if r["total_trades"] > 0]
        if len(pfs) >= 2:
            mean_pf = np.mean(pfs)
            std_pf = np.std(pfs)
            cv = std_pf / mean_pf if mean_pf > 0 else 0
            sensitivity_scores[param_name] = cv
        else:
            sensitivity_scores[param_name] = 0.0

    # 敏感性排名
    print(f"\n  敏感性排名（PF 变异系数，越高越敏感）:")
    for param, score in sorted(sensitivity_scores.items(), key=lambda x: -x[1]):
        bar = "█" * int(score * 20)
        label = "⚠ 敏感" if score > 0.3 else "✓ 稳健" if score < 0.1 else "~ 适中"
        print(f"    {param:<24} CV={score:.3f} {bar} {label}")


def main():
    # P1.8 筛选结果：C 和 F 边缘过关（接近盈亏平衡、有调参空间），A/B/G 淘汰
    strategies_to_analyze = [
        "C_FVGPullback",
        "F_MomentumSequence",
    ]

    print("=" * 70)
    print("P1.9 参数敏感性分析（2024 BTCUSDT 1h 训练集）")
    print("=" * 70)

    data = load_training_data()
    print(f"数据：{len(data)} 根 bar\n")

    for name in strategies_to_analyze:
        if name not in STRATEGIES:
            print(f"  跳过未知策略：{name}")
            continue
        run_sensitivity(name, STRATEGIES[name], data)

    print("\n" + "=" * 70)
    print("分析完成。稳健参数可保持默认，敏感参数需进一步验证或收紧范围。")
    print("=" * 70)


if __name__ == "__main__":
    main()
