"""P1.9 收尾：最优参数组合 + 训练集/OOS 验证

基于 sensitivity 单参数最佳值组合，验证 C 和 F 策略是否真有 edge。
训练集：2024 全年（已用于参数搜索）
OOS：2026-01 至 2026-06（从未触碰过的样本外）

用法：
    python scripts/validate_pa_optimized.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.strategy.pa import FVGPullbackStrategy, MomentumSequenceStrategy

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "Binance" / "BTCUSDT_1h.csv"
COMMISSION = 0.001
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 10000.0


def load_period(year_or_range: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["open_time_str"])
    if year_or_range == "train_2024":
        df = df[df["timestamp"].dt.year == 2024]
    elif year_or_range == "oos_2026h1":
        df = df[(df["timestamp"] >= "2026-01-01") & (df["timestamp"] < "2026-07-01")]
    cols = ["timestamp", "open", "high", "low", "close", "volume", "taker_buy_base_volume"]
    return df[cols].reset_index(drop=True)


def fast_backtest(strategy, data: pd.DataFrame) -> dict:
    cash = INITIAL_CAPITAL
    position = 0.0
    entry_price = 0.0
    trades = []
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

    if position > 0:
        last_close = float(data.iloc[-1]["close"])
        exec_price = last_close * (1 - SLIPPAGE)
        proceeds = position * exec_price * (1 - COMMISSION)
        pnl = proceeds - position * entry_price * (1 + COMMISSION)
        trades.append(pnl)
        cash = proceeds

    n_trades = len(trades)
    if n_trades == 0:
        return {"trades": 0, "wr": 0, "pf": 0, "ret": 0, "dd": 0}

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    wr = len(wins) / n_trades
    gp = sum(wins) if wins else 0
    gl = abs(sum(losses)) if losses else 1e-9
    pf = gp / gl if gl > 0 else float("inf")
    ret = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL

    equity = INITIAL_CAPITAL
    peak = equity
    max_dd = 0
    for pnl in trades:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0)

    return {"trades": n_trades, "wr": wr, "pf": pf, "ret": ret, "dd": max_dd}


def print_row(label: str, m: dict):
    print(f"  {label:<24} 交易 {m['trades']:>4}  胜率 {m['wr']:>5.1%}  "
          f"PF {m['pf']:>5.2f}  收益 {m['ret']:>+7.2%}  MaxDD {m['dd']:>6.2%}")


def main():
    print("=" * 78)
    print("P1.9 收尾：最优参数组合 + 训练集/OOS 验证")
    print("=" * 78)

    train = load_period("train_2024")
    oos = load_period("oos_2026h1")
    print(f"\n训练集 (2024)：{len(train)} bar | OOS (2026 H1)：{len(oos)} bar\n")

    # ===== C_FVGPullback =====
    print("─" * 78)
    print("C_FVGPullback")
    print("─" * 78)

    c_default = {}
    c_optimized = {
        "sl_buffer_pct": 0.0076,
        "min_height_pct": 0.0078,
        "tp_rr": 3.0,
        "max_consecutive_losses": 9999,
        "max_daily_loss": 1.0,
    }

    print("默认参数 (训练):")
    m = fast_backtest(FVGPullbackStrategy(max_consecutive_losses=9999, max_daily_loss=1.0), train)
    print_row("baseline-train", m)

    print("优化参数 (训练):")
    m = fast_backtest(FVGPullbackStrategy(**c_optimized), train)
    print_row("optimized-train", m)
    c_train = m

    print("默认参数 (OOS):")
    m = fast_backtest(FVGPullbackStrategy(max_consecutive_losses=9999, max_daily_loss=1.0), oos)
    print_row("baseline-oos", m)

    print("优化参数 (OOS):")
    m = fast_backtest(FVGPullbackStrategy(**c_optimized), oos)
    print_row("optimized-oos", m)
    c_oos = m
    print()

    # ===== F_MomentumSequence =====
    print("─" * 78)
    print("F_MomentumSequence")
    print("─" * 78)

    f_optimized = {
        "time_stop_bars": 100,
        "tp_rr": 2.0,
        "sl_buffer_pct": 0.01,
        "max_consecutive_losses": 9999,
        "max_daily_loss": 1.0,
    }

    print("默认参数 (训练):")
    m = fast_backtest(MomentumSequenceStrategy(max_consecutive_losses=9999, max_daily_loss=1.0), train)
    print_row("baseline-train", m)

    print("优化参数 (训练):")
    m = fast_backtest(MomentumSequenceStrategy(**f_optimized), train)
    print_row("optimized-train", m)
    f_train = m

    print("默认参数 (OOS):")
    m = fast_backtest(MomentumSequenceStrategy(max_consecutive_losses=9999, max_daily_loss=1.0), oos)
    print_row("baseline-oos", m)

    print("优化参数 (OOS):")
    m = fast_backtest(MomentumSequenceStrategy(**f_optimized), oos)
    print_row("optimized-oos", m)
    f_oos = m
    print()

    # ===== 判定 =====
    print("=" * 78)
    print("最终判定（门槛 PF > 1.2 且 OOS 收益 > 0）")
    print("=" * 78)
    print(f"\nC_FVGPullback:")
    print(f"  训练 PF={c_train['pf']:.2f}, OOS PF={c_oos['pf']:.2f}, OOS 收益={c_oos['ret']:+.2%}")
    c_pass = c_train["pf"] > 1.2 and c_oos["pf"] > 1.0 and c_oos["ret"] > 0
    print(f"  → {'✓ 通过，有 edge' if c_pass else '✗ 边缘/未通过'}")

    print(f"\nF_MomentumSequence:")
    print(f"  训练 PF={f_train['pf']:.2f}, OOS PF={f_oos['pf']:.2f}, OOS 收益={f_oos['ret']:+.2%}")
    f_pass = f_train["pf"] > 1.2 and f_oos["pf"] > 1.0 and f_oos["ret"] > 0
    print(f"  → {'✓ 通过，有 edge' if f_pass else '✗ 边缘/未通过'}")

    print()


if __name__ == "__main__":
    main()
