#!/usr/bin/env python3
"""
测试网格交易策略

测试网格策略的基本功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.grid_trading import GridTradingStrategy
from src.utils.logger import setup_logger, logger


def test_grid_strategy():
    """测试网格策略"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Grid Trading Strategy Test")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("ERROR: No data found")
        return 1

    print(f"Loaded {len(df)} bars")

    # 分析价格范围
    print("\n[2] Analyzing price range...")
    min_price = df["low"].min()
    max_price = df["high"].max()
    mean_price = df["close"].mean()

    print(f"Price range: ${min_price:.2f} - ${max_price:.2f}")
    print(f"Mean price: ${mean_price:.2f}")

    # 设置网格参数
    print("\n[3] Setting up grid parameters...")

    # 使用价格范围的 80% 作为网格区间
    price_range = max_price - min_price
    lower_price = min_price + price_range * 0.1
    upper_price = max_price - price_range * 0.1

    print(f"Grid range: ${lower_price:.2f} - ${upper_price:.2f}")

    # 测试不同的网格数量
    grid_counts = [5, 10, 15]

    all_results = []

    for grid_count in grid_counts:
        print(f"\n{'=' * 60}")
        print(f"Testing with {grid_count} grids")
        print('=' * 60)

        # 创建策略
        strategy = GridTradingStrategy(
            lower_price=lower_price,
            upper_price=upper_price,
            grid_count=grid_count,
        )

        print(f"\nGrid spacing: ${strategy.grid_spacing:.2f}")
        print(f"Grid lines: {len(strategy.grids)}")

        # 运行回测
        engine = BacktestEngine(
            initial_capital=10000.0,
            commission=0.001,
            slippage=0.0005,
        )

        results = engine.run(data=df, strategy=strategy)

        if not results["success"]:
            print(f"ERROR: {results.get('message')}")
            continue

        # 显示结果
        print(f"\n[Results]")
        print(f"  Initial Capital: ${results['initial_capital']:.2f}")
        print(f"  Final Equity: ${results['final_equity']:.2f}")
        print(f"  Total Return: {results['total_return']:.2%}")
        print(f"  Total Trades: {results['total_trades']}")

        if "metrics" in results:
            metrics = results["metrics"]
            print(f"\n[Metrics]")
            print(f"  Annual Return: {metrics['annual_return']:.2%}")
            print(f"  Max Drawdown: {metrics['max_drawdown']:.2%}")
            print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
            print(f"  Win Rate: {metrics['win_rate']:.2%}")
            print(f"  Profit Factor: {metrics['profit_factor']:.2f}")

        # 交易统计
        buy_trades = sum(1 for t in results["trades"] if t["type"] == "BUY")
        sell_trades = sum(1 for t in results["trades"] if t["type"] == "SELL")

        print(f"\n[Trades]")
        print(f"  Buy: {buy_trades}")
        print(f"  Sell: {sell_trades}")

        if sell_trades > 0:
            profits = [t.get("profit", 0) for t in results["trades"] if t["type"] == "SELL"]
            winning = sum(1 for p in profits if p > 0)
            losing = sum(1 for p in profits if p < 0)

            print(f"  Winning: {winning}")
            print(f"  Losing: {losing}")

            if profits:
                print(f"  Avg Profit: ${sum(profits)/len(profits):.2f}")
                print(f"  Total Profit: ${sum(profits):.2f}")

        all_results.append((grid_count, results))

    # 对比总结
    print(f"\n{'=' * 60}")
    print("Comparison Summary")
    print('=' * 60)

    print(f"\n{'Grid Count':<12} {'Return':<12} {'Max DD':<12} {'Trades':<10} {'Win Rate'}")
    print('-' * 60)

    for grid_count, results in all_results:
        metrics = results.get("metrics", {})
        print(
            f"{grid_count:<12} "
            f"{results['total_return']:>10.2%}  "
            f"{metrics.get('max_drawdown', 0):>10.2%}  "
            f"{results['total_trades']:>8}  "
            f"{metrics.get('win_rate', 0):>8.2%}"
        )

    # 最佳配置
    if all_results:
        print(f"\n{'=' * 60}")
        print("Best Configuration")
        print('=' * 60)

        best = max(all_results, key=lambda x: x[1]['total_return'])
        print(f"\nBest by Return: {best[0]} grids")
        print(f"  Return: {best[1]['total_return']:.2%}")
        print(f"  Trades: {best[1]['total_trades']}")

    print("\n" + "=" * 60)
    print("SUCCESS: Grid strategy test completed!")
    print("\nNext step:")
    print("  - Test with different market conditions")
    print("  - Optimize parameters")
    print("  - Risk assessment")

    return 0


if __name__ == "__main__":
    sys.exit(test_grid_strategy())
