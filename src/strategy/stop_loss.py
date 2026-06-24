"""
止损管理器

统一的止损门面类，支持四种止损类型：
1. ATR 止损 — 入场价 - N × ATR（固定止损）
2. 移动止损 — 价格涨到激活阈值后，追踪最高价的回撤止损
3. 区间突破止损 — 价格突破交易区间上/下沿一定比例（均值回归策略用）
4. 时间止损 — 持仓超过 N 根 K 线未达标平仓

设计原则：
- 无状态检查：check_stop() 是纯函数，不修改内部状态
- 状态由 on_fill() 更新：BUY 时记录入场，SELL 时重置
- 安全边界：所有参数有 min/max 限制，防止 EvolutionEngine 优化出危险值

用法：
    slm = StopLossManager(
        stop_type="atr_trailing",
        atr_mult=1.5,
        trailing_activation=0.03,
        trailing_drawback=0.03,
        max_bars=50,
    )
    # 在策略 on_fill 中
    slm.on_fill(trade)
    # 在策略 on_bar 开头
    triggered, reason = slm.check_stop(current_price, current_time, atr)
    if triggered:
        return "SELL"  # 或 Order 列表
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal

from src.utils.logger import logger


# 止损类型
StopType = Literal["none", "atr_trailing", "range_breakout", "time_only"]

# 安全边界
MAX_STOP_PCT = 0.10   # 止损比例永远不能超过 10%
MIN_STOP_PCT = 0.01   # 止损比例永远不能低于 1%
MAX_BARS = 200        # 时间止损最多 200 根 K 线
MIN_BARS = 5          # 时间止损最少 5 根 K 线


@dataclass
class StopLossConfig:
    """止损配置

    参数说明：
        stop_type: 止损类型
            - "none": 不止损（BuyHold 用）
            - "atr_trailing": ATR 固定止损 + 移动止损（趋势策略用）
            - "range_breakout": 区间突破止损（均值回归策略用）
            - "time_only": 仅时间止损

        atr_mult: ATR 倍数（atr_trailing 用），止损 = entry - atr_mult × ATR
            安全范围 [0.5, 4.0]，默认 1.5

        trailing_activation: 移动止损激活阈值（价格涨多少开始追踪）
            安全范围 [0.01, 0.10]，默认 0.03（3%）

        trailing_drawback: 移动止损回撤比例（从最高点回撤多少触发）
            安全范围 [0.01, 0.08]，默认 0.03（3%）

        range_breakout_pct: 区间突破止损比例（突破入场价多少触发）
            安全范围 [0.02, 0.10]，默认 0.05（5%）

        max_bars: 时间止损 K 线数（0 = 不启用）
            安全范围 [0, 200]，默认 50

        min_stop_pct: 最小止损比例（防止 ATR 过小导致止损太紧）
            安全范围 [0.005, 0.03]，默认 0.01（1%）
    """
    stop_type: StopType = "atr_trailing"
    atr_mult: float = 1.5
    trailing_activation: float = 0.03
    trailing_drawback: float = 0.03
    range_breakout_pct: float = 0.05
    max_bars: int = 50
    min_stop_pct: float = 0.01

    def __post_init__(self):
        """参数安全边界校验"""
        self.atr_mult = _clamp(self.atr_mult, 0.5, 4.0)
        self.trailing_activation = _clamp(self.trailing_activation, 0.01, 0.10)
        self.trailing_drawback = _clamp(self.trailing_drawback, 0.01, 0.08)
        self.range_breakout_pct = _clamp(self.range_breakout_pct, 0.02, 0.10)
        self.max_bars = _clamp(self.max_bars, 0, MAX_BARS)
        self.min_stop_pct = _clamp(self.min_stop_pct, 0.005, 0.03)


def _clamp(val: float, lo: float, hi: float) -> float:
    """限制值在 [lo, hi] 范围内"""
    return max(lo, min(hi, val))


class StopLossManager:
    """止损管理器

    跟踪持仓的入场价、入场时间、最高价，并在 check_stop() 时
    根据配置的止损类型判断是否应该止损。

    生命周期：
        on_fill(BUY)  → 记录 entry_price, entry_time, highest_price
        check_stop()  → 每根 K 线检查是否触发止损
        on_fill(SELL) → 重置状态
    """

    def __init__(self, config: StopLossConfig):
        self.config = config

        # 持仓状态
        self._entry_price: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        self._highest_price: Optional[float] = None
        self._bars_held: int = 0
        self._in_position: bool = False

        # 当前止损价（用于日志和通知）
        self._current_stop_price: Optional[float] = None

    @property
    def in_position(self) -> bool:
        return self._in_position

    @property
    def entry_price(self) -> Optional[float]:
        return self._entry_price

    @property
    def entry_time(self) -> Optional[datetime]:
        return self._entry_time

    @property
    def current_stop_price(self) -> Optional[float]:
        return self._current_stop_price

    @property
    def bars_held(self) -> int:
        return self._bars_held

    def on_fill(self, trade: dict) -> None:
        """成交回报：更新持仓状态

        参数：
            trade: 成交记录，需包含 'type'（'buy'/'sell'）和 'price'
        """
        trade_type = trade.get("type", trade.get("side", "")).lower()
        price = float(trade.get("price", 0))

        if trade_type in ("buy", "BUY"):
            if not self._in_position:
                # 新开仓
                self._entry_price = price
                self._entry_time = trade.get("time")
                self._highest_price = price
                self._bars_held = 0
                self._in_position = True
                self._current_stop_price = None
                logger.debug(
                    f"StopLoss: entry recorded price={price}, "
                    f"type={self.config.stop_type}"
                )
            else:
                # 加仓（网格等），更新最高价
                if self._highest_price is None or price > self._highest_price:
                    self._highest_price = price
        elif trade_type in ("sell", "SELL"):
            # 清仓（全部卖出）
            if trade.get("tag") is None or trade.get("all", False):
                self._reset()
            # 部分卖出（网格单档卖出）不重置整体状态

    def _reset(self) -> None:
        """重置持仓状态"""
        self._entry_price = None
        self._entry_time = None
        self._highest_price = None
        self._bars_held = 0
        self._in_position = False
        self._current_stop_price = None

    def check_stop(
        self,
        current_price: float,
        current_time: Optional[datetime] = None,
        atr: Optional[float] = None,
    ) -> tuple[bool, str]:
        """检查是否触发止损

        参数：
            current_price: 当前价格
            current_time: 当前时间（用于时间止损）
            atr: 当前 ATR 值（ATR 止损用）

        返回：
            (是否触发, 触发原因)
            原因为空字符串表示未触发
        """
        if not self._in_position or self._entry_price is None:
            return False, ""

        # 更新最高价
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price

        # 递增持仓 bar 数
        self._bars_held += 1

        cfg = self.config

        # ---- 时间止损（所有类型通用）----
        if cfg.max_bars > 0 and self._bars_held >= cfg.max_bars:
            reason = (
                f"时间止损: 持仓 {self._bars_held} 根 K 线 "
                f"(阈值 {cfg.max_bars})"
            )
            logger.info(f"StopLoss triggered: {reason}")
            return True, reason

        # ---- ATR + 移动止损 ----
        if cfg.stop_type == "atr_trailing":
            return self._check_atr_trailing(current_price, atr)

        # ---- 区间突破止损 ----
        if cfg.stop_type == "range_breakout":
            return self._check_range_breakout(current_price)

        return False, ""

    def _check_atr_trailing(
        self, current_price: float, atr: Optional[float]
    ) -> tuple[bool, str]:
        """ATR 固定止损 + 移动止损

        1. 固定止损：entry_price - atr_mult × ATR（不低于 min_stop_pct）
        2. 移动止损：价格涨超 activation 后，从最高价回撤 drawback 触发
        """
        cfg = self.config
        entry = self._entry_price
        highest = self._highest_price or entry

        # 计算固定止损价
        if atr is not None and atr > 0:
            atr_stop = entry - cfg.atr_mult * atr
            # 确保止损不低于 min_stop_pct（使用配置值）
            min_stop = entry * (1 - cfg.min_stop_pct)
            fixed_stop = max(atr_stop, min_stop)
        else:
            # 无 ATR 时用 min_stop_pct 作为兜底
            fixed_stop = entry * (1 - cfg.min_stop_pct)

        # 计算移动止损价
        trailing_stop = None
        gain_pct = (highest - entry) / entry if entry > 0 else 0
        if gain_pct >= cfg.trailing_activation:
            trailing_stop = highest * (1 - cfg.trailing_drawback)

        # 取两者中较高的（更紧的止损）
        if trailing_stop is not None:
            self._current_stop_price = max(fixed_stop, trailing_stop)
        else:
            self._current_stop_price = fixed_stop

        # 检查是否触发
        if current_price <= self._current_stop_price:
            # 判断是哪种止损触发
            if trailing_stop is not None and current_price <= trailing_stop:
                reason = (
                    f"移动止损: 价格 {current_price:.2f} <= "
                    f"追踪止损 {trailing_stop:.2f} "
                    f"(最高 {highest:.2f}, 回撤 {cfg.trailing_drawback:.1%})"
                )
            else:
                reason = (
                    f"ATR止损: 价格 {current_price:.2f} <= "
                    f"固定止损 {fixed_stop:.2f} "
                    f"(ATR×{cfg.atr_mult}, 入场 {entry:.2f})"
                )
            logger.info(f"StopLoss triggered: {reason}")
            return True, reason

        return False, ""

    def _check_range_breakout(
        self, current_price: float
    ) -> tuple[bool, str]:
        """区间突破止损（均值回归策略用）

        价格从入场价向不利方向移动超过 range_breakout_pct 时触发。
        对多头：价格跌破 entry × (1 - range_breakout_pct)
        """
        cfg = self.config
        entry = self._entry_price

        stop_price = entry * (1 - cfg.range_breakout_pct)
        self._current_stop_price = stop_price

        if current_price <= stop_price:
            reason = (
                f"区间突破止损: 价格 {current_price:.2f} <= "
                f"止损线 {stop_price:.2f} "
                f"(入场 {entry:.2f}, 突破 {cfg.range_breakout_pct:.1%})"
            )
            logger.info(f"StopLoss triggered: {reason}")
            return True, reason

        return False, ""

    def get_stop_info(self) -> dict:
        """获取当前止损状态信息（用于通知和日志）"""
        return {
            "in_position": self._in_position,
            "entry_price": self._entry_price,
            "entry_time": str(self._entry_time) if self._entry_time else None,
            "highest_price": self._highest_price,
            "bars_held": self._bars_held,
            "current_stop_price": self._current_stop_price,
            "stop_type": self.config.stop_type,
        }

    def reset(self) -> None:
        """重置（策略 reset 时调用）"""
        self._reset()


__all__ = [
    "StopLossManager",
    "StopLossConfig",
    "StopType",
    "MAX_STOP_PCT",
    "MIN_STOP_PCT",
    "MAX_BARS",
    "MIN_BARS",
]
