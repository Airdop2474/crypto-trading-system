"""
RiskManager 单元测试（Phase 5 风控清单）

覆盖 LIVE_TRADING_CHECKLIST.md 风控测试项：
日亏损熔断、连亏熔断、数据异常熔断、API 失败熔断、人工恢复、紧急停止。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.execution.risk_manager import RiskManager, ACTIVE, PAUSED, STOPPED


def loss(amount, day="2024-01-01"):
    return {"time": pd.Timestamp(day), "type": "SELL", "profit": -abs(amount)}


def win(amount, day="2024-01-01"):
    return {"time": pd.Timestamp(day), "type": "SELL", "profit": abs(amount)}


class TestInit:
    def test_starts_active(self):
        rm = RiskManager(10000.0)
        assert rm.state == ACTIVE
        assert rm.can_trade()

    def test_invalid_capital(self):
        with pytest.raises(ValueError):
            RiskManager(0.0)


class TestConsecutiveLosses:
    def test_trips_at_threshold(self):
        rm = RiskManager(100000.0, max_consecutive_losses=5, max_daily_loss=1.0)
        for _ in range(4):
            rm.record_fill(loss(1))
        assert rm.can_trade()  # 4 笔未到阈值
        rm.record_fill(loss(1))  # 第 5 笔
        assert rm.is_paused()
        assert not rm.can_trade()

    def test_win_resets_counter(self):
        rm = RiskManager(100000.0, max_consecutive_losses=3, max_daily_loss=1.0)
        rm.record_fill(loss(1))
        rm.record_fill(loss(1))
        rm.record_fill(win(1))  # 重置
        assert rm.consecutive_losses == 0
        rm.record_fill(loss(1))
        assert rm.can_trade()


class TestDailyLoss:
    def test_trips_at_limit(self):
        # 资金 10000，日亏损上限 3% = 300
        rm = RiskManager(10000.0, max_daily_loss=0.03, max_consecutive_losses=99)
        rm.record_fill(loss(200))
        assert rm.can_trade()  # 2% 未到
        rm.record_fill(loss(150))  # 累计 350 = 3.5% > 3%
        assert rm.is_paused()

    def test_new_day_resets_daily_pnl(self):
        rm = RiskManager(10000.0, max_daily_loss=0.03, max_consecutive_losses=99)
        rm.record_fill(loss(250, day="2024-01-01"))  # 2.5%
        assert rm.can_trade()
        rm.record_fill(loss(250, day="2024-01-02"))  # 新的一天，重置后 2.5%
        assert rm.can_trade()
        assert rm.daily_pnl == pytest.approx(-250)


class TestDataAnomaly:
    def test_pauses(self):
        rm = RiskManager(10000.0)
        rm.record_data_anomaly("gap detected")
        assert rm.is_paused()


class TestApiFailure:
    def test_trips_after_threshold(self):
        rm = RiskManager(10000.0, max_api_failures=3)
        rm.record_api_failure()
        rm.record_api_failure()
        assert rm.can_trade()
        rm.record_api_failure()  # 第 3 次
        assert rm.is_paused()

    def test_success_resets(self):
        rm = RiskManager(10000.0, max_api_failures=3)
        rm.record_api_failure()
        rm.record_api_failure()
        rm.record_api_success()
        assert rm.api_failures == 0
        rm.record_api_failure()
        assert rm.can_trade()


class TestManualRecovery:
    def test_resume_from_paused(self):
        rm = RiskManager(10000.0, max_consecutive_losses=2, max_daily_loss=1.0)
        rm.record_fill(loss(1))
        rm.record_fill(loss(1))
        assert rm.is_paused()
        assert rm.resume() is True
        assert rm.can_trade()
        assert rm.consecutive_losses == 0  # 瞬时计数重置

    def test_resume_ignored_when_active(self):
        rm = RiskManager(10000.0)
        assert rm.resume() is False

    def test_cannot_resume_from_stopped(self):
        rm = RiskManager(10000.0)
        rm.emergency_stop()
        assert rm.resume() is False
        assert rm.is_stopped()


class TestEmergencyStop:
    def test_stop_is_terminal_until_reset(self):
        rm = RiskManager(10000.0)
        rm.emergency_stop("kill switch")
        assert rm.is_stopped()
        assert not rm.can_trade()
        # 熔断不能把 STOPPED 降级
        rm.record_data_anomaly()
        assert rm.is_stopped()

    def test_reset_restores_active(self):
        rm = RiskManager(10000.0)
        rm.emergency_stop()
        rm.reset()
        assert rm.can_trade()
        assert rm.state == ACTIVE


class TestPositionCheck:
    def test_within_limit(self):
        rm = RiskManager(10000.0, max_total_position=0.60)
        assert rm.check_position(5000, 10000) is True  # 50% <= 60%

    def test_over_limit(self):
        rm = RiskManager(10000.0, max_total_position=0.60)
        assert rm.check_position(7000, 10000) is False  # 70% > 60%


class TestEventLog:
    def test_events_recorded(self):
        rm = RiskManager(10000.0)
        rm.record_data_anomaly("test")
        rm.resume()
        rm.emergency_stop("test")
        types = [e["type"] for e in rm.events]
        assert "PAUSE" in types
        assert "RESUME" in types
        assert "EMERGENCY_STOP" in types
