#!/usr/bin/env python3
"""
测试回测引擎 - 带性能指标

测试回测引擎和性能指标计算
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.buy_and_hold import BuyAndHoldStrategy
from src.utils.logger import setup_logger, logger


def test_backtest_with_metrics():
    """测试回测引擎和性能指标"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Backtest Engine with Performance Metrics")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("    ERROR: No data found")
        return 1

    print(f"    Loaded {len(df)} bars")

    # 初始化回测引擎
    print("\n[2] Initializing backtest engine...")
    engine = BacktestEngine(
        initial_capital=10000.0,
        commission=0.001,
        slippage=0.0005,
    )

    # 初始化策略
    print("\n[3] Initializing strategy...")
    strategy = BuyAndHoldStrategy()

    # 运行回测
    print("\n[4] Running backtest...")
    results = engine.run(data=df, strategy=strategy)

    if not results["success"]:
        print(f"    ERROR: {results.get('message')}")
        return 1

    # 显示基本结果
    print("\n[5] Basic Results:")
    print("-" * 60)
    print(f"    Initial Capital: ${results['initial_capital']:.2f}")
    print(f"    Final Equity: ${results['final_equity']:.2f}")
    print(f"    Total Return: {results['total_return']:.2%}")
    print(f"    Total Trades: {results['total_trades']}")

    # 显示性能指标
    if "metrics" in results:
        print("\n[6] Performance Metrics:")
        print("-" * 60)
        metrics = results["metrics"]

        print(f"    Total Return: {metrics['total_return']:.2%}")
        print(f"    Annual Return: {metrics['annual_return']:.2%}")
        print(f"    Max Drawdown: {metrics['max_drawdown']:.2%}")
        print(f"    Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"    Win Rate: {metrics['win_rate']:.2%}")
        print(f"    Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"    Avg Trade: ${metrics['avg_trade']:.2f}")

    # 显示交易详情
    print("\n[7] Trade Summary:")
    print("-" * 60)

    buy_trades = [t for t in results["trades"] if t["type"] == "BUY"]
    sell_trades = [t for t in results["trades"] if t["type"] == "SELL"]

    print(f"    Buy trades: {len(buy_trades)}")
    print(f"    Sell trades: {len(sell_trades)}")

    if sell_trades:
        winning = sum(1 for t in sell_trades if t.get("profit", 0) > 0)
        losing = len(sell_trades) - winning
        print(f"    Winning trades: {winning}")
        print(f"    Losing trades: {losing}")

    # 显示权益曲线统计
    print("\n[8] Equity Curve Statistics:")
    print("-" * 60)

    equity_values = [e["total_equity"] for e in results["equity_curve"]]
    print(f"    Min Equity: ${min(equity_values):.2f}")
    print(f"    Max Equity: ${max(equity_values):.2f}")
    print(f"    Final Equity: ${equity_values[-1]:.2f}")

    # 总结
    print("\n" + "=" * 60)
    print("SUCCESS: Backtest completed with metrics!")
    print("\nNext step:")
    print("  - Create a simple moving average strategy")
    print("  - Test with multiple strategies")
    print("  - Implement bias detection")

    return 0


if __name__ == "__main__":
    sys.exit(test_backtest_with_metrics())
