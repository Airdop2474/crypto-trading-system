#!/usr/bin/env python3
"""
测试数据质量检查

对生成的数据进行质量检查
"""

import sys
from pathlib import Path
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.data.quality_checker import DataQualityChecker
from src.utils.logger import setup_logger, logger


def print_check_result(check_name: str, result: dict, indent: str = "    "):
    """打印检查结果"""
    status = "PASS" if result.get("passed", False) else "FAIL"
    print(f"{indent}{status}: {check_name}")

    # 显示详细信息
    if not result.get("passed", False):
        # 显示失败原因
        if "gap_count" in result and result["gap_count"] > 0:
            print(f"{indent}  - Found {result['gap_count']} gap(s)")
        if "duplicate_count" in result and result["duplicate_count"] > 0:
            print(f"{indent}  - Found {result['duplicate_count']} duplicate(s)")
        if "invalid_count" in result and result["invalid_count"] > 0:
            print(f"{indent}  - Found {result['invalid_count']} invalid row(s)")
        if "abnormal_count" in result and result["abnormal_count"] > 0:
            print(f"{indent}  - Found {result['abnormal_count']} abnormal row(s)")
        if "zero_volume_count" in result and result["zero_volume_count"] > 0:
            print(f"{indent}  - Found {result['zero_volume_count']} zero volume row(s)")
        if "total_nulls" in result and result["total_nulls"] > 0:
            print(f"{indent}  - Found {result['total_nulls']} null value(s)")

    # 显示哈希（如果有）
    if "hash" in result:
        print(f"{indent}  - Hash: {result['hash'][:16]}...")


def main():
    """主函数"""
    setup_logger(log_level="INFO")

    print("=" * 60)
    print("Data Quality Check Test")
    print("=" * 60)

    try:
        # 加载数据
        print("\n[1] Loading data...")
        downloader = DataDownloader()
        df = downloader.load_data(
            symbol="BTC/USDT",
            timeframe="4h",
        )

        if df.empty:
            print("    ERROR: No data found")
            print("    Run: python scripts/generate_mock_data.py")
            return 1

        print(f"    Loaded {len(df)} records")
        print(f"    Columns: {df.columns.tolist()}")

        # 初始化质量检查器
        print("\n[2] Initializing quality checker...")
        checker = DataQualityChecker(timeframe="4h")
        print("    OK: Checker initialized")

        # 执行质量检查
        print("\n[3] Running quality checks...")
        results = checker.check_all(df)

        # 显示检查结果
        print("\n[4] Check Results:")
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
                print_check_result(
                    check_name,
                    results["checks"][check_id]
                )

        # 显示总结
        print("\n" + "-" * 60)
        print("[5] Summary:")
        summary = results["summary"]
        print(f"    Total checks: {summary['total_checks']}")
        print(f"    Passed: {summary['passed']}")
        print(f"    Failed: {summary['failed']}")

        if summary["all_passed"]:
            print("\n    Result: ALL CHECKS PASSED")
        else:
            print(f"\n    Result: {summary['failed']} CHECK(S) FAILED")

        # 保存完整报告
        print("\n[6] Saving report...")
        report_dir = Path("data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        report_file = report_dir / "quality_check_report.json"
        with open(report_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"    Report saved to: {report_file}")

        # 显示详细信息（如果有失败）
        if not summary["all_passed"]:
            print("\n[7] Detailed Issues:")
            for check_id, result in results["checks"].items():
                if not result.get("passed", False):
                    print(f"\n    {check_names.get(check_id, check_id)}:")

                    # 显示具体问题
                    if "gaps" in result and result["gaps"]:
                        print("      Gaps:")
                        for gap in result["gaps"][:3]:  # 最多显示3个
                            print(f"        - Position {gap['position']}")
                            print(f"          Before: {gap['before']}")
                            print(f"          After: {gap['after']}")

                    if "duplicates" in result and result["duplicates"]:
                        print("      Duplicates:")
                        for dup in result["duplicates"][:3]:
                            print(f"        - Timestamp: {dup['timestamp']}")
                            print(f"          Count: {dup['count']}")

                    if "invalid_rows" in result and result["invalid_rows"]:
                        print("      Invalid rows:")
                        for invalid in result["invalid_rows"][:3]:
                            print(f"        - Index: {invalid['index']}")
                            print(f"          Violations: {', '.join(invalid['violations'])}")

        print("\n" + "=" * 60)

        if summary["all_passed"]:
            print("SUCCESS: All quality checks passed!")
            print("\nNext step:")
            print("  - Review the report: data/reports/quality_check_report.json")
            print("  - Continue with Day 5: Report generation")
            return 0
        else:
            print(f"WARNING: {summary['failed']} check(s) failed")
            print("\nNext step:")
            print("  - Review the detailed issues above")
            print("  - Fix data quality problems")
            print("  - Re-run quality checks")
            return 1

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
