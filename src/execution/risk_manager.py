"""
风控管理器（Phase 5）

独立的账户级风控状态机，与策略/Broker 解耦。

状态机：
    ACTIVE  -> 正常交易
    PAUSED  -> 熔断暂停，需人工 resume() 恢复
    STOPPED -> 紧急停止，需人工 reset() 重置（最强保护）

熔断条件（来自 LIVE_TRADING_CHECKLIST.md / config）：
    - 当日亏损达到上限
    - 连续亏损达到上限
    - 数据异常
    - API 连续失败达到阈值
    - 账户级最大回撤达到上限（累计慢亏保护）

职责边界：本模块负责账户级熔断与开关；每单的资金/仓位 sanity 检查
仍由 Broker 负责（见 PaperBroker）。
"""

from typing import List, Optional
import pandas as pd

from src.utils.logger import logger


# 状态常量
ACTIVE = "ACTIVE"
PAUSED = "PAUSED"
STOPPED = "STOPPED"


class RiskManager:
    """账户级风控状态机"""

    def __init__(
        self,
        capital_base: float,
        max_daily_loss: float = 0.03,
        max_consecutive_losses: int = 5,
        max_total_position: float = 0.60,
        max_api_failures: int = 3,
        max_total_drawdown: float = 0.15,
    ):
        """
        参数：
            capital_base: 资金基准（用于日亏损比例计算）
            max_daily_loss: 当日亏损上限（占资金基准比例）
            max_consecutive_losses: 连续亏损上限（笔）
            max_total_position: 总仓位上限（占总价值比例）
            max_api_failures: API 连续失败熔断阈值
            max_total_drawdown: 账户级最大回撤上限（占总价值比例，默认 15%）
        """
        if capital_base <= 0:
            raise ValueError("capital_base must be positive")

        self.capital_base = capital_base
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_total_position = max_total_position
        self.max_api_failures = max_api_failures
        self.max_total_drawdown = max_total_drawdown

        self._init_state()
        logger.info(
            f"RiskManager initialized: capital_base={capital_base}, "
            f"max_daily_loss={max_daily_loss}, "
            f"max_consecutive_losses={max_consecutive_losses}, "
            f"max_total_drawdown={max_total_drawdown}"
        )

    def _init_state(self) -> None:
        self.state = ACTIVE
        self.daily_pnl = 0.0
        self.current_day = None
        self.consecutive_losses = 0
        self.api_failures = 0
        self.events: List[dict] = []
        # 账户级最大回撤跟踪
        self.cumulative_pnl = 0.0          # 累计已实现盈亏
        self.peak_equity = self.capital_base  # 权益峰值（近似）

    # ---- 状态查询 ----

    def can_trade(self) -> bool:
        """是否允许交易（仅 ACTIVE）"""
        return self.state == ACTIVE

    def is_paused(self) -> bool:
        return self.state == PAUSED

    def is_stopped(self) -> bool:
        return self.state == STOPPED

    # ---- 事件记录与状态转移 ----

    def _log_event(self, event_type: str, reason: str) -> None:
        """记录风控事件（供告警/审计）"""
        self.events.append({
            "type": event_type,
            "reason": reason,
            "state": self.state,
        })
        logger.warning(f"RiskManager[{event_type}] {reason} -> {self.state}")

    def _trip_pause(self, reason: str) -> None:
        """触发熔断暂停（STOPPED 状态不降级）"""
        if self.state == STOPPED:
            return
        self.state = PAUSED
        self._log_event("PAUSE", reason)

    # ---- 仓位检查（账户级，与 Broker 的每单检查互补）----

    def check_position(self, new_position_value: float, total_value: float) -> bool:
        """新持仓市值占比是否在上限内"""
        if total_value <= 0:
            return False
        return (new_position_value / total_value) <= self.max_total_position

    # ---- 成交回报：驱动日亏损/连亏熔断 ----

    def record_fill(self, trade: dict) -> None:
        """处理一笔成交，更新盈亏并按需熔断"""
        profit = trade.get("profit")
        if profit is None:
            return  # 买入无已实现盈亏

        # 当日盈亏按成交日重置基准
        trade_time = trade.get("time")
        if trade_time is not None:
            day = pd.Timestamp(trade_time).date()
            if self.current_day != day:
                self.current_day = day
                self.daily_pnl = 0.0

        self.daily_pnl += profit
        self.cumulative_pnl += profit

        # 连亏计数
        if profit < 0:
            self.consecutive_losses += 1
        elif profit > 0:
            self.consecutive_losses = 0

        if self.consecutive_losses >= self.max_consecutive_losses:
            self._trip_pause(
                f"consecutive losses {self.consecutive_losses} "
                f">= {self.max_consecutive_losses}"
            )

        # 当日亏损熔断
        if self.daily_pnl < 0:
            loss_ratio = abs(self.daily_pnl) / self.capital_base
            if loss_ratio >= self.max_daily_loss:
                self._trip_pause(f"daily loss {loss_ratio:.2%}")

        # 账户级最大回撤熔断
        current_equity = self.capital_base + self.cumulative_pnl
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            if drawdown >= self.max_total_drawdown:
                self._trip_pause(
                    f"total drawdown {drawdown:.2%} >= {self.max_total_drawdown:.2%}"
                )

    # ---- 数据/API 异常熔断 ----

    def record_data_anomaly(self, reason: str = "data anomaly") -> None:
        """数据异常 -> 暂停"""
        self._trip_pause(reason)

    def record_api_failure(self, reason: str = "api failure") -> None:
        """API 失败计数，连续达到阈值 -> 暂停"""
        self.api_failures += 1
        if self.api_failures >= self.max_api_failures:
            self._trip_pause(
                f"api failures {self.api_failures} >= {self.max_api_failures}: {reason}"
            )

    def record_api_success(self) -> None:
        """API 成功，重置连续失败计数"""
        self.api_failures = 0

    # ---- 紧急停止与人工恢复 ----

    def emergency_stop(self, reason: str = "manual emergency stop") -> None:
        """紧急停止 -> STOPPED（最强保护，需 reset 才能恢复）"""
        self.state = STOPPED
        self._log_event("EMERGENCY_STOP", reason)

    def resume(self) -> bool:
        """
        人工恢复：PAUSED -> ACTIVE。重置瞬时熔断计数（连亏/API），
        保留当日盈亏。STOPPED 状态不能 resume（需 reset）。

        返回：是否成功恢复
        """
        if self.state != PAUSED:
            logger.warning(f"resume() ignored: state={self.state} (not PAUSED)")
            return False
        self.consecutive_losses = 0
        self.api_failures = 0
        self.state = ACTIVE
        self._log_event("RESUME", "manual resume")
        return True

    def reset(self) -> None:
        """完全重置到 ACTIVE（清空所有状态，含 STOPPED）"""
        self._init_state()
        logger.info("RiskManager reset to ACTIVE")


# 导出
__all__ = ["RiskManager", "ACTIVE", "PAUSED", "STOPPED"]
