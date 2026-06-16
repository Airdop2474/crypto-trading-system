"""订单级下单护栏测试（src/execution/order_guard.py）。

覆盖：单笔名义额上限、最小间隔（按 bar，同 bar 多 lot 放行）、日订单数 rollover。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.execution.order_guard import OrderRateGuard


def _guard(**kw):
    kw.setdefault("reference_capital", 10000.0)
    return OrderRateGuard(**kw)


# ---- 单笔名义额上限 ----

def test_rejects_over_per_trade_cap():
    g = _guard(max_position_per_trade=0.20)  # 上限 2000
    ok, reason = g.check(2500.0, pd.Timestamp("2024-01-01 00:00"))
    assert not ok
    assert "单笔" in reason


def test_allows_within_per_trade_cap():
    g = _guard(max_position_per_trade=0.20)
    ok, _ = g.check(1500.0, pd.Timestamp("2024-01-01 00:00"))
    assert ok


# ---- 间隔（按 bar）----

def test_interval_blocks_too_soon_next_bar():
    g = _guard(min_trade_interval=300, max_position_per_trade=1.0)
    t0 = pd.Timestamp("2024-01-01 00:00")
    assert g.check(100.0, t0)[0]
    g.record(t0)
    # 下一根 bar 仅隔 60s < 300s → 拒
    t1 = pd.Timestamp("2024-01-01 00:01")
    ok, reason = g.check(100.0, t1)
    assert not ok and "间隔" in reason


def test_interval_allows_after_gap():
    g = _guard(min_trade_interval=300, max_position_per_trade=1.0)
    t0 = pd.Timestamp("2024-01-01 00:00")
    g.record(t0)
    t1 = pd.Timestamp("2024-01-01 00:05")  # 隔 300s
    assert g.check(100.0, t1)[0]


def test_same_bar_multi_lot_passes_interval():
    """同一 bar 触发的多笔 lot 视作一次决策，间隔不阻断。"""
    g = _guard(min_trade_interval=300, max_position_per_trade=1.0,
               max_trades_per_day=100)
    t0 = pd.Timestamp("2024-01-01 00:00")
    g.record(t0)
    # 同 ts 再下单（grid 多 lot）→ 放行
    ok, _ = g.check(100.0, t0)
    assert ok


# ---- 日订单数 ----

def test_daily_count_blocks_over_limit():
    g = _guard(max_trades_per_day=2, min_trade_interval=0,
               max_position_per_trade=1.0)
    for i in range(2):
        t = pd.Timestamp(f"2024-01-01 00:0{i}")
        assert g.check(100.0, t)[0]
        g.record(t)
    t3 = pd.Timestamp("2024-01-01 00:03")
    ok, reason = g.check(100.0, t3)
    assert not ok and "当日" in reason


def test_daily_count_resets_next_day():
    g = _guard(max_trades_per_day=2, min_trade_interval=0,
               max_position_per_trade=1.0)
    for i in range(2):
        t = pd.Timestamp(f"2024-01-01 00:0{i}")
        g.check(100.0, t)
        g.record(t)
    # 跨日 → 计数归零
    t_next = pd.Timestamp("2024-01-02 00:00")
    assert g.check(100.0, t_next)[0]
