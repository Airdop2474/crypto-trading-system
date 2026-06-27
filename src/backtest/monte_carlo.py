"""
Monte Carlo 模拟器

两种模拟方法：
1. 交易 Bootstrap — 对历史交易的 profit 序列做有放回重采样，重建权益曲线
2. 收益率重采样 — 对每 bar 收益率做有放回重采样，生成替代路径

输出统计量：
- 收益率分布：median, mean, std, p5, p25, p75, p95
- 最大回撤分布：median, p95 (VaR), CVaR
- Sharpe 分布：median, p5, p95
- 破产概率：最终权益 < 初始资金 × 0.5 的比例

性能要求：1000 次模拟 < 5 秒（NumPy 向量化）

用法：
    from src.backtest.monte_carlo import MonteCarloSimulator

    mc = MonteCarloSimulator(n_simulations=1000)
    result = mc.run(trades=backtest_result["trades"],
                    equity_curve=backtest_result["equity_curve"],
                    initial_capital=10000.0)
    print(result.summary())
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd

from src.utils.logger import logger


@dataclass
class MonteCarloResult:
    """Monte Carlo 模拟结果"""

    n_simulations: int
    method: str  # "trade_bootstrap" or "return_resample"

    # 收益率分布（百分比）
    return_median: float
    return_mean: float
    return_std: float
    return_p5: float
    return_p25: float
    return_p75: float
    return_p95: float

    # 最大回撤分布（正数，百分比）
    max_dd_median: float
    max_dd_p75: float
    max_dd_p95: float  # VaR 95%
    max_dd_cvar_95: float  # CVaR (条件 VaR)

    # Sharpe 分布
    sharpe_median: float
    sharpe_p5: float
    sharpe_p95: float

    # 风险指标
    ruin_probability: float  # P(final < initial * 0.5)
    loss_probability: float  # P(final < initial)
    profit_probability: float  # P(final > initial)

    # 原始分布（用于绘图，可选）
    return_distribution: Optional[np.ndarray] = None
    max_dd_distribution: Optional[np.ndarray] = None
    sharpe_distribution: Optional[np.ndarray] = None

    # 执行时间
    elapsed_seconds: float = 0.0

    def summary(self) -> str:
        """返回可读的摘要"""
        lines = [
            f"Monte Carlo 模拟结果 ({self.method}, {self.n_simulations} 次)",
            f"  执行时间: {self.elapsed_seconds:.2f}s",
            f"",
            f"  收益率分布:",
            f"    中位数: {self.return_median:.2%}",
            f"    均值:   {self.return_mean:.2%}",
            f"    标准差: {self.return_std:.2%}",
            f"    5%:     {self.return_p5:.2%}",
            f"    95%:    {self.return_p95:.2%}",
            f"",
            f"  最大回撤分布:",
            f"    中位数: {self.max_dd_median:.2%}",
            f"    75%:    {self.max_dd_p75:.2%}",
            f"    95%:    {self.max_dd_p95:.2%}",
            f"    CVaR95: {self.max_dd_cvar_95:.2%}",
            f"",
            f"  Sharpe 分布:",
            f"    中位数: {self.sharpe_median:.2f}",
            f"    5%:     {self.sharpe_p5:.2f}",
            f"    95%:    {self.sharpe_p95:.2f}",
            f"",
            f"  风险指标:",
            f"    盈利概率: {self.profit_probability:.1%}",
            f"    亏损概率: {self.loss_probability:.1%}",
            f"    破产概率: {self.ruin_probability:.1%}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """转为字典（用于 API 返回和数据库存储）

        字段名与前端 MonteCarloResult 类型定义对齐：
        return_distribution / max_dd_distribution / sharpe_distribution
        """
        return {
            "n_simulations": self.n_simulations,
            "method": self.method,
            "return_distribution": {
                "mean": round(self.return_mean, 4),
                "median": round(self.return_median, 4),
                "std": round(self.return_std, 4),
                "p5": round(self.return_p5, 4),
                "p25": round(self.return_p25, 4),
                "p75": round(self.return_p75, 4),
                "p95": round(self.return_p95, 4),
                "min": round(float(np.min(self.return_distribution)) if self.return_distribution is not None and len(self.return_distribution) > 0 else self.return_p5, 4),
                "max": round(float(np.max(self.return_distribution)) if self.return_distribution is not None and len(self.return_distribution) > 0 else self.return_p95, 4),
            },
            "max_dd_distribution": {
                "mean": round(float(np.mean(self.max_dd_distribution)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else self.max_dd_median, 4),
                "median": round(self.max_dd_median, 4),
                "std": round(float(np.std(self.max_dd_distribution)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else 0.0, 4),
                "p5": round(float(np.percentile(self.max_dd_distribution, 5)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else self.max_dd_median, 4),
                "p25": round(float(np.percentile(self.max_dd_distribution, 25)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else self.max_dd_median, 4),
                "p75": round(self.max_dd_p75, 4),
                "p95": round(self.max_dd_p95, 4),
                "min": round(float(np.min(self.max_dd_distribution)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else self.max_dd_p95, 4),
                "max": round(float(np.max(self.max_dd_distribution)) if self.max_dd_distribution is not None and len(self.max_dd_distribution) > 0 else self.max_dd_p95, 4),
                "cvar_95": round(self.max_dd_cvar_95, 4),
            },
            "sharpe_distribution": {
                "mean": round(float(np.mean(self.sharpe_distribution)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else self.sharpe_median, 2),
                "median": round(self.sharpe_median, 2),
                "std": round(float(np.std(self.sharpe_distribution)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else 0.0, 2),
                "p5": round(self.sharpe_p5, 2),
                "p25": round(float(np.percentile(self.sharpe_distribution, 25)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else self.sharpe_p5, 2),
                "p75": round(float(np.percentile(self.sharpe_distribution, 75)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else self.sharpe_p95, 2),
                "p95": round(self.sharpe_p95, 2),
                "min": round(float(np.min(self.sharpe_distribution)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else self.sharpe_p5, 2),
                "max": round(float(np.max(self.sharpe_distribution)) if self.sharpe_distribution is not None and len(self.sharpe_distribution) > 0 else self.sharpe_p95, 2),
            },
            "var_95": round(self.return_p5, 4),           # 95% VaR ≈ 5% 分位收益率
            "cvar_95": round(self.max_dd_cvar_95, 4),     # CVaR (Expected Shortfall)
            "ruin_probability": round(self.ruin_probability, 4),
            "loss_probability": round(self.loss_probability, 4),
            "profit_probability": round(self.profit_probability, 4),
            "original_return": round(self.return_median, 4),
            "original_max_dd": round(self.max_dd_median, 4),
            "original_sharpe": round(self.sharpe_median, 2),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


class MonteCarloSimulator:
    """Monte Carlo 模拟器

    通过对历史交易或收益率序列做 bootstrap 重采样，
    生成策略表现的置信区间。

    性能：1000 次模拟在 < 1 秒内完成（纯 NumPy 向量化）。
    """

    def __init__(self, n_simulations: int = 1000, random_seed: Optional[int] = None):
        """
        参数：
            n_simulations: 模拟次数（默认 1000）
            random_seed: 随机种子（可复现）
        """
        self.n_simulations = n_simulations
        self._rng = np.random.default_rng(random_seed)

    def run(
        self,
        trades: List[Dict],
        equity_curve: Optional[List[Dict]] = None,
        initial_capital: float = 10000.0,
        method: str = "trade_bootstrap",
    ) -> MonteCarloResult:
        """运行 Monte Carlo 模拟

        参数：
            trades: 回测交易记录列表（需含 type 和 profit 字段）
            equity_curve: 权益曲线（用于 return_resample 方法）
            initial_capital: 初始资金
            method: "trade_bootstrap" 或 "return_resample"

        返回：
            MonteCarloResult
        """
        start_time = time.time()

        if method == "trade_bootstrap":
            result = self._trade_bootstrap(trades, initial_capital)
        elif method == "return_resample":
            result = self._return_resample(equity_curve, initial_capital)
        else:
            raise ValueError(f"Unknown method: {method}")

        result.elapsed_seconds = time.time() - start_time
        logger.info(
            f"Monte Carlo completed: {self.n_simulations} simulations "
            f"in {result.elapsed_seconds:.2f}s"
        )
        return result

    def _trade_bootstrap(
        self, trades: List[Dict], initial_capital: float
    ) -> MonteCarloResult:
        """交易 Bootstrap — 重采样交易 profit 序列

        1. 提取所有平仓交易的 profit 序列
        2. 有放回重采样 N 次，每次生成一条替代权益曲线
        3. 计算每条曲线的收益率、最大回撤、Sharpe
        """
        # 提取 profit 序列
        profits = []
        for t in trades:
            if t.get("type", "").upper() in ("SELL", "LIQUIDATE"):
                p = t.get("profit")
                if p is not None:
                    profits.append(float(p))

        profits = np.array(profits)
        n_trades = len(profits)

        if n_trades < 5:
            logger.warning(
                f"Monte Carlo: only {n_trades} trades, results may be unreliable"
            )

        if n_trades == 0:
            # 无交易，返回空结果
            return self._empty_result("trade_bootstrap")

        # 向量化 bootstrap：生成 (n_simulations, n_trades) 的重采样矩阵
        # 每行是一次模拟，从 profits 中有放回抽取 n_trades 个
        indices = self._rng.integers(
            0, n_trades, size=(self.n_simulations, n_trades)
        )
        sampled_profits = profits[indices]  # shape: (n_sim, n_trades)

        # 累加得到权益曲线
        equity_paths = initial_capital + np.cumsum(sampled_profits, axis=1)
        # 在开头插入初始资金
        equity_paths = np.column_stack([
            np.full(self.n_simulations, initial_capital),
            equity_paths,
        ])  # shape: (n_sim, n_trades + 1)

        # 计算指标
        returns, max_dds, sharpes = self._calculate_metrics_vectorized(
            equity_paths, initial_capital
        )

        return self._build_result(returns, max_dds, sharpes, "trade_bootstrap")

    def _return_resample(
        self, equity_curve: Optional[List[Dict]], initial_capital: float
    ) -> MonteCarloResult:
        """收益率重采样 — 对每 bar 收益率做有放回重采样

        1. 从权益曲线计算每 bar 收益率序列
        2. 有放回重采样 N 次，每次生成一条替代权益路径
        3. 计算每条路径的收益率、最大回撤、Sharpe
        """
        if not equity_curve or len(equity_curve) < 5:
            logger.warning(
                f"Monte Carlo: equity_curve too short ({len(equity_curve) if equity_curve else 0} bars) "
                f"for return_resample, need >= 5"
            )
            return self._empty_result("return_resample")

        # 提取权益序列
        equities = np.array(
            [float(e.get("total_equity", 0)) for e in equity_curve]
        )

        # 计算每 bar 收益率（保护除零：equities 含 0 时返回 0）
        with np.errstate(divide="ignore", invalid="ignore"):
            returns_per_bar = np.diff(equities) / equities[:-1]
        returns_per_bar = np.nan_to_num(returns_per_bar, nan=0.0, posinf=0.0, neginf=0.0)
        n_bars = len(returns_per_bar)

        if n_bars < 5:
            return self._empty_result("return_resample")

        # 向量化重采样
        indices = self._rng.integers(
            0, n_bars, size=(self.n_simulations, n_bars)
        )
        sampled_returns = returns_per_bar[indices]  # (n_sim, n_bars)

        # 构建权益路径（向量化 cumprod 替代逐 bar 循环，数学等价但更快）
        growth = np.concatenate(
            [np.ones((self.n_simulations, 1)), 1 + sampled_returns],
            axis=1,
        )
        equity_paths = initial_capital * np.cumprod(growth, axis=1)

        # 计算指标
        returns, max_dds, sharpes = self._calculate_metrics_vectorized(
            equity_paths, initial_capital
        )

        return self._build_result(returns, max_dds, sharpes, "return_resample")

    def _calculate_metrics_vectorized(
        self, equity_paths: np.ndarray, initial_capital: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """向量化计算收益率、最大回撤、Sharpe

        参数：
            equity_paths: shape (n_sim, n_bars)
            initial_capital: 初始资金

        返回：
            (returns, max_drawdowns, sharpes) — 每个 shape (n_sim,)
        """
        n_sim, n_bars = equity_paths.shape

        # 收益率
        returns = (equity_paths[:, -1] - initial_capital) / initial_capital

        # 最大回撤（向量化）
        # running max along axis 1
        running_max = np.maximum.accumulate(equity_paths, axis=1)
        # 保护除零：running_max=0 时（权益触 0）会产生 inf/nan，污染 max_drawdowns
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdowns = (equity_paths - running_max) / running_max
        drawdowns = np.nan_to_num(drawdowns, nan=0.0, posinf=0.0, neginf=-1.0)
        max_drawdowns = np.abs(np.min(drawdowns, axis=1))

        # Sharpe Ratio（年化，假设 4h K线 → 6 bars/day → 2190 bars/year）
        # 每行计算每 bar 收益率
        bar_returns = np.diff(equity_paths, axis=1) / equity_paths[:, :-1]
        # 排除 inf/nan
        bar_returns = np.nan_to_num(bar_returns, nan=0.0, posinf=0.0, neginf=0.0)

        mean_returns = np.mean(bar_returns, axis=1)
        std_returns = np.std(bar_returns, axis=1)

        # 年化 Sharpe = mean / std * sqrt(bars_per_year)
        bars_per_year = 2190  # 4h: 6*365
        # 避免除零
        sharpes = np.where(
            std_returns > 0,
            mean_returns / std_returns * np.sqrt(bars_per_year),
            0.0,
        )

        return returns, max_drawdowns, sharpes

    def _build_result(
        self,
        returns: np.ndarray,
        max_dds: np.ndarray,
        sharpes: np.ndarray,
        method: str,
    ) -> MonteCarloResult:
        """构建结果对象"""
        n = self.n_simulations
        initial = 10000.0  # 用于 ruin/loss 判断的基准

        # 破产概率：最终权益 < 初始资金 * 0.5
        final_equities = initial * (1 + returns)
        ruin_prob = np.mean(final_equities < initial * 0.5)
        loss_prob = np.mean(returns < 0)
        profit_prob = np.mean(returns > 0)

        # CVaR 95%: 最大回撤超过 p95 的均值
        dd_p95 = np.percentile(max_dds, 95)
        cvar_95 = np.mean(max_dds[max_dds >= dd_p95]) if np.any(max_dds >= dd_p95) else dd_p95

        return MonteCarloResult(
            n_simulations=n,
            method=method,
            return_median=float(np.median(returns)),
            return_mean=float(np.mean(returns)),
            return_std=float(np.std(returns)),
            return_p5=float(np.percentile(returns, 5)),
            return_p25=float(np.percentile(returns, 25)),
            return_p75=float(np.percentile(returns, 75)),
            return_p95=float(np.percentile(returns, 95)),
            max_dd_median=float(np.median(max_dds)),
            max_dd_p75=float(np.percentile(max_dds, 75)),
            max_dd_p95=float(dd_p95),
            max_dd_cvar_95=float(cvar_95),
            sharpe_median=float(np.median(sharpes)),
            sharpe_p5=float(np.percentile(sharpes, 5)),
            sharpe_p95=float(np.percentile(sharpes, 95)),
            ruin_probability=float(ruin_prob),
            loss_probability=float(loss_prob),
            profit_probability=float(profit_prob),
            return_distribution=returns,
            max_dd_distribution=max_dds,
            sharpe_distribution=sharpes,
        )

    def _empty_result(self, method: str) -> MonteCarloResult:
        """空结果（数据不足时）"""
        return MonteCarloResult(
            n_simulations=0,
            method=method,
            return_median=0, return_mean=0, return_std=0,
            return_p5=0, return_p25=0, return_p75=0, return_p95=0,
            max_dd_median=0, max_dd_p75=0, max_dd_p95=0, max_dd_cvar_95=0,
            sharpe_median=0, sharpe_p5=0, sharpe_p95=0,
            ruin_probability=0, loss_probability=0, profit_probability=0,
        )


__all__ = ["MonteCarloSimulator", "MonteCarloResult"]
