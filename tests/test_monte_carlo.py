"""
Monte Carlo 模拟器单元测试

覆盖：
- 交易 Bootstrap（5 用例）
- 收益率重采样（3 用例）
- 边界条件（4 用例）
- 性能验证（1 用例）
"""

import time
import pytest
import numpy as np

from src.backtest.monte_carlo import MonteCarloSimulator, MonteCarloResult


def _make_trades(profits: list) -> list:
    """构造交易记录"""
    return [{"type": "SELL", "profit": p} for p in profits]


def _make_equity_curve(prices: list) -> list:
    """构造权益曲线"""
    return [{"total_equity": p} for p in prices]


class TestTradeBootstrap:
    """交易 Bootstrap 测试"""

    def test_basic_bootstrap(self):
        """基本 bootstrap 产生合理结果"""
        trades = _make_trades([100, -50, 200, -30, 150, -80, 50, -20])
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)

        assert result.n_simulations == 500
        assert result.method == "trade_bootstrap"
        # 中位数收益应该为正（正期望的交易序列）
        assert result.return_median > 0

    def test_all_winning_trades(self):
        """全盈利交易的 bootstrap"""
        trades = _make_trades([100, 200, 150, 80, 120])
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)

        # 全盈利 → 亏损概率应为 0
        assert result.loss_probability == 0
        assert result.profit_probability == 1.0
        assert result.ruin_probability == 0

    def test_all_losing_trades(self):
        """全亏损交易的 bootstrap"""
        trades = _make_trades([-100, -200, -150, -80, -120])
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)

        # 全亏损 → 盈利概率应为 0
        assert result.profit_probability == 0
        assert result.loss_probability == 1.0
        assert result.return_median < 0

    def test_percentiles_ordered(self):
        """百分位有序：p5 < p25 < median < p75 < p95"""
        trades = _make_trades([100, -50, 200, -30, 150, -80, 50, -20, 300, -100])
        mc = MonteCarloSimulator(n_simulations=1000, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)

        assert result.return_p5 <= result.return_p25
        assert result.return_p25 <= result.return_median
        assert result.return_median <= result.return_p75
        assert result.return_p75 <= result.return_p95

    def test_reproducible_with_seed(self):
        """相同种子产生相同结果"""
        trades = _make_trades([100, -50, 200, -30, 150])
        mc1 = MonteCarloSimulator(n_simulations=100, random_seed=42)
        r1 = mc1.run(trades=trades, initial_capital=10000)
        mc2 = MonteCarloSimulator(n_simulations=100, random_seed=42)
        r2 = mc2.run(trades=trades, initial_capital=10000)

        assert r1.return_median == r2.return_median
        assert r1.max_dd_p95 == r2.max_dd_p95


class TestReturnResample:
    """收益率重采样测试"""

    def test_basic_resample(self):
        """基本收益率重采样"""
        equity = _make_equity_curve(
            [10000, 10100, 9950, 10200, 10050, 10300, 10100, 10400,
             10350, 10500, 10400, 10600, 10550, 10700]
        )
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(
            trades=[], equity_curve=equity, initial_capital=10000,
            method="return_resample",
        )

        assert result.method == "return_resample"
        assert result.n_simulations == 500

    def test_uptrend_equity(self):
        """上升趋势的权益曲线"""
        equity = _make_equity_curve([10000 + i * 100 for i in range(20)])
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(
            trades=[], equity_curve=equity, initial_capital=10000,
            method="return_resample",
        )
        # 上升趋势 → 中位数收益应偏正
        assert result.return_median > 0

    def test_downtrend_equity(self):
        """下降趋势的权益曲线"""
        equity = _make_equity_curve([10000 - i * 100 for i in range(20)])
        mc = MonteCarloSimulator(n_simulations=500, random_seed=42)
        result = mc.run(
            trades=[], equity_curve=equity, initial_capital=10000,
            method="return_resample",
        )
        assert result.return_median < 0


class TestEdgeCases:
    """边界条件测试"""

    def test_empty_trades(self):
        """空交易列表"""
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        result = mc.run(trades=[], initial_capital=10000)
        assert result.n_simulations == 0  # 空结果

    def test_few_trades(self):
        """交易太少（< 5）"""
        trades = _make_trades([100, -50])
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)
        # 应该仍然返回结果，但日志会警告
        assert result.n_simulations == 100

    def test_short_equity_curve(self):
        """权益曲线太短"""
        equity = _make_equity_curve([10000, 10100])
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        result = mc.run(
            trades=[], equity_curve=equity, initial_capital=10000,
            method="return_resample",
        )
        assert result.n_simulations == 0  # 空结果

    def test_invalid_method(self):
        """无效方法名"""
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        with pytest.raises(ValueError):
            mc.run(trades=_make_trades([100]), initial_capital=10000, method="invalid")


class TestPerformance:
    """性能测试"""

    def test_1000_simulations_under_5_seconds(self):
        """1000 次模拟 < 5 秒"""
        trades = _make_trades(
            [100, -50, 200, -30, 150, -80, 50, -20, 300, -100,
             80, -40, 120, -60, 90, -30, 200, -80, 150, -50]
        )
        mc = MonteCarloSimulator(n_simulations=1000, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)

        assert result.elapsed_seconds < 5.0, (
            f"Monte Carlo took {result.elapsed_seconds:.2f}s, expected < 5s"
        )


class TestResultFormat:
    """结果格式测试"""

    def test_to_dict(self):
        """to_dict 返回正确结构"""
        trades = _make_trades([100, -50, 200])
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)
        d = result.to_dict()

        assert "n_simulations" in d
        assert "method" in d
        assert "return" in d
        assert "max_drawdown" in d
        assert "sharpe" in d
        assert "risk" in d
        assert "elapsed_seconds" in d
        assert "median" in d["return"]
        assert "p95" in d["max_drawdown"]
        assert "cvar_95" in d["max_drawdown"]

    def test_summary_string(self):
        """summary 返回可读字符串"""
        trades = _make_trades([100, -50, 200])
        mc = MonteCarloSimulator(n_simulations=100, random_seed=42)
        result = mc.run(trades=trades, initial_capital=10000)
        s = result.summary()

        assert "Monte Carlo" in s
        assert "收益率" in s
        assert "最大回撤" in s
        assert "Sharpe" in s
