#!/usr/bin/env python3
"""
网格参数敏感性扫描脚本

对 GridTradingStrategy 的核心参数进行网格搜索：
- grid_count: [5, 10, 15, 20]
- boundary_offset: [0.10, 0.15, 0.20]（上下界偏移比例）
- position_per_grid: [0.03, 0.05, 0.08, 0.10]

按月度回测（过去 12 个月），输出参数 × 月份收益矩阵。
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from itertools import product

import pandas as pd

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import setup_logger, logger

# ---------------------------------------------------------------------------
# 参数空间
# ---------------------------------------------------------------------------
GRID_COUNTS = [5, 10, 15, 20]
BOUNDARY_OFFSETS = [0.10, 0.15, 0.20]
POSITION_PER_GRID = [0.03, 0.05, 0.08, 0.10]

# 回测基础配置
INITIAL_CAPITAL = 10000.0
COMMISSION = 0.001
SLIPPAGE = 0.0005


def _get_monthly_windows(df: pd.DataFrame, months: int = 12) -> list[tuple[str, pd.DataFrame]]:
    """将 DataFrame 按自然月切片为窗口列表。

    返回：[(label, window_df), ...] 按时间升序排列。
    """
    if df.empty:
        return []

    ts = pd.to_datetime(df["timestamp"])
    start = ts.dt.to_period("M").min()
    end = ts.dt.to_period("M").max()

    windows = []
    cursor = end
    for _ in range(months):
        month_str = str(cursor)
        mask = ts.dt.to_period("M") == cursor
        window = df.loc[mask].copy()
        if not window.empty:
            windows.append((month_str, window.reset_index(drop=True)))
        cursor = cursor - 1
        if cursor < start:
            break

    windows.reverse()
    return windows


def _boundary_params(mid_price: float, offset: float) -> tuple[float, float]:
    """根据中间价和偏移比例计算网格上下界。

    上界 = mid * (1 + offset)，下界 = mid * (1 - offset)
    """
    return (
        round(mid_price * (1 - offset), 2),
        round(mid_price * (1 + offset), 2),
    )


def _run_single(
    data: pd.DataFrame,
    grid_count: int,
    boundary_offset: float,
    pos_per_grid: float,
) -> dict | None:
    """执行单次回测，返回指标字典或 None（数据不足）。"""
    if len(data) < 2:
        return None

    mid_price = float(data["close"].mean())
    lower, upper = _boundary_params(mid_price, boundary_offset)

    try:
        strategy = GridTradingStrategy(
            lower_price=lower,
            upper_price=upper,
            grid_count=grid_count,
            position_per_grid=pos_per_grid,
            enable_filters=False,
            initial_capital=INITIAL_CAPITAL,
        )
    except (ValueError, TypeError):
        return None

    engine = BacktestEngine(
        initial_capital=INITIAL_CAPITAL,
        commission=COMMISSION,
        slippage=SLIPPAGE,
    )
    results = engine.run(data=data, strategy=strategy)

    if not results.get("success"):
        return None

    metrics = results.get("metrics", {})
    return {
        "total_return": results.get("total_return", 0.0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
        "max_drawdown": metrics.get("max_drawdown", 0.0),
        "win_rate": metrics.get("win_rate", 0.0),
        "total_trades": metrics.get("total_trades", 0),
    }


def _print_matrix(
    months: list[str],
    combos: list[dict],
    matrix: dict[str, list[float | None]],
) -> None:
    """打印参数 × 月份收益矩阵。"""
    # ---- 汇总行 ----
    print()
    print("=" * 100)
    print("Grid Parameter Sweep — Return Matrix (parameter × month)")
    print("=" * 100)

    header = f"{'grid/boundary/pos%':<30}"
    for m in months:
        header += f" {m:>10}"
    header += f" {'AVG':>10}"
    print(header)
    print("-" * 100)

    for label, returns in matrix.items():
        # 计算有效月份的平均
        valid = [r for r in returns if r is not None]
        avg = sum(valid) / len(valid) if valid else float("nan")

        row = f"  {label:<28}"
        for r in returns:
            if r is None:
                row += f" {'N/A':>10}"
            else:
                row += f" {r:>10.2%}"
        if valid:
            row += f" {avg:>10.2%}"
        else:
            row += f" {'N/A':>10}"
        print(row)

    print("-" * 100)

    # ---- 最佳组合 ----
    print("\nTop 5 by Average Return:")
    print("-" * 60)
    rankings = []
    for label, returns in matrix.items():
        valid = [r for r in returns if r is not None]
        if valid:
            rankings.append((label, sum(valid) / len(valid), len(valid)))
    rankings.sort(key=lambda x: -x[1])
    for rank, (label, avg, n) in enumerate(rankings[:5], 1):
        print(f"  #{rank}  {label:<30} avg={avg:.2%}  ({n}/{len(months)} months)")


def main() -> int:
    """主入口。"""
    setup_logger(log_level="WARNING")

    print("=" * 60)
    print("Grid Parameter Sweep")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1] Loading BTC/USDT 4h data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("    No local data found. Generating mock data...")
        from scripts.generate_mock_data import main as gen_mock
        gen_mock()
        df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("    ERROR: Failed to load or generate data")
        return 1

    print(f"    Loaded {len(df)} bars, {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    # 2. 按月度切片
    print("\n[2] Slicing into monthly windows...")
    windows = _get_monthly_windows(df, months=12)
    months = [w[0] for w in windows]
    print(f"    {len(windows)} month(s) available: {', '.join(months)}")

    if not windows:
        print("    ERROR: No monthly windows found")
        return 1

    # 3. 参数空间
    print(f"\n[3] Parameter space:")
    print(f"    grid_count:       {GRID_COUNTS}")
    print(f"    boundary_offset:  {BOUNDARY_OFFSETS}")
    print(f"    position_per_grid:{POSITION_PER_GRID}")
    total = len(GRID_COUNTS) * len(BOUNDARY_OFFSETS) * len(POSITION_PER_GRID)
    print(f"    Total combos: {total} × {len(windows)} months = {total * len(windows)} runs")

    # 4. 运行扫描
    print(f"\n[4] Running sweep...")

    param_space = list(product(GRID_COUNTS, BOUNDARY_OFFSETS, POSITION_PER_GRID))
    matrix: dict[str, list[float | None]] = {}
    combos: list[dict] = []

    for gc, bo, ppg in param_space:
        label = f"{gc:>3}/{bo:.2f}/{ppg:.2f}"
        returns: list[float | None] = []

        for month_label, window_df in windows:
            mid = float(window_df["close"].mean())
            lower, upper = _boundary_params(mid, bo)
            res = _run_single(window_df, gc, bo, ppg)
            returns.append(res["total_return"] if res else None)

        matrix[label] = returns
        combos.append({"grid_count": gc, "boundary_offset": bo, "pos_per_grid": ppg})
        valid = sum(1 for r in returns if r is not None)
        print(f"    [{label}] {valid}/{len(months)} months completed")

    # 5. 打印矩阵
    print("\n[5] Results:")
    _print_matrix(months, combos, matrix)

    print("\n" + "=" * 60)
    print("Sweep complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
