"""P1.9 终验：多年训练集 + 真实 OOS 验证

使用 2022+2023 作为训练集，2024 作为 OOS（更严格的"未见过"测试）。
对每个候选策略，分别用默认参数和 P1.9 最优参数跑训练集+OOS。

判定门槛（实战可上线）：
- 训练集 PF > 1.2 且总收益 > 0
- OOS PF > 1.0 且总收益 > 0（不要求 > 训练集，但不能崩盘）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.strategy.pa import FVGPullbackStrategy, MomentumSequenceStrategy

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "Binance"

COMMISSION = 0.001
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 10000.0


def load_years(years: list[int]) -> pd.DataFrame:
    """加载多年 1h 数据并拼接"""
    frames = []
    for y in years:
        path = DATA_DIR / str(y) / "BTCUSDT_1h.csv"
        if not path.exists():
            # fallback to root (2024 is at root)
            path = DATA_DIR / "BTCUSDT_1h.csv"
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["open_time_str"])
            df = df[df["timestamp"].dt.year == y].reset_index(drop=True)
        else:
            df = pd.read_csv(path)
            df["timestamp"] = pd.to_datetime(df["open_time_str"])
        frames.append(df)
    out = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    cols = ["timestamp", "open", "high", "low", "close", "volume", "taker_buy_base_volume"]
    return out[cols].copy()


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

    if not trades:
        return {"total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "total_return": 0.0, "max_drawdown": 0.0}

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / len(trades)
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 1e-9
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    total_return = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL

    equity, peak, max_dd = INITIAL_CAPITAL, INITIAL_CAPITAL, 0.0
    for pnl in trades:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0)

    return {"total_trades": len(trades), "win_rate": win_rate,
            "profit_factor": pf, "total_return": total_return, "max_drawdown": max_dd}


CANDIDATES = {
    "C_FVGPullback": {
        "cls": FVGPullbackStrategy,
        "default": {"max_consecutive_losses": 9999, "max_daily_loss": 1.0},
        "optimized": {
            "max_consecutive_losses": 9999, "max_daily_loss": 1.0,
            "sl_buffer_pct": 0.0076, "min_height_pct": 0.0078,
            "tp_rr": 3.0, "cooldown_bars": 12,
        },
    },
    "F_MomentumSequence": {
        "cls": MomentumSequenceStrategy,
        "default": {"max_consecutive_losses": 9999, "max_daily_loss": 1.0},
        "optimized": {
            "max_consecutive_losses": 9999, "max_daily_loss": 1.0,
            "time_stop_bars": 100, "tp_rr": 2.0, "sl_buffer_pct": 0.0055,
        },
    },
}


def fmt_row(label, m):
    return (f"  {label:<22} 交易 {m['total_trades']:>4}  "
            f"胜率 {m['win_rate']:>5.1%}  PF {m['profit_factor']:>5.2f}  "
            f"收益 {m['total_return']:>+7.2%}  MaxDD {m['max_drawdown']:>5.2%}")


def main():
    print("=" * 78)
    print("P1.9 终验：训练 (2022+2023) + OOS (2024)")
    print("=" * 78)

    train_data = load_years([2022, 2023])
    oos_data = load_years([2024])
    print(f"\n训练: {len(train_data)} bar ({train_data['timestamp'].iloc[0].date()} ~ {train_data['timestamp'].iloc[-1].date()})")
    print(f"OOS:  {len(oos_data)} bar ({oos_data['timestamp'].iloc[0].date()} ~ {oos_data['timestamp'].iloc[-1].date()})\n")

    final = {}

    for name, cfg in CANDIDATES.items():
        print("─" * 78)
        print(name)
        print("─" * 78)

        results = {}
        for label, params in [("default", cfg["default"]), ("optimized", cfg["optimized"])]:
            train_m = fast_backtest(cfg["cls"](**params), train_data)
            oos_m = fast_backtest(cfg["cls"](**params), oos_data)
            print(fmt_row(f"{label}-train", train_m))
            print(fmt_row(f"{label}-oos",   oos_m))
            results[label] = {"train": train_m, "oos": oos_m}
        print()

        # 用 optimized 判定
        opt = results["optimized"]
        train_pass = opt["train"]["profit_factor"] > 1.2 and opt["train"]["total_return"] > 0
        oos_pass = opt["oos"]["profit_factor"] > 1.0 and opt["oos"]["total_return"] > 0
        passed = train_pass and oos_pass
        final[name] = {
            "train": opt["train"], "oos": opt["oos"],
            "train_pass": train_pass, "oos_pass": oos_pass, "passed": passed,
        }

    print("=" * 78)
    print("最终判定（训练 PF>1.2 且收益>0；OOS PF>1.0 且收益>0）")
    print("=" * 78)
    for name, r in final.items():
        train_mark = "✓" if r["train_pass"] else "✗"
        oos_mark = "✓" if r["oos_pass"] else "✗"
        verdict = "✓ 通过" if r["passed"] else "✗ 未通过"
        print(f"\n{name}: {verdict}")
        print(f"  训练 {train_mark}: PF={r['train']['profit_factor']:.2f} 收益={r['train']['total_return']:+.2%}")
        print(f"  OOS  {oos_mark}: PF={r['oos']['profit_factor']:.2f} 收益={r['oos']['total_return']:+.2%}")

    passed_list = [n for n, r in final.items() if r["passed"]]
    print(f"\n→ 通过的策略: {passed_list if passed_list else '无'}")


if __name__ == "__main__":
    main()
