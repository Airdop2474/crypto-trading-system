#!/usr/bin/env python3
"""
测试前视偏差检测器

检测策略代码中的前视偏差
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.backtest.bias_detector import BiasDetector
from src.strategy.buy_and_hold import BuyAndHoldStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.utils.logger import setup_logger, logger


def test_bias_detection():
    """测试前视偏差检测"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Bias Detection Test")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol="BTC/USDT", timeframe="4h")

    if df.empty:
        print("ERROR: No data found")
        return 1

    print(f"Loaded {len(df)} bars")

    # 初始化偏差检测器
    print("\n[2] Initializing bias detector...")
    detector = BiasDetector()

    # 测试策略列表
    strategies = [
        ("Buy and Hold", BuyAndHoldStrategy()),
        ("Simple MA (5, 10)", SimpleMAStrategy(short_window=5, long_window=10)),
    ]

    all_reports = []

    for name, strategy in strategies:
        print(f"\n{'=' * 60}")
        print(f"Testing: {name}")
        print('=' * 60)

        # 步骤 1：检查策略代码
        print("\n[A] Checking strategy code...")
        code_check = detector.check_strategy_code(strategy)

        if code_check["success"]:
            print(f"    Strategy: {code_check['strategy']}")
            print(f"    Warnings: {code_check['warning_count']}")

            if code_check["has_warnings"]:
                print("\n    Detected issues:")
                for warning in code_check["warnings"]:
                    print(f"      - [{warning['severity'].upper()}] {warning['description']}")
                    print(f"        Pattern: {warning['pattern']}")
                    print(f"        Line: {warning['line']}")
            else:
                print("    No code warnings found")

            print(f"    Has safe patterns: {code_check['has_safe_patterns']}")

        # 步骤 2：运行回测
        print("\n[B] Running backtest...")
        engine = BacktestEngine(
            initial_capital=10000.0,
            commission=0.001,
            slippage=0.0005,
        )

        results = engine.run(data=df, strategy=strategy)

        if not results["success"]:
            print(f"    ERROR: {results.get('message')}")
            continue

        print(f"    Completed: {results['total_trades']} trades")

        # 步骤 3：检查回测逻辑
        print("\n[C] Checking backtest logic...")
        logic_check = detector.check_backtest_logic(results)

        print(f"    Violations: {logic_check['violation_count']}")

        if logic_check["has_violations"]:
            print("\n    Detected violations:")
            for violation in logic_check["violations"]:
                print(f"      - {violation['type']}: {violation['message']}")
        else:
            print("    No logic violations found")

        # 步骤 4：检查订单执行
        print("\n[D] Checking order execution...")
        execution_check = detector.check_order_execution(results)

        print(f"    Issues: {execution_check['issue_count']}")

        if execution_check["has_issues"]:
            print("\n    Detected issues:")
            for issue in execution_check["issues"]:
                print(f"      - {issue['type']}")
                print(f"        Signal: {issue['signal_time']}")
                print(f"        Trade: {issue['trade_time']}")
                print(f"        Message: {issue['message']}")
        else:
            print("    No execution issues found")

        # 步骤 5：生成综合报告
        print("\n[E] Generating report...")
        report = detector.generate_report(
            code_check=code_check,
            logic_check=logic_check,
            execution_check=execution_check,
        )

        summary = report["summary"]
        print(f"\n    Summary:")
        print(f"      Code warnings: {summary['code_warnings']}")
        print(f"      Critical: {summary['critical_warnings']}")
        print(f"      High: {summary['high_warnings']}")
        print(f"      Logic violations: {summary['logic_violations']}")
        print(f"      Execution issues: {summary['execution_issues']}")

        print(f"\n    Result: {'PASS' if report['passed'] else 'FAIL'}")
        print(f"    Recommendation: {report['recommendation']}")

        all_reports.append((name, report))

    # 总结
    print(f"\n{'=' * 60}")
    print("Bias Detection Summary")
    print('=' * 60)

    print(f"\n{'Strategy':<25} {'Warnings':<10} {'Violations':<12} {'Result'}")
    print('-' * 60)

    for name, report in all_reports:
        summary = report["summary"]
        result = "PASS" if report["passed"] else "FAIL"
        print(
            f"{name:<25} "
            f"{summary['code_warnings']:<10} "
            f"{summary['logic_violations']:<12} "
            f"{result}"
        )

    print("\n" + "=" * 60)

    passed_count = sum(1 for _, r in all_reports if r["passed"])
    total_count = len(all_reports)

    if passed_count == total_count:
        print(f"SUCCESS: All {total_count} strategies passed bias detection!")
        print("\nNext step:")
        print("  - Test parameter sensitivity")
        print("  - Implement out-of-sample testing")
        print("  - Generate backtest reports")
        return 0
    else:
        print(f"WARNING: {total_count - passed_count}/{total_count} strategies failed")
        print("\nNext step:")
        print("  - Review and fix detected issues")
        print("  - Re-run bias detection")
        return 1


if __name__ == "__main__":
    sys.exit(test_bias_detection())
