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

双层熔断职责边界（与 RiskAwareStrategy 的分工）：
    - RiskAwareStrategy（策略级）：单策略连亏/日亏/回撤熔断，
      回答"这个策略是否还适合当前市场"。
    - RiskManager（账户级）：账户整体资金安全，回答"账户是否
      还在安全线内"。多策略叠加时账户可能过热，即使各策略健康。
    - 回测模式仅用策略级熔断（BacktestEngine 不接入 RiskManager）；
      纸面/实盘同时用两层（PaperTradingRunner 先 can_trade 再发单，
      成交后 record_fill）。两层 OR 关系：任一暂停即止。

本模块同时负责：每单的资金/仓位 sanity 检查仍由 Broker 负责（见 PaperBroker）。
"""

import time
import threading
from collections import deque
from typing import Deque, Dict, List, Optional
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

        self._lock = threading.Lock()
        self.capital_base = capital_base
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_total_position = max_total_position
        self.max_api_failures = max_api_failures
        self.max_total_drawdown = max_total_drawdown

        self._init_state()
        self._init_debounce()
        logger.info(
            f"RiskManager initialized: capital_base={capital_base}, "
            f"max_daily_loss={max_daily_loss}, "
            f"max_consecutive_losses={max_consecutive_losses}, "
            f"max_total_drawdown={max_total_drawdown}"
        )

    def _init_state(self) -> None:
        """初始化交易追踪状态（不含防抖计数器与回撤跟踪）。

        回撤跟踪（peak_equity / cumulative_pnl）仅在 __init__ 时初始化，
        reset() 不清零，防止绕过年化回撤熔断线。
        防抖计数器由 _init_debounce() 独立管理。
        """
        self.state = ACTIVE
        self.daily_pnl = 0.0
        self.current_day = None
        self.consecutive_losses = 0
        self.api_failures = 0
        self.events: Deque[Dict] = deque(maxlen=10000)
        # 账户级最大回撤跟踪（reset 不清零）
        self.cumulative_pnl = 0.0          # 累计已实现盈亏
        self.peak_equity = self.capital_base  # 权益峰值（近似）

    def _init_debounce(self) -> None:
        """初始化防抖计数器（仅 __init__ 调用，reset 不清零）。"""
        self._last_reset_time = 0.0
        self._reset_count = 0
        self._reset_window_start = 0.0

    # ---- 状态查询 ----

    def can_trade(self) -> bool:
        """是否允许交易（仅 ACTIVE）"""
        with self._lock:
            return self.state == ACTIVE

    def is_paused(self) -> bool:
        with self._lock:
            return self.state == PAUSED

    def is_stopped(self) -> bool:
        with self._lock:
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
        with self._lock:
            if total_value <= 0:
                return False
            return (new_position_value / total_value) <= self.max_total_position

    # ---- 成交回报：驱动日亏损/连亏熔断 ----

    def record_fill(self, trade: dict) -> None:
        """处理一笔成交，更新盈亏并按需熔断"""
        with self._lock:
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
            # profit == 0：不重置连亏（平局不改变趋势），也不递增

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
        with self._lock:
            self._trip_pause(reason)

    def record_api_failure(self, reason: str = "api failure") -> None:
        """API 失败计数，连续达到阈值 -> 暂停"""
        with self._lock:
            self.api_failures += 1
            if self.api_failures >= self.max_api_failures:
                self._trip_pause(
                    f"api failures {self.api_failures} >= {self.max_api_failures}: {reason}"
                )

    def record_api_success(self) -> None:
        """API 成功，重置连续失败计数"""
        with self._lock:
            self.api_failures = 0

    def resume(self) -> bool:
        """
        人工恢复：PAUSED -> ACTIVE。重置瞬时熔断计数（连亏/API），
        保留当日盈亏。STOPPED 状态不能 resume（需 reset）。

        返回：是否成功恢复
        """
        with self._lock:
            if self.state != PAUSED:
                logger.warning(f"resume() ignored: state={self.state} (not PAUSED)")
                return False
            self.consecutive_losses = 0
            self.api_failures = 0
            self.state = ACTIVE
            self._log_event("RESUME", "manual resume")
            return True

    # ---- 紧急停止与人工恢复 ----

    def emergency_stop(self, reason: str = "manual emergency stop") -> None:
        """紧急停止 -> STOPPED（最强保护，需 reset 才能恢复）"""
        with self._lock:
            if self.state == STOPPED:
                return
            self.state = STOPPED
            self._log_event("EMERGENCY_STOP", reason)

    def reset(self) -> None:
        """完全重置到 ACTIVE（清空所有状态，含 STOPPED）。

        防抖保护：
        - 冷却期：reset() 后 5 分钟内禁止再次 reset（强制等待）
        - 频次限制：1 小时内超过 3 次 reset → 拒绝，需人工确认

        回撤跟踪（peak_equity / cumulative_pnl）不清零：
        避免已亏损策略 reset 后绕过年化回撤熔断线。
        """
        with self._lock:
            now = time.time()
            # 冷却期检查：距上次 reset 不足 5 分钟
            cooldown = 300  # 5 分钟
            if self._last_reset_time > 0 and (now - self._last_reset_time) < cooldown:
                remaining = int(cooldown - (now - self._last_reset_time))
                logger.warning(
                    f"RiskManager reset rejected: cooling period active "
                    f"({remaining}s remaining)"
                )
                return

            # 频次限制：滑动窗口 1 小时内最多 3 次
            hour = 3600
            if now - self._reset_window_start > hour:
                self._reset_window_start = now
                self._reset_count = 0  # 窗口重置时清零计数
            if self._reset_count >= 3:
                logger.error(
                    f"RiskManager reset rejected: max 3 resets/hour exceeded. "
                    f"Manual intervention required."
                )
                return

            self._reset_count += 1
            self._last_reset_time = now

            # 保存回撤跟踪（不清零，防止绕过年化回撤熔断）
            saved_peak = self.peak_equity
            saved_cumulative = self.cumulative_pnl
            self._init_state()
            self.peak_equity = saved_peak
            self.cumulative_pnl = saved_cumulative

            logger.info(
                f"RiskManager reset to ACTIVE (reset #{self._reset_count} in current window)"
            )


# 导出
__all__ = ["RiskManager", "ACTIVE", "PAUSED", "STOPPED"]
