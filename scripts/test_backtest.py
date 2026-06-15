#!/usr/bin/env python3
"""
测试回测引擎

使用买入持有策略验证回测引擎
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


def test_backtest_engine():
    """测试回测引擎"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Backtest Engine Test")
    print("=" * 60)

    # 步骤 1：加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("    ERROR: No data found")
        print("    Run: python scripts/generate_mock_data.py")
        return 1

    print(f"    Loaded {len(df)} bars")
    print(f"    Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"    Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")

    # 步骤 2：初始化回测引擎
    print("\n[2] Initializing backtest engine...")
    initial_capital = 10000.0
    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission=0.001,  # 0.1%
        slippage=0.0005,   # 0.05%
    )
    print(f"    Initial capital: ${initial_capital:.2f}")
    print(f"    Commission: 0.1%")
    print(f"    Slippage: 0.05%")

    # 步骤 3：初始化策略
    print("\n[3] Initializing strategy...")
    strategy = BuyAndHoldStrategy()
    print(f"    Strategy: {strategy.name}")

    # 步骤 4：运行回测
    print("\n[4] Running backtest...")
    results = engine.run(data=df, strategy=strategy)

    if not results["success"]:
        print(f"    ERROR: {results.get('message', 'Unknown error')}")
        return 1

    # 步骤 5：显示结果
    print("\n[5] Backtest Results:")
    print("-" * 60)

    print(f"    Initial Capital: ${results['initial_capital']:.2f}")
    print(f"    Final Equity: ${results['final_equity']:.2f}")
    print(f"    Total Return: {results['total_return']:.2%}")
    print(f"    Total Trades: {results['total_trades']}")

    # 步骤 6：验证结果
    print("\n[6] Validation:")
    print("-" * 60)

    # 计算预期收益
    first_price = df.iloc[0]["open"]  # 第一根 K 线开盘价
    last_price = df.iloc[-1]["close"]  # 最后一根 K 线收盘价

    # 理论收益（不含成本）
    theoretical_return = (last_price - first_price) / first_price

    # 成本估算
    total_cost = 0.001 + 0.0005  # 买入手续费 + 滑点
    total_cost += 0.001 + 0.0005  # 卖出手续费 + 滑点

    # 预期收益（含成本）
    expected_return = theoretical_return - total_cost

    print(f"    First price (open): ${first_price:.2f}")
    print(f"    Last price (close): ${last_price:.2f}")
    print(f"    Theoretical return: {theoretical_return:.2%}")
    print(f"    Expected cost: {total_cost:.2%}")
    print(f"    Expected return: {expected_return:.2%}")
    print(f"    Actual return: {results['total_return']:.2%}")

    # 误差检查
    error = abs(results['total_return'] - expected_return)
    print(f"\n    Error: {error:.4%}")

    if error < 0.01:  # 1% 误差容忍
        print("    Result: PASS (within 1% tolerance)")
        validation_passed = True
    else:
        print("    Result: WARNING (error > 1%)")
        validation_passed = False

    # 步骤 7：显示交易详情
    print("\n[7] Trade Details:")
    print("-" * 60)

    for i, trade in enumerate(results["trades"], 1):
        print(f"\n    Trade {i}:")
        print(f"      Type: {trade['type']}")
        print(f"      Time: {trade['time']}")
        print(f"      Price: ${trade['price']:.2f}")
        print(f"      Quantity: {trade['quantity']:.6f}")

        if trade['type'] == 'BUY':
            print(f"      Cost: ${trade['cost']:.2f}")
            print(f"      Commission: ${trade['commission']:.2f}")
        else:
            print(f"      Proceeds: ${trade.get('proceeds', 0):.2f}")
            print(f"      Commission: ${trade['commission']:.2f}")
            print(f"      Profit: ${trade.get('profit', 0):.2f}")

    # 步骤 8：显示权益曲线
    print("\n[8] Equity Curve (first 5 and last 5):")
    print("-" * 60)

    equity = results["equity_curve"]
    print("\n    First 5:")
    for e in equity[:5]:
        print(f"      {e['time']}: ${e['total_equity']:.2f}")

    if len(equity) > 10:
        print("\n    ...")

    print("\n    Last 5:")
    for e in equity[-5:]:
        print(f"      {e['time']}: ${e['total_equity']:.2f}")

    # 总结
    print("\n" + "=" * 60)

    if validation_passed:
        print("SUCCESS: Backtest engine validation passed!")
        print("\nNext step:")
        print("  - Add more performance metrics")
        print("  - Implement bias detection")
        print("  - Create more strategies")
        return 0
    else:
        print("WARNING: Backtest results need review")
        print("\nPlease check:")
        print("  - Cost model implementation")
        print("  - Order execution logic")
        print("  - Price data accuracy")
        return 1


if __name__ == "__main__":
    sys.exit(test_backtest_engine())
