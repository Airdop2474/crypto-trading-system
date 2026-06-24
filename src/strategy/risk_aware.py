"""风险感知策略基类

提取 GridTrading / RSIMomentum / SimpleMA 三份策略中公共的熔断逻辑，
统一封装为 RiskAwareStrategy，子类只需继承并调用 _is_paused() 即可。

与 RiskManager 的职责分工：
    本模块是策略级熔断（连亏/日亏/回撤），回答"策略是否适应当前市场"。
    RiskManager 是账户级熔断，回答"账户整体是否安全"。两者 OR 关系。

熔断条件（按序检测）：
1. 累计回撤 > max_drawdown（默认 15%）→ 抛出 CircuitBreaker
2. 连亏笔数 >= max_consecutive_losses    → 抛出 CircuitBreaker
3. 当日亏损 >= max_daily_loss（占初始资金比例）→ 抛出 CircuitBreaker
"""

from datetime import date as DateType
from typing import Optional, Union, List

import pandas as pd
import numpy as np

from src.strategy.base import Strategy, Order
from src.strategy.stop_loss import StopLossManager, StopLossConfig
from src.utils.logger import logger


class CircuitBreaker(Exception):
    """熔断异常。

    当策略触发熔断条件时抛出，引擎可捕获此异常以做出相应处理
    （暂停策略、清仓、通知等）。
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class RiskAwareStrategy(Strategy):
    """带统一熔断逻辑的策略基类。

    子类应在 __init__ 末尾调用 self._init_risk_state()，
    并在 on_bar() 开头调用 self._is_paused() 检查是否暂停。

    参数：
        name: 策略名称
        max_consecutive_losses: 连亏熔断阈值（默认 3）
        max_daily_loss: 当日亏损熔断阈值（占初始资金比例，默认 0.02）
        max_drawdown: 累计回撤熔断阈值（默认 0.15）
        initial_capital: 初始资金（熔断基准，默认 10000.0）
    """

    def __init__(
        self,
        name: str = "RiskAwareStrategy",
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        max_drawdown: float = 0.15,
        initial_capital: float = 10000.0,
        stop_loss_config: Optional[StopLossConfig] = None,
    ):
        super().__init__(name=name)
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        self.initial_capital = initial_capital

        # 熔断状态（由 _init_risk_state 初始化）
        self._consecutive_losses: int = 0
        self._day_start_balance: float = initial_capital
        self._paused: bool = False
        self._paused_reason: Optional[str] = None
        self._auto_resume_count: int = 0
        self._current_day: Optional[DateType] = None
        self._daily_pnl: float = 0.0
        self._peak_balance: float = initial_capital
        self._current_balance: float = initial_capital

        # 止损管理器
        self._stop_loss: Optional[StopLossManager] = None
        if stop_loss_config is not None:
            self._stop_loss = StopLossManager(stop_loss_config)
            logger.info(
                f"StopLoss enabled for {name}: type={stop_loss_config.stop_type}"
            )

    def _init_risk_state(self) -> None:
        """初始化/重置风险追踪状态。

        子类应在 __init__ 设置自身参数后调用，reset() 中也应调用。
        """
        self._consecutive_losses = 0
        self._day_start_balance = self.initial_capital
        self._paused = False
        self._paused_reason = None
        self._auto_resume_count = 0
        self._current_day = None
        self._daily_pnl = 0.0
        self._peak_balance = self.initial_capital
        self._current_balance = self.initial_capital

    def _is_paused(self, current_time=None) -> bool:
        """检查策略是否处于熔断暂停状态。

        子类应在 on_bar() 开头调用：若返回 True 则跳过本根 K 线的信号生成。

        日切自动恢复：如果当前交易日与暂停日不同且当日亏损未超限额，
        自动清除熔断状态。最多自动恢复 max_auto_resumes 次（默认 3 次），
        超过后需手动 reset()。

        参数：
            current_time: 当前 K 线时间（可选的 datetime/None，用于日切检测）

        返回：
            True:  策略已暂停，不应生成交易信号
            False: 策略正常运行
        """
        if not self._paused:
            return False

        # 日切自动恢复（仅日亏/连亏熔断；回撤熔断不自动恢复）
        if current_time is not None and self._auto_resume_count < 3:
            bar_day = pd.Timestamp(current_time).date() if hasattr(current_time, 'date') else None
            if bar_day is not None and self._current_day != bar_day:
                if "drawdown" not in (self._paused_reason or ""):
                    self._consecutive_losses = 0
                    self._daily_pnl = 0.0
                    self._paused = False
                    self._paused_reason = None
                    self._auto_resume_count += 1
                    self._current_day = bar_day
                    self._day_start_balance = self._current_balance
                    logger.info(
                        f"CircuitBreaker: auto-resumed on new day "
                        f"(count={self._auto_resume_count}/3)"
                    )
                    return False

        return True

    def resume(self) -> None:
        """手动恢复策略（清除熔断状态）。

        调用后策略恢复正常信号生成。连亏/日亏/回撤计数清零。
        注意：这绕过了自动恢复次数限制，应由运维人员显式调用。
        """
        was_paused = self._paused
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._paused = False
        self._paused_reason = None
        if was_paused:
            logger.info("CircuitBreaker: manually resumed (all counters reset)")

    def _trigger_breaker(self, reason: str) -> None:
        """触发熔断：设置暂停状态并记录原因。"""
        self._paused = True
        self._paused_reason = reason
        logger.warning(f"CircuitBreaker triggered: {reason}")

    def on_fill(self, trade: dict) -> None:
        """成交回报钩子：统一熔断逻辑 + 止损状态更新。

        在每笔订单成交后由引擎调用，依次检测累计回撤、连亏笔数、
        当日亏损三条熔断线。任一触发即设置 _paused = True 并抛出
        CircuitBreaker 异常。

        同时更新止损管理器的持仓状态（入场价、最高价等）。

        参数：
            trade: 成交记录字典，需包含 'profit' 和 'time' 字段。
        """
        # 更新止损管理器状态
        if self._stop_loss is not None:
            self._stop_loss.on_fill(trade)

        profit = trade.get("profit")
        if profit is None:
            return  # 买入开仓无已实现盈亏，不计入熔断

        # 跨日重置当日累计盈亏
        trade_day = pd.Timestamp(trade["time"]).date()
        if self._current_day != trade_day:
            self._current_day = trade_day
            self._daily_pnl = 0.0
            self._day_start_balance = self._current_balance

        self._daily_pnl += profit
        self._current_balance += profit

        # 更新峰值余额
        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance

        # 条件 3: 累计回撤检测（基于峰值回撤）
        if self._peak_balance > 0:
            drawdown = (self._peak_balance - self._current_balance) / self._peak_balance
            if drawdown >= self.max_drawdown:
                self._trigger_breaker(
                    f"max drawdown {drawdown:.2%} >= threshold {self.max_drawdown:.2%}"
                )

        # 连亏计数
        if profit < 0:
            self._consecutive_losses += 1
        elif profit > 0:
            self._consecutive_losses = 0

        # 条件 1: 连亏熔断
        if self._consecutive_losses >= self.max_consecutive_losses:
            self._trigger_breaker(
                f"{self._consecutive_losses} consecutive losses (threshold={self.max_consecutive_losses})"
            )

        # 条件 2: 当日亏损熔断
        if self._daily_pnl < 0 and self.initial_capital > 0:
            loss_ratio = abs(self._daily_pnl) / self.initial_capital
            if loss_ratio >= self.max_daily_loss:
                self._trigger_breaker(
                    f"daily loss {loss_ratio:.2%} >= threshold {self.max_daily_loss:.2%}"
                )

    def reset(self) -> None:
        """重置策略状态（含风险追踪）。"""
        super().reset()
        self._init_risk_state()
        if self._stop_loss is not None:
            self._stop_loss.reset()

    # ------------------------------------------------------------------
    # 止损检查（子类在 on_bar 中调用）
    # ------------------------------------------------------------------

    def _check_stop_loss(
        self,
        current_price: float,
        current_time=None,
        atr: Optional[float] = None,
    ) -> tuple[bool, str]:
        """检查是否触发止损。

        子类应在 on_bar() 中、策略信号生成之前调用此方法。
        如果返回 True，子类应直接返回 'SELL'（单仓位策略）或
        生成卖出 Order 列表（多仓位策略），跳过策略本身的信号逻辑。

        参数：
            current_price: 当前 K 线收盘价
            current_time: 当前 K 线时间
            atr: 当前 ATR 值（ATR 止损用，可选）

        返回：
            (是否触发, 触发原因)
        """
        if self._stop_loss is None:
            return False, ""

        if not self._stop_loss.in_position:
            return False, ""

        triggered, reason = self._stop_loss.check_stop(
            current_price, current_time, atr
        )

        if triggered:
            # 发送 Telegram 通知（异步，不阻塞）
            try:
                from src.utils.telegram_notifier import notifier
                info = self._stop_loss.get_stop_info()
                msg = (
                    f"止损触发: {self.name}\n\n"
                    f"• 原因: {reason}\n"
                    f"• 入场价: {info.get('entry_price')}\n"
                    f"• 当前价: {current_price:.2f}\n"
                    f"• 持仓 K 线: {info.get('bars_held')}\n"
                    f"• 止损类型: {info.get('stop_type')}"
                )
                notifier.send_warning_sync(msg)
            except Exception:
                pass  # 通知失败不影响止损逻辑

        return triggered, reason

    def _get_stop_loss_info(self) -> dict:
        """获取止损状态信息（供前端/日志使用）"""
        if self._stop_loss is None:
            return {"enabled": False}
        info = self._stop_loss.get_stop_info()
        info["enabled"] = True
        return info

    # ---- 向后兼容属性（旧代码直接访问 public 属性） ----

    @property
    def paused(self) -> bool:
        """向后兼容：委托给 _paused"""
        return self._paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self._paused = value

    @property
    def consecutive_losses(self) -> int:
        """向后兼容：委托给 _consecutive_losses"""
        return self._consecutive_losses

    @consecutive_losses.setter
    def consecutive_losses(self, value: int) -> None:
        self._consecutive_losses = value

    @property
    def current_day(self):
        """向后兼容：委托给 _current_day"""
        return self._current_day

    @current_day.setter
    def current_day(self, value) -> None:
        self._current_day = value

    @property
    def daily_pnl(self) -> float:
        """向后兼容：委托给 _daily_pnl"""
        return self._daily_pnl

    @daily_pnl.setter
    def daily_pnl(self, value: float) -> None:
        self._daily_pnl = value

    # ------------------------------------------------------------------
    # ADX 趋势过滤器
    # ------------------------------------------------------------------
    _adx_period: int = 14
    _adx_high_buffer: list = []
    _adx_low_buffer: list = []
    _adx_close_buffer: list = []
    _adx_value: Optional[float] = None
    _adx_trend_direction: Optional[str] = None
    _adx_initialized: bool = False

    def _init_adx(self, period: int = 14) -> None:
        """初始化 ADX 状态。"""
        self._adx_period = period
        self._adx_high_buffer.clear()
        self._adx_low_buffer.clear()
        self._adx_close_buffer.clear()
        self._adx_value = None
        self._adx_trend_direction = None
        self._adx_initialized = False

    def _update_adx(self, high: float, low: float, close: float) -> None:
        """增量更新 ADX。

        计算：+DM, -DM, TR → 平滑 → +DI, -DI → DX → ADX(平滑)
        """
        self._adx_high_buffer.append(high)
        self._adx_low_buffer.append(low)
        self._adx_close_buffer.append(close)

        n = self._adx_period
        if len(self._adx_high_buffer) < n + 1:
            return

        # 只保留需要的数据
        h = self._adx_high_buffer[-(n + 1):]
        l_vals = self._adx_low_buffer[-(n + 1):]
        c = self._adx_close_buffer[-(n + 1):]
        self._adx_high_buffer = h
        self._adx_low_buffer = l_vals
        self._adx_close_buffer = c

        # 计算 +DM, -DM, TR
        plus_dm = []
        minus_dm = []
        tr = []
        for i in range(1, len(h)):
            up_move = h[i] - h[i - 1]
            down_move = l_vals[i - 1] - l_vals[i]
            p = up_move if up_move > down_move and up_move > 0 else 0
            m = down_move if down_move > up_move and down_move > 0 else 0
            plus_dm.append(p)
            minus_dm.append(m)
            tr.append(max(h[i] - l_vals[i], abs(h[i] - c[i - 1]), abs(l_vals[i] - c[i - 1])))

        if not plus_dm:
            return

        # Wilder 平滑
        def wilder_smooth(values):
            result = [values[0]]
            for v in values[1:]:
                result.append(result[-1] * (n - 1) / n + v / n)
            return result

        smooth_plus = wilder_smooth(plus_dm)
        smooth_minus = wilder_smooth(minus_dm)
        smooth_tr = wilder_smooth(tr)

        plus_di = 100 * smooth_plus[-1] / smooth_tr[-1] if smooth_tr[-1] > 0 else 0
        minus_di = 100 * smooth_minus[-1] / smooth_tr[-1] if smooth_tr[-1] > 0 else 0

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0

        if self._adx_value is None:
            self._adx_value = dx
        else:
            self._adx_value = (self._adx_value * (n - 1) + dx) / n

        self._adx_trend_direction = "up" if plus_di > minus_di else "down"
        self._adx_initialized = True

    def _is_trending(self, threshold: float = 25.0) -> bool:
        """ADX > threshold → 趋势市。"""
        return self._adx_initialized and (self._adx_value or 0) > threshold

    def _is_ranging(self, threshold: float = 20.0) -> bool:
        """ADX < threshold → 震荡市。"""
        return self._adx_initialized and (self._adx_value or 0) < threshold

    def _get_adx(self) -> Optional[float]:
        return self._adx_value


__all__ = ["RiskAwareStrategy", "CircuitBreaker"]
