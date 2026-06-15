"""
AlertManager 单元测试

验证：风控事件增量告警、级别映射、回撤告警、CRITICAL 过滤。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.monitor.alert_manager import AlertManager, INFO, WARNING, CRITICAL
from src.execution.risk_manager import RiskManager


class TestRiskEventAlerts:
    def test_pause_maps_to_warning(self):
        am = AlertManager()
        rm = RiskManager(10000.0)
        rm.record_data_anomaly("gap")  # -> PAUSE 事件
        alerts = am.check_risk_events(rm)
        assert len(alerts) == 1
        assert alerts[0]["level"] == WARNING

    def test_emergency_stop_maps_to_critical(self):
        am = AlertManager()
        rm = RiskManager(10000.0)
        rm.emergency_stop("kill")
        alerts = am.check_risk_events(rm)
        assert alerts[0]["level"] == CRITICAL

    def test_incremental_no_duplicate(self):
        am = AlertManager()
        rm = RiskManager(10000.0)
        rm.record_data_anomaly("first")
        first = am.check_risk_events(rm)
        assert len(first) == 1
        # 无新事件 -> 不重复
        second = am.check_risk_events(rm)
        assert len(second) == 0
        # 新事件 -> 增量告警
        rm.emergency_stop("kill")
        third = am.check_risk_events(rm)
        assert len(third) == 1


class TestDrawdownAlert:
    def test_triggers_below_threshold(self):
        am = AlertManager(max_drawdown_alert=0.10)
        alert = am.check_drawdown(-0.12)  # -12% < -10%
        assert alert is not None
        assert alert["level"] == CRITICAL

    def test_no_trigger_above_threshold(self):
        am = AlertManager(max_drawdown_alert=0.10)
        assert am.check_drawdown(-0.05) is None
        assert am.check_drawdown(0.05) is None


class TestCriticalFilter:
    def test_critical_alerts_only(self):
        am = AlertManager()
        am.emit(INFO, "src", "info msg")
        am.emit(WARNING, "src", "warn msg")
        am.emit(CRITICAL, "src", "crit msg")
        crits = am.critical_alerts()
        assert len(crits) == 1
        assert crits[0]["message"] == "crit msg"
