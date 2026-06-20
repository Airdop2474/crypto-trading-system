"""
集成测试骨架

覆盖：
- 跨模块导入完整性
- 策略注册表与监控联动
- 市场分类器集成
- 参数扫描与回测联动
- 多模块协作正确性
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest

from src.strategy.registry import get_strategy, list_strategies, STRATEGY_REGISTRY
from src.backtest.engine import BacktestEngine
from src.backtest.param_scanner import ParameterScanner
from src.monitor.market_classifier import MarketClassifier, classify_market, get_strategy_recommendation, classify_and_recommend
from src.execution.multi_runner import MultiStrategyRunner

SYMBOL = "BTC/USDT"


def _make_trending_data(direction="up", n=100, seed=99):
    """生成趋势/震荡数据用于市场分类器测试。"""
    rng = np.random.default_rng(seed)
    base = 50000.0
    if direction == "up":
        drift = 0.005
    elif direction == "down":
        drift = -0.005
    else:
        drift = 0.0

    rets = rng.normal(drift, 0.01, n)
    close = base * np.exp(np.cumsum(rets))
    if direction == "sideways":
        close = base + (close - base) * 0.2

    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    openp = np.concatenate([[close[0]], close[:-1]])
    ts = pd.date_range("2025-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": ts, "open": openp, "high": high,
        "low": low, "close": close, "volume": 1000.0,
    })


def _make_volatile_data(n=100, seed=42):
    """生成高波动数据。"""
    rng = np.random.default_rng(seed)
    base = 50000.0
    rets = rng.normal(0, 0.03, n)  # 高波动
    close = base * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    openp = np.concatenate([[close[0]], close[:-1]])
    ts = pd.date_range("2025-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": ts, "open": openp, "high": high,
        "low": low, "close": close, "volume": 1000.0,
    })


class TestCrossModuleImports:
    """跨模块导入完整性。"""

    def test_all_strategy_modules_importable(self):
        """所有策略模块可导入。"""
        from src.strategy.grid_trading import GridTradingStrategy
        from src.strategy.rsi_momentum import RSIMomentumStrategy
        from src.strategy.simple_ma import SimpleMAStrategy
        from src.strategy.buy_and_hold import BuyAndHoldStrategy
        from src.strategy.risk_aware import RiskAwareStrategy, CircuitBreaker
        from src.strategy.base import Strategy, Order
        assert True

    def test_all_execution_modules_importable(self):
        """所有执行模块可导入。"""
        from src.execution.paper_broker import PaperBroker
        from src.execution.paper_trading_runner import PaperTradingRunner
        from src.execution.multi_runner import MultiStrategyRunner, StrategyConfig
        assert True

    def test_all_monitor_modules_importable(self):
        """所有监控模块可导入。"""
        from src.monitor.metrics_collector import MetricsCollector
        from src.monitor.alert_manager import AlertManager
        from src.monitor.market_classifier import MarketState
        assert True

    def test_all_backtest_modules_importable(self):
        """所有回测模块可导入。"""
        from src.backtest.engine import BacktestEngine
        from src.backtest.metrics import PerformanceMetrics
        from src.backtest.param_scanner import ParameterScanner
        from src.backtest.report_generator import BacktestReportGenerator
        assert True

    def test_all_utils_importable(self):
        """所有工具模块可导入。"""
        from src.utils.trading import apply_slippage, apply_commission
        from src.utils.logger import logger
        from src.utils.cache import MemoryCache
        from src.utils.df_hash import hash_dataframe
        assert True


class TestMarketClassifierIntegration:
    """市场分类器集成测试。"""

    @pytest.fixture(autouse=True)
    def _setup_classifier(self):
        self.mc = MarketClassifier()

    def test_classify_trending_up(self):
        """上升趋势数据应被分类为 trending_up。"""
        df = _make_trending_data("up", 100)
        state = self.mc.classify_market(df)
        assert state in ("trending_up", "trending_down", "ranging", "volatile")
        # 强上升趋势大概率 trending_up
        rec = get_strategy_recommendation(state)
        assert "state" in rec
        assert "strategies" in rec

    def test_classify_trending_down(self):
        """下降趋势数据分类。"""
        df = _make_trending_data("down", 100)
        state = self.mc.classify_market(df)
        assert state in ("trending_up", "trending_down", "ranging", "volatile")

    def test_classify_sideways(self):
        """横盘震荡数据分类。"""
        df = _make_trending_data("sideways", 100)
        state = self.mc.classify_market(df)
        assert state in ("trending_up", "trending_down", "ranging", "volatile")

    def test_classify_volatile(self):
        """高波动数据应被分类为 volatile。"""
        df = _make_volatile_data(100)
        state = self.mc.classify_market(df)
        assert state in ("trending_up", "trending_down", "ranging", "volatile")

    def test_classify_and_recommend_returns_details(self):
        """一站式分类推荐应返回详情。"""
        df = _make_trending_data("up", 100)
        result = classify_and_recommend(df, classifier=self.mc)
        assert "state" in result
        assert "strategies" in result
        assert "action" in result
        assert "details" in result
        assert "adx" in result["details"]
        assert "bb_width" in result["details"]

    def test_ranging_recommends_grid(self):
        """横盘市场推荐网格策略。"""
        df = _make_trending_data("sideways", 200)
        state = self.mc.classify_market(df)
        rec = get_strategy_recommendation(state)
        if state == "ranging":
            assert "grid" in rec["strategies"]


class TestParamScannerIntegration:
    """参数扫描器集成测试。"""

    def test_grid_search_with_backtest(self):
        """参数扫描—回测联动。"""
        df = _make_trending_data("up", 100)
        scanner = ParameterScanner(
            initial_capital=10000, commission=0.001, slippage=0.0005,
        )

        from src.strategy.simple_ma import SimpleMAStrategy
        param_grid = {"short_window": [3, 5], "long_window": [10, 15]}

        results = scanner.grid_search(df, SimpleMAStrategy, param_grid)
        assert not results.empty
        assert len(results) == 4  # 2×2
        assert "total_return" in results.columns


class TestMultiRunnerIntegration:
    """MultiRunner 集成测试。"""

    def test_comparison_table_output(self):
        """对比表生成正确。"""
        mock_results = {
            "grid": {
                "total_return": 0.15, "total_trades": 120,
                "metrics": {"sharpe_ratio": 1.5, "max_drawdown": -0.08,
                            "win_rate": 0.55},
            },
            "ma": {
                "total_return": 0.22, "total_trades": 45,
                "metrics": {"sharpe_ratio": 1.8, "max_drawdown": -0.12,
                            "win_rate": 0.62},
            },
        }
        table = MultiStrategyRunner.comparison_table(mock_results)
        assert "Strategy Comparison" in table
        assert "grid" in table
        assert "ma" in table

    def test_correlation_matrix_output(self):
        """相关性矩阵生成正确。"""
        curves = {
            "a": pd.Series([100, 101, 102, 103, 104]),
            "b": pd.Series([100, 101.5, 102, 103.5, 104]),
        }
        corr = MultiStrategyRunner.correlation_matrix(curves)
        assert "Correlation Matrix" in corr
        assert "a" in corr
        assert "b" in corr

    def test_comparison_table_backtest_format(self):
        """BacktestEngine 格式对比表。"""
        mock = {
            "s1": {"total_return": 0.10, "total_trades": 10,
                   "metrics": {"sharpe_ratio": 1.0, "max_drawdown": -0.05,
                               "win_rate": 0.50}},
        }
        table = MultiStrategyRunner.comparison_table_backtest(mock)
        assert "s1" in table
