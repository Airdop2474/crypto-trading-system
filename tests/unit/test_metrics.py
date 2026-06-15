"""
性能指标的单元测试

重点验证夏普比率的周期推断（4h / 日频自动适配）
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics import PerformanceMetrics


def make_equity_curve(values: list, freq: str) -> pd.DataFrame:
    """从权益值列表构建权益曲线，timestamp 按给定频率生成"""
    times = pd.date_range("2024-01-01", periods=len(values), freq=freq)
    return pd.DataFrame({"time": times, "total_equity": values})


class TestInferPeriodsPerYear:
    """周期推断"""

    def test_4h_data(self):
        ec = make_equity_curve([100, 101, 102, 103], freq="4h")
        ppy = PerformanceMetrics._infer_periods_per_year(ec)
        # 4h -> 365 * 24 / 4 = 2190
        assert ppy == pytest.approx(2190.0)

    def test_daily_data(self):
        ec = make_equity_curve([100, 101, 102, 103], freq="1D")
        ppy = PerformanceMetrics._infer_periods_per_year(ec)
        assert ppy == pytest.approx(365.0)

    def test_hourly_data(self):
        ec = make_equity_curve([100, 101, 102, 103], freq="1h")
        ppy = PerformanceMetrics._infer_periods_per_year(ec)
        assert ppy == pytest.approx(365.0 * 24)

    def test_single_row_falls_back(self):
        ec = make_equity_curve([100], freq="4h")
        assert PerformanceMetrics._infer_periods_per_year(ec) == 365.0


class TestSharpeRatio:
    """夏普比率"""

    def test_4h_annualization_factor(self):
        # 固定的日内收益序列，验证年化系数用的是 sqrt(2190) 而非 sqrt(365)
        ec = make_equity_curve([100, 101, 102, 101, 103, 104, 103, 105], freq="4h")
        sharpe = PerformanceMetrics.sharpe_ratio(ec)

        equity = ec["total_equity"].values
        returns = np.diff(equity) / equity[:-1]
        expected = returns.mean() / returns.std() * np.sqrt(2190.0)

        assert sharpe == pytest.approx(expected)

    def test_zero_volatility_returns_zero(self):
        ec = make_equity_curve([100, 100, 100, 100], freq="4h")
        assert PerformanceMetrics.sharpe_ratio(ec) == 0.0

    def test_too_short_returns_zero(self):
        ec = make_equity_curve([100], freq="4h")
        assert PerformanceMetrics.sharpe_ratio(ec) == 0.0

    def test_4h_sharpe_larger_than_daily_assumption(self):
        # 同样的收益序列，按 4h 推断的夏普应比错误的日频假设大 sqrt(2190/365) ≈ 2.45 倍
        ec = make_equity_curve([100, 101, 102, 101, 103, 104, 103, 105], freq="4h")
        sharpe_4h = PerformanceMetrics.sharpe_ratio(ec)

        equity = ec["total_equity"].values
        returns = np.diff(equity) / equity[:-1]
        sharpe_daily_wrong = returns.mean() / returns.std() * np.sqrt(365.0)

        assert sharpe_4h == pytest.approx(sharpe_daily_wrong * np.sqrt(2190.0 / 365.0))
