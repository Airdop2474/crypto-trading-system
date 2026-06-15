"""
回测报告生成器的单元测试

验证：成本真实汇总、元信息完整、性能指标映射、Markdown 渲染。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import json
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.report_generator import BacktestReportGenerator
from src.strategy.base import Strategy


def make_data(closes: list) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=len(closes), freq="4h")
    return pd.DataFrame({
        "timestamp": times,
        "open": closes,
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
    })


class BuySellStrategy(Strategy):
    """bar0 买入，bar2 卖出"""

    def __init__(self):
        super().__init__(name="TestBuySell")
        self.set_parameters(foo=1, bar="x")
        self.i = -1

    def on_bar(self, data, current_time):
        self.i += 1
        return {0: "BUY", 2: "SELL"}.get(self.i)

    def reset(self):
        super().reset()
        self.i = -1


@pytest.fixture
def backtest_result():
    data = make_data([100, 110, 120, 130, 140])
    strat = BuySellStrategy()
    engine = BacktestEngine(10000.0, commission=0.001, slippage=0.0005)
    result = engine.run(data, strat)
    return result, strat, data


class TestBuildReport:
    def test_report_has_required_sections(self, backtest_result):
        result, strat, data = backtest_result
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        report = gen.build_report(result, strat, data=data)

        assert "backtest_id" in report
        assert "metadata" in report
        assert "performance" in report
        assert "cost_analysis" in report

    def test_cost_analysis_sums_trades(self, backtest_result):
        result, strat, data = backtest_result
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        report = gen.build_report(result, strat, data=data)

        # 手动汇总交易成本，应与报告一致
        expected_comm = sum(t.get("commission", 0) for t in result["trades"])
        expected_slip = sum(t.get("slippage", 0) for t in result["trades"])
        cost = report["cost_analysis"]
        assert cost["total_commission"] == pytest.approx(expected_comm)
        assert cost["total_slippage"] == pytest.approx(expected_slip)
        assert cost["total_cost"] == pytest.approx(expected_comm + expected_slip)

    def test_metadata_records_params_and_version(self, backtest_result):
        result, strat, data = backtest_result
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        report = gen.build_report(result, strat, data=data)
        meta = report["metadata"]

        assert meta["strategy_name"] == "TestBuySell"
        assert meta["parameters"] == {"foo": 1, "bar": "x"}
        assert meta["initial_balance"] == 10000.0
        # 提供了 data，应有 SHA256（64 位十六进制）
        assert len(meta["data_version"]) == 64

    def test_no_data_version_na(self, backtest_result):
        result, strat, _ = backtest_result
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        report = gen.build_report(result, strat, data=None)
        assert report["metadata"]["data_version"] == "N/A"

    def test_unsuccessful_raises(self):
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        with pytest.raises(ValueError):
            gen.build_report({"success": False}, None)


class TestRenderMarkdown:
    def test_markdown_contains_key_fields(self, backtest_result):
        result, strat, data = backtest_result
        gen = BacktestReportGenerator(report_dir="data/reports/test")
        report = gen.build_report(result, strat, data=data)
        md = gen.render_markdown(report)

        assert "# 回测报告" in md
        assert "TestBuySell" in md
        assert "性能指标" in md
        assert "成本分析" in md


class TestReproducibility:
    def test_same_input_same_performance(self):
        """相同输入产生相同性能指标（可复现性）"""
        data = make_data([100, 110, 120, 130, 140])
        gen = BacktestReportGenerator(report_dir="data/reports/test")

        reports = []
        for _ in range(2):
            strat = BuySellStrategy()
            engine = BacktestEngine(10000.0, commission=0.001, slippage=0.0005)
            result = engine.run(data, strat)
            reports.append(gen.build_report(result, strat, data=data))

        assert reports[0]["performance"] == reports[1]["performance"]
        assert reports[0]["cost_analysis"] == reports[1]["cost_analysis"]
        # backtest_id 是 uuid，应不同
        assert reports[0]["backtest_id"] != reports[1]["backtest_id"]
