"""数据质量检查器.

实现 7 项强制质量检查
"""

import hashlib
from datetime import datetime
from typing import Any, Dict

import pandas as pd

from src.utils.logger import logger


class DataQualityChecker:
    """数据质量检查器"""

    def __init__(self, timeframe: str = "4h"):
        """
        初始化质量检查器

        参数：
            timeframe: 时间周期（用于连续性检查）
        """
        self.timeframe = timeframe
        self.timeframe_deltas = {
            "1m": pd.Timedelta(minutes=1),
            "5m": pd.Timedelta(minutes=5),
            "15m": pd.Timedelta(minutes=15),
            "1h": pd.Timedelta(hours=1),
            "4h": pd.Timedelta(hours=4),
            "1d": pd.Timedelta(days=1),
        }

    def check_all(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        执行所有质量检查

        参数：
            df: OHLCV DataFrame

        返回：
            完整的检查结果字典
        """
        logger.info("Starting data quality checks...")

        results: Dict[str, Any] = {
            "check_time": datetime.now().isoformat(),
            "record_count": len(df),
            "timeframe": self.timeframe,
            "checks": {},
            "summary": {
                "total_checks": 7,
                "passed": 0,
                "failed": 0,
            },
        }

        # 执行 7 项检查
        checks = [
            ("time_continuity", self.check_time_continuity),
            ("time_uniqueness", self.check_time_uniqueness),
            ("price_logic", self.check_price_logic),
            ("price_reasonability", self.check_price_reasonability),
            ("volume_reasonability", self.check_volume_reasonability),
            ("data_completeness", self.check_data_completeness),
            ("data_version", self.check_data_version),
        ]

        for check_name, check_func in checks:
            try:
                check_result = check_func(df)
                results["checks"][check_name] = check_result

                if check_result["passed"]:
                    results["summary"]["passed"] += 1
                else:
                    results["summary"]["failed"] += 1

                logger.info(
                    f"Check '{check_name}': "
                    f"{'PASS' if check_result['passed'] else 'FAIL'}"
                )

            except Exception as e:
                logger.error(f"Check '{check_name}' failed with error: {e}")
                results["checks"][check_name] = {
                    "passed": False,
                    "error": str(e),
                }
                results["summary"]["failed"] += 1

        # 总体通过/失败
        results["summary"]["all_passed"] = (
            results["summary"]["failed"] == 0
        )

        logger.info(
            f"Quality check completed: "
            f"{results['summary']['passed']}/{results['summary']['total_checks']} passed"
        )

        return results

    def check_time_continuity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 1: 时间连续性

        K线时间戳必须连续，不允许缺口

        返回：
            {
                'passed': bool,
                'gaps': list,
                'gap_count': int
            }
        """
        if len(df) < 2:
            return {"passed": True, "gaps": [], "gap_count": 0}

        expected_delta = self.timeframe_deltas.get(
            self.timeframe, pd.Timedelta(hours=4)
        )

        # 计算时间差
        time_diff = df["timestamp"].diff()

        # 找出缺口（时间差大于预期）
        gaps = df[time_diff > expected_delta]

        gap_list = []
        for idx in gaps.index:
            if idx > 0:
                gap_list.append(
                    {
                        "position": int(idx),
                        "before": pd.Timestamp(df.loc[idx - 1, "timestamp"]).isoformat(),
                        "after": pd.Timestamp(df.loc[idx, "timestamp"]).isoformat(),
                        "gap_size": str(time_diff.loc[idx]),
                    }
                )

        return {
            "passed": len(gaps) == 0,
            "gaps": gap_list,
            "gap_count": len(gaps),
            "expected_delta": str(expected_delta),
        }

    def check_time_uniqueness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 2: 时间唯一性

        每个时间戳只能出现一次

        返回：
            {
                'passed': bool,
                'duplicates': list,
                'duplicate_count': int
            }
        """
        # 找出重复的时间戳
        duplicates = df[df["timestamp"].duplicated(keep=False)]

        duplicate_list = []
        if len(duplicates) > 0:
            for timestamp in duplicates["timestamp"].unique():
                dup_rows = df[df["timestamp"] == timestamp]
                duplicate_list.append(
                    {
                        "timestamp": pd.Timestamp(timestamp).isoformat(),
                        "count": len(dup_rows),
                        "indices": dup_rows.index.tolist(),
                    }
                )

        return {
            "passed": len(duplicates) == 0,
            "duplicates": duplicate_list,
            "duplicate_count": len(duplicates),
        }

    def check_price_logic(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 3: 价格逻辑性

        OHLC 必须满足逻辑关系：
        - high >= max(open, close)
        - low <= min(open, close)
        - high >= low

        返回：
            {
                'passed': bool,
                'invalid_rows': list,
                'invalid_count': int
            }
        """
        invalid_rows = []

        # 向量化检测三类违规
        high_lt_oc = df["high"] < df[["open", "close"]].max(axis=1)
        low_gt_oc = df["low"] > df[["open", "close"]].min(axis=1)
        high_lt_low = df["high"] < df["low"]

        invalid_mask = high_lt_oc | low_gt_oc | high_lt_low

        # 只对违规行（正常数据下为空）构建详情
        for idx, row in df[invalid_mask].iterrows():
            violations = []
            if high_lt_oc.loc[idx]:
                violations.append("high < max(open, close)")
            if low_gt_oc.loc[idx]:
                violations.append("low > min(open, close)")
            if high_lt_low.loc[idx]:
                violations.append("high < low")

            invalid_rows.append(
                {
                    "index": int(idx),
                    "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    "violations": violations,
                    "ohlc": {
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    },
                }
            )

        return {
            "passed": len(invalid_rows) == 0,
            "invalid_rows": invalid_rows,
            "invalid_count": len(invalid_rows),
        }

    def check_price_reasonability(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 4: 价格合理性

        单根K线涨跌幅不应超过 50%（异常波动）

        返回：
            {
                'passed': bool,
                'abnormal_rows': list,
                'abnormal_count': int,
                'threshold': float
            }
        """
        threshold = 0.50  # 50%
        abnormal_rows = []

        # 向量化计算单根K线涨跌幅（open > 0 时）
        valid_open = df["open"] > 0
        change_pct = (df["close"] - df["open"]).abs() / df["open"].where(valid_open)
        abnormal_mask = valid_open & (change_pct > threshold)

        for idx, row in df[abnormal_mask].iterrows():
            abnormal_rows.append(
                {
                    "index": int(idx),
                    "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    "change_pct": float(change_pct.loc[idx]),
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                }
            )

        # 容忍度：异常K线 < 0.1%
        abnormal_ratio = len(abnormal_rows) / len(df) if len(df) > 0 else 0
        passed = abnormal_ratio < 0.001  # 0.1%

        return {
            "passed": passed,
            "abnormal_rows": abnormal_rows[:10],  # 最多返回10个
            "abnormal_count": len(abnormal_rows),
            "abnormal_ratio": float(abnormal_ratio),
            "threshold": threshold,
        }

    def check_volume_reasonability(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 5: 成交量合理性

        - 成交量不能为 0
        - 成交量不能有异常值（如 > 均值 + 10*标准差）

        返回：
            {
                'passed': bool,
                'zero_volume_count': int,
                'abnormal_volume_count': int,
                'issues': list
            }
        """
        issues = []

        # 检查零成交量
        zero_volume = df[df["volume"] == 0]
        zero_count = len(zero_volume)

        if zero_count > 0:
            for idx in zero_volume.index[:5]:  # 最多显示5个
                issues.append(
                    {
                        "type": "zero_volume",
                        "index": int(idx),
                        "timestamp": pd.Timestamp(df.loc[idx, "timestamp"]).isoformat(),
                    }
                )

        # 检查异常成交量
        if len(df) > 0:
            mean_volume = df["volume"].mean()
            std_volume = df["volume"].std()
            threshold = mean_volume + 10 * std_volume

            abnormal_volume = df[df["volume"] > threshold]
            abnormal_count = len(abnormal_volume)

            if abnormal_count > 0:
                for idx in abnormal_volume.index[:5]:  # 最多显示5个
                    issues.append(
                        {
                            "type": "abnormal_volume",
                            "index": int(idx),
                            "timestamp": pd.Timestamp(
                                df.loc[idx, "timestamp"]
                            ).isoformat(),
                            "volume": float(df.loc[idx, "volume"]),
                            "threshold": float(threshold),
                        }
                    )
        else:
            abnormal_count = 0

        return {
            "passed": zero_count == 0 and abnormal_count == 0,
            "zero_volume_count": zero_count,
            "abnormal_volume_count": abnormal_count,
            "issues": issues,
        }

    def check_data_completeness(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 6: 数据完整性

        所有字段不能有空值

        返回：
            {
                'passed': bool,
                'null_counts': dict,
                'total_nulls': int
            }
        """
        # 检查每列的空值数量
        null_counts = df.isnull().sum().to_dict()

        # 转换为 Python int（避免 numpy.int64）
        null_counts = {k: int(v) for k, v in null_counts.items()}

        total_nulls = sum(null_counts.values())

        return {
            "passed": total_nulls == 0,
            "null_counts": null_counts,
            "total_nulls": total_nulls,
        }

    def check_data_version(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检查 7: 数据版本记录

        计算数据的 SHA256 哈希，用于版本追踪

        返回：
            {
                'passed': bool,
                'hash': str,
                'algorithm': str
            }
        """
        # 将 DataFrame 转换为字符串并计算哈希
        data_string = df.to_csv(index=False)
        hash_object = hashlib.sha256(data_string.encode())
        data_hash = hash_object.hexdigest()

        return {
            "passed": True,  # 总是通过（只要能计算哈希）
            "hash": data_hash,
            "algorithm": "SHA256",
            "data_size": len(data_string),
        }


# 导出
__all__ = ["DataQualityChecker"]
