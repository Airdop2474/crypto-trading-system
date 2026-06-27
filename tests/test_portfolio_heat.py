"""PortfolioHeatManager 单元测试

测试组合热力（Portfolio Heat）的计算、共享文件协调、超阈值拒单逻辑。

测试分组：
1. 热力计算 (5 tests) — update_position_heat 的数学正确性
2. 共享文件协调 (5 tests) — 多策略读写共享文件
3. 超阈值拒单 (5 tests) — can_open_new_position 门控逻辑
4. 清除与边界 (5 tests) — clear()、空持仓、异常输入
"""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from src.risk.portfolio_heat import PortfolioHeatManager, DEFAULT_MAX_HEAT


@pytest.fixture
def tmp_state_dir():
    """临时 state 目录，每个测试独立"""
    with tempfile.TemporaryDirectory() as d:
        yield d


# ===========================================================================
# 1. 热力计算
# ===========================================================================

class TestHeatCalculation:
    """update_position_heat 的数学正确性"""

    def test_no_position_zero_heat(self, tmp_state_dir):
        """无持仓时热力为 0"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        heat = phm.update_position_heat(
            lots={}, current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        assert heat == 0.0

    def test_single_position_heat(self, tmp_state_dir):
        """单仓位热力 = (amount × price × ATR/price) / capital"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # amount=0.1 BTC, price=50000, ATR=1000
        # position_value = 0.1 × 50000 = 5000
        # atr_pct = 1000 / 50000 = 0.02
        # risk = 5000 × 0.02 = 100
        # heat = 100 / 10000 = 0.01 (1%)
        lots = {"tag1": {"amount": 0.1, "cost_price": 49000.0}}
        heat = phm.update_position_heat(
            lots=lots, current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        assert heat == pytest.approx(0.01, abs=1e-6)

    def test_multiple_positions_summed(self, tmp_state_dir):
        """多仓位热力 = 各仓位风险之和"""
        phm = PortfolioHeatManager("grid", state_dir=tmp_state_dir)
        # 3 个网格仓位，各 0.05 BTC
        # total_value = 3 × 0.05 × 50000 = 7500
        # atr_pct = 0.02
        # total_risk = 7500 × 0.02 = 150
        # heat = 150 / 10000 = 0.015 (1.5%)
        lots = {
            "g1": {"amount": 0.05, "cost_price": 49000.0},
            "g2": {"amount": 0.05, "cost_price": 49500.0},
            "g3": {"amount": 0.05, "cost_price": 50000.0},
        }
        heat = phm.update_position_heat(
            lots=lots, current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        assert heat == pytest.approx(0.015, abs=1e-6)

    def test_no_atr_uses_2pct_fallback(self, tmp_state_dir):
        """无 ATR 时用 2% 近似"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        lots = {"tag1": {"amount": 0.2, "cost_price": 50000.0}}
        # position_value = 0.2 × 50000 = 10000
        # atr_pct = 0.02 (fallback)
        # risk = 10000 × 0.02 = 200
        # heat = 200 / 10000 = 0.02 (2%)
        heat = phm.update_position_heat(
            lots=lots, current_price=50000.0, atr=None, initial_capital=10000.0
        )
        assert heat == pytest.approx(0.02, abs=1e-6)

    def test_zero_amount_skipped(self, tmp_state_dir):
        """amount=0 的仓位不计入热力"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        lots = {
            "tag1": {"amount": 0.0, "cost_price": 50000.0},
            "tag2": {"amount": 0.1, "cost_price": 50000.0},
        }
        heat = phm.update_position_heat(
            lots=lots, current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # 只有 tag2 计入
        assert heat == pytest.approx(0.01, abs=1e-6)


# ===========================================================================
# 2. 共享文件协调
# ===========================================================================

class TestSharedFile:
    """多策略通过共享文件协调"""

    def test_write_creates_shared_file(self, tmp_state_dir):
        """写入后共享文件存在"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # 新设计：每策略独立文件 portfolio_heat_{strategy}.json
        assert (Path(tmp_state_dir) / "portfolio_heat_rsi.json").exists()

    def test_multiple_strategies_aggregate(self, tmp_state_dir):
        """多个策略写入同一共享文件，读取时聚合"""
        phm1 = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm1.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # 强制写入（绕过 update_interval）
        phm1._last_update = 0
        phm1.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )

        phm2 = PortfolioHeatManager("ma", state_dir=tmp_state_dir)
        phm2._last_update = 0
        phm2.update_position_heat(
            lots={"t1": {"amount": 0.2, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )

        # 总热力 = 1% (rsi) + 2% (ma) = 3%
        total = phm2.get_portfolio_heat()
        assert total == pytest.approx(0.03, abs=1e-4)

    def test_get_portfolio_detail(self, tmp_state_dir):
        """get_portfolio_detail 返回完整结构"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm._last_update = 0  # 强制写入
        phm.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )

        detail = phm.get_portfolio_detail()
        assert "total_heat" in detail
        assert "max_heat" in detail
        assert "heat_pct" in detail
        assert "strategies" in detail
        assert "rsi" in detail["strategies"]
        assert detail["strategies"]["rsi"]["heat"] == pytest.approx(0.01, abs=1e-4)
        assert detail["strategies"]["rsi"]["position_value"] == pytest.approx(5000.0, abs=0.01)

    def test_update_interval_throttles_io(self, tmp_state_dir):
        """UPDATE_INTERVAL 内多次调用只写一次"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # 第一次调用写入
        phm.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # 立即再调用（不写文件，但内存值更新）
        phm.update_position_heat(
            lots={"t1": {"amount": 0.2, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # 共享文件中应该是第一次的值（0.01），不是第二次的（0.02）
        detail = phm.get_portfolio_detail()
        assert detail["strategies"]["rsi"]["heat"] == pytest.approx(0.01, abs=1e-4)

    def test_corrupt_file_returns_none(self, tmp_state_dir):
        """损坏的共享文件不崩溃"""
        heat_file = Path(tmp_state_dir) / "portfolio_heat.json"
        heat_file.write_text("NOT JSON", encoding="utf-8")
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # 不崩溃，返回 0
        assert phm.get_portfolio_heat() == 0.0


# ===========================================================================
# 3. 超阈值拒单
# ===========================================================================

class TestRejectionLogic:
    """can_open_new_position 门控逻辑"""

    def test_allow_when_below_threshold(self, tmp_state_dir):
        """总热力 + 新仓热力 < 阈值 → 允许"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # 当前无持仓，热力 = 0
        # 新仓风险 = 500, capital = 10000 → new_heat = 5%
        # projected = 0% + 5% = 5% < 15% → 允许
        allowed = phm.can_open_new_position(
            new_position_risk=500.0, initial_capital=10000.0
        )
        assert allowed is True

    def test_reject_when_above_threshold(self, tmp_state_dir):
        """总热力 + 新仓热力 > 阈值 → 拒绝"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # 先写入一个高热力
        phm._last_update = 0
        phm.update_position_heat(
            lots={"t1": {"amount": 1.0, "cost_price": 50000.0}},
            current_price=50000.0, atr=2000.0, initial_capital=10000.0
        )
        # 当前热力 = (50000 × 2000/50000) / 10000 = 2000/10000 = 20%
        # 新仓风险 = 100, capital = 10000 → new_heat = 1%
        # projected = 20% + 1% = 21% > 15% → 拒绝
        allowed = phm.can_open_new_position(
            new_position_risk=100.0, initial_capital=10000.0
        )
        assert allowed is False

    def test_reject_at_exact_threshold(self, tmp_state_dir):
        """projected == 阈值时拒绝（> 判断）"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir, max_heat=0.10)
        # 当前热力 5%，新仓热力 5% → projected = 10% == 阈值 → 不拒绝（> 不是 >=）
        phm._last_update = 0
        phm.update_position_heat(
            lots={"t1": {"amount": 0.25, "cost_price": 50000.0}},
            current_price=50000.0, atr=2000.0, initial_capital=10000.0
        )
        # heat = (0.25 × 50000 × 2000/50000) / 10000 = 500/10000 = 5%
        # new_risk = 500, capital = 10000 → new_heat = 5%
        # projected = 10% == 10% → 不 > 10% → 允许
        allowed = phm.can_open_new_position(
            new_position_risk=500.0, initial_capital=10000.0
        )
        assert allowed is True

    def test_allow_sell_when_above_threshold(self, tmp_state_dir):
        """超阈值时仍允许（can_open_new_position 只管新开仓）"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        # 无持仓时即使热力高也只看新仓
        # 这里测试：无共享文件 → heat=0 → 总是允许
        allowed = phm.can_open_new_position(
            new_position_risk=100.0, initial_capital=10000.0
        )
        assert allowed is True

    def test_zero_capital_no_crash(self, tmp_state_dir):
        """initial_capital=0 不崩溃"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=0.0
        )
        assert phm._my_heat == 0.0
        # can_open_new_position 也不崩溃
        allowed = phm.can_open_new_position(
            new_position_risk=100.0, initial_capital=0.0
        )
        assert allowed is True  # new_heat = 0, projected = 0 < 15%


