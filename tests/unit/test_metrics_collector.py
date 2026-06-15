"""
MetricsCollector 单元测试

验证：账户/交易/风控指标采集、风控可选、快照累积、时序展平。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.monitor.metrics_collector import MetricsCollector
from src.execution.risk_manager import RiskManager


def fake_result(cash=8000.0, positions=None, trades=10, cost=20.0,
                realized=500.0, open_lots=2):
    return {
        "statistics": {
            "initial_balance": 10000.0,
            "current_balance": cash,
            "positions": positions or {"BTC/USDT": 0.05},
            "total_trades": trades,
            "total_cost": cost,
        },
        "realized_pnl": realized,
        "open_lots": {i: 1.0 for i in range(open_lots)},
    }


class TestSnapshot:
    def test_account_metrics(self):
        mc = MetricsCollector()
        snap = mc.snapshot(fake_result(), {"BTC/USDT": 50000})
        acc = snap["account"]
        # 持仓市值 = 0.05 * 50000 = 2500，总值 = 8000 + 2500 = 10500
        assert acc["position_value"] == pytest.approx(2500.0)
        assert acc["total_value"] == pytest.approx(10500.0)
        assert acc["total_return"] == pytest.approx(0.05)

    def test_trade_metrics(self):
        mc = MetricsCollector()
        snap = mc.snapshot(fake_result(trades=15, cost=30.0, open_lots=3),
                           {"BTC/USDT": 50000})
        assert snap["trades"]["total"] == 15
        assert snap["trades"]["total_cost"] == 30.0
        assert snap["trades"]["open_lots"] == 3

    def test_risk_disabled_when_none(self):
        mc = MetricsCollector()
        snap = mc.snapshot(fake_result(), {"BTC/USDT": 50000})
        assert snap["risk"]["enabled"] is False

    def test_risk_metrics_when_present(self):
        mc = MetricsCollector()
        rm = RiskManager(10000.0)
        rm.record_data_anomaly("test")  # -> PAUSED
        snap = mc.snapshot(fake_result(), {"BTC/USDT": 50000}, risk_manager=rm)
        risk = snap["risk"]
        assert risk["enabled"] is True
        assert risk["state"] == "PAUSED"
        assert risk["can_trade"] is False
        assert risk["event_count"] == 1


class TestAccumulation:
    def test_snapshots_accumulate(self):
        mc = MetricsCollector()
        mc.snapshot(fake_result(), {"BTC/USDT": 50000})
        mc.snapshot(fake_result(), {"BTC/USDT": 51000})
        assert len(mc.snapshots) == 2
        assert mc.latest() is mc.snapshots[-1]

    def test_latest_none_when_empty(self):
        assert MetricsCollector().latest() is None

    def test_to_records_shape(self):
        mc = MetricsCollector()
        rm = RiskManager(10000.0)
        mc.snapshot(fake_result(), {"BTC/USDT": 50000}, risk_manager=rm)
        records = mc.to_records()
        assert len(records) == 1
        rec = records[0]
        for key in ("timestamp", "total_value", "total_return",
                    "realized_pnl", "total_trades", "risk_state"):
            assert key in rec
