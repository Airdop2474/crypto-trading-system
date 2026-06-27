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


class TestOrderRateGuardPersistence:
    """OrderRateGuard 状态持久化测试（修复护栏可绕过）"""

    def test_state_dict_roundtrip(self):
        """state_dict → load_state 后状态应一致"""
        g = OrderRateGuard(reference_capital=10000.0,
                           max_position_per_trade=1.0,
                           min_trade_interval=60,
                           max_trades_per_day=10)
        ts = pd.Timestamp("2024-01-01 12:00")
        for _ in range(3):
            g.check(100.0, ts)
            g.record(ts)
        assert g._count == 3

        # 序列化 → 反序列化
        st = g.state_dict()
        g2 = OrderRateGuard(reference_capital=10000.0,
                            max_position_per_trade=1.0,
                            min_trade_interval=60,
                            max_trades_per_day=10)
        g2.load_state(st)

        # 验证状态一致（_last_ts 序列化为字符串，加载后保持字符串，pd.Timestamp 可解析）
        assert g2._count == 3
        assert g2._day == g._day
        assert pd.Timestamp(g2._last_ts) == pd.Timestamp(g._last_ts)

        # 续跑：再下一单应到 count=4
        g2.check(100.0, ts)
        g2.record(ts)
        assert g2._count == 4

    def test_load_state_with_empty_dict(self):
        """空 dict 不影响默认状态（向后兼容旧 checkpoint 无 guard 字段）"""
        g = OrderRateGuard(reference_capital=10000.0)
        g.load_state({})
        assert g._count == 0
        assert g._day is None

    def test_load_state_with_none(self):
        """None 不影响默认状态"""
        g = OrderRateGuard(reference_capital=10000.0)
        g.load_state(None)
        assert g._count == 0

    def test_persistence_prevents_bypass(self):
        """护栏持久化后重启不再绕过日订单上限"""
        g = OrderRateGuard(reference_capital=10000.0,
                           max_position_per_trade=1.0,
                           min_trade_interval=0,
                           max_trades_per_day=5)
        ts = pd.Timestamp("2024-01-01 12:00")
        # 当天已下 5 单（达上限）
        for _ in range(5):
            g.check(100.0, ts)
            g.record(ts)

        # 模拟重启：序列化 → 新实例加载
        st = g.state_dict()
        g2 = OrderRateGuard(reference_capital=10000.0,
                            max_position_per_trade=1.0,
                            min_trade_interval=0,
                            max_trades_per_day=5)
        g2.load_state(st)
        # 重启后继续下单应被拒绝（未绕过）
        ok, _ = g2.check(100.0, ts)
        assert ok is False
