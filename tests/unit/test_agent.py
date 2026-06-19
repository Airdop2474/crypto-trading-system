"""
AI Agent 模块单元测试

覆盖：
- AuditLog 审计日志
- TradingAnalyzer 5 种分析类型
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.agent.audit_log import AuditLog
from src.agent.analyzer import TradingAnalyzer


# --------------------------------------------------------------------------
# AuditLog 测试
# --------------------------------------------------------------------------
class TestAuditLog:
    """审计日志测试"""

    def test_record_and_retrieve(self, tmp_path):
        """记录并检索日志"""
        log = AuditLog(log_dir=str(tmp_path))

        entry_id = log.record(
            task="backtest",
            phase="Phase 2",
            input_summary={"strategy": "test"},
            output_summary={"confidence": 0.8},
        )

        assert entry_id.startswith("backtest_")
        logs = log.get_logs()
        assert len(logs) == 1
        assert logs[0]["task"] == "backtest"
        assert logs[0]["human_approved"] is False

    def test_update_approval(self, tmp_path):
        """更新采纳状态"""
        log = AuditLog(log_dir=str(tmp_path))

        entry_id = log.record(
            task="backtest",
            phase="Phase 2",
            input_summary={},
            output_summary={},
        )

        result = log.update_approval(entry_id, approved=True, action="applied_suggestion")
        assert result is True

        logs = log.get_logs()
        assert logs[0]["human_approved"] is True
        assert logs[0]["action_taken"] == "applied_suggestion"

    def test_update_nonexistent(self, tmp_path):
        """更新不存在的条目"""
        log = AuditLog(log_dir=str(tmp_path))
        result = log.update_approval("nonexistent_id", True)
        assert result is False

    def test_filter_by_task(self, tmp_path):
        """按任务类型过滤"""
        log = AuditLog(log_dir=str(tmp_path))

        log.record("backtest", "Phase 2", {}, {})
        log.record("weekly_review", "Phase 6", {}, {})
        log.record("backtest", "Phase 3", {}, {})

        backtest_logs = log.get_logs(task="backtest")
        assert len(backtest_logs) == 2

        weekly_logs = log.get_logs(task="weekly_review")
        assert len(weekly_logs) == 1

    def test_adoption_rate(self, tmp_path):
        """统计采纳率"""
        log = AuditLog(log_dir=str(tmp_path))

        # 3 次调用，2 次采纳
        id1 = log.record("backtest", "Phase 2", {}, {})
        id2 = log.record("backtest", "Phase 2", {}, {})
        log.record("backtest", "Phase 2", {}, {})

        log.update_approval(id1, True)
        log.update_approval(id2, True)

        stats = log.get_adoption_rate()
        assert stats["total_calls"] == 3
        assert stats["approved"] == 2
        assert abs(stats["adoption_rate"] - 2/3) < 0.01

    def test_adoption_rate_empty(self, tmp_path):
        """空日志的采纳率"""
        log = AuditLog(log_dir=str(tmp_path))
        stats = log.get_adoption_rate()
        assert stats["total_calls"] == 0
        assert stats["adoption_rate"] == 0.0


# --------------------------------------------------------------------------
# TradingAnalyzer 测试
# --------------------------------------------------------------------------
class TestTradingAnalyzer:
    """AI 分析引擎测试"""

    @pytest.fixture
    def analyzer(self, tmp_path):
        """创建带临时日志的分析器"""
        audit = AuditLog(log_dir=str(tmp_path))
        return TradingAnalyzer(audit_log=audit)

    # ----- 1. 回测分析 -----
    def test_analyze_backtest_basic(self, analyzer):
        """基本回测分析"""
        results = {
            "success": True,
            "total_return": 0.15,
            "total_trades": 50,
            "trades": [
                {"pnl": 100}, {"pnl": -50}, {"pnl": 80},
                {"pnl": -30}, {"pnl": 120},
            ] * 10,
            "equity_curve": [
                {"equity": 10000 + i * 30} for i in range(50)
            ],
            "metrics": {
                "win_rate": 0.6,
                "sharpe_ratio": 1.2,
                "max_drawdown": 0.08,
                "sortino_ratio": 1.5,
                "profit_factor": 1.8,
                "kelly_criterion": 0.2,
            },
        }

        report = analyzer.analyze_backtest(results, strategy_name="TestStrategy")

        assert report["task"] == "backtest_analysis"
        assert report["strategy_name"] == "TestStrategy"
        assert report["requires_human_approval"] is True
        assert report["confidence"] > 0

    def test_analyze_backtest_no_trades(self, analyzer):
        """无交易的回测"""
        results = {
            "success": True,
            "total_return": 0.0,
            "total_trades": 0,
            "trades": [],
            "equity_curve": [],
            "metrics": {},
        }

        report = analyzer.analyze_backtest(results)
        assert "无交易" in report["reasoning"]["return_source"]["source"]

    # ----- 2. 失败交易归因 -----
    def test_analyze_failed_trades(self, analyzer):
        """失败交易归因"""
        trades = [
            {"pnl": 100, "time": "2026-01-01T10:00:00"},
            {"pnl": -50, "time": "2026-01-01T14:00:00"},
            {"pnl": -30, "time": "2026-01-02T08:00:00"},
            {"pnl": 80, "time": "2026-01-02T12:00:00"},
            {"pnl": -60, "time": "2026-01-03T16:00:00"},
        ]

        report = analyzer.analyze_failed_trades(trades)

        assert report["task"] == "trade_attribution"
        assert report["reasoning"]["loss_patterns"]["total_loss_count"] == 3
        assert report["requires_human_approval"] is True

    def test_analyze_failed_trades_empty(self, analyzer):
        """空交易列表"""
        report = analyzer.analyze_failed_trades([])
        assert "无交易记录" in report["analysis"]

    def test_analyze_failed_trades_all_winners(self, analyzer):
        """全部盈利"""
        trades = [{"pnl": 100}, {"pnl": 50}, {"pnl": 80}]
        report = analyzer.analyze_failed_trades(trades)
        assert "无亏损交易" in report["analysis"]

    def test_max_consecutive_losses(self, analyzer):
        """最大连续亏损"""
        trades = [
            {"pnl": 100}, {"pnl": -50}, {"pnl": -30},
            {"pnl": -20}, {"pnl": 80}, {"pnl": -10},
        ]

        max_consec = analyzer._max_consecutive_losses(trades)
        assert max_consec == 3  # 连续 3 笔亏损

    # ----- 3. 风险清单检查 -----
    def test_analyze_risk_checklist_all_pass(self, analyzer):
        """全部通过的风险清单"""
        checklist = {
            "paper_trading_days": 65,
            "risk_tests_passed": True,
            "api_key_restricted": True,
            "initial_capital": 500,
            "max_drawdown": 0.05,
            "data_quality_score": 0.995,
            "consecutive_losses": 2,
            "win_rate": 0.55,
        }

        report = analyzer.analyze_risk_checklist(checklist)

        assert report["task"] == "risk_checklist"
        assert report["confidence"] == 1.0
        assert report["reasoning"]["passed"] == 6

    def test_analyze_risk_checklist_failures(self, analyzer):
        """有未通过项的清单"""
        checklist = {
            "paper_trading_days": 30,  # 不足 60 天
            "risk_tests_passed": False,  # 未通过
            "api_key_restricted": False,  # 未限制
            "initial_capital": 1000,  # 超过 500
            "max_drawdown": 0.15,  # 超过 10%
            "data_quality_score": 0.95,  # 低于 99%
        }

        report = analyzer.analyze_risk_checklist(checklist)

        assert report["reasoning"]["passed"] == 0
        assert len(report["reasoning"]["failed"]) == 6
        assert len(report["risks"]) >= 6

    # ----- 4. 参数敏感性分析 -----
    def test_analyze_param_sensitivity(self, analyzer):
        """参数敏感性分析"""
        # 构造模拟的扫描结果
        df = pd.DataFrame({
            "grid_count": [8, 10, 12, 15, 20],
            "lower_price": [50000, 50000, 50000, 50000, 50000],
            "upper_price": [70000, 70000, 70000, 70000, 70000],
            "total_return": [0.08, 0.12, 0.10, 0.05, -0.02],
            "sharpe_ratio": [0.8, 1.2, 1.0, 0.5, -0.3],
            "max_drawdown": [0.05, 0.06, 0.07, 0.09, 0.12],
        })

        report = analyzer.analyze_param_sensitivity(df)

        assert report["task"] == "param_sensitivity"
        assert "parameter_sensitivity" in report["reasoning"]
        assert report["requires_human_approval"] is True

    def test_analyze_param_sensitivity_empty(self, analyzer):
        """空的扫描结果"""
        df = pd.DataFrame()
        report = analyzer.analyze_param_sensitivity(df)
        assert "无扫描结果" in report["analysis"]

    # ----- 5. 每周策略复盘 -----
    def test_analyze_weekly_review(self, analyzer):
        """每周复盘分析"""
        paper_report = {
            "account": {
                "initial_balance": 10000,
                "cash": 9500,
                "position_value": 800,
                "total_value": 10300,
                "total_return": 0.03,
            },
            "pnl": {
                "realized": 400,
                "unrealized": -100,
            },
            "cost_analysis": {
                "total_commission": 50,
                "total_slippage": 25,
                "total_cost": 75,
            },
            "trades": {
                "total": 20,
                "buy": 12,
                "sell": 8,
                "open_lots": 5,
            },
        }

        report = analyzer.analyze_weekly_review(paper_report)

        assert report["task"] == "weekly_review"
        assert report["reasoning"]["performance"]["rating"] == "good"
        assert report["requires_human_approval"] is True

    def test_analyze_weekly_review_poor_performance(self, analyzer):
        """表现差的周报"""
        paper_report = {
            "account": {"total_return": -0.06},
            "pnl": {"realized": -500, "unrealized": -100},
            "cost_analysis": {"total_cost": 100},
            "trades": {"total": 5, "buy": 4, "sell": 1, "open_lots": 3},
        }

        report = analyzer.analyze_weekly_review(paper_report)

        assert report["reasoning"]["performance"]["rating"] in ["poor", "critical"]
        assert len(report["risks"]) > 0


# --------------------------------------------------------------------------
# 集成测试：模块导出
# --------------------------------------------------------------------------
class TestAgentExports:
    """模块导出测试"""

    def test_imports(self):
        """验证模块可以正确导入"""
        from src.agent import TradingAnalyzer, AuditLog
        assert TradingAnalyzer is not None
        assert AuditLog is not None

    def test_analyzer_has_all_methods(self):
        """验证分析器包含所有5种分析方法"""
        analyzer = TradingAnalyzer()
        assert hasattr(analyzer, "analyze_backtest")
        assert hasattr(analyzer, "analyze_failed_trades")
        assert hasattr(analyzer, "analyze_risk_checklist")
        assert hasattr(analyzer, "analyze_param_sensitivity")
        assert hasattr(analyzer, "analyze_weekly_review")