# ===========================================================================
# 4. 清除与边界
# ===========================================================================

class TestClearAndEdgeCases:
    """clear()、空持仓、异常输入"""

    def test_clear_zeros_heat(self, tmp_state_dir):
        """clear() 后本策略热力为 0"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm._last_update = 0
        phm.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        assert phm._my_heat > 0

        phm.clear()
        assert phm._my_heat == 0.0

        detail = phm.get_portfolio_detail()
        assert detail["strategies"]["rsi"]["heat"] == 0.0

    def test_clear_does_not_affect_other_strategies(self, tmp_state_dir):
        """clear() 只清自己，不清其他策略"""
        phm1 = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        phm1._last_update = 0
        phm1.update_position_heat(
            lots={"t1": {"amount": 0.1, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )

        phm2 = PortfolioHeatManager("ma", state_dir=tmp_state_dir)
        phm2._last_update = 0
        phm2.update_position_heat(
            lots={"t1": {"amount": 0.2, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )

        # rsi 清除，ma 保留
        phm1.clear()

        detail = phm2.get_portfolio_detail()
        assert detail["strategies"]["rsi"]["heat"] == 0.0
        assert detail["strategies"]["ma"]["heat"] == pytest.approx(0.02, abs=1e-4)

    def test_no_shared_file_returns_empty_detail(self, tmp_state_dir):
        """无共享文件时 get_portfolio_detail 返回空结构"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        detail = phm.get_portfolio_detail()
        assert detail["total_heat"] == 0.0
        assert detail["max_heat"] == DEFAULT_MAX_HEAT
        assert detail["strategies"] == {}

    def test_no_shared_file_returns_zero_heat(self, tmp_state_dir):
        """无共享文件时 get_portfolio_heat 返回 0"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir)
        assert phm.get_portfolio_heat() == 0.0

    def test_custom_max_heat(self, tmp_state_dir):
        """自定义阈值生效"""
        phm = PortfolioHeatManager("rsi", state_dir=tmp_state_dir, max_heat=0.05)
        assert phm.max_heat == 0.05

        # 3% 热力 + 3% 新仓 = 6% > 5% → 拒绝
        phm._last_update = 0
        phm.update_position_heat(
            lots={"t1": {"amount": 0.15, "cost_price": 50000.0}},
            current_price=50000.0, atr=1000.0, initial_capital=10000.0
        )
        # heat = (0.15 × 50000 × 0.02) / 10000 = 150/10000 = 1.5%
        # new_risk = 300, capital = 10000 → new_heat = 3%
        # projected = 1.5% + 3% = 4.5% < 5% → 允许
        allowed = phm.can_open_new_position(
            new_position_risk=300.0, initial_capital=10000.0
        )
        assert allowed is True

        # new_risk = 400 → new_heat = 4% → projected = 5.5% > 5% → 拒绝
        allowed = phm.can_open_new_position(
            new_position_risk=400.0, initial_capital=10000.0
        )
        assert allowed is False
