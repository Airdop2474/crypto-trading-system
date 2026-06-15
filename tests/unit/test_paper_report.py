"""
Paper Trading 报告生成器单元测试

验证：账户价值、已实现/未实现盈亏对账、成本汇总、交易统计、Markdown 渲染。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.execution.paper_report import PaperTradingReportGenerator
from src.strategy.base import Strategy, Order


def make_data(closes):
    times = pd.date_range("2024-01-01", periods=len(closes), freq="4h")
    return pd.DataFrame({
        "timestamp": times,
        "open": closes, "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes], "close": closes,
        "volume": [100.0] * len(closes),
    })


class Scripted(Strategy):
    def __init__(self, signals):
        super().__init__(name="Scripted")
        self.signals = signals
        self.i = -1

    def on_bar(self, data, t):
        self.i += 1
        return self.signals.get(self.i)

    def reset(self):
        super().reset()
        self.i = -1


def run_scenario(signals, closes, balance=100000.0):
    broker = PaperBroker(balance, commission=0.001, slippage={"BTC/USDT": 0.0},
                         max_position_per_trade=1.0, max_total_position=1.0)
    runner = PaperTradingRunner(broker, "BTC/USDT")
    result = runner.run(make_data(closes), Scripted(signals))
    return result, closes[-1]


class TestAccount:
    def test_total_value_and_return(self):
        # 买 @110，最后价 140，持仓未平
        result, last = run_scenario(
            {0: [Order("BUY", tag=1, fraction=0.1)]},
            [100, 110, 120, 130, 140],
        )
        gen = PaperTradingReportGenerator(report_dir="data/reports/test_paper")
        rep = gen.build_report(result, {"BTC/USDT": last})
        acc = rep["account"]
        assert acc["initial_balance"] == 100000.0
        assert acc["total_value"] == pytest.approx(
            acc["cash"] + acc["position_value"]
        )

    def test_pnl_reconciles(self):
        # 已实现 + 未实现 应等于总盈亏
        result, last = run_scenario(
            {0: [Order("BUY", tag=1, fraction=0.1)],
             2: [Order("SELL", tag=1)],
             3: [Order("BUY", tag=2, fraction=0.1)]},
            [100, 110, 120, 130, 140],
        )
        gen = PaperTradingReportGenerator(report_dir="data/reports/test_paper")
        rep = gen.build_report(result, {"BTC/USDT": last})
        total_gain = rep["account"]["total_value"] - 100000.0
        assert (rep["pnl"]["realized"] + rep["pnl"]["unrealized"]) == pytest.approx(
            total_gain
        )


class TestCostAndTrades:
    def test_cost_from_statistics(self):
        result, last = run_scenario(
            {0: [Order("BUY", tag=1, fraction=0.1)]},
            [100, 110, 120],
        )
        gen = PaperTradingReportGenerator(report_dir="data/reports/test_paper")
        rep = gen.build_report(result, {"BTC/USDT": last})
        stats = result["statistics"]
        assert rep["cost_analysis"]["total_cost"] == pytest.approx(stats["total_cost"])

    def test_trade_counts(self):
        result, last = run_scenario(
            {0: [Order("BUY", tag=1, fraction=0.1)],
             2: [Order("SELL", tag=1)]},
            [100, 110, 120, 130],
        )
        gen = PaperTradingReportGenerator(report_dir="data/reports/test_paper")
        rep = gen.build_report(result, {"BTC/USDT": last})
        assert rep["trades"]["buy"] == 1
        assert rep["trades"]["sell"] == 1
        assert rep["trades"]["open_lots"] == 0


class TestRender:
    def test_markdown_contains_sections(self):
        result, last = run_scenario(
            {0: [Order("BUY", tag=1, fraction=0.1)]},
            [100, 110, 120],
        )
        gen = PaperTradingReportGenerator(report_dir="data/reports/test_paper")
        rep = gen.build_report(result, {"BTC/USDT": last})
        md = gen.render_markdown(rep)
        assert "# Paper Trading 报告" in md
        assert "账户" in md
        assert "盈亏" in md
        assert "成本分析" in md
