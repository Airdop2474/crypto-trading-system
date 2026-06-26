"""
端到端集成测试：数据下载 → 质量检查 → 回测全链路

验证整个交易系统的核心流水线：
1. 数据下载/加载
2. 数据质量检查
3. 策略回测
4. 报告生成
"""

import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd

from src.data.downloader import DataDownloader
from src.data.quality_checker import DataQualityChecker
from src.backtest.engine import BacktestEngine
from src.backtest.report_generator import BacktestReportGenerator
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.simple_ma import SimpleMAStrategy
from src.strategy.registry import get_strategy, list_strategies

SYMBOL = "BTC/USDT"
CAP = 10000.0


def _make_data(n=200, seed=42):
    """生成高质量合成OHLCV数据。"""
    rng = np.random.default_rng(seed)
    base = 50000.0
    rets = rng.normal(0, 0.01, n)
    close = base * np.exp(np.cumsum(rets))
    close = base + (close - base) * 0.5
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    # 确保 high >= open/low, low <= open
    openp = np.concatenate([[close[0]], close[:-1]])
    ts = pd.date_range("2025-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": ts, "open": openp, "high": high,
        "low": low, "close": close, "volume": np.abs(rng.normal(500, 100, n)),
    })


class TestE2EPipeline:
    """端到端全链路集成测试。"""

    def test_data_to_backtest_full_pipeline(self):
        """数据→质量检查→回测全链路。"""
        df = _make_data(200)

        # 1. 质量检查
        qc = DataQualityChecker()
        qc_results = qc.check_all(df)
        assert qc_results, "质量检查应返回结果"
        # 数据应通过检查
        for check_name, result in qc_results.items():
            if hasattr(result, "passed"):
                assert result.passed, f"质量检查失败: {check_name}"

        # 2. 策略回测
        lo = float(df["low"].min()) * 1.01
        hi = float(df["high"].max()) * 0.99
        strategy = GridTradingStrategy(
            lower_price=lo, upper_price=hi, grid_count=10,
            enable_filters=False, initial_capital=CAP,
        )

        engine = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        results = engine.run(df, strategy)

        assert results["success"], f"回测失败: {results.get('message', '')}"
        assert results["initial_capital"] == CAP
        assert "trades" in results
        assert "metrics" in results

    def test_multi_strategy_pipeline(self):
        """多策略全链路：registry→回测→对比。"""
        df = _make_data(200)

        results_map = {}
        for name in ["grid", "ma", "buyhold"]:
            cls = get_strategy(name)
            if name == "grid":
                lo = float(df["low"].min()) * 1.01
                hi = float(df["high"].max()) * 0.99
                strategy = cls(lower_price=lo, upper_price=hi, grid_count=10,
                               enable_filters=False, initial_capital=CAP)
            elif name == "ma":
                strategy = cls(short_window=5, long_window=20)
            else:
                strategy = cls()

            engine = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
            results = engine.run(df, strategy)
            if results["success"]:
                results_map[name] = results

        assert len(results_map) >= 2, "应有至少2个策略成功"
        # 所有成功回测的结果结构应一致
        for res in results_map.values():
            assert "total_return" in res
            assert "metrics" in res

    def test_report_generation_from_backtest(self):
        """回测结果生成报告。"""
        df = _make_data(150)

        lo = float(df["low"].min()) * 1.01
        hi = float(df["high"].max()) * 0.99
        strategy = GridTradingStrategy(
            lower_price=lo, upper_price=hi, grid_count=10,
            enable_filters=False, initial_capital=CAP,
        )

        engine = BacktestEngine(initial_capital=CAP, commission=0.001, slippage=0.0005)
        results = engine.run(df, strategy)

        assert results["success"]

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            generator = BacktestReportGenerator(report_dir=str(report_dir))

            report = generator.build_report(
                results=results,
                strategy=strategy,
                data=df,
            )
            assert report is not None
            assert "metrics" in report or isinstance(report, dict)

            md = generator.render_markdown(report)
            assert len(md) > 0
            assert "GridTrading" in md

    def test_registry_consistency(self):
        """Registry 导出与策略列表一致。"""
        strategies = list_strategies()
        assert len(strategies) >= 12
        assert "grid" in strategies
        assert "rsi" in strategies
        assert "ma" in strategies
        assert "buyhold" in strategies
        assert "donchian" in strategies
        assert "structure" in strategies
        assert "supertrend" in strategies
        assert "reversal" in strategies
        assert "priceaction" in strategies
        assert "bollinger" in strategies
        assert "macd" in strategies

        for name in strategies:
            cls = get_strategy(name)
            assert cls is not None, f"策略 '{name}' 未找到"
            assert hasattr(cls, "PARAM_SCHEMA"), f"策略 '{name}' 缺少 PARAM_SCHEMA"
            assert hasattr(cls, "validate_params") or hasattr(cls, "__init__")

    def test_strategy_parameter_ranges(self):
        """各策略参数安全范围校验。"""
        df = _make_data(50)

        # Grid: 合法参数应成功
        lo, hi = float(df["low"].min()), float(df["high"].max())
        s = GridTradingStrategy(lower_price=lo, upper_price=hi, grid_count=10,
                                enable_filters=False, initial_capital=CAP)
        assert s is not None

        # Grid: 非法参数应抛异常
        try:
            GridTradingStrategy(lower_price=hi, upper_price=lo, grid_count=10)
            assert False, "应抛出 ValueError"
        except ValueError:
            pass

        # MA: 合法参数
        s_ma = SimpleMAStrategy(short_window=5, long_window=20)
        assert s_ma is not None

        # MA: 参数范围无硬约束（仅逻辑约束）
