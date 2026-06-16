"""守护进程运行健康巡检的纯函数测试（scripts/check_daemon_health.py）。

只测 assess_health 决策逻辑，不触文件系统/时钟。
"""

import sys
from datetime import date
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.check_daemon_health import _date_gaps, assess_health


def _state(day_count=3, risk_state="ACTIVE"):
    return {
        "day_count": day_count,
        "last_bar_ts": "2024-01-09 00:00:00",
        "risk": {"state": risk_state, "consecutive_losses": 0, "api_failures": 0},
    }


def _dates(*days):
    return [date(2024, 1, d) for d in days]


def _status(checks, name):
    return next(c["status"] for c in checks if c["name"] == name)


def test_healthy_run_passes():
    ok, checks = assess_health(
        _state(day_count=3), _dates(6, 7, 8),
        checkpoint_age_hours=1.0, resume_flag_present=False,
    )
    assert ok
    assert all(c["status"] != "FAIL" for c in checks)


def test_missing_state_fails_fast():
    ok, checks = assess_health(None, [], None, False)
    assert not ok
    assert len(checks) == 1 and checks[0]["status"] == "FAIL"


def test_emergency_stopped_fails():
    ok, checks = assess_health(
        _state(day_count=3, risk_state="STOPPED"), _dates(6, 7, 8),
        checkpoint_age_hours=1.0, resume_flag_present=False,
    )
    assert not ok
    assert _status(checks, "风控状态") == "FAIL"


def test_paused_is_warn_not_fail():
    ok, checks = assess_health(
        _state(day_count=3, risk_state="PAUSED"), _dates(6, 7, 8),
        checkpoint_age_hours=1.0, resume_flag_present=False,
    )
    assert ok  # PAUSED 是预期的熔断机制，不算 FAIL
    assert _status(checks, "风控状态") == "WARN"


def test_stale_checkpoint_warns():
    ok, checks = assess_health(
        _state(day_count=3), _dates(6, 7, 8),
        checkpoint_age_hours=48.0, resume_flag_present=False, max_age_hours=12.0,
    )
    assert ok
    assert _status(checks, "检查点新鲜度") == "WARN"


def test_resume_flag_warns():
    ok, checks = assess_health(
        _state(day_count=3), _dates(6, 7, 8),
        checkpoint_age_hours=1.0, resume_flag_present=True,
    )
    assert ok
    assert _status(checks, "人工恢复标志") == "WARN"


def test_report_date_gap_fails():
    ok, checks = assess_health(
        _state(day_count=3), _dates(6, 8, 9),  # 缺 01-07
        checkpoint_age_hours=1.0, resume_flag_present=False,
    )
    assert not ok
    assert _status(checks, "日报连续无缺口") == "FAIL"


def test_count_mismatch_fails():
    ok, checks = assess_health(
        _state(day_count=5), _dates(6, 7, 8),  # 3 份 ≠ day_count 5
        checkpoint_age_hours=1.0, resume_flag_present=False,
    )
    assert not ok
    assert _status(checks, "日报数量对账") == "FAIL"


def test_date_gaps_helper():
    assert _date_gaps(_dates(6, 7, 8)) == []
    assert _date_gaps(_dates(6, 9)) == _dates(7, 8)
    assert _date_gaps(_dates(6)) == []


# ---- exchange 模式扩展（卡单 + 下单错误率）----

def _exchange_state(unconfirmed=None, errors=0, fills=0, day_count=3):
    st = _state(day_count=day_count)
    st["broker"] = {
        "unconfirmed": unconfirmed or [],
        "errors": errors,
        "ledger": [{} for _ in range(fills)],
        "initial_balance": 10000.0, "initial_position": 0.0,
    }
    return st


def test_paper_state_has_no_exchange_checks():
    """paper 形态（无 broker.unconfirmed 键）不触发 exchange 检查，向后兼容。"""
    _, checks = assess_health(_state(), _dates(6, 7, 8), 1.0, False)
    names = [c["name"] for c in checks]
    assert "卡单（未确认订单）" not in names
    assert "下单错误率" not in names


def test_exchange_clean_passes():
    ok, checks = assess_health(
        _exchange_state(fills=5), _dates(6, 7, 8), 1.0, False)
    assert ok
    assert _status(checks, "卡单（未确认订单）") == "PASS"
    assert _status(checks, "下单错误率") == "PASS"


def test_stuck_orders_warn():
    ok, checks = assess_health(
        _exchange_state(unconfirmed=["X1", "X2"], fills=5), _dates(6, 7, 8),
        1.0, False)
    assert ok  # WARN 不算 FAIL
    assert _status(checks, "卡单（未确认订单）") == "WARN"


def test_high_error_rate_warns():
    # errors=4, fills=6 → rate=40% > 默认 20%
    _, checks = assess_health(
        _exchange_state(errors=4, fills=6), _dates(6, 7, 8), 1.0, False)
    assert _status(checks, "下单错误率") == "WARN"


def test_error_rate_threshold_configurable():
    # rate=40%，阈值放宽到 50% → PASS
    _, checks = assess_health(
        _exchange_state(errors=4, fills=6), _dates(6, 7, 8), 1.0, False,
        error_rate_threshold=0.5)
    assert _status(checks, "下单错误率") == "PASS"
