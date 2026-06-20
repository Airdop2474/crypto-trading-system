"""
数据质量检查器的单元测试

测试每个检查能正确检测出问题数据
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.data.quality_checker import DataQualityChecker


def make_df(rows: list) -> pd.DataFrame:
    """从字典列表创建 DataFrame，自动转换 timestamp"""
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def good_row(ts: str, price: float = 100.0, volume: float = 500.0) -> dict:
    """生成一个合法的 OHLCV 行"""
    return {
        "timestamp": ts,
        "open": price,
        "high": price + 2,
        "low": price - 2,
        "close": price + 1,
        "volume": volume,
    }


class TestTimeContinuity:
    """时间连续性检查"""

    def test_continuous_passes(self):
        df = make_df([
            good_row("2024-01-01 00:00:00"),
            good_row("2024-01-01 04:00:00"),
            good_row("2024-01-01 08:00:00"),
        ])
        result = DataQualityChecker("4h").check_time_continuity(df)
        assert result["passed"]
        assert result["gap_count"] == 0

    def test_gap_detected(self):
        # 缺少 04:00，从 00:00 直接跳到 08:00
        df = make_df([
            good_row("2024-01-01 00:00:00"),
            good_row("2024-01-01 08:00:00"),
        ])
        result = DataQualityChecker("4h").check_time_continuity(df)
        assert not result["passed"]
        assert result["gap_count"] == 1


class TestTimeUniqueness:
    """时间唯一性检查"""

    def test_unique_passes(self):
        df = make_df([
            good_row("2024-01-01 00:00:00"),
            good_row("2024-01-01 04:00:00"),
        ])
        result = DataQualityChecker("4h").check_time_uniqueness(df)
        assert result["passed"]

    def test_duplicate_detected(self):
        df = make_df([
            good_row("2024-01-01 00:00:00"),
            good_row("2024-01-01 00:00:00"),  # 重复
        ])
        result = DataQualityChecker("4h").check_time_uniqueness(df)
        assert not result["passed"]
        assert result["duplicate_count"] == 2


class TestPriceLogic:
    """价格逻辑性检查"""

    def test_valid_ohlc_passes(self):
        df = make_df([good_row("2024-01-01 00:00:00")])
        result = DataQualityChecker("4h").check_price_logic(df)
        assert result["passed"]

    def test_high_below_close_detected(self):
        # high 低于 close，违反逻辑
        df = make_df([{
            "timestamp": "2024-01-01 00:00:00",
            "open": 100, "high": 100, "low": 90, "close": 105, "volume": 500,
        }])
        result = DataQualityChecker("4h").check_price_logic(df)
        assert not result["passed"]
        assert result["invalid_count"] == 1

    def test_low_above_open_detected(self):
        # low 高于 open，违反逻辑
        df = make_df([{
            "timestamp": "2024-01-01 00:00:00",
            "open": 100, "high": 110, "low": 105, "close": 108, "volume": 500,
        }])
        result = DataQualityChecker("4h").check_price_logic(df)
        assert not result["passed"]


class TestPriceReasonability:
    """价格合理性检查"""

    def test_normal_change_passes(self):
        df = make_df([good_row("2024-01-01 00:00:00")])
        result = DataQualityChecker("4h").check_price_reasonability(df)
        assert result["passed"]

    def test_extreme_change_detected(self):
        # 单根 K 线涨幅 60%，超过 50% 阈值
        # 需要多行让单个异常占比超过 0.1%
        df = make_df([{
            "timestamp": "2024-01-01 00:00:00",
            "open": 100, "high": 170, "low": 100, "close": 160, "volume": 500,
        }])
        result = DataQualityChecker("4h").check_price_reasonability(df)
        assert not result["passed"]
        assert result["abnormal_count"] == 1


class TestVolumeReasonability:
    """成交量合理性检查"""

    def test_normal_volume_passes(self):
        df = make_df([
            good_row("2024-01-01 00:00:00", volume=500),
            good_row("2024-01-01 04:00:00", volume=510),
        ])
        result = DataQualityChecker("4h").check_volume_reasonability(df)
        assert result["passed"]

    def test_zero_volume_detected(self):
        df = make_df([
            good_row("2024-01-01 00:00:00", volume=0),
            good_row("2024-01-01 04:00:00", volume=500),
        ])
        result = DataQualityChecker("4h").check_volume_reasonability(df)
        assert not result["passed"]
        assert result["zero_volume_count"] == 1


class TestDataCompleteness:
    """数据完整性检查"""

    def test_complete_passes(self):
        df = make_df([good_row("2024-01-01 00:00:00")])
        result = DataQualityChecker("4h").check_data_completeness(df)
        assert result["passed"]
        assert result["total_nulls"] == 0

    def test_null_detected(self):
        df = make_df([good_row("2024-01-01 00:00:00")])
        df.loc[0, "close"] = None  # 注入空值
        result = DataQualityChecker("4h").check_data_completeness(df)
        assert not result["passed"]
        assert result["total_nulls"] == 1


class TestDataVersion:
    """数据版本检查"""

    def test_hash_generated(self):
        df = make_df([good_row("2024-01-01 00:00:00")])
        result = DataQualityChecker("4h").check_data_version(df)
        assert result["passed"]
        assert isinstance(result["hash"], (int, str)) and len(str(result["hash"])) > 0

    def test_same_data_same_hash(self):
        df1 = make_df([good_row("2024-01-01 00:00:00")])
        df2 = make_df([good_row("2024-01-01 00:00:00")])
        h1 = DataQualityChecker("4h").check_data_version(df1)["hash"]
        h2 = DataQualityChecker("4h").check_data_version(df2)["hash"]
        assert h1 == h2  # 相同数据应产生相同哈希


class TestCheckAll:
    """整体检查"""

    def test_all_pass_on_good_data(self):
        df = make_df([
            good_row("2024-01-01 00:00:00"),
            good_row("2024-01-01 04:00:00"),
            good_row("2024-01-01 08:00:00"),
        ])
        results = DataQualityChecker("4h").check_all(df)
        assert results["summary"]["all_passed"]
        assert results["summary"]["passed"] == 7
