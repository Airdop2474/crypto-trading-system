"""性能指标计算.

计算回测的各种性能指标
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.utils.logger import logger


class PerformanceMetrics:
    """性能指标计算器"""

    @staticmethod
    def calculate_all(results: Dict[str, Any]) -> Dict[str, float]:
        """
        计算所有性能指标

        参数：
            results: 回测结果

        返回：
            性能指标字典
        """
        equity_curve = pd.DataFrame(results["equity_curve"])
        trades = results["trades"]
        initial_capital = results["initial_capital"]

        metrics: Dict[str, float] = {}

        # 基本指标
        metrics["total_return"] = PerformanceMetrics.total_return(
            initial_capital, equity_curve
        )
        metrics["annual_return"] = PerformanceMetrics.annual_return(
            equity_curve
        )

        # 风险指标
        metrics["max_drawdown"] = PerformanceMetrics.max_drawdown(
            equity_curve
        )
        metrics["sharpe_ratio"] = PerformanceMetrics.sharpe_ratio(
            equity_curve
        )

        # 交易指标
        metrics["total_trades"] = len(trades)
        metrics["win_rate"] = PerformanceMetrics.win_rate(trades)
        metrics["profit_factor"] = PerformanceMetrics.profit_factor(trades)
        metrics["avg_trade"] = PerformanceMetrics.avg_trade(trades)

        # 新增指标
        metrics["sortino_ratio"] = PerformanceMetrics.sortino_ratio(
            equity_curve
        )
        metrics["max_drawdown_duration"] = PerformanceMetrics.max_drawdown_duration(
            equity_curve
        )
        metrics["avg_win_loss_ratio"] = PerformanceMetrics.avg_win_loss_ratio(
            trades
        )
        metrics["kelly_criterion"] = PerformanceMetrics.kelly_criterion(trades)

        return metrics

    @staticmethod
    def total_return(initial_capital: float, equity_curve: pd.DataFrame) -> float:
        """
        计算总收益率

        参数：
            initial_capital: 初始资金
            equity_curve: 权益曲线

        返回：
            总收益率
        """
        if equity_curve.empty:
            return 0.0

        final_equity = float(equity_curve.iloc[-1]["total_equity"])
        return (final_equity - initial_capital) / initial_capital

    @staticmethod
    def annual_return(equity_curve: pd.DataFrame) -> float:
        """
        计算年化收益率

        参数：
            equity_curve: 权益曲线

        返回：
            年化收益率
        """
        if len(equity_curve) < 2:
            return 0.0

        # 计算总天数
        start_time = pd.Timestamp(equity_curve.iloc[0]["time"])
        end_time = pd.Timestamp(equity_curve.iloc[-1]["time"])
        total_days = (end_time - start_time).total_seconds() / 86400

        if total_days <= 0:
            return 0.0

        # 计算总收益率
        start_equity = float(equity_curve.iloc[0]["total_equity"])
        end_equity = float(equity_curve.iloc[-1]["total_equity"])
        total_return = (end_equity - start_equity) / start_equity

        # 年化
        years = total_days / 365.0
        if years <= 0:
            return 0.0

        # 复利年化公式：(1 + r)^(1/years) - 1
        annual_return = (1 + total_return) ** (1 / years) - 1

        return float(annual_return)

    @staticmethod
    def max_drawdown(equity_curve: pd.DataFrame) -> float:
        """
        计算最大回撤

        参数：
            equity_curve: 权益曲线

        返回：
            最大回撤（负数）
        """
        if equity_curve.empty:
            return 0.0

        equity = equity_curve["total_equity"].values

        # 计算累计最大值
        cummax = np.maximum.accumulate(equity)

        # 计算回撤
        drawdown = (equity - cummax) / cummax

        # 最大回撤
        max_dd = drawdown.min()
        return float(max_dd)

    @staticmethod
    def sharpe_ratio(equity_curve: pd.DataFrame, risk_free_rate: float = 0.0) -> float:
        """
        计算夏普比率

        参数：
            equity_curve: 权益曲线
            risk_free_rate: 无风险利率（年化）

        返回：
            夏普比率
        """
        if len(equity_curve) < 2:
            return 0.0

        # 计算日收益率
        equity = equity_curve["total_equity"].values
        returns = np.diff(equity) / equity[:-1]

        if len(returns) == 0:
            return 0.0

        # 平均收益率
        mean_return = returns.mean()

        # 收益率标准差
        std_return = returns.std()

        if std_return == 0:
            return 0.0

        # 从权益曲线时间戳推断每年周期数（自动适配 4h/1h/1d 等周期）
        periods_per_year = PerformanceMetrics._infer_periods_per_year(equity_curve)

        # 夏普比率（年化系数 sqrt(periods_per_year)）
        sharpe = (
            (mean_return - risk_free_rate / periods_per_year)
            / std_return
            * np.sqrt(periods_per_year)
        )

        return float(sharpe)

    @staticmethod
    def _infer_periods_per_year(equity_curve: pd.DataFrame) -> float:
        """
        从权益曲线的时间戳推断每年的周期数

        例如 4h 周期 -> 365 * 24 / 4 = 2190，日频 -> 365

        参数：
            equity_curve: 权益曲线

        返回：
            每年周期数（无法推断时回退到 365）
        """
        if len(equity_curve) < 2:
            return 365.0

        times = pd.to_datetime(equity_curve["time"])
        mode_result = times.diff().dropna().mode()
        mode_delta = mode_result.iloc[0] if len(mode_result) > 0 else pd.NaT

        if pd.isna(mode_delta):
            return 365.0

        seconds = mode_delta.total_seconds()
        if seconds <= 0:
            return 365.0

        return float(365.0 * 86400.0 / seconds)

    @staticmethod
    def _get_closed_trades(trades: List[Dict]) -> List[Dict]:
        """获取已平仓交易（SELL 或 LIQUIDATE），统一过滤"""
        return [t for t in trades if t.get("type") in ("SELL", "LIQUIDATE")]

    @staticmethod
    def win_rate(trades: List[Dict]) -> float:
        """
        计算胜率

        参数：
            trades: 交易记录

        返回：
            胜率（0-1）
        """
        if not trades:
            return 0.0

        closed_trades = PerformanceMetrics._get_closed_trades(trades)

        if not closed_trades:
            return 0.0

        winning_trades = sum(1 for t in closed_trades if t.get("profit", 0) > 0)

        return winning_trades / len(closed_trades)

    @staticmethod
    def profit_factor(trades: List[Dict]) -> float:
        """
        计算盈亏比（盈利因子）

        参数：
            trades: 交易记录

        返回：
            盈亏比（总盈利/总亏损）
        """
        if not trades:
            return 0.0

        closed_trades = PerformanceMetrics._get_closed_trades(trades)

        if not closed_trades:
            return 0.0

        total_profit = sum(
            t.get("profit", 0) for t in closed_trades if t.get("profit", 0) > 0
        )
        total_loss = abs(
            sum(t.get("profit", 0) for t in closed_trades if t.get("profit", 0) < 0)
        )

        if total_loss == 0:
            return 999.0 if total_profit > 0 else 0.0  # 999 = 标记"无亏损"

        return float(total_profit / total_loss)

    @staticmethod
    def avg_trade(trades: List[Dict]) -> float:
        """
        计算平均每笔交易盈亏

        参数：
            trades: 交易记录

        返回：
            平均盈亏
        """
        if not trades:
            return 0.0

        closed_trades = PerformanceMetrics._get_closed_trades(trades)

        if not closed_trades:
            return 0.0

        total_profit = sum(t.get("profit", 0) for t in closed_trades)

        return float(total_profit / len(closed_trades))

    @staticmethod
    def sortino_ratio(equity_curve: pd.DataFrame, risk_free_rate: float = 0.0) -> float:
        """
        计算 Sortino 比率（只惩罚下行波动，比 Sharpe 更适合加密市场）

        参数：
            equity_curve: 权益曲线
            risk_free_rate: 无风险利率（年化）

        返回：
            Sortino 比率
        """
        if len(equity_curve) < 2:
            return 0.0

        equity = equity_curve["total_equity"].values
        returns = np.diff(equity) / equity[:-1]

        if len(returns) == 0:
            return 0.0

        mean_return = returns.mean()
        periods_per_year = PerformanceMetrics._infer_periods_per_year(equity_curve)

        # 下行标准差（只计算负收益的标准差）
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            # 无下行波动时返回有限大数（与 profit_factor=999.0 约定一致），
            # 避免 inf 破坏 JSON 序列化与下游加权评分
            logger.info("Sortino: no downside volatility, returning 999.0")
            return 999.0 if mean_return > 0 else 0.0

        downside_std = downside_returns.std()
        if downside_std == 0:
            return 0.0

        sortino = (
            (mean_return - risk_free_rate / periods_per_year)
            / downside_std
            * np.sqrt(periods_per_year)
        )
        return float(sortino)

    @staticmethod
    def max_drawdown_duration(equity_curve: pd.DataFrame) -> float:
        """
        计算最大回撤持续时间（从峰值到恢复或至今的最大 bar 数）

        参数：
            equity_curve: 权益曲线

        返回：
            最大回撤持续 bar 数
        """
        if len(equity_curve) < 2:
            return 0.0

        equity = equity_curve["total_equity"].values
        cummax = np.maximum.accumulate(equity)

        # 标记是否处于回撤（当前权益 < 峰值）
        in_drawdown = equity < cummax

        if not in_drawdown.any():
            return 0.0

        # 计算最长连续回撤段
        max_duration = 0
        current_duration = 0
        for dd in in_drawdown:
            if dd:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return float(max_duration)

    @staticmethod
    def avg_win_loss_ratio(trades: List[Dict]) -> float:
        """
        计算平均盈利/平均亏损比

        参数：
            trades: 交易记录

        返回：
            平均盈利 / 平均亏损（绝对值），无亏损返回 inf
        """
        if not trades:
            return 0.0

        closed_trades = PerformanceMetrics._get_closed_trades(trades)
        if not closed_trades:
            return 0.0

        wins = [t.get("profit", 0) for t in closed_trades if t.get("profit", 0) > 0]
        losses = [t.get("profit", 0) for t in closed_trades if t.get("profit", 0) < 0]

        if not wins:
            return 0.0
        if not losses:
            return 999.0

        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss == 0:
            return 999.0

        return float(avg_win / avg_loss)

    @staticmethod
    def kelly_criterion(trades: List[Dict]) -> float:
        """
        计算 Kelly 比率（最优仓位比例）

        Kelly = W - (1 - W) / R
        W = 胜率，R = 平均盈亏比

        参数：
            trades: 交易记录

        返回：
            Kelly 比率（0-1，0 表示不应交易）
        """
        if not trades:
            return 0.0

        closed_trades = PerformanceMetrics._get_closed_trades(trades)
        if not closed_trades:
            return 0.0

        total = len(closed_trades)
        wins = sum(1 for t in closed_trades if t.get("profit", 0) > 0)
        losses = sum(1 for t in closed_trades if t.get("profit", 0) < 0)

        if total == 0 or wins == 0 or losses == 0:
            return 0.0

        win_rate = wins / total
        avg_win_loss = PerformanceMetrics.avg_win_loss_ratio(trades)

        if avg_win_loss == 0 or avg_win_loss >= 999.0:
            return 0.0

        kelly = win_rate - (1 - win_rate) / avg_win_loss
        return float(max(0.0, kelly))


# 导出
__all__ = ["PerformanceMetrics"]
