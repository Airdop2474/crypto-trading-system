"""PerformanceMetrics 扩展测试 —— 补审查报告 T1 点名的关键指标覆盖缺口。

只测 PerformanceMetrics 运行时真实存在的方法（以 dir() 为准，非源码——
metrics.py 内含一块从未被调用的 list 版重复实现，本测试不碰）。

接口契约（实测）：
- equity 类方法收 DataFrame（列：total_equity / time）
- trade 类方法收 List[Dict]，已平仓交易须带 type∈{SELL,LIQUIDATE} + profit
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import math

import numpy as np
import pandas as pd

from src.backtest.metrics import PerformanceMetrics as M


def _equity(values, freq="D"):
    """构造权益曲线 DataFrame（total_equity + time 列）。"""
    times = pd.date_range("2024-01-01", periods=len(values), freq=freq)
    return pd.DataFrame({"total_equity": values, "time": times})


def _sell(profit):
    """一笔已平仓交易（SELL）。"""
    return {"type": "SELL", "profit": profit}


def _liq(profit):
    return {"type": "LIQUIDATE", "profit": profit}


def _buy(profit=0.0):
    """开仓腿——不应计入已平仓统计。"""
    return {"type": "BUY", "profit": profit}


# ============== equity 类指标 ==============

class TestSortino:
    def test_short_curve_zero(self):
        assert M.sortino_ratio(_equity([100])) == 0.0

    def test_no_downside_positive_mean_is_inf(self):
        # 单调上升 → 无负收益 → inf
        assert M.sortino_ratio(_equity([100, 110, 120, 130])) == float("inf")

    def test_with_downside_is_finite(self):
        eq = _equity([100, 90, 100, 95, 105])
        r = M.sortino_ratio(eq)
        assert math.isfinite(r)

    def test_downside_only_negative_mean_not_positive(self):
        # 单调下降：mean<0 且无…其实全是负收益 → 有下行波动 → 有限且为负
        r = M.sortino_ratio(_equity([100, 90, 80, 70]))
        assert r < 0


class TestMaxDrawdown:
    def test_empty_zero(self):
        assert M.max_drawdown(_equity([])) == 0.0

    def test_monotonic_increasing_zero(self):
        assert M.max_drawdown(_equity([100, 110, 120])) == 0.0

    def test_known_drawdown(self):
        # 100→150→75：峰值150跌到75 → -50%
        dd = M.max_drawdown(_equity([100, 150, 75, 120]))
        assert math.isclose(dd, -0.5, rel_tol=1e-9)


class TestMaxDrawdownDuration:
    def test_short_curve_zero(self):
        assert M.max_drawdown_duration(_equity([100])) == 0.0

    def test_no_drawdown_zero(self):
        assert M.max_drawdown_duration(_equity([100, 110, 120])) == 0.0

    def test_counts_bars_below_peak(self):
        # 峰值在 idx1(110)，之后 90,95,100 三根都低于峰值 → 时长3
        dur = M.max_drawdown_duration(_equity([100, 110, 90, 95, 100]))
        assert dur == 3.0


class TestSharpe:
    def test_short_curve_zero(self):
        assert M.sharpe_ratio(_equity([100])) == 0.0

    def test_constant_equity_zero_vol(self):
        # 零波动 → std=0 → 0.0
        assert M.sharpe_ratio(_equity([100, 100, 100])) == 0.0

    def test_steady_growth_positive(self):
        assert M.sharpe_ratio(_equity([100, 101, 102, 103, 104])) > 0


class TestTotalReturn:
    def test_empty_zero(self):
        assert M.total_return(10000.0, _equity([])) == 0.0

    def test_known(self):
        # 初始10000，末值11000 → 10%
        tr = M.total_return(10000.0, _equity([10000, 10500, 11000]))
        assert math.isclose(tr, 0.1, rel_tol=1e-9)


# ============== trade 类指标 ==============

class TestWinRate:
    def test_empty_zero(self):
        assert M.win_rate([]) == 0.0

    def test_no_closed_trades_zero(self):
        # 只有开仓腿 → 无已平仓 → 0
        assert M.win_rate([_buy(), _buy()]) == 0.0

    def test_ratio_of_winners(self):
        # 3笔平仓，2盈1亏 → 2/3
        trades = [_sell(10), _sell(-5), _sell(20)]
        assert math.isclose(M.win_rate(trades), 2 / 3, rel_tol=1e-9)

    def test_liquidate_counted_as_closed(self):
        # LIQUIDATE 也算已平仓（审计#11 修复点）
        trades = [_sell(10), _liq(-30)]
        assert math.isclose(M.win_rate(trades), 0.5, rel_tol=1e-9)


class TestProfitFactor:
    def test_empty_zero(self):
        assert M.profit_factor([]) == 0.0

    def test_gross_profit_over_gross_loss(self):
        # 盈利100+50=150，亏损50 → 3.0
        trades = [_sell(100), _sell(50), _sell(-50)]
        assert math.isclose(M.profit_factor(trades), 3.0, rel_tol=1e-9)

    def test_no_loss_sentinel(self):
        # 无亏损 + 有盈利 → 哨兵值 999
        assert M.profit_factor([_sell(10), _sell(20)]) == 999.0

    def test_no_profit_no_loss_zero(self):
        assert M.profit_factor([_buy(), _buy()]) == 0.0


class TestAvgTrade:
    def test_empty_zero(self):
        assert M.avg_trade([]) == 0.0

    def test_mean_of_closed_profits(self):
        # (100-50+30)/3
        trades = [_sell(100), _sell(-50), _sell(30)]
        assert math.isclose(M.avg_trade(trades), 80.0 / 3, rel_tol=1e-9)


class TestAvgWinLossRatio:
    def test_empty_zero(self):
        assert M.avg_win_loss_ratio([]) == 0.0

    def test_ratio(self):
        # avg_win=(100+50)/2=75，avg_loss=|(-30)|=30 → 2.5
        trades = [_sell(100), _sell(50), _sell(-30)]
        assert math.isclose(M.avg_win_loss_ratio(trades), 2.5, rel_tol=1e-9)

    def test_no_loss_sentinel(self):
        assert M.avg_win_loss_ratio([_sell(10), _sell(20)]) == 999.0

    def test_no_win_zero(self):
        assert M.avg_win_loss_ratio([_sell(-10), _sell(-20)]) == 0.0


class TestKelly:
    def test_empty_zero(self):
        assert M.kelly_criterion([]) == 0.0

    def test_no_closed_zero(self):
        assert M.kelly_criterion([_buy()]) == 0.0

    def test_known_value(self):
        # 4笔：3盈(各100)1亏(100)。W=0.75，avg_win=100，avg_loss=100，R=1
        # Kelly = 0.75 - 0.25/1 = 0.5
        trades = [_sell(100), _sell(100), _sell(100), _sell(-100)]
        assert math.isclose(M.kelly_criterion(trades), 0.5, rel_tol=1e-9)

    def test_clamped_non_negative(self):
        # 低胜率 → Kelly 公式为负 → clamp 到 0
        trades = [_sell(10), _sell(-100), _sell(-100), _sell(-100)]
        assert M.kelly_criterion(trades) == 0.0

    def test_all_wins_returns_zero(self):
        # 无亏损 → losses==0 → 0（公式无定义，保守返回 0）
        assert M.kelly_criterion([_sell(10), _sell(20)]) == 0.0
