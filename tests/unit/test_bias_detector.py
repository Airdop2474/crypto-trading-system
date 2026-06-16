"""BiasDetector 单元测试，覆盖代码/逻辑/执行检查与报告分支。"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.backtest.bias_detector import BiasDetector
from src.strategy.base import Strategy


class _DangerStrategy(Strategy):
    def __init__(self):
        super().__init__(name="Danger")

    def on_bar(self, data, current_time):
        return data.iloc[-1]["close"]  # 危险：使用当前K线 iloc[-1]


class _SafeStrategy(Strategy):
    def __init__(self):
        super().__init__(name="Safe")

    def on_bar(self, data, current_time):
        return data.iloc[:-1]["close"].mean()  # 安全：排除当前K线


def test_check_strategy_code_flags_danger():
    r = BiasDetector().check_strategy_code(_DangerStrategy())
    assert r["success"] is True
    assert r["has_warnings"] is True
    assert r["warning_count"] >= 1


def test_check_strategy_code_safe_pattern():
    r = BiasDetector().check_strategy_code(_SafeStrategy())
    assert r["has_safe_patterns"] is True


def test_check_backtest_logic_violations():
    d = BiasDetector()
    t1 = datetime(2024, 1, 1)
    results = {
        "signals": [{"time": t1, "signal": "BUY"}],
        # 第二笔无先前信号 + 时间倒序
        "trades": [
            {"time": t1 + timedelta(hours=4), "type": "BUY"},
            {"time": t1 + timedelta(hours=2), "type": "SELL"},
        ],
    }
    r = d.check_backtest_logic(results)
    assert r["has_violations"] is True
    assert r["violation_count"] >= 1


def test_check_order_execution_too_fast():
    d = BiasDetector()
    t1 = datetime(2024, 1, 1)
    results = {
        "signals": [{"time": t1, "signal": "BUY"}],
        "trades": [{"time": t1 + timedelta(minutes=10), "type": "BUY"}],  # <1h 过快
        "equity_curve": [],
    }
    r = d.check_order_execution(results)
    assert r["has_issues"] is True


def test_generate_report_recommendations():
    d = BiasDetector()
    code = d.check_strategy_code(_DangerStrategy())   # 含 high/critical
    logic = {"violation_count": 0, "violations": []}
    execu = {"issue_count": 0, "issues": []}
    rep = d.generate_report(code, logic, execu)
    assert "summary" in rep
    assert isinstance(rep["passed"], bool)
    assert isinstance(rep["recommendation"], str) and rep["recommendation"]


def test_get_recommendation_branches():
    d = BiasDetector()
    assert "严重" in d._get_recommendation(1, 0, 0, 0)
    assert "逻辑" in d._get_recommendation(0, 0, 1, 0)
    assert "执行" in d._get_recommendation(0, 0, 0, 1)
    assert "高风险" in d._get_recommendation(0, 1, 0, 0)
    assert "未发现" in d._get_recommendation(0, 0, 0, 0)
