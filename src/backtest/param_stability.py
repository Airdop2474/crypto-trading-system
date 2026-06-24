"""
参数稳定性分析

对策略参数施加 ±10% 微扰，测量关键指标的变化幅度。
稳定性评分 0-1，1 = 完全稳定（参数变化不影响指标）。

用法：
    from src.backtest.param_stability import ParameterStability

    ps = ParameterStability(data, strategy_class, base_params)
    result = ps.analyze()
    print(f"稳定性评分: {result.stability_score}")
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from copy import deepcopy

import numpy as np
import pandas as pd

from src.utils.logger import logger
from src.backtest.engine import BacktestEngine
from src.execution.paper_broker import PaperBroker


# 微扰幅度
PERTURBATIONS = [-0.10, -0.05, 0, 0.05, 0.10]

# 评分权重
SCORE_WEIGHTS = {
    "sharpe_stability": 0.3,
    "return_stability": 0.3,
    "drawdown_stability": 0.2,
    "win_rate_stability": 0.2,
}


@dataclass
class StabilityResult:
    """参数稳定性分析结果"""

    strategy_name: str
    base_params: dict
    stability_score: float  # 0-1, 1=完全稳定
    sharpe_cv: float  # Sharpe 变异系数
    return_cv: float  # 收益率变异系数
    drawdown_cv: float  # 回撤变异系数
    win_rate_cv: float  # 胜率变异系数
    param_details: list = field(default_factory=list)  # 每个参数的详细变化
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "stability_score": round(self.stability_score, 3),
            "sharpe_cv": round(self.sharpe_cv, 3),
            "return_cv": round(self.return_cv, 3),
            "drawdown_cv": round(self.drawdown_cv, 3),
            "win_rate_cv": round(self.win_rate_cv, 3),
            "param_details": self.param_details,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }

    def summary(self) -> str:
        lines = [
            f"参数稳定性分析: {self.strategy_name}",
            f"  稳定性评分: {self.stability_score:.3f} (1.0=完全稳定)",
            f"  Sharpe CV: {self.sharpe_cv:.3f}",
            f"  收益率 CV: {self.return_cv:.3f}",
            f"  回撤 CV:   {self.drawdown_cv:.3f}",
            f"  胜率 CV:   {self.win_rate_cv:.3f}",
        ]
        return "\n".join(lines)


class ParameterStability:
    """参数稳定性分析器

    对每个数值型参数施加 ±10% 微扰，
    测量 Sharpe/收益率/回撤/胜率的变化幅度。
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_class,
        base_params: dict,
        initial_capital: float = 10000.0,
    ):
        self.data = data
        self.strategy_class = strategy_class
        self.base_params = base_params
        self.initial_capital = initial_capital

    def analyze(self) -> StabilityResult:
        """运行参数稳定性分析"""
        start_time = time.time()
        strategy_name = self.strategy_class.__name__

        # 找出可微扰的数值型参数
        perturbable_params = self._get_perturbable_params()
        if not perturbable_params:
            logger.warning(f"No perturbable params for {strategy_name}")
            return StabilityResult(
                strategy_name=strategy_name,
                base_params=self.base_params,
                stability_score=1.0,
                sharpe_cv=0, return_cv=0, drawdown_cv=0, win_rate_cv=0,
                elapsed_seconds=time.time() - start_time,
            )

        all_sharpes = []
        all_returns = []
        all_drawdowns = []
        all_win_rates = []
        param_details = []

        for param_name in perturbable_params:
            base_val = self.base_params.get(param_name)
            if base_val is None or not isinstance(base_val, (int, float)):
                continue

            param_results = []
            for pct in PERTURBATIONS:
                test_params = deepcopy(self.base_params)
                test_params[param_name] = base_val * (1 + pct)

                metrics = self._run_backtest(test_params)
                if metrics:
                    all_sharpes.append(metrics["sharpe_ratio"])
                    all_returns.append(metrics["total_return"])
                    all_drawdowns.append(abs(metrics["max_drawdown"]))
                    all_win_rates.append(metrics["win_rate"])
                    param_results.append({
                        "variation": pct,
                        "value": test_params[param_name],
                        "sharpe": metrics["sharpe_ratio"],
                        "return": metrics["total_return"],
                        "max_dd": abs(metrics["max_drawdown"]),
                        "win_rate": metrics["win_rate"],
                    })

            if param_results:
                param_details.append({
                    "param": param_name,
                    "base_value": base_val,
                    "results": param_results,
                })

        # 计算变异系数 (CV = std/|mean|)
        sharpe_cv = self._cv(all_sharpes)
        return_cv = self._cv(all_returns)
        drawdown_cv = self._cv(all_drawdowns)
        win_rate_cv = self._cv(all_win_rates)

        # 稳定性评分 = 1 - 加权平均 CV（截断到 [0, 1]）
        weighted_cv = (
            sharpe_cv * SCORE_WEIGHTS["sharpe_stability"]
            + return_cv * SCORE_WEIGHTS["return_stability"]
            + drawdown_cv * SCORE_WEIGHTS["drawdown_stability"]
            + win_rate_cv * SCORE_WEIGHTS["win_rate_stability"]
        )
        stability_score = max(0.0, min(1.0, 1.0 - weighted_cv))

        elapsed = time.time() - start_time
        logger.info(
            f"ParameterStability: {strategy_name} score={stability_score:.3f} "
            f"({len(perturbable_params)} params, {elapsed:.1f}s)"
        )

        return StabilityResult(
            strategy_name=strategy_name,
            base_params=self.base_params,
            stability_score=stability_score,
            sharpe_cv=sharpe_cv,
            return_cv=return_cv,
            drawdown_cv=drawdown_cv,
            win_rate_cv=win_rate_cv,
            param_details=param_details,
            elapsed_seconds=elapsed,
        )

    def _get_perturbable_params(self) -> list:
        """找出可微扰的数值型参数"""
        result = []
        for k, v in self.base_params.items():
            if isinstance(v, (int, float)) and v != 0 and k not in (
                "initial_capital", "max_consecutive_losses",
                "max_daily_loss", "max_drawdown",
            ):
                result.append(k)
        return result

    def _run_backtest(self, params: dict) -> Optional[dict]:
        """运行单次回测，返回 metrics"""
        try:
            strategy = self.strategy_class(**params)
            broker = PaperBroker(
                initial_balance=self.initial_capital,
                commission=0.001,
                slippage_pct=0.0005,
            )
            engine = BacktestEngine(strategy=strategy, broker=broker)
            result = engine.run(self.data)
            return result.get("metrics", {})
        except Exception as e:
            logger.debug(f"Backtest failed with params {params}: {e}")
            return None

    @staticmethod
    def _cv(values: list) -> float:
        """计算变异系数 CV = std / |mean|"""
        if not values or len(values) < 2:
            return 0.0
        arr = np.array(values)
        mean = np.mean(arr)
        if abs(mean) < 1e-10:
            return 0.0 if np.std(arr) < 1e-10 else 1.0
        return float(np.std(arr) / abs(mean))


__all__ = ["ParameterStability", "StabilityResult", "PERTURBATIONS"]
