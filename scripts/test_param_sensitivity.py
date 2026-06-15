#!/usr/bin/env python3
"""
测试参数敏感性

测试策略参数变化对结果的影响
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.param_scanner import ParameterScanner
from src.strategy.simple_ma import SimpleMAStrategy
from src.utils.logger import setup_logger, logger


def test_grid_search():
    """测试网格搜索"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Parameter Sensitivity Test - Grid Search")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("ERROR: No data found")
        return 1

    print(f"Loaded {len(df)} bars")

    # 初始化参数扫描器
    print("\n[2] Initializing parameter scanner...")
    scanner = ParameterScanner(
        initial_capital=10000.0,
        commission=0.001,
        slippage=0.0005,
    )

    # 定义参数网格
    print("\n[3] Defining parameter grid...")
    param_grid = {
        "short_window": [3, 5, 7],
        "long_window": [10, 15, 20],
    }

    print(f"Parameters:")
    for param, values in param_grid.items():
        print(f"  {param}: {values}")

    total_combinations = 1
    for values in param_grid.values():
        total_combinations *= len(values)
    print(f"\nTotal combinations: {total_combinations}")

    # 运行网格搜索
    print("\n[4] Running grid search...")
    results = scanner.grid_search(
        data=df,
        strategy_class=SimpleMAStrategy,
        param_grid=param_grid,
    )

    print(f"\nCompleted: {len(results)} results")

    # 显示结果
    print("\n[5] Results Summary:")
    print("-" * 60)

    # 按收益排序
    results_sorted = results.sort_values("total_return", ascending=False)

    print("\nTop 5 by Total Return:")
    print(results_sorted.head(5).to_string(index=False))

    print("\n\nTop 5 by Sharpe Ratio:")
    results_by_sharpe = results.sort_values("sharpe_ratio", ascending=False)
    print(results_by_sharpe.head(5).to_string(index=False))

    # 最佳参数
    print("\n[6] Best Parameters:")
    print("-" * 60)

    best_return = results_sorted.iloc[0]
    print(f"\nBest by Return:")
    print(f"  Short Window: {best_return['short_window']}")
    print(f"  Long Window: {best_return['long_window']}")
    print(f"  Total Return: {best_return['total_return']:.2%}")
    print(f"  Max Drawdown: {best_return['max_drawdown']:.2%}")
    print(f"  Sharpe Ratio: {best_return['sharpe_ratio']:.2f}")

    best_sharpe = results_by_sharpe.iloc[0]
    print(f"\nBest by Sharpe:")
    print(f"  Short Window: {best_sharpe['short_window']}")
    print(f"  Long Window: {best_sharpe['long_window']}")
    print(f"  Total Return: {best_sharpe['total_return']:.2%}")
    print(f"  Sharpe Ratio: {best_sharpe['sharpe_ratio']:.2f}")

    return results


def test_sensitivity_analysis(results_df):
    """测试敏感性分析"""
    print("\n" + "=" * 60)
    print("Parameter Sensitivity Analysis")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    # 初始化扫描器
    scanner = ParameterScanner()

    # 使用最佳参数作为基准
    best_params = results_df.sort_values("total_return", ascending=False).iloc[0]
    base_params = {
        "short_window": int(best_params["short_window"]),
        "long_window": int(best_params["long_window"]),
    }

    print(f"\n[2] Base parameters:")
    print(f"  Short Window: {base_params['short_window']}")
    print(f"  Long Window: {base_params['long_window']}")

    # 测试每个参数的敏感性
    for param in ["short_window", "long_window"]:
        print(f"\n[3] Testing sensitivity of: {param}")
        print("-" * 60)

        sensitivity_results = scanner.sensitivity_analysis(
            data=df,
            strategy_class=SimpleMAStrategy,
            base_params=base_params,
            test_param=param,
            variations=[-0.2, -0.1, 0, 0.1, 0.2],
        )

        print(f"\nResults:")
        print(sensitivity_results[["value", "variation", "total_return", "sharpe_ratio"]].to_string(index=False))

        # 分析稳定性
        stability = scanner.analyze_stability(sensitivity_results, tolerance=0.5)

        print(f"\nStability Analysis:")
        print(f"  Stable: {'Yes' if stability['stable'] else 'No'}")
        print(f"  Max Deviation: {stability['max_deviation']:.2f}")
        print(f"  Tolerance: {stability['tolerance']:.2f}")
        print(f"  Base Return: {stability['base_return']:.2%}")

        if stability['stable']:
            print(f"  ✓ Parameter {param} is STABLE")
        else:
            print(f"  ✗ Parameter {param} is SENSITIVE (may be overfitting)")

    return 0


def main():
    """主函数"""
    # 测试 1：网格搜索
    results = test_grid_search()

    if results is None or results.empty:
        print("\nERROR: Grid search failed")
        return 1

    # 测试 2：敏感性分析
    test_sensitivity_analysis(results)

    print("\n" + "=" * 60)
    print("SUCCESS: Parameter sensitivity test completed!")
    print("\nNext step:")
    print("  - Implement out-of-sample testing")
    print("  - Generate backtest reports")
    print("  - Phase 2 final acceptance")

    return 0


if __name__ == "__main__":
    sys.exit(main())
