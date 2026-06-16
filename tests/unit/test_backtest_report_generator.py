"""BacktestReportGenerator 单元测试（构建/渲染/保存/分支）。"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.backtest.report_generator import BacktestReportGenerator
from src.strategy.simple_ma import SimpleMAStrategy


def _results():
    return {
        "success": True,
        "initial_capital": 10000.0,
        "final_equity": 11000.0,
        "total_return": 0.10,
        "total_trades": 4,
        "equity_curve": [
            {"time": datetime(2024, 1, 1), "total_equity": 10000.0},
            {"time": datetime(2024, 1, 2), "total_equity": 11000.0},
        ],
        "metrics": {
            "annual_return": 0.5, "max_drawdown": -0.08, "sharpe_ratio": 1.3,
            "win_rate": 0.6, "profit_factor": 1.8, "avg_trade": 25.0,
        },
        "trades": [
            {"commission": 1.0, "slippage": 0.5},
            {"commission": 2.0, "slippage": 1.0},
        ],
    }


class _NoParamStrategy:
    name = "Bare"
    parameters = {}


def test_build_report_structure(tmp_path):
    gen = BacktestReportGenerator(report_dir=str(tmp_path))
    df = pd.DataFrame({"close": [1, 2, 3]})
    rep = gen.build_report(_results(), SimpleMAStrategy(), data=df,
                           cost_model={"commission": 0.001})
    assert "backtest_id" in rep
    assert rep["metadata"]["strategy_name"] == "SimpleMA"
    assert rep["metadata"]["data_version"] != "N/A"
    assert rep["performance"]["total_return"] == 0.10
    assert rep["performance"]["total_trades"] == 4
    assert rep["cost_analysis"]["total_commission"] == 3.0
    assert rep["cost_analysis"]["total_slippage"] == 1.5


def test_build_report_rejects_failed_backtest(tmp_path):
    gen = BacktestReportGenerator(report_dir=str(tmp_path))
    with pytest.raises(ValueError):
        gen.build_report({"success": False}, SimpleMAStrategy())


def test_render_markdown_with_params_and_hash(tmp_path):
    gen = BacktestReportGenerator(report_dir=str(tmp_path))
    df = pd.DataFrame({"close": [1, 2, 3]})
    rep = gen.build_report(_results(), SimpleMAStrategy(), data=df)
    md = gen.render_markdown(rep)
    assert "# 回测报告" in md
    assert "short_window" in md          # 参数表分支
    assert "总收益率" in md


def test_render_markdown_no_params_no_data(tmp_path):
    gen = BacktestReportGenerator(report_dir=str(tmp_path))
    rep = gen.build_report(_results(), _NoParamStrategy(), data=None)
    md = gen.render_markdown(rep)
    assert "（无记录）" in md             # 空参数分支
    assert "N/A" in md                    # data_version N/A 分支


def test_generate_writes_files(tmp_path):
    gen = BacktestReportGenerator(report_dir=str(tmp_path))
    out = gen.generate(_results(), SimpleMAStrategy(), data=pd.DataFrame({"close": [1, 2]}))
    assert out["json_path"].exists()
    assert out["markdown_path"].exists()
    assert out["report"]["metadata"]["strategy_name"] == "SimpleMA"
