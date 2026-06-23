#!/usr/bin/env python3
"""
数据管道：下载 -> 质量检查 -> 生成报告

完整的端到端数据处理流程
"""

import sys
import argparse
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
    market_type: str = "oscillating",
) -> bool:
    """
    运行完整的数据管道

    参数：
        symbol: 交易对
        timeframe: 时间周期
        use_mock: 是否使用模拟数据（无网络时，自动生成）
        market_type: 市场类型（oscillating/trending/black_swan）

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
        if use_mock:
            print(f"    No data file found. Generating mock data ({market_type})...")
            from scripts.generate_mock_data import generate_and_save_data
            df = generate_and_save_data(symbol=symbol, timeframe=timeframe, market_type=market_type)
        else:
            print("    ERROR: No data found. Use --live to download from exchange.")
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
    parser = argparse.ArgumentParser(description="Data pipeline: generate mock data, quality check, report")
    parser.add_argument("--market-type", default="oscillating", choices=["oscillating", "trending", "black_swan"],
                        help="市场类型：震荡/趋势/黑天鹅")
    parser.add_argument("--live", action="store_true", help="从交易所下载真实数据（而非生成模拟数据）")
    args = parser.parse_args()

    setup_logger(log_level="INFO")

    # 配置
    symbol = "BTC/USDT"
    timeframe = "4h"

    # 运行管道
    success = run_pipeline(
        symbol=symbol,
        timeframe=timeframe,
        use_mock=not args.live,
        market_type=args.market_type,
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
