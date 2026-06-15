#!/usr/bin/env python3
"""
手动运行质量检查器的单元测试
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from tests.unit.test_quality_checker import *


def run_test(test_class, method_name):
    """运行单个测试方法"""
    test_instance = test_class()
    method = getattr(test_instance, method_name)

    try:
        method()
        print(f"  PASS: {test_class.__name__}.{method_name}")
        return True
    except AssertionError as e:
        print(f"  FAIL: {test_class.__name__}.{method_name}")
        print(f"        {e}")
        return False
    except Exception as e:
        print(f"  ERROR: {test_class.__name__}.{method_name}")
        print(f"         {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Quality Checker Unit Tests")
    print("=" * 60)

    test_classes = [
        (TestTimeContinuity, [
            "test_continuous_passes",
            "test_gap_detected",
        ]),
        (TestTimeUniqueness, [
            "test_unique_passes",
            "test_duplicate_detected",
        ]),
        (TestPriceLogic, [
            "test_valid_ohlc_passes",
            "test_high_below_close_detected",
            "test_low_above_open_detected",
        ]),
        (TestPriceReasonability, [
            "test_normal_change_passes",
            "test_extreme_change_detected",
        ]),
        (TestVolumeReasonability, [
            "test_normal_volume_passes",
            "test_zero_volume_detected",
        ]),
        (TestDataCompleteness, [
            "test_complete_passes",
            "test_null_detected",
        ]),
        (TestDataVersion, [
            "test_hash_generated",
            "test_same_data_same_hash",
        ]),
        (TestCheckAll, [
            "test_all_pass_on_good_data",
        ]),
    ]

    passed = 0
    failed = 0

    for test_class, methods in test_classes:
        print(f"\n{test_class.__name__}:")
        for method_name in methods:
            if run_test(test_class, method_name):
                passed += 1
            else:
                failed += 1

    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    print(f"Total: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("\nSUCCESS: All tests passed!")
        return 0
    else:
        print(f"\nFAILED: {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
