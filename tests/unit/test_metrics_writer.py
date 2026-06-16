"""MetricsWriter 单元测试。

用假 DB 捕获 query + data，不连真实数据库。
验证：参数化 SQL、列顺序、空输入不触库、从采集器写入。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.monitor.metrics_writer import MetricsWriter
from src.monitor.metrics_collector import MetricsCollector


class FakeDB:
    """捕获 execute_many 的 query 和 data。"""

    def __init__(self):
        self.calls = []

    def execute_many(self, query, data):
        self.calls.append((query, data))


def _record(ts="2026-01-01T00:00:00", **over):
    base = {
        "timestamp": ts,
        "total_value": 10000.0,
        "total_return": 0.0,
        "realized_pnl": 0.0,
        "total_trades": 0,
        "risk_state": "ACTIVE",
        "consecutive_losses": 0,
    }
    base.update(over)
    return base


class TestWriteRecords:
    def test_parameterized_query_and_column_order(self):
        db = FakeDB()
        w = MetricsWriter(db=db)
        n = w.write_records([_record(total_value=10500.0, total_trades=3)])

        assert n == 1
        query, data = db.calls[0]
        # 参数化占位，无值拼接
        assert "VALUES (%s, %s, %s, %s, %s, %s, %s)" in query
        assert "INSERT INTO monitor_metrics" in query
        # data 按 COLUMNS 顺序成元组
        assert data[0] == (
            "2026-01-01T00:00:00", 10500.0, 0.0, 0.0, 3, "ACTIVE", 0
        )

    def test_multiple_records(self):
        db = FakeDB()
        w = MetricsWriter(db=db)
        n = w.write_records([_record(), _record(ts="2026-01-01T04:00:00")])
        assert n == 2
        _, data = db.calls[0]
        assert len(data) == 2

    def test_empty_records_no_db_call(self):
        db = FakeDB()
        w = MetricsWriter(db=db)
        n = w.write_records([])
        assert n == 0
        assert db.calls == []  # 不触库

    def test_missing_field_becomes_none(self):
        """记录缺列 → 该位置为 None（不抛错）。"""
        db = FakeDB()
        w = MetricsWriter(db=db)
        rec = _record()
        del rec["risk_state"]
        w.write_records([rec])
        _, data = db.calls[0]
        # risk_state 是第 6 个列（索引 5）
        assert data[0][5] is None


class TestWriteCollector:
    def test_writes_collector_snapshots(self):
        db = FakeDB()
        collector = MetricsCollector()
        runner_result = {
            "statistics": {
                "initial_balance": 10000.0,
                "current_balance": 9000.0,
                "positions": {"BTC/USDT": 0.01},
                "total_trades": 5,
                "total_cost": 12.3,
            },
            "realized_pnl": 50.0,
            "open_lots": {"g0": {}},
        }
        collector.snapshot(runner_result, {"BTC/USDT": 110000.0})

        w = MetricsWriter(db=db)
        n = w.write_collector(collector)
        assert n == 1
        _, data = db.calls[0]
        # 列数与 schema 一致
        assert len(data[0]) == len(MetricsWriter.COLUMNS)
