#!/usr/bin/env python3
"""
对比测试多个策略

测试买入持有 vs 简单移动平均策略
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.buy_and_hold import BuyAndHoldStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.utils.logger import setup_logger, logger


def test_strategy(name: str, strategy, data, initial_capital=10000.0):
    """测试单个策略"""
    print(f"\n{'=' * 60}")
    print(f"Testing: {name}")
    print('=' * 60)

    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission=0.001,
        slippage=0.0005,
    )

    results = engine.run(data=data, strategy=strategy)

    if not results["success"]:
        print(f"ERROR: {results.get('message')}")
        return None

    # 显示结果
    print(f"\nBasic Results:")
    print(f"  Initial Capital: ${results['initial_capital']:.2f}")
    print(f"  Final Equity: ${results['final_equity']:.2f}")
    print(f"  Total Return: {results['total_return']:.2%}")
    print(f"  Total Trades: {results['total_trades']}")

    if "metrics" in results:
        metrics = results["metrics"]
        print(f"\nPerformance Metrics:")
        print(f"  Annual Return: {metrics['annual_return']:.2%}")
        print(f"  Max Drawdown: {metrics['max_drawdown']:.2%}")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Win Rate: {metrics['win_rate']:.2%}")
        print(f"  Profit Factor: {metrics['profit_factor']:.2f}")

    # 交易详情
    buy_trades = sum(1 for t in results["trades"] if t["type"] == "BUY")
    sell_trades = sum(1 for t in results["trades"] if t["type"] == "SELL")
    print(f"\nTrade Summary:")
    print(f"  Buy: {buy_trades}, Sell: {sell_trades}")

    return results


def compare_strategies():
    """对比策略"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Strategy Comparison Test")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("ERROR: No data found")
        return 1

    print(f"Loaded {len(df)} bars")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    initial_capital = 10000.0

    # 策略列表
    strategies = [
        ("Buy and Hold", BuyAndHoldStrategy()),
        ("Simple MA (5, 10)", SimpleMAStrategy(short_window=5, long_window=10)),
        ("Simple MA (3, 7)", SimpleMAStrategy(short_window=3, long_window=7)),
    ]

    # 测试每个策略
    all_results = []
    for name, strategy in strategies:
        results = test_strategy(name, strategy, df, initial_capital)
        if results:
            all_results.append((name, results))

    # 对比总结
    print(f"\n{'=' * 60}")
    print("Comparison Summary")
    print('=' * 60)
    print(f"\n{'Strategy':<25} {'Return':<12} {'Max DD':<12} {'Sharpe':<10} {'Trades'}")
    print('-' * 60)

    for name, results in all_results:
        metrics = results.get("metrics", {})
        print(
            f"{name:<25} "
            f"{results['total_return']:>10.2%}  "
            f"{metrics.get('max_drawdown', 0):>10.2%}  "
            f"{metrics.get('sharpe_ratio', 0):>8.2f}  "
            f"{results['total_trades']:>6}"
        )

    # 找出最佳策略
    print(f"\n{'=' * 60}")
    print("Best Strategy by Metric:")
    print('=' * 60)

    best_return = max(all_results, key=lambda x: x[1]['total_return'])
    print(f"  Best Return: {best_return[0]} ({best_return[1]['total_return']:.2%})")

    best_sharpe = max(all_results, key=lambda x: x[1].get('metrics', {}).get('sharpe_ratio', -999))
    print(f"  Best Sharpe: {best_sharpe[0]} ({best_sharpe[1]['metrics']['sharpe_ratio']:.2f})")

    print("\n" + "=" * 60)
    print("SUCCESS: Strategy comparison completed!")
    print("\nNext step:")
    print("  - Implement bias detection")
    print("  - Test parameter sensitivity")
    print("  - Generate backtest reports")

    return 0


if __name__ == "__main__":
    sys.exit(compare_strategies())
