"""
AI Agent 分析引擎

提供 5 种分析类型（AI_USAGE_BOUNDARIES.md 规范）：
1. 回测报告解释
2. 失败交易归因
3. 风险清单检查
4. 参数敏感性分析总结
5. 每周策略复盘

核心原则：
- 只分析，不自动执行
- 所有输出标注"需要人工确认"
- 完整审计日志
- 结构化 JSON 输出

输出格式（统一）：
{
  "analysis": "分析结论",
  "reasoning": "推理过程",
  "recommendation": "建议",
  "risks": ["风险提示列表"],
  "requires_human_approval": true,
  "confidence": 0.0-1.0
}
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from src.utils.logger import logger
from src.agent.audit_log import AuditLog
from src.agent.memory import ContextBuilder, MemoryKind, get_memory_store


class TradingAnalyzer:
    """AI 交易分析引擎（只分析，不执行）"""

    def __init__(self, audit_log: Optional[AuditLog] = None):
        self.audit_log = audit_log or AuditLog()
        self._ctx = ContextBuilder()
        self._memory = get_memory_store()

    # ------------------------------------------------------------------
    # 1. 回测报告解释
    # ------------------------------------------------------------------
    def analyze_backtest(
        self,
        results: Dict[str, Any],
        metrics: Optional[Dict[str, float]] = None,
        strategy_name: str = "Unknown",
    ) -> Dict[str, Any]:
        """
        分析回测结果，解释收益来源、回撤原因、潜在风险

        参数：
            results: BacktestEngine.run() 返回的结果
            metrics: 性能指标（可选，从 results 中提取）
            strategy_name: 策略名称

        返回：
            结构化分析报告
        """
        if metrics is None:
            metrics = results.get("metrics", {})

        total_return = results.get("total_return", 0.0)
        trades = results.get("trades", [])
        total_trades = len(trades)
        win_rate = metrics.get("win_rate", 0.0)
        sharpe = metrics.get("sharpe_ratio", 0.0)
        max_dd = metrics.get("max_drawdown", 0.0)
        sortino = metrics.get("sortino_ratio", 0.0)
        kelly = metrics.get("kelly_criterion", 0.0)
        profit_factor = metrics.get("profit_factor", 0.0)

        # 注入历史记忆上下文
        memory_ctx = self._ctx.build_analysis_context(strategy_name, "backtest")
        has_memory = bool(memory_ctx)

        # 收益来源分析
        source = self._analyze_return_source(trades, total_return)

        # 回撤分析
        dd_analysis = self._analyze_drawdown(results, max_dd)

        # 风险评估
        risks = self._assess_backtest_risks(metrics, total_trades)

        # 综合判断
        confidence = self._calculate_backtest_confidence(metrics, total_trades)

        # 写入记忆
        self._memory.store(
            MemoryKind.ANALYSIS,
            content={
                "strategy": strategy_name,
                "total_return": total_return,
                "win_rate": win_rate,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "total_trades": total_trades,
            },
            tags=[strategy_name, "backtest"],
            source="analyzer",
        )

        report = {
            "task": "backtest_analysis",
            "strategy_name": strategy_name,
            "analysis": self._format_backtest_analysis(
                total_return, win_rate, sharpe, max_dd, source, dd_analysis
            ),
            "reasoning": {
                "return_source": source,
                "drawdown_analysis": dd_analysis,
                "memory_context": memory_ctx if has_memory else None,
                "key_metrics": {
                    "total_return": total_return,
                    "win_rate": win_rate,
                    "sharpe_ratio": sharpe,
                    "sortino_ratio": sortino,
                    "max_drawdown": max_dd,
                    "profit_factor": profit_factor,
                    "kelly_criterion": kelly,
                },
            },
            "recommendation": self._backtest_recommendation(metrics, risks),
            "risks": risks,
            "requires_human_approval": True,
            "confidence": confidence,
        }

        # 审计日志
        self.audit_log.record(
            task="backtest",
            phase="Phase 2-3",
            input_summary={
                "strategy_name": strategy_name,
                "total_return": total_return,
                "total_trades": total_trades,
            },
            output_summary={
                "confidence": confidence,
                "recommendation": report["recommendation"][:100],
            },
        )

        logger.info(f"Backtest analysis completed for {strategy_name}")
        return report

    # ------------------------------------------------------------------
    # 2. 失败交易归因
    # ------------------------------------------------------------------
    def analyze_failed_trades(
        self,
        trades: List[Dict[str, Any]],
        equity_curve: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        分析失败交易，找出亏损模式、信号问题、改进建议

        参数：
            trades: 交易记录列表（每笔需有 pnl 字段）
            equity_curve: 权益曲线（可选）

        返回：
            结构化归因报告
        """
        if not trades:
            return self._empty_report("trade_attribution", "无交易记录")

        # 分离盈亏交易
        winners = [t for t in trades if t.get("pnl", 0) > 0]
        losers = [t for t in trades if t.get("pnl", 0) < 0]

        if not losers:
            return self._empty_report("trade_attribution", "无亏损交易")

        # 亏损模式分析
        patterns = self._analyze_loss_patterns(losers, trades)

        # 信号质量评估
        signal_quality = self._assess_signal_quality(winners, losers)

        # 最大连续亏损
        max_consecutive = self._max_consecutive_losses(trades)

        # 时间分布
        time_dist = self._analyze_loss_time_distribution(losers)

        risks = []
        if max_consecutive >= 5:
            risks.append(f"最大连续亏损 {max_consecutive} 笔，可能触发风控熔断")
        if signal_quality["false_signal_rate"] > 0.5:
            risks.append(f"假信号率 {signal_quality['false_signal_rate']:.2%}，信号质量差")
        if patterns["avg_loss_magnitude"] > patterns["avg_win_magnitude"] * 2:
            risks.append("平均亏损幅度超过平均盈利的 2 倍，盈亏比失衡")

        report = {
            "task": "trade_attribution",
            "analysis": self._format_attribution_analysis(
                len(losers), len(trades), patterns, signal_quality
            ),
            "reasoning": {
                "loss_patterns": patterns,
                "signal_quality": signal_quality,
                "max_consecutive_losses": max_consecutive,
                "time_distribution": time_dist,
            },
            "recommendation": self._attribution_recommendation(patterns, signal_quality),
            "risks": risks,
            "requires_human_approval": True,
            "confidence": 0.7 if len(losers) >= 10 else 0.5,
        }

        # 审计日志
        self.audit_log.record(
            task="trade_attribution",
            phase="Phase 4-6",
            input_summary={
                "total_trades": len(trades),
                "losing_trades": len(losers),
            },
            output_summary={
                "max_consecutive_losses": max_consecutive,
                "false_signal_rate": signal_quality["false_signal_rate"],
            },
        )

        logger.info(f"Trade attribution analysis: {len(losers)} losing trades analyzed")
        return report

    # ------------------------------------------------------------------
    # 3. 风险清单检查
    # ------------------------------------------------------------------
    def analyze_risk_checklist(self, checklist: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查实盘准备清单，识别遗漏风险

        参数：
            checklist: 风险清单数据，格式如：
                {
                    "paper_trading_days": 45,
                    "risk_tests_passed": True,
                    "api_key_restricted": True,
                    "initial_capital": 500,
                    "max_drawdown": 0.08,
                    "consecutive_losses": 3,
                    "data_quality_score": 0.99,
                    ...
                }

        返回：
            结构化风险检查报告
        """
        # 强制检查项
        mandatory_checks = {
            "paper_trading_days": {
                "required": 60,
                "actual": checklist.get("paper_trading_days", 0),
                "pass": checklist.get("paper_trading_days", 0) >= 60,
            },
            "risk_tests_passed": {
                "required": True,
                "actual": checklist.get("risk_tests_passed", False),
                "pass": checklist.get("risk_tests_passed", False) is True,
            },
            "api_key_restricted": {
                "required": True,
                "actual": checklist.get("api_key_restricted", False),
                "pass": checklist.get("api_key_restricted", False) is True,
            },
            "initial_capital_le__500": {
                "required": "<= 500",
                "actual": checklist.get("initial_capital", 0),
                "pass": 0 < checklist.get("initial_capital", 0) <= 500,
            },
            "max_drawdown_lt_10pct": {
                "required": "< 10%",
                "actual": checklist.get("max_drawdown", 1.0),
                "pass": checklist.get("max_drawdown", 1.0) < 0.10,
            },
            "data_quality_score_gt_99pct": {
                "required": "> 99%",
                "actual": checklist.get("data_quality_score", 0.0),
                "pass": checklist.get("data_quality_score", 0.0) >= 0.99,
            },
        }

        passed = sum(1 for c in mandatory_checks.values() if c["pass"])
        total = len(mandatory_checks)

        risks = []
        failed = []
        for name, check in mandatory_checks.items():
            if not check["pass"]:
                failed.append(name)
                risks.append(f"未通过：{name} (要求 {check['required']}, 实际 {check['actual']})")

        # 可选检查项（警告级别）
        warnings = []
        if checklist.get("consecutive_losses", 0) >= 4:
            warnings.append(f"连续亏损 {checklist['consecutive_losses']} 笔，接近熔断阈值")
        if checklist.get("win_rate", 0) < 0.4:
            warnings.append(f"胜率 {checklist.get('win_rate', 0):.2%}，偏低")

        report = {
            "task": "risk_checklist",
            "analysis": f"风险清单检查：{passed}/{total} 项通过" +
                       (f"，{len(warnings)} 项警告" if warnings else ""),
            "reasoning": {
                "mandatory_checks": mandatory_checks,
                "passed": passed,
                "total": total,
                "failed": failed,
            },
            "recommendation": "可以进入实盘" if passed == total and not warnings else
                            "需要修复未通过项" if failed else
                            "可以通过，但请注意警告项",
            "risks": risks + [f"警告：{w}" for w in warnings],
            "requires_human_approval": True,
            "confidence": 1.0 if passed == total else 0.3,
        }

        # 审计日志
        self.audit_log.record(
            task="risk_checklist",
            phase="Phase 5-6",
            input_summary={
                "paper_trading_days": checklist.get("paper_trading_days", 0),
                "initial_capital": checklist.get("initial_capital", 0),
            },
            output_summary={
                "passed": passed,
                "total": total,
                "failed": failed,
            },
        )

        logger.info(f"Risk checklist analysis: {passed}/{total} passed")
        return report

    # ------------------------------------------------------------------
    # 4. 参数敏感性分析总结
    # ------------------------------------------------------------------
    def analyze_param_sensitivity(
        self,
        scan_results: pd.DataFrame,
        base_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        总结参数敏感性测试结果，识别最敏感参数和过拟合风险

        参数：
            scan_results: ParameterScanner.grid_search() 返回的 DataFrame
            base_params: 基准参数（可选）

        返回：
            结构化敏感性分析报告
        """
        if scan_results.empty:
            return self._empty_report("param_sensitivity", "无扫描结果")

        # 计算每个参数的敏感度（收益变化 / 参数变化）
        sensitivity = {}
        metric_cols = [c for c in scan_results.columns if c in
                      ["total_return", "sharpe_ratio", "max_drawdown", "win_rate"]]

        for col in scan_results.columns:
            if col in metric_cols:
                continue
            # 尝试数值列
            try:
                values = pd.to_numeric(scan_results[col], errors="coerce").dropna()
                if values.nunique() > 1 and "total_return" in scan_results.columns:
                    returns = pd.to_numeric(scan_results["total_return"], errors="coerce")
                    # 计算相关系数
                    corr = values.corr(returns)
                    sensitivity[col] = {
                        "correlation": float(corr) if not pd.isna(corr) else 0.0,
                        "unique_values": int(values.nunique()),
                        "range": [float(values.min()), float(values.max())],
                    }
            except Exception as e:
                logger.debug(f"参数敏感性分析失败 (col={col}): {e}")

        # 识别最敏感参数
        sorted_sens = sorted(
            sensitivity.items(),
            key=lambda x: abs(x[1]["correlation"]),
            reverse=True,
        )

        # 过拟合风险评估
        overfit_risk = self._assess_overfit_risk(scan_results, sensitivity)

        risks = []
        if sorted_sens and abs(sorted_sens[0][1]["correlation"]) > 0.7:
            risks.append(f"参数 {sorted_sens[0][0]} 与收益高度相关 (r={sorted_sens[0][1]['correlation']:.2f})，可能过拟合")
        if overfit_risk["risk_level"] == "high":
            risks.append("过拟合风险高，建议使用 walk-forward 验证")

        report = {
            "task": "param_sensitivity",
            "analysis": self._format_sensitivity_analysis(sorted_sens, overfit_risk),
            "reasoning": {
                "parameter_sensitivity": sensitivity,
                "most_sensitive": sorted_sens[0][0] if sorted_sens else None,
                "overfit_risk": overfit_risk,
            },
            "recommendation": self._sensitivity_recommendation(sorted_sens, overfit_risk),
            "risks": risks,
            "requires_human_approval": True,
            "confidence": 0.8 if len(scan_results) >= 20 else 0.5,
        }

        # 审计日志
        self.audit_log.record(
            task="param_sensitivity",
            phase="Phase 2-3",
            input_summary={
                "scan_results_count": len(scan_results),
                "parameters_tested": len(sensitivity),
            },
            output_summary={
                "most_sensitive": sorted_sens[0][0] if sorted_sens else None,
                "overfit_risk": overfit_risk["risk_level"],
            },
        )

        logger.info(f"Param sensitivity analysis: {len(sensitivity)} parameters analyzed")
        return report

    # ------------------------------------------------------------------
    # 5. 每周策略复盘
    # ------------------------------------------------------------------
    def analyze_weekly_review(
        self,
        paper_report: Dict[str, Any],
        trade_history: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        每周 Paper Trading 复盘：表现评估、异常检测、关注重点

        参数：
            paper_report: PaperTradingReportGenerator 生成的报告
            trade_history: 交易历史（可选）

        返回：
            结构化周报
        """
        account = paper_report.get("account", {})
        pnl = paper_report.get("pnl", {})
        trades_info = paper_report.get("trades", {})
        cost = paper_report.get("cost_analysis", {})

        total_return = account.get("total_return", 0.0)
        realized = pnl.get("realized", 0.0)
        unrealized = pnl.get("unrealized", 0.0)
        total_trades = trades_info.get("total", 0)
        total_cost = cost.get("total_cost", 0.0)

        # 注入近期日结记忆
        memory_ctx = self._ctx.build_daily_context()
        has_memory = bool(memory_ctx)

        # 表现评估
        performance = self._assess_weekly_performance(
            total_return, realized, total_trades, total_cost
        )

        # 异常检测
        anomalies = self._detect_weekly_anomalies(paper_report, trade_history)

        # 关注重点
        focus_points = self._identify_focus_points(paper_report, performance)

        # 写入记忆
        self._memory.store(
            MemoryKind.DAILY,
            content={
                "total_return": total_return,
                "realized_pnl": realized,
                "total_trades": total_trades,
                "rating": performance.get("rating", ""),
                "total_cost": total_cost,
            },
            tags=["weekly_review"],
            source="analyzer",
        )

        risks = []
        if anomalies:
            for a in anomalies:
                risks.append(f"异常：{a}")
        if total_return < -0.03:
            risks.append(f"周收益率 {total_return:.2%}，接近日亏损 3% 熔断")

        report = {
            "task": "weekly_review",
            "analysis": self._format_weekly_review(
                total_return, realized, unrealized, total_trades, performance
            ),
            "reasoning": {
                "performance": performance,
                "anomalies": anomalies,
                "focus_points": focus_points,
                "cost_analysis": cost,
            },
            "recommendation": self._weekly_recommendation(performance, anomalies),
            "risks": risks,
            "requires_human_approval": True,
            "confidence": 0.75 if total_trades >= 5 else 0.5,
        }

        # 审计日志
        self.audit_log.record(
            task="weekly_review",
            phase="Phase 6",
            input_summary={
                "total_return": total_return,
                "total_trades": total_trades,
            },
            output_summary={
                "performance_rating": performance["rating"],
                "anomaly_count": len(anomalies),
            },
        )

        logger.info("Weekly review analysis completed")
        return report

    # ==================================================================
    # 私有辅助方法
    # ==================================================================

    def _analyze_return_source(
        self, trades: List[Dict], total_return: float
    ) -> Dict[str, Any]:
        """分析收益来源（趋势 vs 震荡）"""
        if not trades:
            return {"source": "无交易", "details": "无交易记录"}

        wins = [t for t in trades if t.get("profit", t.get("pnl", 0)) > 0]
        losses = [t for t in trades if t.get("profit", t.get("pnl", 0)) < 0]

        win_rate = len(wins) / len(trades) if trades else 0
        avg_win = np.mean([t.get("profit", t.get("pnl", 0)) for t in wins]) if wins else 0
        avg_loss = np.mean([t.get("profit", t.get("pnl", 0)) for t in losses]) if losses else 0

        # 震荡特征：高胜率 + 小盈亏比
        # 趋势特征：低胜率 + 大盈亏比
        if avg_loss != 0:
            win_loss_ratio = abs(avg_win / avg_loss)
        else:
            win_loss_ratio = float("inf")

        if win_rate > 0.6 and win_loss_ratio < 2:
            source = "震荡市场"
            details = f"高胜率({win_rate:.2%})+ 小盈亏比({win_loss_ratio:.2f})，典型震荡策略特征"
        elif win_rate < 0.5 and win_loss_ratio > 2:
            source = "趋势市场"
            details = f"低胜率({win_rate:.2%})+ 大盈亏比({win_loss_ratio:.2f})，典型趋势策略特征"
        else:
            source = "混合市场"
            details = f"胜率({win_rate:.2%})、盈亏比({win_loss_ratio:.2f}) 介于趋势与震荡之间"

        return {
            "source": source,
            "details": details,
            "win_rate": win_rate,
            "win_loss_ratio": win_loss_ratio,
        }

    def _analyze_drawdown(self, results: Dict, max_dd: float) -> Dict[str, Any]:
        """分析回撤特征"""
        equity_curve = results.get("equity_curve", [])
        if not equity_curve:
            return {"severity": "unknown", "details": "无权益曲线数据"}

        # 计算回撤持续期
        equities = [e.get("equity", e.get("balance", 0)) for e in equity_curve]
        if not equities:
            return {"severity": "unknown", "details": "无权益数据"}

        peak = equities[0]
        max_dd_duration = 0
        current_dd_duration = 0

        for eq in equities:
            if eq > peak:
                peak = eq
                current_dd_duration = 0
            else:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)

        severity = "low" if max_dd < 0.05 else "medium" if max_dd < 0.10 else "high"

        return {
            "max_drawdown": max_dd,
            "max_duration_bars": max_dd_duration,
            "severity": severity,
            "details": f"最大回撤 {max_dd:.2%}，持续 {max_dd_duration} 根 K 线",
        }

    def _assess_backtest_risks(
        self, metrics: Dict[str, float], total_trades: int
    ) -> List[str]:
        """评估回测风险"""
        risks = []

        if total_trades < 30:
            risks.append(f"交易次数不足 ({total_trades} 笔)，统计意义有限")

        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe < 0:
            risks.append(f"夏普比率为负 ({sharpe:.2f})，风险调整收益差")

        max_dd = metrics.get("max_drawdown", 0)
        if max_dd > 0.20:
            risks.append(f"最大回撤过大 ({max_dd:.2%})，可能无法承受")

        win_rate = metrics.get("win_rate", 0)
        if win_rate < 0.35:
            risks.append(f"胜率偏低 ({win_rate:.2%})，心理压力大")

        profit_factor = metrics.get("profit_factor", 0)
        if 0 < profit_factor < 1.2:
            risks.append(f"盈亏比接近 1 ({profit_factor:.2f})，策略边际效益低")

        return risks

    def _calculate_backtest_confidence(
        self, metrics: Dict[str, float], total_trades: int
    ) -> float:
        """计算回测结果置信度 (0-1)"""
        score = 0.5

        # 交易次数加分
        if total_trades >= 100:
            score += 0.2
        elif total_trades >= 50:
            score += 0.1

        # 夏普比率加分
        sharpe = metrics.get("sharpe_ratio", 0)
        if sharpe > 1:
            score += 0.15
        elif sharpe > 0.5:
            score += 0.1

        # 最大回撤扣分
        max_dd = metrics.get("max_drawdown", 0)
        if max_dd > 0.20:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _analyze_loss_patterns(
        self, losers: List[Dict], all_trades: List[Dict]
    ) -> Dict[str, Any]:
        """分析亏损模式"""
        loss_pnls = [t.get("profit", t.get("pnl", 0)) for t in losers if "profit" in t or "pnl" in t]
        win_pnls = [t.get("profit", t.get("pnl", 0)) for t in all_trades if t.get("profit", t.get("pnl", 0)) > 0]

        avg_loss = float(np.mean(loss_pnls)) if loss_pnls else 0
        avg_win = float(np.mean(win_pnls)) if win_pnls else 0
        max_loss = float(min(loss_pnls)) if loss_pnls else 0

        return {
            "avg_loss_magnitude": abs(avg_loss),
            "avg_win_magnitude": avg_win,
            "max_single_loss": max_loss,
            "loss_to_win_ratio": abs(avg_loss / avg_win) if avg_win > 0 else float("inf"),
            "total_loss_count": len(losers),
        }

    def _assess_signal_quality(
        self, winners: List[Dict], losers: List[Dict]
    ) -> Dict[str, float]:
        """评估信号质量"""
        total = len(winners) + len(losers)
        if total == 0:
            return {"false_signal_rate": 0.0, "win_rate": 0.0}

        # 假信号 = 亏损交易（简化定义）
        false_signal_rate = len(losers) / total

        return {
            "false_signal_rate": false_signal_rate,
            "win_rate": len(winners) / total,
            "signal_quality_score": 1 - false_signal_rate,
        }

    def _max_consecutive_losses(self, trades: List[Dict]) -> int:
        """计算最大连续亏损笔数"""
        max_consec = 0
        current = 0
        for t in trades:
            if t.get("profit", t.get("pnl", 0)) < 0:
                current += 1
                max_consec = max(max_consec, current)
            else:
                current = 0
        return max_consec

    def _analyze_loss_time_distribution(self, losers: List[Dict]) -> Dict[str, int]:
        """分析亏损的时间分布"""
        # 简化：按小时统计
        dist = {}
        for t in losers:
            time = t.get("time", "")
            if time:
                try:
                    hour = pd.Timestamp(time).hour
                    dist[str(hour)] = dist.get(str(hour), 0) + 1
                except Exception as e:
                    logger.debug(f"交易时间解析失败 (time={time}): {e}")
        return dist

    def _assess_overfit_risk(
        self, scan_results: pd.DataFrame, sensitivity: Dict
    ) -> Dict[str, Any]:
        """评估过拟合风险"""
        if len(scan_results) < 10:
            return {"risk_level": "unknown", "reason": "样本量不足"}

        # 高相关参数数量
        high_corr_params = [
            name for name, info in sensitivity.items()
            if abs(info.get("correlation", 0)) > 0.7
        ]

        # 收益分布是否集中
        if "total_return" in scan_results.columns:
            returns = pd.to_numeric(scan_results["total_return"], errors="coerce").dropna()
            if len(returns) > 0:
                cv = float(returns.std() / returns.mean()) if returns.mean() != 0 else float("inf")
            else:
                cv = float("inf")
        else:
            cv = float("inf")

        if len(high_corr_params) >= 2 or cv > 2:
            risk_level = "high"
        elif len(high_corr_params) >= 1 or cv > 1:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "high_correlation_params": high_corr_params,
            "return_cv": cv,
        }

    def _assess_weekly_performance(
        self, total_return: float, realized: float,
        total_trades: int, total_cost: float
    ) -> Dict[str, Any]:
        """评估每周表现"""
        # 评级
        if total_return > 0.05:
            rating = "excellent"
        elif total_return > 0.02:
            rating = "good"
        elif total_return > -0.02:
            rating = "normal"
        elif total_return > -0.05:
            rating = "poor"
        else:
            rating = "critical"

        # 成本占比
        cost_pct = total_cost / abs(realized) if realized != 0 else 0

        return {
            "rating": rating,
            "total_return": total_return,
            "realized_pnl": realized,
            "trade_count": total_trades,
            "cost_ratio": cost_pct,
        }

    def _detect_weekly_anomalies(
        self, report: Dict, trade_history: Optional[List[Dict]]
    ) -> List[str]:
        """检测周异常"""
        anomalies = []
        account = report.get("account", {})
        trades = report.get("trades", {})

        # 检查买卖不平衡
        buy = trades.get("buy", 0)
        sell = trades.get("sell", 0)
        if buy > 0 and sell == 0:
            anomalies.append("只有买入无卖出，可能存在仓位累积风险")
        if sell > 0 and buy == 0:
            anomalies.append("只有卖出无买入，可能在清仓")

        # 检查未平仓档位
        open_lots = trades.get("open_lots", 0)
        if open_lots > 10:
            anomalies.append(f"未平仓档位 {open_lots} 个，仓位复杂度高")

        return anomalies

    def _identify_focus_points(
        self, report: Dict, performance: Dict
    ) -> List[str]:
        """识别下周关注重点"""
        points = []

        if performance["rating"] in ["poor", "critical"]:
            points.append("关注收益率下滑趋势，检查策略是否失效")

        if performance.get("cost_ratio", 0) > 0.3:
            points.append(f"交易成本占比 {performance['cost_ratio']:.2%}，考虑降低交易频率")

        account = report.get("account", {})
        if account.get("total_return", 0) < -0.05:
            points.append("累计收益率接近 -5%，需要评估是否暂停")

        if not points:
            points.append("保持观察，关注交易频率和胜率变化")

        return points

    # ------------------------------------------------------------------
    # 格式化方法
    # ------------------------------------------------------------------

    def _format_backtest_analysis(
        self, total_return, win_rate, sharpe, max_dd, source, dd_analysis
    ) -> str:
        return (
            f"策略总收益 {total_return:.2%}，胜率 {win_rate:.2%}，"
            f"夏普比率 {sharpe:.2f}。"
            f"收益主要来自{source['source']}环境（{source['details']}）。"
            f"最大回撤 {max_dd:.2%}（{dd_analysis.get('severity', 'unknown')} 级别），"
            f"持续 {dd_analysis.get('max_duration_bars', 0)} 根 K 线。"
        )

    def _format_attribution_analysis(
        self, loss_count, total_count, patterns, signal_quality
    ) -> str:
        return (
            f"共 {total_count} 笔交易中 {loss_count} 笔亏损 "
            f"(假信号率 {signal_quality['false_signal_rate']:.2%})。"
            f"平均亏损 ${patterns['avg_loss_magnitude']:,.2f}，"
            f"最大单笔亏损 ${patterns['max_single_loss']:,.2f}。"
        )

    def _format_sensitivity_analysis(self, sorted_sens, overfit_risk) -> str:
        if not sorted_sens:
            return "参数敏感性分析：无可分析参数"
        top = sorted_sens[0]
        return (
            f"最敏感参数：{top[0]}（相关系数 {top[1]['correlation']:.2f}）。"
            f"过拟合风险：{overfit_risk['risk_level']}。"
        )

    def _format_weekly_review(
        self, total_return, realized, unrealized, total_trades, performance
    ) -> str:
        return (
            f"本周收益 {total_return:.2%}（已实现 ${realized:,.2f}，"
            f"未实现 ${unrealized:,.2f}），共 {total_trades} 笔交易。"
            f"表现评级：{performance['rating']}。"
        )

    # ------------------------------------------------------------------
    # 建议生成方法
    # ------------------------------------------------------------------

    def _backtest_recommendation(self, metrics: Dict, risks: List[str]) -> str:
        if not risks:
            return "回测结果良好，可以进入下一阶段验证"
        if len(risks) >= 3:
            return "存在多项风险，建议先优化策略再推进"
        return f"有 {len(risks)} 项风险需要关注，建议针对性改进"

    def _attribution_recommendation(self, patterns: Dict, signal_quality: Dict) -> str:
        recs = []
        if signal_quality["false_signal_rate"] > 0.5:
            recs.append("信号质量较差，建议增强过滤器")
        if patterns.get("loss_to_win_ratio", 0) > 2:
            recs.append("亏损幅度远超盈利，建议优化止损逻辑")
        if not recs:
            recs.append("亏损模式无明显异常，继续观察")
        return "；".join(recs)

    def _sensitivity_recommendation(self, sorted_sens, overfit_risk) -> str:
        recs = []
        if overfit_risk["risk_level"] == "high":
            recs.append("过拟合风险高，强烈建议使用 walk-forward 验证")
        if sorted_sens:
            recs.append(f"参数 {sorted_sens[0][0]} 最敏感，应谨慎调整")
        if not recs:
            recs.append("参数敏感性在可接受范围内")
        return "；".join(recs)

    def _weekly_recommendation(self, performance: Dict, anomalies: List[str]) -> str:
        recs = []
        if performance["rating"] == "critical":
            recs.append("表现评级为危急，建议立即检查策略状态")
        if anomalies:
            recs.append(f"发现 {len(anomalies)} 项异常，建议逐一排查")
        if not recs:
            recs.append("本周表现正常，继续保持观察")
        return "；".join(recs)

    def _empty_report(self, task: str, reason: str) -> Dict[str, Any]:
        """生成空报告"""
        return {
            "task": task,
            "analysis": reason,
            "reasoning": {},
            "recommendation": "无数据可分析",
            "risks": [],
            "requires_human_approval": True,
            "confidence": 0.0,
        }


# 导出
__all__ = ["TradingAnalyzer"]
