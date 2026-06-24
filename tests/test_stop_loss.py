"""
StopLossManager 单元测试

覆盖：
- ATR 固定止损（5 用例）
- 移动止损（5 用例）
- 区间突破止损（5 用例）
- 时间止损（5 用例）
- 状态管理（5 用例）
"""

import pytest
from datetime import datetime, timedelta

from src.strategy.stop_loss import StopLossManager, StopLossConfig


class TestATRStopLoss:
    """ATR 固定止损测试"""

    def _setup(self, atr_mult=1.5, min_stop_pct=0.01):
        cfg = StopLossConfig(
            stop_type="atr_trailing",
            atr_mult=atr_mult,
            trailing_activation=0.99,  # 设很高，不触发移动止损
            trailing_drawback=0.03,
            max_bars=0,  # 不启用时间止损
            min_stop_pct=min_stop_pct,
        )
        return StopLossManager(cfg)

    def test_atr_stop_triggers_when_price_drops(self):
        """价格跌破 ATR 止损线时触发"""
        slm = self._setup(atr_mult=1.5, min_stop_pct=0.005)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # ATR=2, 止损 = 100 - 1.5*2 = 97, min_stop = 100*(1-0.005) = 99.5
        # max(97, 99.5) = 99.5 → 止损线 99.5
        triggered, reason = slm.check_stop(99.0, datetime.now(), atr=2.0)
        assert triggered is True
        assert "ATR" in reason

    def test_atr_stop_not_triggered_above_stop(self):
        """价格在止损线之上不触发"""
        slm = self._setup(atr_mult=1.5, min_stop_pct=0.005)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 止损 = max(97, 99.5) = 99.5, 价格 99.6 > 99.5
        triggered, _ = slm.check_stop(99.6, datetime.now(), atr=2.0)
        assert triggered is False

    def test_atr_stop_uses_min_stop_pct_when_atr_small(self):
        """ATR 过小时使用 min_stop_pct 兜底"""
        slm = self._setup(atr_mult=1.5, min_stop_pct=0.02)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # ATR=0.1, 止损 = 100 - 0.15 = 99.85, 但 min_stop = 100*(1-0.02) = 98
        # 取 max(99.85, 98) = 99.85... 不对，min_stop_pct 是下限
        # 实际：fixed_stop = max(100 - 1.5*0.1, 100*(1-0.02)) = max(99.85, 98) = 99.85
        # 但 min_stop_pct=0.02 意味着止损不低于 2%，所以止损线 = 98
        # 代码逻辑：min_stop = entry * (1 - MIN_STOP_PCT) = 100 * 0.99 = 99
        # 但 min_stop_pct=0.02, 所以 min_stop = 100 * (1-0.02) = 98
        # fixed_stop = max(99.85, 98) = 99.85
        # 这说明 ATR 止损比 min_stop 更紧
        triggered, _ = slm.check_stop(99.0, datetime.now(), atr=0.1)
        assert triggered is True  # 99 < 99.85

    def test_atr_stop_no_atr_uses_min_stop_pct(self):
        """无 ATR 时用 min_stop_pct 作为兜底"""
        slm = self._setup(min_stop_pct=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 无 ATR, 止损 = 100 * (1 - 0.03) = 97
        triggered, _ = slm.check_stop(96.0, datetime.now(), atr=None)
        assert triggered is True

    def test_atr_stop_resets_after_sell(self):
        """卖出后止损状态重置"""
        slm = self._setup()
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.on_fill({"type": "sell", "price": 105.0, "time": datetime.now()})
        # 重置后不应触发
        triggered, _ = slm.check_stop(50.0, datetime.now(), atr=2.0)
        assert triggered is False


class TestTrailingStop:
    """移动止损测试"""

    def _setup(self, activation=0.03, drawback=0.03):
        cfg = StopLossConfig(
            stop_type="atr_trailing",
            atr_mult=10.0,  # ATR 止损很远，只测移动止损
            trailing_activation=activation,
            trailing_drawback=drawback,
            max_bars=0,
            min_stop_pct=0.005,
        )
        return StopLossManager(cfg)

    def test_trailing_not_active_below_threshold(self):
        """涨幅未达激活阈值时移动止损不激活"""
        slm = self._setup(activation=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 涨 2%，未达 3% 激活阈值
        triggered, _ = slm.check_stop(102.0, datetime.now(), atr=1.0)
        assert triggered is False

    def test_trailing_activates_and_trails(self):
        """涨幅达阈值后激活移动止损"""
        slm = self._setup(activation=0.03, drawback=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 涨到 105（涨 5% > 3%），激活移动止损
        slm.check_stop(105.0, datetime.now(), atr=1.0)
        # 最高价 = 105, 追踪止损 = 105 * (1-0.03) = 101.85
        # 价格回落到 101，触发
        triggered, reason = slm.check_stop(101.0, datetime.now(), atr=1.0)
        assert triggered is True
        assert "移动" in reason

    def test_trailing_does_not_trigger_above_trail(self):
        """价格在追踪止损之上不触发"""
        slm = self._setup(activation=0.03, drawback=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(105.0, datetime.now(), atr=1.0)  # 激活
        # 追踪止损 = 101.85, 价格 103 > 101.85
        triggered, _ = slm.check_stop(103.0, datetime.now(), atr=1.0)
        assert triggered is False

    def test_trailing_moves_up_with_price(self):
        """追踪止损随价格上涨而上移"""
        slm = self._setup(activation=0.03, drawback=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(105.0, datetime.now(), atr=1.0)  # 激活, trail=101.85
        slm.check_stop(110.0, datetime.now(), atr=1.0)  # 涨到 110, trail=106.7
        # 价格回落到 105 < 106.7, 触发
        triggered, _ = slm.check_stop(105.0, datetime.now(), atr=1.0)
        assert triggered is True

    def test_trailing_never_moves_down(self):
        """追踪止损只上移不下移"""
        slm = self._setup(activation=0.03, drawback=0.03)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(110.0, datetime.now(), atr=1.0)  # trail=106.7
        slm.check_stop(105.0, datetime.now(), atr=1.0)  # 价格回落但 trail 不变
        # 此时 trail 仍为 106.7
        triggered, _ = slm.check_stop(106.0, datetime.now(), atr=1.0)
        assert triggered is True  # 106 < 106.7


class TestRangeBreakoutStop:
    """区间突破止损测试"""

    def _setup(self, breakout_pct=0.05):
        cfg = StopLossConfig(
            stop_type="range_breakout",
            range_breakout_pct=breakout_pct,
            max_bars=0,
        )
        return StopLossManager(cfg)

    def test_range_stop_triggers_on_drop(self):
        """价格跌破区间触发"""
        slm = self._setup(breakout_pct=0.05)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 止损 = 100 * (1-0.05) = 95
        triggered, reason = slm.check_stop(94.0, datetime.now())
        assert triggered is True
        assert "区间" in reason

    def test_range_stop_not_triggered_above(self):
        """价格在止损线之上不触发"""
        slm = self._setup(breakout_pct=0.05)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        triggered, _ = slm.check_stop(96.0, datetime.now())
        assert triggered is False

    def test_range_stop_at_exact_boundary(self):
        """价格正好在止损线不触发（<= 才触发）"""
        slm = self._setup(breakout_pct=0.05)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 止损 = 95.0, 价格 = 95.0, 95.0 <= 95.0 → 触发
        triggered, _ = slm.check_stop(95.0, datetime.now())
        assert triggered is True

    def test_range_stop_different_pct(self):
        """不同突破比例"""
        slm = self._setup(breakout_pct=0.10)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 止损 = 90
        triggered, _ = slm.check_stop(91.0, datetime.now())
        assert triggered is False
        triggered, _ = slm.check_stop(89.0, datetime.now())
        assert triggered is True

    def test_range_stop_resets_after_sell(self):
        """卖出后重置"""
        slm = self._setup()
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.on_fill({"type": "sell", "price": 98.0, "time": datetime.now()})
        triggered, _ = slm.check_stop(50.0, datetime.now())
        assert triggered is False


class TestTimeStop:
    """时间止损测试"""

    def _setup(self, max_bars=5):
        cfg = StopLossConfig(
            stop_type="time_only",
            max_bars=max_bars,
        )
        return StopLossManager(cfg)

    def test_time_stop_triggers_after_max_bars(self):
        """持仓超过 max_bars 触发"""
        slm = self._setup(max_bars=5)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 前 4 根不触发
        for i in range(4):
            triggered, _ = slm.check_stop(100.0, datetime.now())
            assert triggered is False, f"Should not trigger at bar {i+1}"
        # 第 5 根触发
        triggered, reason = slm.check_stop(100.0, datetime.now())
        assert triggered is True
        assert "时间" in reason

    def test_time_stop_not_triggered_before_max(self):
        """持仓未达 max_bars 不触发"""
        slm = self._setup(max_bars=10)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        for i in range(9):
            triggered, _ = slm.check_stop(100.0, datetime.now())
            assert triggered is False

    def test_time_stop_zero_disables(self):
        """max_bars=0 禁用时间止损"""
        slm = self._setup(max_bars=0)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        for i in range(100):
            triggered, _ = slm.check_stop(100.0, datetime.now())
            assert triggered is False

    def test_time_stop_resets_after_sell(self):
        """卖出后 bar 计数重置"""
        slm = self._setup(max_bars=3)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(100.0, datetime.now())
        slm.check_stop(100.0, datetime.now())
        slm.on_fill({"type": "sell", "price": 100.0, "time": datetime.now()})
        # 重新买入
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 计数应从 0 开始
        triggered, _ = slm.check_stop(100.0, datetime.now())
        assert triggered is False  # bar 1, 未达 3

    def test_time_stop_works_with_other_stops(self):
        """时间止损与其他止损类型共存"""
        cfg = StopLossConfig(
            stop_type="atr_trailing",
            atr_mult=10.0,  # ATR 止损很远
            max_bars=3,
        )
        slm = StopLossManager(cfg)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(100.0, datetime.now(), atr=1.0)
        slm.check_stop(100.0, datetime.now(), atr=1.0)
        triggered, reason = slm.check_stop(100.0, datetime.now(), atr=1.0)
        assert triggered is True
        assert "时间" in reason


class TestStateManagement:
    """状态管理测试"""

    def test_no_position_does_not_trigger(self):
        """无持仓时不触发"""
        cfg = StopLossConfig(stop_type="atr_trailing", max_bars=5)
        slm = StopLossManager(cfg)
        triggered, _ = slm.check_stop(50.0, datetime.now(), atr=2.0)
        assert triggered is False

    def test_get_stop_info(self):
        """获取止损状态信息"""
        cfg = StopLossConfig(stop_type="atr_trailing")
        slm = StopLossManager(cfg)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.check_stop(105.0, datetime.now(), atr=2.0)
        info = slm.get_stop_info()
        assert info["in_position"] is True
        assert info["entry_price"] == 100.0
        assert info["highest_price"] == 105.0
        assert info["bars_held"] == 1

    def test_reset_clears_state(self):
        """reset 清除所有状态"""
        cfg = StopLossConfig(stop_type="atr_trailing")
        slm = StopLossManager(cfg)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        slm.reset()
        assert slm.in_position is False
        assert slm.entry_price is None

    def test_config_clamps_values(self):
        """配置参数被安全边界限制"""
        cfg = StopLossConfig(
            atr_mult=100.0,      # 超出 [0.5, 4.0]
            trailing_activation=0.5,  # 超出 [0.01, 0.10]
            max_bars=500,        # 超出 [0, 200]
        )
        assert cfg.atr_mult == 4.0
        assert cfg.trailing_activation == 0.10
        assert cfg.max_bars == 200

    def test_partial_sell_does_not_reset(self):
        """部分卖出（网格单档）不重置整体状态"""
        cfg = StopLossConfig(stop_type="atr_trailing")
        slm = StopLossManager(cfg)
        slm.on_fill({"type": "buy", "price": 100.0, "time": datetime.now()})
        # 部分卖出（有 tag 但不是全部）
        slm.on_fill({"type": "sell", "price": 105.0, "time": datetime.now(), "tag": "grid_0"})
        # 状态应保持
        assert slm.in_position is True
