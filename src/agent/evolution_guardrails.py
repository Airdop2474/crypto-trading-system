"""
策略进化安全阈值

6 道防线确保自动应用的参数不会引入过度风险：
1. 参数合法性（PARAM_SCHEMA 校验）
2. Sharpe 提升 ≥ 阈值
3. OOS 回撤 < 上限
4. OOS 窗口稳定性（标准差/均值 < 阈值）
5. 最低交易笔数
6. 窗口共识（≥ N 个窗口独立通过）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import pandas as pd
from loguru import logger


@dataclass
class EvolutionThresholds:
    """进化安全阈值配置。"""

    min_sharpe_improvement: float = 0.10   # Sharpe 至少提升 10%
    max_drawdown_limit: float = 0.15       # OOS 回撤 < 15%
    max_oos_degradation: float = 0.50      # OOS Sharpe 标准差 < 均值 50%
    min_total_trades: int = 10             # 每窗口至少 10 笔交易
    min_oos_windows: int = 2               # 至少 2 个窗口通过


class EvolutionGuardrails:
    """策略进化安全校验。"""

    def __init__(self, thresholds: EvolutionThresholds | None = None):
        self.thresholds = thresholds or EvolutionThresholds()

    def validate(
        self,
        strategy_class,
        new_params: Dict[str, Any],
        walk_forward_df: pd.DataFrame,
        current_sharpe: float,
        risk_manager_state: str = "ACTIVE",
    ) -> tuple[bool, List[str]]:
        """执行全部安全校验。

        参数:
            strategy_class: 策略类（需有 PARAM_SCHEMA）
            new_params: 候选新参数
            walk_forward_df: walk_forward() 返回的 DataFrame
            current_sharpe: 当前策略的 Sharpe 比率
            risk_manager_state: RiskManager 状态（ACTIVE/PAUSED/STOPPED）

        返回:
            (passed: bool, reasons: list[str])
            passed=True 表示所有校验通过，可以安全应用
        """
        reasons: List[str] = []
        t = self.thresholds

        # 0. 风控状态检查
        if risk_manager_state != "ACTIVE":
            reasons.append(f"风控状态为 {risk_manager_state}，拒绝自动应用")
            return False, reasons

        # 1. 参数合法性
        schema = getattr(strategy_class, "PARAM_SCHEMA", {})
        for key, value in new_params.items():
            if key not in schema:
                continue
            spec = schema[key]
            lo = spec.get("min")
            hi = spec.get("max")
            if lo is not None and value < lo:
                reasons.append(f"参数 {key}={value} 低于下限 {lo}")
            if hi is not None and value > hi:
                reasons.append(f"参数 {key}={value} 超过上限 {hi}")

        if reasons:
            return False, reasons

        # 2-6 需要 walk_forward 数据
        if walk_forward_df is None or walk_forward_df.empty:
            reasons.append("walk_forward 无数据")
            return False, reasons

        # 2. Sharpe 提升
        oos_sharpes = walk_forward_df["out_sample_sharpe"].values
        avg_oos_sharpe = float(oos_sharpes.mean())
        target_sharpe = current_sharpe * (1 + t.min_sharpe_improvement)

        if avg_oos_sharpe < target_sharpe:
            reasons.append(
                f"OOS 平均 Sharpe {avg_oos_sharpe:.3f} < 目标 {target_sharpe:.3f} "
                f"(当前 {current_sharpe:.3f} × {1 + t.min_sharpe_improvement})"
            )

        # 3. OOS 回撤上限
        worst_drawdown = float(walk_forward_df["out_sample_max_drawdown"].max())
        if worst_drawdown > t.max_drawdown_limit:
            reasons.append(
                f"最差 OOS 回撤 {worst_drawdown:.2%} > 上限 {t.max_drawdown_limit:.0%}"
            )

        # 4. OOS 稳定性
        if len(oos_sharpes) >= 2 and avg_oos_sharpe != 0:
            sharpe_std = float(oos_sharpes.std())
            cv = sharpe_std / abs(avg_oos_sharpe)
            if cv > t.max_oos_degradation:
                reasons.append(
                    f"OOS Sharpe CV={cv:.2%} > 上限 {t.max_oos_degradation:.0%} "
                    f"(std={sharpe_std:.3f}, mean={avg_oos_sharpe:.3f})"
                )

        # 5. 交易数量
        trade_counts = walk_forward_df["out_sample_trades"].values
        min_trades = int(trade_counts.min())
        if min_trades < t.min_total_trades:
            reasons.append(
                f"最少交易笔数 {min_trades} < 下限 {t.min_total_trades}"
            )

        # 6. 窗口共识：独立检查每个窗口的 Sharpe > 0 且 回撤 < 上限
        passed_windows = 0
        for _, row in walk_forward_df.iterrows():
            window_sharpe = row["out_sample_sharpe"]
            window_dd = row["out_sample_max_drawdown"]
            window_trades = row["out_sample_trades"]

            if (
                window_sharpe > 0
                and window_dd <= t.max_drawdown_limit
                and window_trades >= t.min_total_trades
            ):
                passed_windows += 1

        if passed_windows < t.min_oos_windows:
            reasons.append(
                f"通过窗口数 {passed_windows} < 最低要求 {t.min_oos_windows}"
            )

        passed = len(reasons) == 0
        if passed:
            logger.info(
                f"Guardrails 通过: avg_sharpe={avg_oos_sharpe:.3f}, "
                f"worst_dd={worst_drawdown:.2%}, passed_windows={passed_windows}"
            )
        else:
            logger.info(f"Guardrails 拒绝: {'; '.join(reasons)}")

        return passed, reasons
