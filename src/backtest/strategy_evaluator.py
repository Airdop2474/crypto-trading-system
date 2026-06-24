"""
策略评估报告

对 12 个策略做全面评估，输出评分和淘汰建议。

评估维度（各 0-100 分，加权汇总）：
1. 收益性（30%）：年化收益、Sharpe、Sortino
2. 风险控制（25%）：最大回撤、VaR、CVaR、破产概率
3. 稳定性（25%）：参数稳定性评分、Monte Carlo 置信区间宽度
4. 交易质量（20%）：胜率、盈亏比、交易频率

淘汰白皮书（v3 Phase 2）：
- Sharpe < 0.3
- 最大回撤 > 25%
- 参数稳定性评分 < 0.4
- IS-OS 差异 > 50%（样本内外收益差异）
命中 2 项以上 → 建议淘汰

用法：
    from src.backtest.strategy_evaluator import StrategyEvaluator

    evaluator = StrategyEvaluator(data, initial_capital=10000)
    report = evaluator.evaluate_all()
    for r in report:
        print(f"{r.strategy_name}: {r.total_score} - {r.verdict}")
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd

from src.utils.logger import logger
from src.strategy.registry import STRATEGY_REGISTRY, get_strategy_label
from src.strategy.stop_configs import get_stop_config
from src.backtest.engine import BacktestEngine
from src.backtest.monte_carlo import MonteCarloSimulator
from src.backtest.param_stability import ParameterStability
from src.execution.paper_broker import PaperBroker


@dataclass
class StrategyEvaluation:
    """单个策略的评估结果"""

    strategy_name: str
    strategy_label: str
    total_score: float  # 0-100
    verdict: str  # "KEEP" / "WARN" / "ELIMINATE"

    # 分项评分
    profitability_score: float
    risk_score: float
    stability_score: float
    trade_quality_score: float

    # 关键指标
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int

    # Monte Carlo 指标
    mc_return_median: float
    mc_return_p5: float
    mc_max_dd_p95: float
    mc_ruin_prob: float

    # 参数稳定性
    param_stability: float

    # 淘汰规则命中
    elimination_flags: list = field(default_factory=list)

    # 执行时间
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "strategy_label": self.strategy_label,
            "total_score": round(self.total_score, 1),
            "verdict": self.verdict,
            "scores": {
                "profitability": round(self.profitability_score, 1),
                "risk": round(self.risk_score, 1),
                "stability": round(self.stability_score, 1),
                "trade_quality": round(self.trade_quality_score, 1),
            },
            "metrics": {
                "annual_return": round(self.annual_return, 4),
                "sharpe_ratio": round(self.sharpe_ratio, 2),
                "max_drawdown": round(self.max_drawdown, 4),
                "win_rate": round(self.win_rate, 4),
                "profit_factor": round(self.profit_factor, 2),
                "total_trades": self.total_trades,
            },
            "monte_carlo": {
                "return_median": round(self.mc_return_median, 4),
                "return_p5": round(self.mc_return_p5, 4),
                "max_dd_p95": round(self.mc_max_dd_p95, 4),
                "ruin_prob": round(self.mc_ruin_prob, 4),
            },
            "param_stability": round(self.param_stability, 3),
            "elimination_flags": self.elimination_flags,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


class StrategyEvaluator:
    """策略评估器

    对每个策略执行：
    1. 基础回测（带止损）
    2. Monte Carlo 模拟（1000 次）
    3. 参数稳定性分析（±10% 微扰）
    4. 综合评分 + 淘汰建议
    """

    # 淘汰阈值
    ELIM_SHARPE_THRESHOLD = 0.3
    ELIM_MDD_THRESHOLD = 0.25
    ELIM_STABILITY_THRESHOLD = 0.4
    ELIM_IS_OS_DIFF_THRESHOLD = 0.50

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float = 10000.0,
        n_mc_simulations: int = 1000,
    ):
        self.data = data
        self.initial_capital = initial_capital
        self.n_mc_simulations = n_mc_simulations

    def evaluate_all(self, strategies: Optional[List[str]] = None) -> List[StrategyEvaluation]:
        """评估所有或指定策略"""
        names = strategies or list(STRATEGY_REGISTRY.keys())
        results = []

        for name in names:
            try:
                logger.info(f"Evaluating strategy: {name}")
                result = self.evaluate_single(name)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to evaluate {name}: {e}")
                results.append(self._error_result(name, str(e)))

        # 按总分排序
        results.sort(key=lambda x: x.total_score, reverse=True)
        return results

    def evaluate_single(self, strategy_name: str) -> StrategyEvaluation:
        """评估单个策略"""
        start_time = time.time()

        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strategy_cls is None:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        # 1. 基础回测（带止损）
        stop_config = get_stop_config(strategy_name)
        try:
            strategy = strategy_cls(
                initial_capital=self.initial_capital,
                stop_loss_config=stop_config,
            )
        except TypeError:
            strategy = strategy_cls(initial_capital=self.initial_capital)

        broker = PaperBroker(
            initial_balance=self.initial_capital,
            commission=0.001,
            slippage_pct=0.0005,
        )
        engine = BacktestEngine(strategy=strategy, broker=broker)
        bt_result = engine.run(self.data)
        metrics = bt_result.get("metrics", {})
        trades = bt_result.get("trades", [])
        equity_curve = bt_result.get("equity_curve", [])

        # 2. Monte Carlo 模拟
        mc = MonteCarloSimulator(n_simulations=self.n_mc_simulations, random_seed=42)
        mc_result = mc.run(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
            method="trade_bootstrap",
        )

        # 3. 参数稳定性分析
        base_params = self._extract_params(strategy)
        ps = ParameterStability(
            data=self.data,
            strategy_class=strategy_cls,
            base_params=base_params,
            initial_capital=self.initial_capital,
        )
        try:
            stability = ps.analyze()
        except Exception as e:
            logger.warning(f"Stability analysis failed for {strategy_name}: {e}")
            from src.backtest.param_stability import StabilityResult
            stability = StabilityResult(
                strategy_name=strategy_name,
                base_params=base_params,
                stability_score=0.5,
                sharpe_cv=0, return_cv=0, drawdown_cv=0, win_rate_cv=0,
            )

        # 4. 评分
        scores = self._calculate_scores(metrics, mc_result, stability)

        # 5. 淘汰检查
        flags = self._check_elimination(metrics, mc_result, stability)

        verdict = "KEEP"
        if len(flags) >= 2:
            verdict = "ELIMINATE"
        elif len(flags) >= 1:
            verdict = "WARN"

        elapsed = time.time() - start_time

        return StrategyEvaluation(
            strategy_name=strategy_name,
            strategy_label=get_strategy_label(strategy_name) or strategy_name,
            total_score=scores["total"],
            verdict=verdict,
            profitability_score=scores["profitability"],
            risk_score=scores["risk"],
            stability_score=scores["stability"],
            trade_quality_score=scores["trade_quality"],
            annual_return=metrics.get("annual_return", 0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0),
            max_drawdown=abs(metrics.get("max_drawdown", 0)),
            win_rate=metrics.get("win_rate", 0),
            profit_factor=metrics.get("profit_factor", 0),
            total_trades=metrics.get("total_trades", 0),
            mc_return_median=mc_result.return_median,
            mc_return_p5=mc_result.return_p5,
            mc_max_dd_p95=mc_result.max_dd_p95,
            mc_ruin_prob=mc_result.ruin_probability,
            param_stability=stability.stability_score,
            elimination_flags=flags,
            elapsed_seconds=elapsed,
        )

    def _extract_params(self, strategy) -> dict:
        """从策略实例提取参数"""
        params = {}
        # 尝试从 strategy.parameters 获取
        if hasattr(strategy, "parameters") and strategy.parameters:
            params.update(strategy.parameters)
        # 尝试从 PARAM_SCHEMA 获取默认值
        if hasattr(strategy, "PARAM_SCHEMA"):
            for k, v in strategy.PARAM_SCHEMA.items():
                if k not in params and "default" in v:
                    params[k] = v["default"]
        # 确保有 initial_capital
        if "initial_capital" not in params:
            params["initial_capital"] = self.initial_capital
        return params

    def _calculate_scores(self, metrics: dict, mc_result, stability) -> dict:
        """计算综合评分（0-100）"""

        # 1. 收益性（30%）
        sharpe = metrics.get("sharpe_ratio", 0)
        annual_ret = metrics.get("annual_return", 0)
        profit_factor = metrics.get("profit_factor", 0)

        profitability = (
            min(100, max(0, sharpe * 30)) * 0.4 +
            min(100, max(0, annual_ret * 200)) * 0.3 +
            min(100, max(0, profit_factor * 20)) * 0.3
        )

        # 2. 风险控制（25%）
        mdd = abs(metrics.get("max_drawdown", 0))
        mc_ruin = mc_result.ruin_probability
        mc_dd_p95 = mc_result.max_dd_p95

        risk = (
            max(0, 100 - mdd * 300) * 0.4 +  # 回撤越小越好
            max(0, 100 - mc_ruin * 500) * 0.3 +  # 破产概率越小越好
            max(0, 100 - mc_dd_p95 * 200) * 0.3
        )

        # 3. 稳定性（25%）
        stability_score = stability.stability_score * 100
        # Monte Carlo 置信区间宽度（p95-p5 越窄越好）
        ci_width = abs(mc_result.return_p95 - mc_result.return_p5)
        ci_score = max(0, 100 - ci_width * 200)

        stability_total = stability_score * 0.6 + ci_score * 0.4

        # 4. 交易质量（20%）
        win_rate = metrics.get("win_rate", 0)
        total_trades = metrics.get("total_trades", 0)
        avg_win_loss = metrics.get("avg_win_loss_ratio", 1)

        trade_quality = (
            min(100, win_rate * 150) * 0.4 +
            min(100, max(0, (total_trades - 10) * 2)) * 0.2 +  # 至少 10 笔交易
            min(100, avg_win_loss * 30) * 0.4
        )

        # 加权汇总
        total = (
            profitability * 0.30 +
            risk * 0.25 +
            stability_total * 0.25 +
            trade_quality * 0.20
        )

        return {
            "total": round(total, 1),
            "profitability": round(profitability, 1),
            "risk": round(risk, 1),
            "stability": round(stability_total, 1),
            "trade_quality": round(trade_quality, 1),
        }

    def _check_elimination(self, metrics: dict, mc_result, stability) -> list:
        """检查淘汰规则"""
        flags = []

        sharpe = metrics.get("sharpe_ratio", 0)
        mdd = abs(metrics.get("max_drawdown", 0))
        stability_score = stability.stability_score

        # IS-OS 差异：用 Monte Carlo 中位数 vs 实际收益的差异近似
        actual_return = metrics.get("total_return", 0)
        mc_median = mc_result.return_median
        if abs(mc_median) > 1e-6:
            is_os_diff = abs(actual_return - mc_median) / abs(mc_median)
        else:
            is_os_diff = 0

        if sharpe < self.ELIM_SHARPE_THRESHOLD:
            flags.append(f"Sharpe {sharpe:.2f} < {self.ELIM_SHARPE_THRESHOLD}")

        if mdd > self.ELIM_MDD_THRESHOLD:
            flags.append(f"最大回撤 {mdd:.1%} > {self.ELIM_MDD_THRESHOLD:.0%}")

        if stability_score < self.ELIM_STABILITY_THRESHOLD:
            flags.append(
                f"参数稳定性 {stability_score:.2f} < {self.ELIM_STABILITY_THRESHOLD}"
            )

        if is_os_diff > self.ELIM_IS_OS_DIFF_THRESHOLD:
            flags.append(
                f"IS-OS 差异 {is_os_diff:.0%} > {self.ELIM_IS_OS_DIFF_THRESHOLD:.0%}"
            )

        return flags

    def _error_result(self, name: str, error: str) -> StrategyEvaluation:
        """错误结果"""
        return StrategyEvaluation(
            strategy_name=name,
            strategy_label=get_strategy_label(name) or name,
            total_score=0,
            verdict="ELIMINATE",
            profitability_score=0, risk_score=0, stability_score=0,
            trade_quality_score=0,
            annual_return=0, sharpe_ratio=0, max_drawdown=0,
            win_rate=0, profit_factor=0, total_trades=0,
            mc_return_median=0, mc_return_p5=0, mc_max_dd_p95=0, mc_ruin_prob=0,
            param_stability=0,
            elimination_flags=[f"评估失败: {error}"],
        )


__all__ = ["StrategyEvaluator", "StrategyEvaluation"]
