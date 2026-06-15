#!/usr/bin/env python3
"""
数据管道：下载 -> 质量检查 -> 生成报告

完整的端到端数据处理流程
"""

import sys
from pathlib import Path
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.data.quality_checker import DataQualityChecker
from src.data.report_generator import ReportGenerator
from src.utils.logger import setup_logger, logger


def run_pipeline(
    symbol: str,
    timeframe: str,
    use_mock: bool = True,
) -> bool:
    """
    运行完整的数据管道

    参数：
        symbol: 交易对
        timeframe: 时间周期
        use_mock: 是否使用模拟数据（无网络时）

    返回：
        是否成功
    """
    print("=" * 60)
    print(f"Data Pipeline: {symbol} {timeframe}")
    print("=" * 60)

    # 步骤 1：加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol=symbol, timeframe=timeframe)

    if df.empty:
        print("    ERROR: No data found")
        if use_mock:
            print("    Run: python scripts/generate_mock_data.py")
        else:
            print("    Run download first")
        return False

    print(f"    Loaded {len(df)} records")

    # 步骤 2：质量检查
    print("\n[2] Running quality checks...")
    checker = DataQualityChecker(timeframe=timeframe)
    results = checker.check_all(df)

    summary = results["summary"]
    print(f"    Checks: {summary['passed']}/{summary['total_checks']} passed")

    # 步骤 3：保存 JSON 报告
    print("\n[3] Saving JSON report...")
    report_dir = Path("data/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    json_file = report_dir / "quality_check_report.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"    JSON report: {json_file}")

    # 步骤 4：生成 Markdown 报告
    print("\n[4] Generating Markdown report...")
    generator = ReportGenerator()
    md_file = generator.generate_markdown(
        results=results,
        symbol=symbol,
        timeframe=timeframe,
    )
    print(f"    Markdown report: {md_file}")

    # 步骤 5：显示结果
    print("\n[5] Results:")
    print("-" * 60)

    check_names = {
        "time_continuity": "Time Continuity",
        "time_uniqueness": "Time Uniqueness",
        "price_logic": "Price Logic",
        "price_reasonability": "Price Reasonability",
        "volume_reasonability": "Volume Reasonability",
        "data_completeness": "Data Completeness",
        "data_version": "Data Version",
    }

    for check_id, check_name in check_names.items():
        if check_id in results["checks"]:
            check = results["checks"][check_id]
            status = "PASS" if check.get("passed", False) else "FAIL"
            print(f"    {status}: {check_name}")

    print("-" * 60)

    if summary["all_passed"]:
        print("\n    Result: ALL CHECKS PASSED")
        return True
    else:
        print(f"\n    Result: {summary['failed']} CHECK(S) FAILED")
        return False


def main():
    """主函数"""
    setup_logger(log_level="INFO")

    # 配置
    symbol = "BTC/USDT"
    timeframe = "4h"

    # 运行管道
    success = run_pipeline(
        symbol=symbol,
        timeframe=timeframe,
        use_mock=True,
    )

    print("\n" + "=" * 60)

    if success:
        print("SUCCESS: Pipeline completed successfully!")
        print("\nGenerated files:")
        print("  - data/reports/quality_check_report.json")
        print("  - data/reports/quality_report_*.md")
        print("\nPhase 1 core functionality complete!")
        print("\nNext step:")
        print("  - Review the Markdown report")
        print("  - Run integration tests")
        print("  - Phase 1 acceptance")
        return 0
    else:
        print("FAILED: Pipeline encountered issues")
        print("\nNext step:")
        print("  - Review the reports for details")
        print("  - Fix data quality issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
